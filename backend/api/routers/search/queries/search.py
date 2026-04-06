# api/routers/search.py

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from typing import Annotated, List
from tenants.context import RequestContext
from media.models import Image, Video, Detection
from search.services import SearchService
from api.dependencies import get_request_context, require_scope
from api.routers.search.schemas import (
    ImageSearchRequest,
    TextSearchRequest,
    HybridSearchRequest,
    SimilaritySearchRequest,
    SearchResponse,
    ImageSearchResult,
    DetectionSearchResult,
    SearchHistoryItem,
    SearchHistoryResponse,
    PaginationMetadata,
    SearchStatsResponse,
    SearchVolumeDay,
    ActivityItem,
    BoundingBox
)
from infrastructure.storage.client import get_storage_manager
from search.models import SearchQuery
from asgiref.sync import sync_to_async
from django.db.models import Avg, Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import timedelta, datetime
import uuid
import logging

router = APIRouter(prefix="/search", tags=["search"])
logger = logging.getLogger(__name__)


def _media_url(storage_backend: str, storage_key: str) -> str:
    """Return an HTTP-accessible URL for a stored file."""
    if storage_backend == 'local':
        return f"/api/v1/media/files/{storage_key}"
    return ""  # cloud backends: caller should generate presigned URL


async def _build_image_result(result_payload: dict, score: float) -> ImageSearchResult:
    """Build ImageSearchResult from vector search result, including download URL."""
    storage_backend = result_payload.get('storage_backend', 'local')
    storage_key = result_payload['storage_key']

    if storage_backend == 'local':
        download_url = _media_url(storage_backend, storage_key)
    else:
        try:
            storage = get_storage_manager(backend=storage_backend)
            download_url = await storage.get_download_url(storage_key)
        except Exception:
            download_url = None

    return ImageSearchResult(
        id=result_payload['image_id'],
        image_id=result_payload['image_uuid'],
        filename=result_payload['filename'],
        storage_key=storage_key,
        similarity_score=score,
        width=result_payload['width'],
        height=result_payload['height'],
        plant_site=result_payload['plant_site'],
        shift=result_payload.get('shift'),
        inspection_line=result_payload.get('inspection_line'),
        captured_at=result_payload['captured_at'],
        video_id=result_payload.get('video_id'),
        video_uuid=result_payload.get('video_uuid'),
        frame_number=result_payload.get('frame_number'),
        timestamp_in_video=result_payload.get('timestamp_in_video'),
        download_url=download_url,
    )


async def _build_detection_result(result_payload: dict, score: float) -> DetectionSearchResult:
    """Build DetectionSearchResult from vector search result, including image URL."""
    image_storage_key = result_payload['image_storage_key']
    image_storage_backend = result_payload.get('image_storage_backend')

    # Older embeddings may not have image_storage_backend stored in the payload —
    # fall back to a DB lookup using the integer image_id.
    if image_storage_backend is None:
        image_id = result_payload.get('image_id')
        if image_id:
            try:
                row = await sync_to_async(
                    Image.objects.values('storage_backend').get
                )(id=image_id)
                image_storage_backend = row['storage_backend']
            except Exception:
                image_storage_backend = 'local'
        else:
            image_storage_backend = 'local'

    if image_storage_backend == 'local':
        image_url = _media_url(image_storage_backend, image_storage_key)
    else:
        try:
            storage = get_storage_manager(backend=image_storage_backend)
            image_url = await storage.get_download_url(image_storage_key)
        except Exception:
            image_url = None

    return DetectionSearchResult(
        id=result_payload['detection_id'],
        detection_id=result_payload['detection_uuid'],
        similarity_score=score,
        label=result_payload['label'],
        confidence=result_payload['confidence'],
        bbox=BoundingBox(
            x=result_payload['bbox_x'],
            y=result_payload['bbox_y'],
            width=result_payload['bbox_width'],
            height=result_payload['bbox_height'],
            format=result_payload['bbox_format']
        ),
        image_id=result_payload['image_id'],
        image_uuid=result_payload['image_uuid'],
        image_filename=result_payload['image_filename'],
        image_storage_key=image_storage_key,
        plant_site=result_payload['plant_site'],
        shift=result_payload.get('shift'),
        inspection_line=result_payload.get('inspection_line'),
        captured_at=result_payload['captured_at'],
        video_id=result_payload.get('video_id'),
        video_uuid=result_payload.get('video_uuid'),
        frame_number=result_payload.get('frame_number'),
        timestamp_in_video=result_payload.get('timestamp_in_video'),
        tags=result_payload.get('tags', []),
        image_url=image_url,
        crop_url=None,
    )


@router.post("/image", response_model=SearchResponse)
async def search_by_image(
    file: Annotated[UploadFile, File(...)],
    request: ImageSearchRequest = Depends(),
    ctx: RequestContext = Depends(require_scope('search'))
):
    """
    Search by uploading an image.
    
    Finds similar images or detections based on visual similarity.
    """
    # Validate file type
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Expected image, got {file.content_type}"
        )
    
    # Read image
    image_bytes = await file.read()
    
    # Create search service
    search_service = SearchService(tenant=ctx.tenant, user=ctx.user)
    
    try:
        # Perform search
        filters = request.filters.dict(exclude_none=True) if request.filters else None
        
        results, execution_time, query_id = await sync_to_async(search_service.search_by_image)(
            image_bytes=image_bytes,
            top_k=request.top_k,
            search_type=request.search_type,
            filters=filters,
            score_threshold=request.score_threshold,
            enable_reranking=request.enable_reranking,
            reranking_alpha=request.reranking_alpha,
        )
        
        # Build response
        image_results = []
        detection_results = []
        
        for result in results:
            if result.payload.get('type') == 'image':
                image_results.append(await _build_image_result(result.payload, result.score))
            elif result.payload.get('type') == 'detection':
                detection_results.append(await _build_detection_result(result.payload, result.score))
        
        # Get model version
        from embeddings.models import ModelVersion
        model_version = await sync_to_async(ModelVersion.objects.get)(is_active=True)
        
        return SearchResponse(
            query_id=uuid.UUID(query_id),
            search_type='image',
            results_type=request.search_type,
            image_results=image_results if image_results else None,
            detection_results=detection_results if detection_results else None,
            total_results=len(results),
            execution_time_ms=execution_time,
            filters_applied=filters or {},
            model_version=model_version.name
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Image search failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search failed. Please try again."
        )


@router.post("/text", response_model=SearchResponse)
async def search_by_text(
    request: TextSearchRequest,
    ctx: RequestContext = Depends(require_scope('search'))
):
    """
    Search by text query.
    
    Finds images or detections matching the text description.
    Requires a model that supports text encoding (e.g., CLIP).
    """
    # Create search service
    search_service = SearchService(tenant=ctx.tenant, user=ctx.user)
    
    try:
        # Perform search
        filters = request.filters.dict(exclude_none=True) if request.filters else None
        
        results, execution_time, query_id = await sync_to_async(search_service.search_by_text)(
            query_text=request.query,
            top_k=request.top_k,
            search_type=request.search_type,
            filters=filters,
            score_threshold=request.score_threshold,
            enable_reranking=request.enable_reranking,
            reranking_alpha=request.reranking_alpha,
        )
        
        # Build response
        image_results = []
        detection_results = []
        
        for result in results:
            if result.payload.get('type') == 'image':
                image_results.append(await _build_image_result(result.payload, result.score))
            elif result.payload.get('type') == 'detection':
                detection_results.append(await _build_detection_result(result.payload, result.score))
        
        # Get model version
        from embeddings.models import ModelVersion
        model_version = await sync_to_async(ModelVersion.objects.get)(is_active=True)
        
        return SearchResponse(
            query_id=uuid.UUID(query_id),
            search_type='text',
            results_type=request.search_type,
            image_results=image_results if image_results else None,
            detection_results=detection_results if detection_results else None,
            total_results=len(results),
            execution_time_ms=execution_time,
            filters_applied=filters or {},
            model_version=model_version.name
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Text search failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search failed. Please try again."
        )


@router.post("/hybrid", response_model=SearchResponse)
async def search_hybrid(
    file: Annotated[UploadFile, File(...)],
    request: HybridSearchRequest = Depends(),
    ctx: RequestContext = Depends(require_scope("search"))
):
    """
    Hybrid search combining image and text.
    
    Finds results that match both visual similarity and text description.
    Useful for queries like "metal scrap similar to this image".
    """
    # Validate file type
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Expected image, got {file.content_type}"
        )
    
    # Read image
    image_bytes = await file.read()
    
    # Create search service
    search_service = SearchService(tenant=ctx.tenant, user=ctx.user)
    
    try:
        # Perform search
        filters = request.filters.dict(exclude_none=True) if request.filters else None
        
        results, execution_time, query_id = await sync_to_async(search_service.search_hybrid)(
            image_bytes=image_bytes,
            query_text=request.query,
            text_weight=request.text_weight,
            top_k=request.top_k,
            search_type=request.search_type,
            filters=filters,
            score_threshold=request.score_threshold,
            enable_reranking=request.enable_reranking,
            reranking_alpha=request.reranking_alpha,
        )
        
        # Build response
        image_results = []
        detection_results = []
        
        for result in results:
            if result.payload.get('type') == 'image':
                image_results.append(await _build_image_result(result.payload, result.score))
            elif result.payload.get('type') == 'detection':
                detection_results.append(await _build_detection_result(result.payload, result.score))
        
        # Get model version
        from embeddings.models import ModelVersion
        model_version = await sync_to_async(ModelVersion.objects.get)(is_active=True)
        
        return SearchResponse(
            query_id=uuid.UUID(query_id),
            search_type='hybrid',
            results_type=request.search_type,
            image_results=image_results if image_results else None,
            detection_results=detection_results if detection_results else None,
            total_results=len(results),
            execution_time_ms=execution_time,
            filters_applied=filters or {},
            model_version=model_version.name
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Hybrid search failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search failed. Please try again."
        )


@router.post("/similar", response_model=SearchResponse)
async def search_similar(
    request: SimilaritySearchRequest,
    ctx: RequestContext = Depends(require_scope('search'))
):
    """
    Find items similar to a given image or detection.
    
    Useful for "find more like this" functionality.
    """
    # Create search service
    search_service = SearchService(tenant=ctx.tenant, user=ctx.user)
    
    try:
        # Perform search
        filters = request.filters.dict(exclude_none=True) if request.filters else None
        
        results, execution_time, query_id = await sync_to_async(search_service.search_similar)(
            item_id=request.item_id,
            item_type=request.item_type,
            top_k=request.top_k,
            filters=filters,
            score_threshold=request.score_threshold
        )
        
        # Build response
        image_results = []
        detection_results = []
        
        for result in results:
            if result.payload.get('type') == 'image':
                image_results.append(await _build_image_result(result.payload, result.score))
            elif result.payload.get('type') == 'detection':
                detection_results.append(await _build_detection_result(result.payload, result.score))
        
        # Get model version
        from embeddings.models import ModelVersion
        model_version = await sync_to_async(ModelVersion.objects.get)(is_active=True)
        
        return SearchResponse(
            query_id=uuid.UUID(query_id),
            search_type='similarity',
            results_type=request.item_type + 's',
            image_results=image_results if image_results else None,
            detection_results=detection_results if detection_results else None,
            total_results=len(results),
            execution_time_ms=execution_time,
            filters_applied=filters or {},
            model_version=model_version.name
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Similarity search failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search failed. Please try again."
        )


@router.get("/history", response_model=SearchHistoryResponse)
async def get_search_history(
    page: int = 1,
    page_size: int = 20,
    ctx: RequestContext = Depends(require_scope('search'))
):
    """
    Get user's search history (paginated).
    """
    qs = SearchQuery.objects.filter(
        tenant=ctx.tenant,
        user=ctx.user
    ).order_by('-created_at')

    total_items = await sync_to_async(qs.count)()
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    offset = (page - 1) * page_size

    queries = await sync_to_async(list)(qs[offset:offset + page_size])

    items = [
        SearchHistoryItem(
            id=q.id,
            query_type=q.query_type,
            query_text=q.query_text,
            search_type='unknown',
            results_count=q.results_count,
            execution_time_ms=q.execution_time_ms,
            created_at=q.created_at
        )
        for q in queries
    ]

    return SearchHistoryResponse(
        items=items,
        pagination=PaginationMetadata(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        ),
    )


@router.get("/stats", response_model=SearchStatsResponse)
async def get_search_stats(
    ctx: RequestContext = Depends(require_scope('search'))
):
    """
    Get search statistics for the tenant.
    """
    # Total searches
    total_searches = await sync_to_async(
        SearchQuery.objects.filter(tenant=ctx.tenant).count
    )()
    
    # Searches today
    today = timezone.now().date()
    searches_today = await sync_to_async(
        SearchQuery.objects.filter(
            tenant=ctx.tenant,
            created_at__date=today
        ).count
    )()
    
    # Average execution time
    avg_time = await sync_to_async(
        lambda: SearchQuery.objects.filter(
            tenant=ctx.tenant
        ).aggregate(avg=Avg('execution_time_ms'))['avg'] or 0
    )()
    
    # Most searched labels (from filters)
    # This is simplified - you might want to store this differently
    most_searched = []
    
    # Search type distribution
    type_dist = await sync_to_async(
        lambda: dict(
            SearchQuery.objects.filter(
                tenant=ctx.tenant
            ).values('query_type').annotate(
                count=Count('id')
            ).values_list('query_type', 'count')
        )
    )()
    
    # Searches yesterday
    yesterday = (timezone.now() - timedelta(days=1)).date()
    searches_yesterday = await sync_to_async(
        SearchQuery.objects.filter(
            tenant=ctx.tenant,
            created_at__date=yesterday
        ).count
    )()

    return SearchStatsResponse(
        total_searches=total_searches,
        searches_today=searches_today,
        searches_yesterday=searches_yesterday,
        avg_execution_time_ms=avg_time,
        most_searched_labels=most_searched,
        search_type_distribution=type_dist
    )


@router.get("/stats/volume", response_model=List[SearchVolumeDay])
async def get_search_volume(
    days: int = 7,
    ctx: RequestContext = Depends(require_scope('search'))
):
    """Get daily search volume for the last N days."""
    now = timezone.now()
    start = now - timedelta(days=days)

    daily = await sync_to_async(
        lambda: list(
            SearchQuery.objects.filter(
                tenant=ctx.tenant,
                created_at__gte=start,
            )
            .annotate(date=TruncDate('created_at'))
            .values('date')
            .annotate(
                searches=Count('id'),
                detections=Count('id', filter=Q(results_count__gt=0)),
            )
            .order_by('date')
        )
    )()

    # Build a complete day-by-day list (fill gaps with zeros)
    day_map = {
        row['date']: row for row in daily
    }
    result = []
    for i in range(days):
        d = (start + timedelta(days=i + 1)).date()
        row = day_map.get(d, {})
        result.append(SearchVolumeDay(
            date=d.isoformat(),
            day=d.strftime('%a'),
            searches=row.get('searches', 0),
            detections=row.get('detections', 0),
        ))

    return result


DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

def _relative_time(dt: datetime) -> str:
    """Convert a datetime to a human-readable relative time string."""
    now = timezone.now()
    diff = now - dt
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


@router.get("/stats/activity", response_model=List[ActivityItem])
async def get_recent_activity(
    limit: int = 10,
    ctx: RequestContext = Depends(require_scope('search'))
):
    """Get recent activity feed (searches, uploads, detections)."""
    items = []

    # Recent searches
    searches = await sync_to_async(list)(
        SearchQuery.objects.filter(tenant=ctx.tenant)
        .order_by('-created_at')[:limit]
    )
    for s in searches:
        tag_map = {'text': 'TEXT', 'image': 'IMAGE', 'hybrid': 'HYBRID', 'video': 'VIDEO'}
        tag = tag_map.get(s.query_type, 'SEARCH')
        msg = f'{tag.capitalize()} search'
        if s.query_text:
            msg += f' — "{s.query_text[:50]}"'
        msg += f' ({s.results_count} results)'
        items.append({
            'type': 'search',
            'msg': msg,
            'time': _relative_time(s.created_at),
            'tag': tag,
            'ts': s.created_at,
        })

    # Recent image uploads
    images = await sync_to_async(list)(
        Image.objects.filter(tenant=ctx.tenant)
        .order_by('-created_at')[:limit]
    )
    for img in images:
        items.append({
            'type': 'upload',
            'msg': f'Image uploaded — {img.filename}',
            'time': _relative_time(img.created_at),
            'tag': 'UPLOAD',
            'ts': img.created_at,
        })

    # Recent video uploads
    videos = await sync_to_async(list)(
        Video.objects.filter(tenant=ctx.tenant)
        .order_by('-created_at')[:limit]
    )
    for vid in videos:
        items.append({
            'type': 'upload',
            'msg': f'Video uploaded — {vid.filename}',
            'time': _relative_time(vid.created_at),
            'tag': 'UPLOAD',
            'ts': vid.created_at,
        })

    # Sort all by timestamp, take top N
    items.sort(key=lambda x: x['ts'], reverse=True)
    items = items[:limit]

    return [
        ActivityItem(type=i['type'], msg=i['msg'], time=i['time'], tag=i['tag'])
        for i in items
    ]