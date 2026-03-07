# api/routers/upload.py

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from typing import Annotated, Optional, List
from datetime import datetime, timezone
from tenants.context import RequestContext
from media.models import Video, Image, Detection, StorageBackend as StorageBackendChoice
from tenants.models import Tenant
from media.utils import get_or_create_tags
from ml.video_processing import VideoProcessor
from api.dependencies import get_request_context, require_permission
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

from PIL import Image as PILImage
from uuid import UUID
import hashlib
import io
import numpy as np
from asgiref.sync import sync_to_async
from infrastructure.storage.client import get_storage_manager
from ml.preprocessing import get_image_dimensions, validate_image, validate_video, calculate_checksum, get_image_format
import uuid
import json
from asgiref.sync import sync_to_async
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["upload"])


def generate_storage_key(tenant: Tenant, filename: str, media_type:str='images') -> str:
    """
    Generate storage key for image.
    
    Format: org-{slug}/images/{year}/{month}/{uuid}_{filename}
    Or with project: org-{slug}/projects/{project-id}/images/{year}/{month}/{uuid}_{filename}
    """
    import uuid
    from datetime import datetime
    
    now = datetime.now()
    year = now.strftime('%Y')
    month = now.strftime('%m')
    unique_id = str(uuid.uuid4())[:8]
    
    # Sanitize filename
    safe_filename = filename.replace(' ', '_').replace('/', '_')
    
    return f"org-{tenant.slug}/{media_type}/{year}/{month}/{unique_id}_{safe_filename}"

@sync_to_async
def verify_image_existing(checksum:str, tenant:Tenant):
    # Check for duplicate (same checksum in same organization)
    return Image.objects.filter(
        tenant=tenant,
        checksum=checksum
    ).first()

@sync_to_async
def verify_video_existing(checksum:str, tenant:Tenant):
    # Check for duplicate (same checksum in same organization)
    return Video.objects.filter(
        tenant=tenant,
        checksum=checksum
    ).first()


@router.post("/video", status_code=status.HTTP_201_CREATED)
async def upload_video(
    file: Annotated[UploadFile, File(...)],
    plant_site: Annotated[str, Form(...)],
    recorded_at: Annotated[str, Form(...)],
    shift: Annotated[Optional[str], Form()] = None,
    inspection_line: Annotated[Optional[str], Form()] = None,
    tags: Annotated[Optional[str], Form()] = None,  # JSON string of tags
    storage_backend: Annotated[Optional[str], Form()] = None,
    ctx: RequestContext = Depends(require_permission('write'))
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
    # # Check role
    # ctx.require_role('admin', 'operator')
    
    @sync_to_async
    def aspect_ratio(video:Video):
        return round(video.aspect_ratio, 2)
    
    @sync_to_async
    def megapixels(video:Video):
        return round(video.megapixels, 2)
    
    @sync_to_async
    def frame_count(video:Video):
        return video.frame_count
    
    # Generate storage key
    filename = file.filename
    if not filename:
        filename = f"video_{uuid.uuid4()}.mp4"

    # Validate file type
    if not file.content_type or not file.content_type.startswith('video/'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Expected video, got {file.content_type}"
        )
    
    allowed_formats = ["mp4", "mov", "avi", "webm"]
    file_format = get_image_format(filename)
    
    if file_format not in allowed_formats:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format: {file_format}. Allowed: {', '.join(allowed_formats)}"
        )

    # Read file
    file_bytes = await file.read()
    file_size = len(file_bytes)
    
    max_size = 50 * 1024 * 1024  # 50MB
    if file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size: {max_size / (1024*1024)}MB"
        )
    
    checksum = calculate_checksum(file_bytes)

    # Check for duplicate (same checksum in same organization)
    existing = await verify_video_existing(checksum, ctx.tenant)
    
    if existing:
        return {
            "message": "Video already exists",
            "id": existing.pk,
            "video_id": str(existing.video_id),
            "filename": existing.filename,
            "storage_key": existing.storage_key,
            "file_size_bytes": existing.file_size_bytes,
            "file_size_mb": round(existing.file_size_mb, 2),
            "aspect_ratio": await aspect_ratio(existing),
            "megapixels": await megapixels(existing),
            "format": existing.file_format,
            "checksum": existing.checksum,
            "download_url": existing.get_download_url(),
            "created_at": existing.created_at.isoformat(),
            "plant_site": existing.plant_site,
            "shift": existing.shift,
            "inspection_line": existing.inspection_line,
            "status": existing.status,
            "frame_count": await frame_count(existing),
            "duration_seconds": existing.duration_seconds,
            "recorded_at": existing.recorded_at.isoformat(),
            "duplicate": True,
            "tags": [
                TagResponse(
                    id=tag.id,
                    name=tag.name,
                    description=tag.description,
                    color=tag.color
                )
                for tag in await sync_to_async(list)(existing.tags.all())
            ]
        }

    video_info = VideoProcessor.get_video_info(file_bytes)
    try:
        duration_seconds = video_info['duration_seconds']
    except:
        duration_seconds = None

    # Validate video
    is_valid = await validate_video(file_bytes)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid video file format"
        )
    
    # Parse datetime
    try:
        recorded_datetime = datetime.fromisoformat(recorded_at).replace(tzinfo=timezone.utc)
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

    storage_key = generate_storage_key(ctx.tenant, filename=filename, media_type='videos')
    
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
        file_format=file_format,
        checksum=checksum,
        duration_seconds=duration_seconds,
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

    return {
        "message": "Video uploaded successfully",
        "id": str(video.pk),
        "video_id": str(video.video_id),
        "filename": video.filename,
        "storage_key": video.storage_key,
        "file_size_bytes": video.file_size_bytes,
        "file_size_mb": round(video.file_size_mb, 2),
        "aspect_ratio": await aspect_ratio(video),
        "megapixels": await megapixels(video),
        "format": video.file_format,
        "checksum": video.checksum,
        "download_url": video.get_download_url(),
        "created_at": video.created_at.isoformat(),
        "plant_site": video.plant_site,
        "shift": video.shift,
        "inspection_line": video.inspection_line,
        "status": video.status,
        "frame_count": await frame_count(video),
        "duration_seconds": video.duration_seconds,
        "recorded_at": video.recorded_at.isoformat(),
        "tags": tags_response,
        "duplicate": False,
    }

@router.post(
    "/image", 
    status_code=status.HTTP_201_CREATED,
    summary="Upload Image",
    description="Upload an image to organization's default storage"
)
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
    ctx: RequestContext = Depends(require_permission('write'))
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
    # ctx.require_role('admin', 'operator')


    if not file:
        raise HTTPException(status_code=400, detail="No file provided")
    
    # Generate storage key
    filename = file.filename
    if not filename:
        filename = f"image_{uuid.uuid4()}.jpg"

    # Validate file type
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Expected image, got {file.content_type}"
        )
    
    # Validate file type
    allowed_formats = ['jpg', 'jpeg', 'png', 'tiff', 'tif', 'bmp', 'webp']
    file_format = get_image_format(filename)
    
    if file_format not in allowed_formats:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format: {file_format}. Allowed: {', '.join(allowed_formats)}"
        )

    # Read file
    file_bytes = await file.read()
    file_size = len(file_bytes)
    
    max_size = 50 * 1024 * 1024  # 50MB
    if file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size: {max_size / (1024*1024)}MB"
        )

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
        captured_datetime = datetime.fromisoformat(captured_at).replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid datetime format"
        )

    # Calculate checksum
    checksum = calculate_checksum(file_bytes)

    # Check for duplicate (same checksum in same organization)
    existing = await verify_image_existing(checksum, ctx.tenant)
    
    if existing:
        return {
            "message": "Image already exists",
            "image_id": str(existing.image_id),
            "id": existing.pk,
            "image_id": str(existing.image_id),
            "filename": existing.filename,
            "storage_key": existing.storage_key,
            "file_size_bytes": existing.file_size_bytes,
            "file_size_mb": round(existing.file_size_mb, 2),
            "width": existing.width,
            "height": existing.height,
            "aspect_ratio": round(existing.aspect_ratio, 2),
            "megapixels": round(existing.megapixels, 2),
            "format": existing.file_format,
            "checksum": existing.checksum,
            "download_url": existing.get_download_url(),
            "created_at": existing.created_at.isoformat(),
            "plant_site": existing.plant_site,
            "shift": existing.shift,
            "inspection_line": existing.inspection_line,
            "status": existing.status,
            "video_id": existing.video.video_id if existing.video else None,
            "frame_number": existing.frame_number,
            "tags": [
                TagResponse(
                    id=tag.id,
                    name=tag.name,
                    description=tag.description,
                    color=tag.color
                )
                for tag in await sync_to_async(list)(existing.tags.all())
            ],
            "duplicate": True
        }

    
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

    storage_key = generate_storage_key(
        tenant=ctx.tenant, 
        filename=filename,
    )
    
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
        file_format=file_format,
        frame_number=frame_number,
        plant_site=plant_site,
        shift=shift,
        inspection_line=inspection_line,
        captured_at=captured_datetime,
        checksum=checksum,
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
    
    return {
        "message": "Image uploaded successfully",
        "id": image.pk,
        "image_id": str(image.image_id),
        "filename": image.filename,
        "storage_key": image.storage_key,
        "file_size_bytes": image.file_size_bytes,
        "file_size_mb": round(image.file_size_mb, 2),
        "width": image.width,
        "height": image.height,
        "aspect_ratio": round(image.aspect_ratio, 2),
        "megapixels": round(image.megapixels, 2),
        "format": image.file_format,
        "checksum": image.checksum,
        "download_url": image.get_download_url(),
        "created_at": image.created_at.isoformat(),
        "plant_site": image.plant_site,
        "shift": image.shift,
        "inspection_line": image.inspection_line,
        "status": image.status,
        "video_id": video.video_id if video else None,
        "frame_number": image.frame_number,
        "duplicate": False,
        "tags": tags_response,
    }


@router.post("/detection", response_model=DetectionResponse, status_code=status.HTTP_201_CREATED)
async def create_detection(
    request: DetectionCreateRequest,
    ctx: RequestContext = Depends(require_permission('write'))
):
    """
    Create a single detection for an image.
    Generates and stores cropped region.
    Checks for duplicates before creating.
    """
    
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
    
    # Download parent image and crop detection region
    storage = get_storage_manager(backend=image.storage_backend)
    
    try:
        # Download image
        image_bytes = await storage.download(image.storage_key)
        
        # Load image
        pil_image = PILImage.open(io.BytesIO(image_bytes)).convert('RGB')
        image_array = np.array(pil_image)
        
        # Calculate absolute coordinates
        if request.bbox_format == 'normalized':
            x = int(request.bbox_x * image.width)
            y = int(request.bbox_y * image.height)
            w = int(request.bbox_width * image.width)
            h = int(request.bbox_height * image.height)
        else:
            x = int(request.bbox_x)
            y = int(request.bbox_y)
            w = int(request.bbox_width)
            h = int(request.bbox_height)
        
        # Ensure bounds are valid
        x = max(0, min(x, image.width))
        y = max(0, min(y, image.height))
        w = max(1, min(w, image.width - x))
        h = max(1, min(h, image.height - y))
        
        # Crop region
        cropped_array = image_array[y:y+h, x:x+w]
        cropped_image = PILImage.fromarray(cropped_array)
        
        # Convert crop to bytes
        crop_buffer = io.BytesIO()
        cropped_image.save(crop_buffer, format='JPEG', quality=95)
        crop_bytes = crop_buffer.getvalue()
        
        # Calculate checksum of cropped region
        checksum = hashlib.sha256(crop_bytes).hexdigest()
        
    except Exception as e:
        logger.error(f"Failed to crop detection region: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process detection region"
        )
    
    # Check if detection already exists
    @sync_to_async
    def check_existing_detection():
        # First check by coordinates and label
        existing = Detection.objects.filter(
            image=image,
            bbox_x=request.bbox_x,
            bbox_y=request.bbox_y,
            bbox_width=request.bbox_width,
            bbox_height=request.bbox_height,
            bbox_format=request.bbox_format,
            label=request.label,
        ).first()
        
        if existing:
            return existing
        
        # Check by checksum (in case coordinates are slightly different)
        existing = Detection.objects.filter(
            image=image,
            checksum=checksum,
        ).first()
        
        return existing
    
    existing_detection = await check_existing_detection()
    
    if existing_detection:
        logger.info(
            f"Detection already exists for image {image.image_id}: "
            f"detection_id={existing_detection.detection_id}"
        )
        
        # Return existing detection
        tags_response = [
            TagResponse(
                id=tag.id,
                name=tag.name,
                description=tag.description,
                color=tag.color
            )
            for tag in await sync_to_async(list)(existing_detection.tags.all())
        ]
        
        return DetectionResponse(
            id=existing_detection.pk,
            detection_id=existing_detection.detection_id,
            image_id=image.pk,
            bbox_x=existing_detection.bbox_x,
            bbox_y=existing_detection.bbox_y,
            bbox_width=existing_detection.bbox_width,
            bbox_height=existing_detection.bbox_height,
            bbox_format=existing_detection.bbox_format,
            label=existing_detection.label,
            confidence=existing_detection.confidence,
            storage_key=existing_detection.storage_key,
            storage_backend=existing_detection.storage_backend,
            checksum=existing_detection.checksum,
            embedding_generated=existing_detection.embedding_generated,
            tags=tags_response,
            created_at=existing_detection.created_at
        )
    
    # Generate storage key for cropped region
    crop_filename = f"{image.image_id}_det_{uuid.uuid4()}.jpg"
    storage_key = generate_storage_key(tenant=ctx.tenant, filename=crop_filename, media_type="detections")
    
    # Upload cropped region to storage
    try:
        await storage.save(
            storage_key=storage_key,
            content=crop_bytes,
            content_type='image/jpeg',
            metadata={
                'image_id': str(image.image_id),
                'label': request.label,
                'confidence': request.confidence,
                'bbox': f"{request.bbox_x},{request.bbox_y},{request.bbox_width},{request.bbox_height}",
                "detected": datetime.now().isoformat(),
            }
        )
        logger.info(f"Cropped detection saved: {storage_key}")
    except Exception as e:
        logger.error(f"Failed to save cropped detection: {str(e)}")
        # Continue anyway - we can regenerate crops later if needed
        storage_key = ""
    
    # Parse tags
    tag_list = []
    if request.tags:
        tag_data = [tag.model_dump() for tag in request.tags]
        tag_list = await get_or_create_tags(tag_data, ctx.tenant, ctx.user)
    
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
        storage_backend=image.storage_backend,
        storage_key=storage_key,
        checksum=checksum,
        embedding_generated=False,
        created_by=ctx.user,
        updated_by=ctx.user
    )
    
    # Add tags
    if tag_list:
        await sync_to_async(detection.tags.set)(tag_list)
    
    # Refresh to get tags
    await detection.arefresh_from_db()
    
    logger.info(
        f"Detection created: id={detection.detection_id}, label={detection.label}, "
        f"crop_size={len(crop_bytes)} bytes"
    )
    
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
        image_id=image.pk,
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
    ctx: RequestContext = Depends(require_permission('write'))
):
    """
    Create multiple detections at once.
    Generates crops and checks for duplicates.
    Maximum 1000 detections per request.
    """
    
    created_ids = []
    skipped_ids = []
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
    
    # Process each detection
    for det_request in request.detections:
        try:
            image = image_map[det_request.image_id]
            
            # Download and crop image
            storage = get_storage_manager(backend=image.storage_backend)
            
            try:
                # Download image (cache it if processing multiple detections for same image)
                image_bytes = await storage.download(image.storage_key)
                pil_image = PILImage.open(io.BytesIO(image_bytes)).convert('RGB')
                image_array = np.array(pil_image)
                
                # Calculate absolute coordinates
                if det_request.bbox_format == 'normalized':
                    x = int(det_request.bbox_x * image.width)
                    y = int(det_request.bbox_y * image.height)
                    w = int(det_request.bbox_width * image.width)
                    h = int(det_request.bbox_height * image.height)
                else:
                    x = int(det_request.bbox_x)
                    y = int(det_request.bbox_y)
                    w = int(det_request.bbox_width)
                    h = int(det_request.bbox_height)
                
                # Bounds check
                x = max(0, min(x, image.width))
                y = max(0, min(y, image.height))
                w = max(1, min(w, image.width - x))
                h = max(1, min(h, image.height - y))
                
                # Crop
                cropped_array = image_array[y:y+h, x:x+w]
                cropped_image = PILImage.fromarray(cropped_array)
                
                # Convert to bytes
                crop_buffer = io.BytesIO()
                cropped_image.save(crop_buffer, format='JPEG', quality=95)
                crop_bytes = crop_buffer.getvalue()
                
                # Calculate checksum
                checksum = hashlib.sha256(crop_bytes).hexdigest()
                
            except Exception as e:
                errors.append(f"Failed to crop detection for image {det_request.image_id}: {str(e)}")
                continue
            
            # Check if detection already exists
            @sync_to_async
            def check_duplicate():
                existing = Detection.objects.filter(
                    image=image,
                    bbox_x=det_request.bbox_x,
                    bbox_y=det_request.bbox_y,
                    bbox_width=det_request.bbox_width,
                    bbox_height=det_request.bbox_height,
                    bbox_format=det_request.bbox_format,
                    label=det_request.label,
                ).first()
                
                if existing:
                    return existing
                
                return Detection.objects.filter(
                    image=image,
                    checksum=checksum,
                ).first()
            
            existing = await check_duplicate()
            
            if existing:
                logger.info(f"Skipping duplicate detection: {existing.detection_id}")
                skipped_ids.append(existing.pk)
                continue
            
            # Generate storage key
            crop_filename = f"{image.image_id}_det_{uuid.uuid4()}.jpg"
            storage_key = generate_storage_key(ctx.tenant, crop_filename, "detections")
            
            # Upload crop
            try:
                await storage.save(
                    storage_key=storage_key,
                    content=crop_bytes,
                    content_type='image/jpeg',
                    metadata={
                        'image_id': str(image.image_id),
                        'label': det_request.label,
                        'confidence': det_request.confidence
                    }
                )
            except Exception as e:
                logger.error(f"Failed to save crop: {str(e)}")
                storage_key = ""
            
            # Parse tags
            tag_list = []
            if det_request.tags:
                tag_data = [tag.model_dump() for tag in det_request.tags]
                tag_list = await get_or_create_tags(tag_data, ctx.tenant, ctx.user)
            
            # Create detection
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
                storage_key=storage_key,
                checksum=checksum,
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
        skipped=len(skipped_ids),
        failed=len(errors),
        detection_ids=created_ids,
        skipped_ids=skipped_ids,
        errors=errors
    )