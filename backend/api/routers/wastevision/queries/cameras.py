"""WasteVision camera CRUD endpoints."""

import logging
from typing import Optional
from uuid import UUID

from asgiref.sync import sync_to_async
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from api.dependencies import require_permission
from api.routers.wastevision.schemas import (
    PaginatedCameras,
    PaginationMeta,
    WasteCameraCreate,
    WasteCameraResponse,
    WasteCameraUpdate,
)
from tenants.context import RequestContext

router = APIRouter(prefix="/wastevision", tags=["WasteVision"])
logger = logging.getLogger(__name__)


def _camera_to_response(cam) -> WasteCameraResponse:
    return WasteCameraResponse(
        id=cam.id,
        camera_uuid=cam.camera_uuid,
        name=cam.name,
        location=cam.location,
        plant_site=cam.plant_site or "",
        stream_type=cam.stream_type,
        stream_url=cam.stream_url or "",
        target_fps=cam.target_fps,
        is_active=cam.is_active,
        status=cam.status,
        consecutive_high=cam.consecutive_high,
        last_frame_at=cam.last_frame_at,
        last_risk_level=cam.last_risk_level or "",
        created_at=cam.created_at,
    )


@router.get("/cameras", response_model=PaginatedCameras)
async def list_cameras(
    is_active: Optional[bool] = Query(None),
    plant_site: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ctx: RequestContext = Depends(require_permission('read')),
):
    from wastevision.models import WasteCamera

    def _query():
        qs = WasteCamera.objects.filter(tenant=ctx.tenant).order_by('name')
        if is_active is not None:
            qs = qs.filter(is_active=is_active)
        if plant_site:
            qs = qs.filter(plant_site__icontains=plant_site)
        total = qs.count()
        offset = (page - 1) * page_size
        items = list(qs[offset:offset + page_size])
        return total, items

    total, cameras = await sync_to_async(_query)()
    total_pages = max(1, (total + page_size - 1) // page_size)

    return PaginatedCameras(
        items=[_camera_to_response(c) for c in cameras],
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total_items=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        ),
    )


@router.post("/cameras", response_model=WasteCameraResponse, status_code=status.HTTP_201_CREATED)
async def create_camera(
    body: WasteCameraCreate,
    request: Request,
    ctx: RequestContext = Depends(require_permission('write')),
):
    from wastevision.models import WasteCamera

    def _create():
        return WasteCamera.objects.create(
            tenant=ctx.tenant,
            created_by=ctx.user,
            name=body.name,
            location=body.location,
            plant_site=body.plant_site,
            stream_type=body.stream_type,
            stream_url=body.stream_url,
            target_fps=body.target_fps,
        )

    try:
        camera = await sync_to_async(_create)()
    except Exception as e:
        if 'unique' in str(e).lower():
            raise HTTPException(status_code=409, detail=f"Camera named '{body.name}' already exists.")
        raise

    # Start stream immediately if active
    stream_manager = getattr(getattr(request.app, 'state', None), 'wv_stream_manager', None)
    if stream_manager:
        await stream_manager.add_camera(camera)

    return _camera_to_response(camera)


@router.put("/cameras/{camera_uuid}", response_model=WasteCameraResponse)
async def update_camera(
    camera_uuid: UUID,
    body: WasteCameraUpdate,
    ctx: RequestContext = Depends(require_permission('write')),
):
    from wastevision.models import WasteCamera

    def _update():
        cam = WasteCamera.objects.get(camera_uuid=camera_uuid, tenant=ctx.tenant)
        for field, value in body.model_dump(exclude_none=True).items():
            setattr(cam, field, value)
        cam.updated_by = ctx.user
        cam.save()
        return cam

    try:
        camera = await sync_to_async(_update)()
    except WasteCamera.DoesNotExist:
        raise HTTPException(status_code=404, detail="Camera not found.")

    return _camera_to_response(camera)


@router.delete("/cameras/{camera_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(
    camera_uuid: UUID,
    request: Request,
    ctx: RequestContext = Depends(require_permission('admin')),
):
    from wastevision.models import WasteCamera

    def _get():
        return WasteCamera.objects.get(camera_uuid=camera_uuid, tenant=ctx.tenant)

    try:
        camera = await sync_to_async(_get)()
    except WasteCamera.DoesNotExist:
        raise HTTPException(status_code=404, detail="Camera not found.")

    stream_manager = getattr(getattr(request.app, 'state', None), 'wv_stream_manager', None)
    if stream_manager:
        await stream_manager.remove_camera(camera.id)

    await sync_to_async(camera.delete)()


@router.post("/cameras/{camera_uuid}/start", response_model=WasteCameraResponse)
async def start_camera(
    camera_uuid: UUID,
    request: Request,
    ctx: RequestContext = Depends(require_permission('write')),
):
    from wastevision.models import WasteCamera

    def _get_and_activate():
        cam = WasteCamera.objects.get(camera_uuid=camera_uuid, tenant=ctx.tenant)
        cam.is_active = True
        cam.save(update_fields=['is_active', 'updated_at'])
        return cam

    try:
        camera = await sync_to_async(_get_and_activate)()
    except WasteCamera.DoesNotExist:
        raise HTTPException(status_code=404, detail="Camera not found.")

    stream_manager = getattr(getattr(request.app, 'state', None), 'wv_stream_manager', None)
    if stream_manager:
        await stream_manager.add_camera(camera)

    return _camera_to_response(camera)


@router.post("/cameras/{camera_uuid}/stop", response_model=WasteCameraResponse)
async def stop_camera(
    camera_uuid: UUID,
    request: Request,
    ctx: RequestContext = Depends(require_permission('write')),
):
    from wastevision.models import WasteCamera, CameraStatus

    def _get_and_deactivate():
        cam = WasteCamera.objects.get(camera_uuid=camera_uuid, tenant=ctx.tenant)
        cam.is_active = False
        cam.status = CameraStatus.IDLE
        cam.save(update_fields=['is_active', 'status', 'updated_at'])
        return cam

    try:
        camera = await sync_to_async(_get_and_deactivate)()
    except WasteCamera.DoesNotExist:
        raise HTTPException(status_code=404, detail="Camera not found.")

    stream_manager = getattr(getattr(request.app, 'state', None), 'wv_stream_manager', None)
    if stream_manager:
        await stream_manager.remove_camera(camera.id)

    return _camera_to_response(camera)
