# api/routers/upload.py

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from typing import Annotated, Optional, List
from datetime import datetime
from tenants.context import RequestContext
from media.models import Video, Image, Detection, StorageBackend as StorageBackendChoice
from media.utils import get_or_create_tags
from api.dependencies import get_request_context
from api.routers.upload.schemas import (
    VideoUploadResponse,
    ImageUploadResponse,
    DetectionCreateRequest,
    DetectionResponse,
    BulkDetectionCreateRequest,
    BulkDetectionResponse,
    TagInput,
    TagResponse
)
from infrastructure.storage.client import get_storage_manager
from ml.preprocessing import get_image_dimensions, validate_image, validate_video
import uuid
import json
from asgiref.sync import sync_to_async
from django.conf import settings

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("/video", response_model=VideoUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_video(
    file: Annotated[UploadFile, File(...)],
    plant_site: Annotated[str, Form(...)],
    recorded_at: Annotated[str, Form(...)],
    shift: Annotated[Optional[str], Form()] = None,
    inspection_line: Annotated[Optional[str], Form()] = None,
    tags: Annotated[Optional[str], Form()] = None,  # JSON string of tags
    storage_backend: Annotated[Optional[str], Form()] = None,
    ctx: RequestContext = Depends(get_request_context)
):
    """
    Upload video file for inspection.
    Requires operator or admin role.
    
    Form parameters:
    - file: Video file (mp4, avi, mkv, webm)
    - plant_site: Plant/site identifier
    - recorded_at: ISO datetime when video was recorded
    - shift: Optional shift identifier
    - inspection_line: Optional inspection line identifier
    - tags: Optional JSON array of tags [{"name": "tag1", "color": "#FF0000"}]
    - storage_backend: Optional storage backend override ('azure', 's3', 'minio', 'local')
    """
    # Check role
    ctx.require_role('admin', 'operator')
    
    # Validate file type
    if not file.content_type or not file.content_type.startswith('video/'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Expected video, got {file.content_type}"
        )
    
    # Read file
    file_bytes = await file.read()
    file_size = len(file_bytes)
    
    # Validate video
    is_valid = await validate_video(file_bytes)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid video file format"
        )
    
    # Parse datetime
    try:
        recorded_datetime = datetime.fromisoformat(recorded_at)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid datetime format. Use ISO format (e.g., '2024-02-20T10:30:00')"
        )
    
    # Determine storage backend
    backend = storage_backend or settings.STORAGE_BACKEND
    if backend not in [choice.value for choice in StorageBackendChoice]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid storage backend: {backend}"
        )
    
    
    filename = file.filename
    if not filename:
        filename = f"video_{uuid.uuid4()}.mp4"

    file_extension = filename.split('.')[-1] if '.' in filename else 'mp4'
    year = recorded_datetime.year
    month = f"{recorded_datetime.month:02d}"
    storage_key = f"{ctx.tenant_id}/videos/{year}/{month}/{uuid.uuid4()}.{file_extension}"
    
    # Save to storage
    storage = get_storage_manager(backend=backend)
    storage_result = await storage.save(
        storage_key, 
        file_bytes,
        content_type=file.content_type,
        metadata={
            "filename": filename,
            "file_size": file_size,
            "recorded_at": recorded_datetime.isoformat(),
            "plant_site": plant_site,
            "shift": shift,
            "inspection_line": inspection_line
        }
    )
    
    # Parse tags
    tag_list = []
    if tags:
        try:
            tag_data = json.loads(tags)
            if isinstance(tag_data, list):
                tag_list = await get_or_create_tags(tag_data, ctx.tenant, ctx.user)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid tags JSON format"
            )
    
    # Create database record
    video = await Video.objects.acreate(
        tenant=ctx.tenant,
        storage_key=storage_key,
        storage_backend=backend,
        filename=file.filename,
        file_size_bytes=file_size,
        plant_site=plant_site,
        shift=shift,
        inspection_line=inspection_line,
        recorded_at=recorded_datetime,
        status='uploaded',
        created_by=ctx.user,
        updated_by=ctx.user
    )
    
    # Add tags
    if tag_list:
        await sync_to_async(video.tags.set)(tag_list)
    
    # Refresh to get tags
    await video.arefresh_from_db()
    
    # Build response
    tags_response = [
        TagResponse(
            id=tag.id,
            name=tag.name,
            description=tag.description,
            color=tag.color
        )
        for tag in await sync_to_async(list)(video.tags.all())
    ]
    
    return VideoUploadResponse(
        id=video.pk,
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
        tags=tags_response,
        created_at=video.created_at
    )


@router.post("/image", response_model=ImageUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_image(
    file: Annotated[UploadFile, File(...)],
    plant_site: Annotated[str, Form(...)],
    captured_at: Annotated[str, Form(...)],
    shift: Annotated[Optional[str], Form()] = None,
    inspection_line: Annotated[Optional[str], Form()] = None,
    video_id: Annotated[Optional[int], Form()] = None,
    frame_number: Annotated[Optional[int], Form()] = None,
    tags: Annotated[Optional[str], Form()] = None,
    storage_backend: Annotated[Optional[str], Form()] = None,
    ctx: RequestContext = Depends(get_request_context)
):
    """
    Upload image file for inspection.
    Requires operator or admin role.
    
    Form parameters:
    - file: Image file (jpg, png, etc.)
    - plant_site: Plant/site identifier
    - captured_at: ISO datetime when image was captured
    - shift: Optional shift identifier
    - inspection_line: Optional inspection line identifier
    - video_id: Optional video ID if this is a frame extraction
    - frame_number: Optional frame number in video
    - tags: Optional JSON array of tags
    - storage_backend: Optional storage backend override
    """
    # Check role
    ctx.require_role('admin', 'operator')
    
    # Validate file type
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Expected image, got {file.content_type}"
        )
    
    # Read file
    file_bytes = await file.read()
    file_size = len(file_bytes)
    
    # Validate image
    is_valid = await validate_image(file_bytes)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image file"
        )
    
    # Get dimensions
    width, height = await get_image_dimensions(file_bytes)
    
    # Parse datetime
    try:
        captured_datetime = datetime.fromisoformat(captured_at)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid datetime format"
        )
    
    # Verify video exists if video_id provided
    video = None
    if video_id:
        try:
            video = await Video.objects.aget(id=video_id, tenant=ctx.tenant)
        except Video.DoesNotExist:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Video {video_id} not found"
            )
    
    # Determine storage backend
    backend = storage_backend or settings.STORAGE_BACKEND
    if backend not in [choice.value for choice in StorageBackendChoice]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid storage backend: {backend}"
        )
    
    # Generate storage key
    filename = file.filename
    if not filename:
        filename = f"image_{uuid.uuid4()}.jpg"

    file_extension = filename.split('.')[-1] if '.' in filename else 'jpg'
    year = captured_datetime.year
    month = f"{captured_datetime.month:02d}"
    storage_key = f"{ctx.tenant_id}/images/{year}/{month}/{uuid.uuid4()}.{file_extension}"
    
    # Save to storage
    storage = get_storage_manager(backend=backend)
    storage_result = await storage.save(
        storage_key, file_bytes,
        content_type=file.content_type,
        metadata={
            "filename": file.filename,
            "file_size": file_size,
            "recorded_at": captured_datetime.isoformat(),
            "plant_site": plant_site,
            "shift": shift,
            "inspection_line": inspection_line
        }
    )
    
    # Parse tags
    tag_list = []
    if tags:
        try:
            tag_data = json.loads(tags)
            if isinstance(tag_data, list):
                tag_list = await get_or_create_tags(tag_data, ctx.tenant, ctx.user)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid tags JSON format"
            )
    
    # Create database record
    image = await Image.objects.acreate(
        tenant=ctx.tenant,
        video=video,
        storage_key=storage_key,
        storage_backend=backend,
        filename=file.filename,
        file_size_bytes=file_size,
        width=width,
        height=height,
        frame_number=frame_number,
        plant_site=plant_site,
        shift=shift,
        inspection_line=inspection_line,
        captured_at=captured_datetime,
        checksum=storage_result['checksum'],
        status='uploaded',
        created_by=ctx.user,
        updated_by=ctx.user
    )
    
    # Add tags
    if tag_list:
        await sync_to_async(image.tags.set)(tag_list)
    
    # Refresh to get tags
    await image.arefresh_from_db()
    
    # Build response
    tags_response = [
        TagResponse(
            id=tag.id,
            name=tag.name,
            description=tag.description,
            color=tag.color
        )
        for tag in await sync_to_async(list)(image.tags.all())
    ]
    
    return ImageUploadResponse(
        id=image.pk,
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
        video_id=video.video_id if video else None,
        frame_number=image.frame_number,
        checksum=image.checksum,
        tags=tags_response,
        status=image.status,
        created_at=image.created_at
    )


@router.post("/detection", response_model=DetectionResponse, status_code=status.HTTP_201_CREATED)
async def create_detection(
    request: DetectionCreateRequest,
    ctx: RequestContext = Depends(get_request_context)
):
    """
    Create a single detection for an image.
    Requires operator or admin role.
    """
    # Check role
    ctx.require_role('admin', 'operator')
    
    # Verify image exists and belongs to tenant
    try:
        image = await Image.objects.aget(id=request.image_id, tenant=ctx.tenant)
    except Image.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image {request.image_id} not found"
        )
    
    # Validate bounding box
    if request.bbox_format == 'normalized':
        if not (0 <= request.bbox_x <= 1 and 0 <= request.bbox_y <= 1):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="For normalized format, bbox_x and bbox_y must be between 0 and 1"
            )
        if not (0 < request.bbox_width <= 1 and 0 < request.bbox_height <= 1):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="For normalized format, bbox dimensions must be between 0 and 1"
            )
    
    # Parse tags
    tag_list = []
    if request.tags:
        tag_data = [tag.dict() for tag in request.tags]
        tag_list = await get_or_create_tags(tag_data, ctx.tenant, ctx.user)
    
    # Use same storage backend as image
    backend = image.storage_backend
    
    # Generate storage key for cropped detection (optional)
    # For now, we'll leave it empty and generate crops later if needed
    storage_key = ""
    
    # Create detection
    detection = await Detection.objects.acreate(
        tenant=ctx.tenant,
        image=image,
        bbox_x=request.bbox_x,
        bbox_y=request.bbox_y,
        bbox_width=request.bbox_width,
        bbox_height=request.bbox_height,
        bbox_format=request.bbox_format,
        label=request.label,
        confidence=request.confidence,
        storage_backend=backend,
        storage_key=storage_key,
        embedding_generated=False,
        created_by=ctx.user,
        updated_by=ctx.user
    )
    
    # Add tags
    if tag_list:
        await sync_to_async(detection.tags.set)(tag_list)
    
    # Refresh to get tags
    await detection.arefresh_from_db()
    
    # Build response
    tags_response = [
        TagResponse(
            id=tag.id,
            name=tag.name,
            description=tag.description,
            color=tag.color
        )
        for tag in await sync_to_async(list)(detection.tags.all())
    ]
    
    return DetectionResponse(
        id=detection.pk,
        detection_id=detection.detection_id,
        image_id=detection.image.pk,
        bbox_x=detection.bbox_x,
        bbox_y=detection.bbox_y,
        bbox_width=detection.bbox_width,
        bbox_height=detection.bbox_height,
        bbox_format=detection.bbox_format,
        label=detection.label,
        confidence=detection.confidence,
        storage_key=detection.storage_key if detection.storage_key else None,
        storage_backend=detection.storage_backend,
        checksum=detection.checksum,
        embedding_generated=detection.embedding_generated,
        tags=tags_response,
        created_at=detection.created_at
    )


@router.post("/detections/bulk", response_model=BulkDetectionResponse, status_code=status.HTTP_201_CREATED)
async def create_detections_bulk(
    request: BulkDetectionCreateRequest,
    ctx: RequestContext = Depends(get_request_context)
):
    """
    Create multiple detections at once.
    Requires operator or admin role.
    Maximum 1000 detections per request.
    """
    # Check role
    ctx.require_role('admin', 'operator')
    
    created_ids = []
    errors = []
    
    # Get all unique image IDs
    image_ids = list(set(d.image_id for d in request.detections))
    
    # Verify all images exist and belong to tenant
    images = await sync_to_async(list)(
        Image.objects.filter(id__in=image_ids, tenant=ctx.tenant)
    )
    image_map = {img.pk: img for img in images}
    
    # Check for missing images
    for det in request.detections:
        if det.image_id not in image_map:
            errors.append(f"Image {det.image_id} not found")
    
    # If any images missing, return error
    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"errors": errors}
        )
    
    # Create detections
    for det_request in request.detections:
        try:
            image = image_map[det_request.image_id]
            
            # Parse tags
            tag_list = []
            if det_request.tags:
                tag_data = [tag.dict() for tag in det_request.tags]
                tag_list = await get_or_create_tags(tag_data, ctx.tenant, ctx.user)
            
            detection = await Detection.objects.acreate(
                tenant=ctx.tenant,
                image=image,
                bbox_x=det_request.bbox_x,
                bbox_y=det_request.bbox_y,
                bbox_width=det_request.bbox_width,
                bbox_height=det_request.bbox_height,
                bbox_format=det_request.bbox_format,
                label=det_request.label,
                confidence=det_request.confidence,
                storage_backend=image.storage_backend,
                storage_key="",
                embedding_generated=False,
                created_by=ctx.user,
                updated_by=ctx.user
            )
            
            # Add tags
            if tag_list:
                await sync_to_async(detection.tags.set)(tag_list)
            
            created_ids.append(detection.pk)
            
        except Exception as e:
            errors.append(f"Failed to create detection for image {det_request.image_id}: {str(e)}")
    
    return BulkDetectionResponse(
        total=len(request.detections),
        created=len(created_ids),
        failed=len(errors),
        detection_ids=created_ids,
        errors=errors
    )