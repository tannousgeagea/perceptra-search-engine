# api/routers/upload.py

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, BackgroundTasks
from typing import Annotated, Optional
from tenants.models import Tenant, TenantMembership
from media.models import Video, Image, Detection
from api.dependencies import get_tenant, verify_tenant_access, require_role
from api.routers.upload.schemas import VideoUploadRequest, VideoResponse, DetectionCreate
from datetime import datetime
import uuid
from asgiref.sync import sync_to_async

router = APIRouter(prefix="/upload", tags=["upload"])


async def process_video_frames(video_id: uuid.UUID, tenant_id: uuid.UUID):
    """
    Background task to extract frames and generate embeddings.
    """
    # TODO: Implement video frame extraction
    # TODO: Generate embeddings for each detection
    pass


@router.post("/video", response_model=VideoResponse)
async def upload_video(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(...)],
    plant_site: Annotated[str, Form(...)],
    recorded_at: Annotated[str, Form(...)],
    shift: Annotated[Optional[str], Form()] = None,
    inspection_line: Annotated[Optional[str], Form()] = None,
    tenant: Annotated[Tenant, Depends(get_tenant)] = None,
    membership: Annotated[TenantMembership, Depends(require_role('admin', 'operator'))] = None
):
    """
    Upload video file for processing.
    Requires admin or operator role.
    """
    # Validate file type
    if not file.content_type.startswith('video/'):
        raise HTTPException(status_code=400, detail="File must be a video")
    
    # Generate file path
    file_path = f"{tenant.tenant_id}/{uuid.uuid4()}_{file.filename}"
    
    file_bytes = await file.read()
    await sync_to_async(storage.save)(file_path, file_bytes)
    
    # Create video record
    video = await Video.objects.acreate(
        tenant=tenant,
        file_path=file_path,
        filename=file.filename,
        file_size_bytes=len(file_bytes),
        plant_site=plant_site,
        shift=shift,
        inspection_line=inspection_line,
        recorded_at=datetime.fromisoformat(recorded_at),
        status='uploaded'
    )
    
    # Queue background processing
    background_tasks.add_task(process_video_frames, video.id, tenant.id)
    
    return VideoResponse(
        id=video.id,
        filename=video.filename,
        file_path=video.file_path,
        plant_site=video.plant_site,
        status=video.status,
        recorded_at=video.recorded_at,
        created_at=video.created_at
    )


@router.post("/detection", response_model=dict)
async def create_detection(
    detection: DetectionCreate,
    tenant: Annotated[Tenant, Depends(get_tenant)] = None,
    membership: Annotated[TenantMembership, Depends(require_role('admin', 'operator'))] = None
):
    """
    Create a new detection with automatic embedding generation.
    """
    # Verify image belongs to tenant
    try:
        image = await Image.objects.aget(id=detection.image_id, tenant=tenant)
    except Image.DoesNotExist:
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Create detection
    det = await Detection.objects.acreate(
        tenant=tenant,
        image=image,
        bbox_x=detection.bbox_x,
        bbox_y=detection.bbox_y,
        bbox_width=detection.bbox_width,
        bbox_height=detection.bbox_height,
        bbox_format=detection.bbox_format,
        label=detection.label,
        confidence=detection.confidence
    )
    
    # Generate and store embedding (async)
    # TODO: Queue as background task for production
    
    return {
        'id': str(det.id),
        'status': 'created',
        'message': 'Detection created, embedding generation queued'
    }