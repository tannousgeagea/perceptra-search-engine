# api/routers/media.py

from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from fastapi.responses import StreamingResponse
from typing import Annotated, List, Optional
from django.db.models import Count
from django.conf import settings
from tenants.context import RequestContext
from media.models import Video, Image, Detection, Tag
from media.services import MediaLibraryService
from api.dependencies import get_request_context
from api.routers.media.schemas import (
    MediaFilterParams,
    VideoResponse,
    ImageResponse,
    DetectionResponse,
    TagResponse,
    VideoListResponse,
    ImageListResponse,
    DetectionListResponse,
    PaginationMetadata,
    MediaStatsResponse
)
from infrastructure.storage.client import get_storage_manager
from asgiref.sync import sync_to_async
import logging
import mimetypes
import re
from pathlib import Path

router = APIRouter(prefix="/media", tags=["Media Library"])
logger = logging.getLogger(__name__)


def _media_url(storage_backend: str, storage_key: str) -> str:
    """Return a browser-accessible URL for a stored file.

    Cloud backends (Azure, S3, MinIO) already return HTTP presigned URLs.
    Local storage returns a file:// URI which browsers cannot load, so we
    return a relative path to the built-in file-serve endpoint instead.
    """
    if storage_backend == "local":
        # URL-encode forward slashes are kept — storage_key is path-safe
        return f"/api/v1/media/files/{storage_key}"
    return ""  # caller will call get_download_url for cloud backends


@router.get("/files/{storage_key:path}", include_in_schema=False)
async def serve_local_file(request: Request, storage_key: str):
    """Stream a file from local storage with HTTP range request support.

    Range support is required for HTML5 video seeking (browsers send
    'Range: bytes=N-M' when the user scrubs the timeline).
    """
    storage_path = getattr(settings, "STORAGE_PATH", "/media/search-engine/")
    full_path = Path(storage_path) / storage_key

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="File not found")

    content_type, _ = mimetypes.guess_type(str(full_path))
    content_type = content_type or "application/octet-stream"
    file_size = full_path.stat().st_size

    range_header = request.headers.get("Range")
    if range_header:
        m = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if m:
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else file_size - 1
            end = min(end, file_size - 1)
            length = end - start + 1

            def iter_range():
                with open(full_path, "rb") as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = f.read(min(65536, remaining))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk

            return StreamingResponse(
                iter_range(),
                status_code=206,
                media_type=content_type,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(length),
                },
            )

    def iter_file():
        with open(full_path, "rb") as f:
            while chunk := f.read(65536):
                yield chunk

    return StreamingResponse(
        iter_file(),
        media_type=content_type,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
        },
    )


async def build_video_response(video: Video) -> VideoResponse:
    """Build video response with download URL."""
    backend = video.storage_backend
    if backend == "local":
        download_url = _media_url(backend, video.storage_key)
    else:
        storage = get_storage_manager(backend=backend)
        download_url = await storage.get_download_url(video.storage_key)

    tags = await sync_to_async(list)(video.tags.all())

    return VideoResponse(
        id=video.id,  #type: ignore
        video_id=video.video_id,
        filename=video.filename,
        storage_key=video.storage_key,
        storage_backend=backend,
        file_size_bytes=video.file_size_bytes,
        duration_seconds=video.duration_seconds,
        plant_site=video.plant_site,
        shift=video.shift,
        inspection_line=video.inspection_line,
        recorded_at=video.recorded_at,
        status=video.status,
        frame_count=video.frame_count,
        detection_count=video.detection_count,    #type: ignore
        tags=[TagResponse(id=t.id, name=t.name, description=t.description, color=t.color) for t in tags],
        created_at=video.created_at,
        updated_at=video.updated_at,
        download_url=download_url,
    )


async def build_image_response(image: Image) -> ImageResponse:
    """Build image response with download URLs."""
    backend = image.storage_backend
    if backend == "local":
        download_url = _media_url(backend, image.storage_key)
    else:
        storage = get_storage_manager(backend=backend)
        download_url = await storage.get_download_url(image.storage_key)

    tags = await sync_to_async(list)(image.tags.all())

    return ImageResponse(
        id=image.id,   # type: ignore
        image_id=image.image_id,
        filename=image.filename,
        storage_key=image.storage_key,
        storage_backend=backend,
        file_size_bytes=image.file_size_bytes,
        width=image.width,
        height=image.height,
        plant_site=image.plant_site,
        shift=image.shift,
        inspection_line=image.inspection_line,
        captured_at=image.captured_at,
        video_id=image.video.id if image.video else None,   # type: ignore
        video_uuid=image.video.video_id if image.video else None,
        frame_number=image.frame_number,
        timestamp_in_video=image.timestamp_in_video,
        status=image.status,
        checksum=image.checksum,
        detection_count=image.detection_count,    #type: ignore
        tags=[TagResponse(id=t.id, name=t.name, description=t.description, color=t.color) for t in tags],
        created_at=image.created_at,
        updated_at=image.updated_at,
        download_url=download_url,
        thumbnail_url=download_url,
    )


async def build_detection_response(detection: Detection) -> DetectionResponse:
    """Build detection response with URLs."""
    img_backend = detection.image.storage_backend
    if img_backend == "local":
        image_url = _media_url(img_backend, detection.image.storage_key)
    else:
        storage = get_storage_manager(backend=img_backend)
        image_url = await storage.get_download_url(detection.image.storage_key)
    
    # Get crop URL if available
    crop_url = None
    if detection.storage_key:
        if img_backend == "local":
            crop_url = _media_url(img_backend, detection.storage_key)
        else:
            storage = get_storage_manager(backend=img_backend)
            crop_url = await storage.get_download_url(detection.storage_key)
    
    # Get tags
    tags = await sync_to_async(list)(detection.tags.all())
    
    return DetectionResponse(
        id=detection.id,   #type: ignore
        detection_id=detection.detection_id,
        label=detection.label,
        confidence=detection.confidence,
        bbox_x=detection.bbox_x,
        bbox_y=detection.bbox_y,
        bbox_width=detection.bbox_width,
        bbox_height=detection.bbox_height,
        bbox_format=detection.bbox_format,
        image_id=detection.image.id,  #type: ignore
        image_uuid=detection.image.image_id,
        image_filename=detection.image.filename,
        image_width=detection.image.width,
        image_height=detection.image.height,
        plant_site=detection.image.plant_site,
        shift=detection.image.shift,
        inspection_line=detection.image.inspection_line,
        captured_at=detection.image.captured_at,
        video_id=detection.image.video.id if detection.image.video else None,  #type: ignore
        video_uuid=detection.image.video.video_id if detection.image.video else None,
        embedding_generated=detection.embedding_generated,
        embedding_model_version=detection.embedding_model_version,
        tags=[TagResponse(id=t.id, name=t.name, description=t.description, color=t.color) for t in tags],
        created_at=detection.created_at,
        updated_at=detection.updated_at,
        image_url=image_url,
        crop_url=crop_url
    )


@router.get("/videos", response_model=VideoListResponse)
async def list_videos(
    filters: Annotated[MediaFilterParams, Depends()],
    ctx: RequestContext = Depends(get_request_context)
):
    """
    List all videos with filtering, sorting, and pagination.
    
    Supports filtering by:
    - Plant site, shift, inspection line
    - Status (uploaded, processing, completed, failed)
    - Date range
    - Duration range
    - Tags
    - Has detections
    """
    service = MediaLibraryService(tenant=ctx.tenant)
    
    # Get videos
    filter_dict = filters.dict(exclude_none=True)
    videos, pagination = await sync_to_async(service.list_videos)(
        filters=filter_dict,
        page=filters.page,
        page_size=filters.page_size
    )
    
    # Build responses
    video_responses = []
    for video in videos:
        try:
            video_responses.append(await build_video_response(video))
        except Exception as exc:
            logger.error("Failed to build video response for id=%s: %s", video.id, exc)
    
    return VideoListResponse(
        items=video_responses,
        pagination=PaginationMetadata(**pagination),
        filters_applied=filter_dict
    )


@router.get("/images", response_model=ImageListResponse)
async def list_images(
    filters: Annotated[MediaFilterParams, Depends()],
    ctx: RequestContext = Depends(get_request_context)
):
    """
    List all images with filtering, sorting, and pagination.
    
    Supports filtering by:
    - Plant site, shift, inspection line
    - Status
    - Date range
    - Is video frame
    - Video ID
    - Tags
    - Has detections
    """
    service = MediaLibraryService(tenant=ctx.tenant)
    
    # Get images
    filter_dict = filters.dict(exclude_none=True)
    images, pagination = await sync_to_async(service.list_images)(
        filters=filter_dict,
        page=filters.page,
        page_size=filters.page_size
    )
    
    # Build responses
    image_responses = []
    for image in images:
        try:
            image_responses.append(await build_image_response(image))
        except Exception as exc:
            logger.error("Failed to build image response for id=%s: %s", image.id, exc)
    
    return ImageListResponse(
        items=image_responses,
        pagination=PaginationMetadata(**pagination),
        filters_applied=filter_dict
    )


@router.get("/detections", response_model=DetectionListResponse)
async def list_detections(
    filters: Annotated[MediaFilterParams, Depends()],
    ctx: RequestContext = Depends(get_request_context)
):
    """
    List all detections with filtering, sorting, and pagination.
    
    Supports filtering by:
    - Labels
    - Confidence range
    - Embedding status
    - Plant site, shift, inspection line (via image)
    - Date range (via image)
    - Video ID (via image)
    - Tags
    """
    service = MediaLibraryService(tenant=ctx.tenant)
    
    # Get detections
    filter_dict = filters.dict(exclude_none=True)
    detections, pagination = await sync_to_async(service.list_detections)(
        filters=filter_dict,
        page=filters.page,
        page_size=filters.page_size
    )
    
    # Build responses
    detection_responses = []
    for detection in detections:
        try:
            detection_responses.append(await build_detection_response(detection))
        except Exception as exc:
            logger.error("Failed to build detection response for id=%s: %s", detection.id, exc)
    
    return DetectionListResponse(
        items=detection_responses,
        pagination=PaginationMetadata(**pagination),
        filters_applied=filter_dict
    )


@router.get("/tags", response_model=List[TagResponse])
async def list_tags(
    ctx: RequestContext = Depends(get_request_context)
):
    """
    List all tags for the tenant with usage counts.
    """
    tags = await sync_to_async(list)(
        Tag.objects.filter(tenant=ctx.tenant)
        .annotate(
            image_count=Count('images', distinct=True),
            video_count=Count('videos', distinct=True),
            detection_count=Count('detections', distinct=True),
        )
        .order_by('name')
    )
    
    tag_responses = []
    for tag in tags:
        tag_response = TagResponse(
            id=tag.id,
            name=tag.name,
            description=tag.description,
            color=tag.color,
            usage_count={
                'images': tag.image_count,         # type: ignore
                'videos': tag.video_count,         # type: ignore
                'detections': tag.detection_count, # type: ignore
                'total': tag.image_count + tag.video_count + tag.detection_count,  # type: ignore
            },
        )
        tag_responses.append(tag_response)
    
    return tag_responses


@router.get("/stats", response_model=MediaStatsResponse)
async def get_media_stats(
    ctx: RequestContext = Depends(get_request_context)
):
    """
    Get media library statistics.
    
    Returns:
    - Total counts for videos, images, detections
    - Total storage used
    - Breakdown by status
    - Top detection labels
    - Recent upload counts
    """
    service = MediaLibraryService(tenant=ctx.tenant)
    
    stats = await sync_to_async(service.get_media_stats)()
    
    return MediaStatsResponse(**stats)


@router.get("/videos/{video_id}", response_model=VideoResponse)
async def get_video(
    video_id: int,
    ctx: RequestContext = Depends(get_request_context)
):
    """Get a specific video by ID."""
    try:
        video = await Video.objects.select_related().prefetch_related('tags').aget(
            id=video_id,
            tenant=ctx.tenant
        )
        
        # Annotate counts
        from django.db.models import Count
        video.frame_count = await sync_to_async(  #type: ignore
            lambda: video.frames.count()   #type: ignore
        )()
        video.detection_count = await sync_to_async(  #type: ignore
            lambda: Detection.objects.filter(image__video=video).count()
        )()
        
        return await build_video_response(video)
        
    except Video.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found"
        )


@router.get("/images/{image_id}", response_model=ImageResponse)
async def get_image(
    image_id: int,
    ctx: RequestContext = Depends(get_request_context)
):
    """Get a specific image by ID."""
    try:
        image = await Image.objects.select_related('video').prefetch_related('tags').aget(
            id=image_id,
            tenant=ctx.tenant
        )
        
        # Annotate count
        image.detection_count = await sync_to_async(  #type: ignore
            lambda: image.detections.count() #type: ignore
        )()
        
        return await build_image_response(image)
        
    except Image.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found"
        )


@router.get("/detections/{detection_id}", response_model=DetectionResponse)
async def get_detection(
    detection_id: int,
    ctx: RequestContext = Depends(get_request_context)
):
    """Get a specific detection by ID."""
    try:
        detection = await Detection.objects.select_related(
            'image', 'image__video'
        ).prefetch_related('tags').aget(
            id=detection_id,
            tenant=ctx.tenant
        )
        
        return await build_detection_response(detection)
        
    except Detection.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Detection not found"
        )


@router.delete("/videos/{video_id}")
async def delete_video(
    video_id: int,
    ctx: RequestContext = Depends(get_request_context)
):
    """Delete a video and all associated data."""
    # Check permission
    if hasattr(ctx, 'api_key') and ctx.api_key:
        from api_keys.auth import APIKeyAuth
        APIKeyAuth.check_permission(ctx.api_key, 'admin')
    else:
        ctx.require_role('admin')
    
    try:
        video = await Video.objects.aget(id=video_id, tenant=ctx.tenant)
        
        # Delete from storage
        storage = get_storage_manager(backend=video.storage_backend)
        await storage.delete(video.storage_key)
        
        # Delete from database (cascades to frames and detections)
        await sync_to_async(video.delete)()
        
        return {"message": "Video deleted successfully"}
        
    except Video.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found"
        )