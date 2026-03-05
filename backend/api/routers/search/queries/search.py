# api/routers/search.py

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from typing import Annotated, List
from tenants.context import RequestContext
from media.models import Image, Detection
from search.services import SearchService
from api.dependencies import get_request_context
from api.routers.search.schemas import (
    ImageSearchRequest,
    TextSearchRequest,
    HybridSearchRequest,
    SimilaritySearchRequest,
    SearchResponse,
    ImageSearchResult,
    DetectionSearchResult,
    SearchHistoryItem,
    SearchStatsResponse,
    BoundingBox
)
from search.models import SearchQuery
from asgiref.sync import sync_to_async
from django.db.models import Avg, Count, Q
from django.utils import timezone
from datetime import timedelta
import uuid
import logging

router = APIRouter(prefix="/search", tags=["search"])
logger = logging.getLogger(__name__)


def _build_image_result(result_payload: dict, score: float) -> ImageSearchResult:
    """Build ImageSearchResult from vector search result."""
    return ImageSearchResult(
        id=result_payload['image_id'],
        image_id=result_payload['image_uuid'],
        filename=result_payload['filename'],
        storage_key=result_payload['storage_key'],
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
        timestamp_in_video=result_payload.get('timestamp_in_video')
    )


def _build_detection_result(result_payload: dict, score: float) -> DetectionSearchResult:
    """Build DetectionSearchResult from vector search result."""
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
        image_storage_key=result_payload['image_storage_key'],
        plant_site=result_payload['plant_site'],
        shift=result_payload.get('shift'),
        inspection_line=result_payload.get('inspection_line'),
        captured_at=result_payload['captured_at'],
        video_id=result_payload.get('video_id'),
        video_uuid=result_payload.get('video_uuid'),
        frame_number=result_payload.get('frame_number'),
        timestamp_in_video=result_payload.get('timestamp_in_video'),
        tags=result_payload.get('tags', [])
    )


@router.post("/image", response_model=SearchResponse)
async def search_by_image(
    file: Annotated[UploadFile, File(...)],
    request: ImageSearchRequest = Depends(),
    ctx: RequestContext = Depends(get_request_context)
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
            score_threshold=request.score_threshold
        )
        
        # Build response
        image_results = []
        detection_results = []
        
        for result in results:
            if result.payload.get('type') == 'image':
                image_results.append(_build_image_result(result.payload, result.score))
            elif result.payload.get('type') == 'detection':
                detection_results.append(_build_detection_result(result.payload, result.score))
        
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
    ctx: RequestContext = Depends(get_request_context)
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
            score_threshold=request.score_threshold
        )
        
        # Build response
        image_results = []
        detection_results = []
        
        for result in results:
            if result.payload.get('type') == 'image':
                image_results.append(_build_image_result(result.payload, result.score))
            elif result.payload.get('type') == 'detection':
                detection_results.append(_build_detection_result(result.payload, result.score))
        
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
    ctx: RequestContext = Depends(get_request_context)
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
            score_threshold=request.score_threshold
        )
        
        # Build response
        image_results = []
        detection_results = []
        
        for result in results:
            if result.payload.get('type') == 'image':
                image_results.append(_build_image_result(result.payload, result.score))
            elif result.payload.get('type') == 'detection':
                detection_results.append(_build_detection_result(result.payload, result.score))
        
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
    ctx: RequestContext = Depends(get_request_context)
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
                image_results.append(_build_image_result(result.payload, result.score))
            elif result.payload.get('type') == 'detection':
                detection_results.append(_build_detection_result(result.payload, result.score))
        
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


@router.get("/history", response_model=List[SearchHistoryItem])
async def get_search_history(
    limit: int = 20,
    offset: int = 0,
    ctx: RequestContext = Depends(get_request_context)
):
    """
    Get user's search history.
    """
    queries = await sync_to_async(list)(
        SearchQuery.objects.filter(
            tenant=ctx.tenant,
            user=ctx.user
        ).order_by('-created_at')[offset:offset + limit]
    )
    
    return [
        SearchHistoryItem(
            id=q.id,
            query_type=q.query_type,
            query_text=q.query_text,
            search_type='unknown',  # Add field to model if needed
            results_count=q.results_count,
            execution_time_ms=q.execution_time_ms,
            created_at=q.created_at
        )
        for q in queries
    ]


@router.get("/stats", response_model=SearchStatsResponse)
async def get_search_stats(
    ctx: RequestContext = Depends(get_request_context)
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
    
    return SearchStatsResponse(
        total_searches=total_searches,
        searches_today=searches_today,
        avg_execution_time_ms=avg_time,
        most_searched_labels=most_searched,
        search_type_distribution=type_dist
    )