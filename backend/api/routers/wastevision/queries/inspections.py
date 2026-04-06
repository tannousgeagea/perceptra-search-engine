"""WasteVision inspection, alert, and stats endpoints."""

import csv
import io
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from asgiref.sync import sync_to_async
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from api.dependencies import require_permission
from api.routers.wastevision.schemas import (
    ContaminationItem,
    InspectFrameRequest,
    PaginatedAlerts,
    PaginatedInspections,
    PaginationMeta,
    RiskBreakdown,
    WasteAlertResponse,
    WasteComposition,
    WasteInspectionResponse,
    WasteStats,
)
from tenants.context import RequestContext

router = APIRouter(prefix="/wastevision", tags=["WasteVision"])
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────── #
# Helpers
# ─────────────────────────────────────────────────────────────── #

def _inspection_to_response(insp) -> WasteInspectionResponse:
    comp = insp.waste_composition or {}
    alerts = [
        ContaminationItem(
            item=a.get('item', ''),
            severity=a.get('severity', 'low'),
            location_in_frame=a.get('location_in_frame', ''),
            action=a.get('action', ''),
        )
        for a in (insp.contamination_alerts or [])
    ]
    return WasteInspectionResponse(
        id=insp.id,
        inspection_uuid=insp.inspection_uuid,
        camera_uuid=insp.camera.camera_uuid,
        sequence_no=insp.sequence_no,
        frame_timestamp=insp.frame_timestamp,
        waste_composition=WasteComposition(**comp),
        contamination_alerts=alerts,
        line_blockage=insp.line_blockage,
        overall_risk=insp.overall_risk,
        confidence=insp.confidence,
        inspector_note=insp.inspector_note,
        vlm_provider=insp.vlm_provider,
        vlm_model=insp.vlm_model,
        processing_time_ms=insp.processing_time_ms,
        created_at=insp.created_at,
    )


def _alert_to_response(alert) -> WasteAlertResponse:
    return WasteAlertResponse(
        id=alert.id,
        alert_uuid=alert.alert_uuid,
        camera_uuid=alert.camera.camera_uuid,
        alert_type=alert.alert_type,
        severity=alert.severity,
        details=alert.details or {},
        is_acknowledged=alert.is_acknowledged,
        acknowledged_at=alert.acknowledged_at,
        created_at=alert.created_at,
    )


# ─────────────────────────────────────────────────────────────── #
# Frame inspection
# ─────────────────────────────────────────────────────────────── #

@router.post("/inspect", response_model=WasteInspectionResponse)
async def inspect_frame(
    body: InspectFrameRequest,
    request: Request,
    ctx: RequestContext = Depends(require_permission('write')),
):
    """Submit a frame for VLM analysis. Returns inspection result (synchronous)."""
    from wastevision.models import WasteCamera

    def _get_cam():
        return WasteCamera.objects.get(camera_uuid=body.camera_uuid, tenant=ctx.tenant)

    try:
        await sync_to_async(_get_cam)()
    except WasteCamera.DoesNotExist:
        raise HTTPException(status_code=404, detail="Camera not found.")

    if body.async_mode:
        from wastevision.tasks import analyze_frame_task
        analyze_frame_task.delay(str(body.camera_uuid), body.image_b64, ctx.tenant.id)
        raise HTTPException(
            status_code=202,
            detail={"queued": True, "camera_uuid": str(body.camera_uuid)},
        )

    # Synchronous path
    vlm_service = getattr(getattr(request.app, 'state', None), 'wv_vlm_service', None)
    if vlm_service is None:
        # Fallback: create a temporary service instance
        import asyncio
        from wastevision.service import WasteVisionService
        vlm_service = WasteVisionService(asyncio.Queue())

    try:
        inspection = await vlm_service.analyze_frame_sync(
            camera_uuid=str(body.camera_uuid),
            image_b64=body.image_b64,
            tenant_id=ctx.tenant.id,
        )
    except Exception as e:
        logger.error("WasteVision inspect_frame error: %s", e)
        raise HTTPException(status_code=500, detail=f"VLM analysis failed: {e}")

    # Re-fetch with camera relation
    from wastevision.models import WasteInspection
    inspection = await sync_to_async(
        WasteInspection.objects.select_related('camera').get
    )(id=inspection.id)
    return _inspection_to_response(inspection)


# ─────────────────────────────────────────────────────────────── #
# Inspection history
# ─────────────────────────────────────────────────────────────── #

@router.get("/inspections", response_model=PaginatedInspections)
async def list_inspections(
    camera_uuid: Optional[UUID] = Query(None),
    overall_risk: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ctx: RequestContext = Depends(require_permission('read')),
):
    from wastevision.models import WasteInspection

    def _query():
        qs = WasteInspection.objects.select_related('camera').filter(tenant=ctx.tenant)
        if camera_uuid:
            qs = qs.filter(camera__camera_uuid=camera_uuid)
        if overall_risk:
            qs = qs.filter(overall_risk=overall_risk.lower())
        if date_from:
            qs = qs.filter(created_at__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__lte=date_to)
        qs = qs.order_by('-created_at')
        total = qs.count()
        offset = (page - 1) * page_size
        items = list(qs[offset:offset + page_size])
        return total, items

    total, inspections = await sync_to_async(_query)()
    total_pages = max(1, (total + page_size - 1) // page_size)

    return PaginatedInspections(
        items=[_inspection_to_response(i) for i in inspections],
        pagination=PaginationMeta(
            page=page, page_size=page_size, total_items=total,
            total_pages=total_pages, has_next=page < total_pages, has_previous=page > 1,
        ),
    )


@router.get("/inspections/export")
async def export_inspections(
    camera_uuid: Optional[UUID] = Query(None),
    overall_risk: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    ctx: RequestContext = Depends(require_permission('read')),
):
    """Stream inspections as CSV."""
    from wastevision.models import WasteInspection

    def _query():
        qs = WasteInspection.objects.select_related('camera').filter(tenant=ctx.tenant)
        if camera_uuid:
            qs = qs.filter(camera__camera_uuid=camera_uuid)
        if overall_risk:
            qs = qs.filter(overall_risk=overall_risk.lower())
        if date_from:
            qs = qs.filter(created_at__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__lte=date_to)
        return list(qs.order_by('-created_at')[:5000])

    inspections = await sync_to_async(_query)()

    def _generate_csv():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            'inspection_uuid', 'camera_name', 'sequence_no', 'frame_timestamp',
            'overall_risk', 'confidence', 'line_blockage', 'inspector_note',
            'plastic', 'paper', 'glass', 'metal', 'organic', 'e_waste', 'hazardous', 'other',
            'contamination_count', 'vlm_provider', 'processing_time_ms', 'created_at',
        ])
        for insp in inspections:
            comp = insp.waste_composition or {}
            writer.writerow([
                insp.inspection_uuid, insp.camera.name, insp.sequence_no,
                insp.frame_timestamp.isoformat(), insp.overall_risk, insp.confidence,
                insp.line_blockage, insp.inspector_note,
                comp.get('plastic', 0), comp.get('paper', 0), comp.get('glass', 0),
                comp.get('metal', 0), comp.get('organic', 0), comp.get('e_waste', 0),
                comp.get('hazardous', 0), comp.get('other', 0),
                len(insp.contamination_alerts or []),
                insp.vlm_provider, insp.processing_time_ms, insp.created_at.isoformat(),
            ])
        return buf.getvalue().encode()

    content = await sync_to_async(_generate_csv)()
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=wastevision_inspections.csv"},
    )


@router.get("/inspections/{inspection_uuid}", response_model=WasteInspectionResponse)
async def get_inspection(
    inspection_uuid: UUID,
    ctx: RequestContext = Depends(require_permission('read')),
):
    from wastevision.models import WasteInspection

    def _get():
        return WasteInspection.objects.select_related('camera').get(
            inspection_uuid=inspection_uuid, tenant=ctx.tenant
        )

    try:
        inspection = await sync_to_async(_get)()
    except WasteInspection.DoesNotExist:
        raise HTTPException(status_code=404, detail="Inspection not found.")

    return _inspection_to_response(inspection)


@router.get("/cameras/{camera_uuid}/trend", response_model=List[WasteInspectionResponse])
async def get_camera_trend(
    camera_uuid: UUID,
    n: int = Query(50, ge=1, le=500),
    ctx: RequestContext = Depends(require_permission('read')),
):
    """Last N inspections for a camera — for composition trend charts."""
    from wastevision.models import WasteInspection

    def _query():
        return list(
            WasteInspection.objects.select_related('camera').filter(
                camera__camera_uuid=camera_uuid, tenant=ctx.tenant
            ).order_by('-created_at')[:n]
        )

    inspections = await sync_to_async(_query)()
    return [_inspection_to_response(i) for i in reversed(inspections)]


# ─────────────────────────────────────────────────────────────── #
# Stats
# ─────────────────────────────────────────────────────────────── #

@router.get("/stats", response_model=WasteStats)
async def get_stats(ctx: RequestContext = Depends(require_permission('read'))):
    from wastevision.models import WasteCamera, WasteInspection, WasteAlert
    from django.db.models import Avg, Count

    def _compute():
        total = WasteInspection.objects.filter(tenant=ctx.tenant).count()

        risk_counts = dict(
            WasteInspection.objects.filter(tenant=ctx.tenant)
            .values('overall_risk')
            .annotate(count=Count('id'))
            .values_list('overall_risk', 'count')
        )

        active_cams = WasteCamera.objects.filter(tenant=ctx.tenant, is_active=True, status='streaming').count()

        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        alerts_24h = WasteAlert.objects.filter(tenant=ctx.tenant, created_at__gte=cutoff).count()

        # Top contamination labels
        recent = list(
            WasteInspection.objects.filter(tenant=ctx.tenant)
            .order_by('-created_at')
            .values_list('contamination_alerts', flat=True)[:500]
        )
        label_counter: Counter = Counter()
        for alerts in recent:
            for a in (alerts or []):
                if isinstance(a, dict) and a.get('item'):
                    label_counter[a['item']] += 1
        top_labels = [{'label': k, 'count': v} for k, v in label_counter.most_common(10)]

        # Avg confidence per camera
        avg_conf = list(
            WasteInspection.objects.filter(tenant=ctx.tenant)
            .values('camera__camera_uuid', 'camera__name')
            .annotate(avg_confidence=Avg('confidence'))
            .order_by('-avg_confidence')[:20]
        )
        avg_conf_list = [
            {
                'camera_uuid': str(r['camera__camera_uuid']),
                'camera_name': r['camera__name'],
                'avg_confidence': round(r['avg_confidence'] or 0, 3),
            }
            for r in avg_conf
        ]

        return total, risk_counts, active_cams, alerts_24h, top_labels, avg_conf_list

    total, risk_counts, active_cams, alerts_24h, top_labels, avg_conf_list = await sync_to_async(_compute)()

    return WasteStats(
        total_inspections=total,
        risk_breakdown=RiskBreakdown(
            low=risk_counts.get('low', 0),
            medium=risk_counts.get('medium', 0),
            high=risk_counts.get('high', 0),
            critical=risk_counts.get('critical', 0),
        ),
        top_contamination_labels=top_labels,
        avg_confidence_by_camera=avg_conf_list,
        active_cameras=active_cams,
        alerts_last_24h=alerts_24h,
    )


# ─────────────────────────────────────────────────────────────── #
# Alerts
# ─────────────────────────────────────────────────────────────── #

@router.get("/alerts", response_model=PaginatedAlerts)
async def list_waste_alerts(
    camera_uuid: Optional[UUID] = Query(None),
    severity: Optional[str] = Query(None),
    is_acknowledged: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ctx: RequestContext = Depends(require_permission('read')),
):
    from wastevision.models import WasteAlert

    def _query():
        qs = WasteAlert.objects.select_related('camera').filter(tenant=ctx.tenant)
        if camera_uuid:
            qs = qs.filter(camera__camera_uuid=camera_uuid)
        if severity:
            qs = qs.filter(severity=severity.lower())
        if is_acknowledged is not None:
            qs = qs.filter(is_acknowledged=is_acknowledged)
        qs = qs.order_by('-created_at')
        total = qs.count()
        offset = (page - 1) * page_size
        items = list(qs[offset:offset + page_size])
        return total, items

    total, alerts = await sync_to_async(_query)()
    total_pages = max(1, (total + page_size - 1) // page_size)

    return PaginatedAlerts(
        items=[_alert_to_response(a) for a in alerts],
        pagination=PaginationMeta(
            page=page, page_size=page_size, total_items=total,
            total_pages=total_pages, has_next=page < total_pages, has_previous=page > 1,
        ),
    )


@router.post("/alerts/{alert_uuid}/acknowledge", response_model=WasteAlertResponse)
async def acknowledge_alert(
    alert_uuid: UUID,
    ctx: RequestContext = Depends(require_permission('write')),
):
    from wastevision.models import WasteAlert
    from django.utils import timezone as django_tz

    def _ack():
        alert = WasteAlert.objects.select_related('camera').get(
            alert_uuid=alert_uuid, tenant=ctx.tenant
        )
        alert.is_acknowledged = True
        alert.acknowledged_by = ctx.user
        alert.acknowledged_at = django_tz.now()
        alert.save(update_fields=['is_acknowledged', 'acknowledged_by', 'acknowledged_at'])
        return alert

    try:
        alert = await sync_to_async(_ack)()
    except WasteAlert.DoesNotExist:
        raise HTTPException(status_code=404, detail="Alert not found.")

    return _alert_to_response(alert)
