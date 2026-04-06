# api/routers/hazard_config/queries/hazard_config.py

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from datetime import datetime
from asgiref.sync import sync_to_async
from pydantic import BaseModel, Field

from tenants.context import RequestContext
from api.dependencies import require_permission
from embeddings.models import (
    TenantHazardConfig,
    DetectionJob,
    DetectionJobStatus,
)

import logging

router = APIRouter(prefix="/hazard-configs", tags=["Hazard Config"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class HazardConfigCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    prompts: List[str] = Field(..., min_length=1, description='List of text prompts for detection')
    detection_backend: str = Field(default='sam3_perceptra')
    confidence_threshold: float = Field(default=0.3, ge=0.0, le=1.0)
    is_active: bool = True
    is_default: bool = False
    config: dict = Field(default_factory=dict)


class HazardConfigUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    prompts: Optional[List[str]] = Field(default=None, min_length=1)
    detection_backend: Optional[str] = None
    confidence_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    config: Optional[dict] = None


class HazardConfigResponse(BaseModel):
    id: int
    name: str
    prompts: List[str]
    detection_backend: str
    confidence_threshold: float
    is_active: bool
    is_default: bool
    config: dict
    created_at: datetime
    updated_at: datetime


class DetectionJobResponse(BaseModel):
    id: int
    detection_job_id: str
    image_id: int
    image_filename: str
    hazard_config_name: Optional[str]
    detection_backend: str
    status: str
    total_detections: int
    inference_time_ms: Optional[float]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
    created_at: datetime


class PaginationInfo(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_previous: bool


class PaginatedHazardConfigs(BaseModel):
    items: List[HazardConfigResponse]
    pagination: PaginationInfo


class PaginatedDetectionJobs(BaseModel):
    items: List[DetectionJobResponse]
    pagination: PaginationInfo


class RunDetectionRequest(BaseModel):
    image_ids: List[int] = Field(..., min_length=1, max_length=100)


class RunDetectionResponse(BaseModel):
    queued: int
    image_ids: List[int]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_config_response(obj: TenantHazardConfig) -> HazardConfigResponse:
    return HazardConfigResponse(
        id=obj.pk,
        name=obj.name,
        prompts=obj.prompts,
        detection_backend=obj.detection_backend,
        confidence_threshold=obj.confidence_threshold,
        is_active=obj.is_active,
        is_default=obj.is_default,
        config=obj.config,
        created_at=obj.created_at,
        updated_at=obj.updated_at,
    )


def _build_job_response(obj: DetectionJob) -> DetectionJobResponse:
    return DetectionJobResponse(
        id=obj.pk,
        detection_job_id=str(obj.detection_job_id),
        image_id=obj.image_id,
        image_filename=obj.image.filename if obj.image else '',
        hazard_config_name=obj.hazard_config.name if obj.hazard_config else None,
        detection_backend=obj.detection_backend,
        status=obj.status,
        total_detections=obj.total_detections,
        inference_time_ms=obj.inference_time_ms,
        started_at=obj.started_at,
        completed_at=obj.completed_at,
        error_message=obj.error_message,
        created_at=obj.created_at,
    )


# ---------------------------------------------------------------------------
# CRUD: TenantHazardConfig
# ---------------------------------------------------------------------------

@router.get("/", response_model=PaginatedHazardConfigs, status_code=status.HTTP_200_OK)
async def list_hazard_configs(
    ctx: RequestContext = Depends(require_permission('read')),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    is_active: Optional[bool] = None,
):
    """List hazard detection configs for the current tenant."""
    qs = TenantHazardConfig.objects.filter(tenant=ctx.tenant).order_by('-created_at')
    if is_active is not None:
        qs = qs.filter(is_active=is_active)

    total = await sync_to_async(qs.count)()
    total_pages = max(1, (total + page_size - 1) // page_size)
    offset = (page - 1) * page_size

    items = await sync_to_async(list)(qs[offset:offset + page_size])
    return PaginatedHazardConfigs(
        items=[_build_config_response(c) for c in items],
        pagination=PaginationInfo(
            page=page,
            page_size=page_size,
            total_items=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        ),
    )


@router.post("/", response_model=HazardConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_hazard_config(
    body: HazardConfigCreate,
    ctx: RequestContext = Depends(require_permission('admin')),
):
    """Create a new hazard detection config for the current tenant."""
    # Validate prompts are non-empty strings
    if not all(isinstance(p, str) and p.strip() for p in body.prompts):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Each prompt must be a non-empty string.",
        )

    # Check for duplicate name
    exists = await sync_to_async(
        TenantHazardConfig.objects.filter(tenant=ctx.tenant, name=body.name).exists
    )()
    if exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A hazard config named '{body.name}' already exists for this tenant.",
        )

    # If this is set as default, unset any existing default
    if body.is_default:
        await sync_to_async(
            TenantHazardConfig.objects.filter(tenant=ctx.tenant, is_default=True).update
        )(is_default=False)

    obj = await sync_to_async(TenantHazardConfig.objects.create)(
        tenant=ctx.tenant,
        name=body.name,
        prompts=body.prompts,
        detection_backend=body.detection_backend,
        confidence_threshold=body.confidence_threshold,
        is_active=body.is_active,
        is_default=body.is_default,
        config=body.config,
    )
    logger.info(f"Created hazard config '{body.name}' for tenant {ctx.tenant.name}")
    return _build_config_response(obj)


@router.get("/{config_id}", response_model=HazardConfigResponse)
async def get_hazard_config(
    config_id: int,
    ctx: RequestContext = Depends(require_permission('read')),
):
    """Get a single hazard config by ID."""
    try:
        obj = await sync_to_async(
            TenantHazardConfig.objects.get
        )(id=config_id, tenant=ctx.tenant)
    except TenantHazardConfig.DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hazard config not found.")
    return _build_config_response(obj)


@router.put("/{config_id}", response_model=HazardConfigResponse)
async def update_hazard_config(
    config_id: int,
    body: HazardConfigUpdate,
    ctx: RequestContext = Depends(require_permission('admin')),
):
    """Update a hazard detection config."""
    try:
        obj = await sync_to_async(
            TenantHazardConfig.objects.get
        )(id=config_id, tenant=ctx.tenant)
    except TenantHazardConfig.DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hazard config not found.")

    update_fields = ['updated_at']
    data = body.model_dump(exclude_unset=True)

    if 'prompts' in data:
        if not all(isinstance(p, str) and p.strip() for p in data['prompts']):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Each prompt must be a non-empty string.",
            )

    if 'name' in data and data['name'] != obj.name:
        exists = await sync_to_async(
            TenantHazardConfig.objects.filter(tenant=ctx.tenant, name=data['name']).exclude(pk=obj.pk).exists
        )()
        if exists:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A hazard config named '{data['name']}' already exists.",
            )

    # If setting as default, unset others
    if data.get('is_default'):
        await sync_to_async(
            TenantHazardConfig.objects.filter(tenant=ctx.tenant, is_default=True).exclude(pk=obj.pk).update
        )(is_default=False)

    for field_name, value in data.items():
        setattr(obj, field_name, value)
        update_fields.append(field_name)

    await sync_to_async(obj.save)(update_fields=update_fields)
    logger.info(f"Updated hazard config {config_id} for tenant {ctx.tenant.name}")
    return _build_config_response(obj)


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_hazard_config(
    config_id: int,
    ctx: RequestContext = Depends(require_permission('admin')),
):
    """Delete a hazard detection config."""
    try:
        obj = await sync_to_async(
            TenantHazardConfig.objects.get
        )(id=config_id, tenant=ctx.tenant)
    except TenantHazardConfig.DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hazard config not found.")

    await sync_to_async(obj.delete)()
    logger.info(f"Deleted hazard config {config_id} for tenant {ctx.tenant.name}")


# ---------------------------------------------------------------------------
# Detection Jobs (read-only listing)
# ---------------------------------------------------------------------------

@router.get("/detection-jobs/", response_model=PaginatedDetectionJobs)
async def list_detection_jobs(
    ctx: RequestContext = Depends(require_permission('read')),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: Optional[str] = Query(default=None, alias='status'),
    image_id: Optional[int] = None,
    config_id: Optional[int] = None,
):
    """List auto-detection jobs for the current tenant."""
    qs = DetectionJob.objects.filter(
        tenant=ctx.tenant,
    ).select_related('image', 'hazard_config').order_by('-created_at')

    if status_filter:
        qs = qs.filter(status=status_filter)
    if image_id:
        qs = qs.filter(image_id=image_id)
    if config_id:
        qs = qs.filter(hazard_config_id=config_id)

    total = await sync_to_async(qs.count)()
    total_pages = max(1, (total + page_size - 1) // page_size)
    offset = (page - 1) * page_size

    items = await sync_to_async(list)(qs[offset:offset + page_size])
    return PaginatedDetectionJobs(
        items=[_build_job_response(j) for j in items],
        pagination=PaginationInfo(
            page=page,
            page_size=page_size,
            total_items=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        ),
    )


# ---------------------------------------------------------------------------
# Manual trigger
# ---------------------------------------------------------------------------

@router.post("/{config_id}/run", response_model=RunDetectionResponse, status_code=status.HTTP_202_ACCEPTED)
async def run_detection(
    config_id: int,
    body: RunDetectionRequest,
    ctx: RequestContext = Depends(require_permission('write')),
):
    """Manually trigger auto-detection on specific images using a config.

    This queues ``auto_detect_image_task`` for each image on the
    ``detection`` Celery queue.
    """
    try:
        config = await sync_to_async(
            TenantHazardConfig.objects.get
        )(id=config_id, tenant=ctx.tenant, is_active=True)
    except TenantHazardConfig.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hazard config not found or is inactive.",
        )

    from embeddings.tasks.auto_detection import auto_detect_image_task

    queued_ids = []
    for img_id in body.image_ids:
        auto_detect_image_task.delay(img_id, hazard_config_id=config.pk)
        queued_ids.append(img_id)

    logger.info(
        f"Manually triggered detection on {len(queued_ids)} images "
        f"with config '{config.name}' for tenant {ctx.tenant.name}"
    )
    return RunDetectionResponse(queued=len(queued_ids), image_ids=queued_ids)
