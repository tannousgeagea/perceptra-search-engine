# api/routers/media.py

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Annotated, List, Optional
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

router = APIRouter(prefix="/media", tags=["Media Library"])
logger = logging.getLogger(__name__)


async def build_video_response(video: Video) -> VideoResponse:
    """Build video response with download URL."""
    # Get download URL
    storage = get_storage_manager(backend=video.storage_backend)
    download_url = await storage.get_download_url(video.storage_key)
    
    # Get tags
    tags = await sync_to_async(list)(video.tags.all())
    
    return VideoResponse(
        id=video.id,  #type: ignore
        video_id=video.video_id,
        filename=video.filename,
        storage_key=video.storage_key,
        storage_backend=video.storage_backend,
        file_size_bytes=video.file_size_bytes,
        duration_seconds=video.duration_seconds,
        plant_site=video.plant_site,
        shift=video.shift,
        inspection_line=video.inspection_line,
        recorded_at=video.recorded_at,
        status=video.status,
        frame_count=video.frame_count,
        detection_count=video.detection_count,    #type: ignore
        tags=[TagResponse.model_validate(tag) for tag in tags],
        created_at=video.created_at,
        updated_at=video.updated_at,
        download_url=download_url
    )


async def build_image_response(image: Image) -> ImageResponse:
    """Build image response with download URLs."""
    # Get download URL
    storage = get_storage_manager(backend=image.storage_backend)
    download_url = await storage.get_download_url(image.storage_key)
    
    # Get tags
    tags = await sync_to_async(list)(image.tags.all())
    
    return ImageResponse(
        id=image.id,   # type: ignore
        image_id=image.image_id,
        filename=image.filename,
        storage_key=image.storage_key,
        storage_backend=image.storage_backend,
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
        tags=[TagResponse.model_validate(tag) for tag in tags],
        created_at=image.created_at,
        updated_at=image.updated_at,
        download_url=download_url,
        thumbnail_url=download_url  # TODO: Generate actual thumbnails
    )


async def build_detection_response(detection: Detection) -> DetectionResponse:
    """Build detection response with URLs."""
    # Get image URL
    storage = get_storage_manager(backend=detection.image.storage_backend)
    image_url = await storage.get_download_url(detection.image.storage_key)
    
    # Get crop URL if available
    crop_url = None
    if detection.storage_key:
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
        tags=[TagResponse.model_validate(tag) for tag in tags],
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
        video_response = await build_video_response(video)
        video_responses.append(video_response)
    
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
        image_response = await build_image_response(image)
        image_responses.append(image_response)
    
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
        detection_response = await build_detection_response(detection)
        detection_responses.append(detection_response)
    
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
        Tag.objects.filter(tenant=ctx.tenant).order_by('name')
    )
    
    tag_responses = []
    for tag in tags:
        usage_count = await sync_to_async(lambda: tag.usage_count)()
        tag_response = TagResponse.model_validate(tag)
        tag_response.usage_count = usage_count
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