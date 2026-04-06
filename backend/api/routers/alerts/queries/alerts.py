# api/routers/alerts/queries/alerts.py

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from datetime import datetime
from asgiref.sync import sync_to_async
from pydantic import BaseModel, Field
from django.utils import timezone

from tenants.context import RequestContext
from api.dependencies import require_permission
from alerts.models import Alert, AlertRule

import logging

router = APIRouter(prefix="/alerts", tags=["Alerts"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class AlertRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    label_pattern: str = Field(..., min_length=1, max_length=200)
    min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    plant_site: Optional[str] = None
    is_active: bool = True
    webhook_url: Optional[str] = None
    notify_websocket: bool = True
    cooldown_minutes: int = Field(default=5, ge=0)


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    label_pattern: Optional[str] = Field(default=None, min_length=1, max_length=200)
    min_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    plant_site: Optional[str] = None
    is_active: Optional[bool] = None
    webhook_url: Optional[str] = None
    notify_websocket: Optional[bool] = None
    cooldown_minutes: Optional[int] = Field(default=None, ge=0)


class AlertRuleResponse(BaseModel):
    id: int
    name: str
    label_pattern: str
    min_confidence: float
    plant_site: Optional[str]
    is_active: bool
    webhook_url: Optional[str]
    notify_websocket: bool
    cooldown_minutes: int
    created_at: datetime
    updated_at: datetime


class AlertResponse(BaseModel):
    id: int
    alert_rule_id: Optional[int]
    alert_rule_name: Optional[str]
    detection_id: int
    image_id: int
    severity: str
    label: str
    confidence: float
    plant_site: Optional[str]
    is_acknowledged: bool
    acknowledged_by_email: Optional[str]
    acknowledged_at: Optional[datetime]
    webhook_sent: bool
    crop_url: Optional[str]
    created_at: datetime


class PaginationInfo(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_previous: bool


class PaginatedAlerts(BaseModel):
    items: List[AlertResponse]
    pagination: PaginationInfo


class PaginatedAlertRules(BaseModel):
    items: List[AlertRuleResponse]
    pagination: PaginationInfo


class UnreadCountResponse(BaseModel):
    count: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_alert_response(obj: Alert) -> AlertResponse:
    crop_url = None
    try:
        if obj.detection and obj.detection.storage_key:
            crop_url = f'/api/v1/media/files/{obj.detection.storage_key}'
    except Exception:
        pass

    return AlertResponse(
        id=obj.pk,
        alert_rule_id=obj.alert_rule_id,
        alert_rule_name=obj.alert_rule.name if obj.alert_rule else None,
        detection_id=obj.detection_id,
        image_id=obj.image_id,
        severity=obj.severity,
        label=obj.label,
        confidence=obj.confidence,
        plant_site=obj.plant_site,
        is_acknowledged=obj.is_acknowledged,
        acknowledged_by_email=obj.acknowledged_by.email if obj.acknowledged_by else None,
        acknowledged_at=obj.acknowledged_at,
        webhook_sent=obj.webhook_sent,
        crop_url=crop_url,
        created_at=obj.created_at,
    )


def _build_rule_response(obj: AlertRule) -> AlertRuleResponse:
    return AlertRuleResponse(
        id=obj.pk,
        name=obj.name,
        label_pattern=obj.label_pattern,
        min_confidence=obj.min_confidence,
        plant_site=obj.plant_site,
        is_active=obj.is_active,
        webhook_url=obj.webhook_url,
        notify_websocket=obj.notify_websocket,
        cooldown_minutes=obj.cooldown_minutes,
        created_at=obj.created_at,
        updated_at=obj.updated_at,
    )


# ---------------------------------------------------------------------------
# Alert Endpoints
# ---------------------------------------------------------------------------

@router.get("/", response_model=PaginatedAlerts, status_code=status.HTTP_200_OK)
async def list_alerts(
    ctx: RequestContext = Depends(require_permission('read')),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    severity: Optional[str] = None,
    is_acknowledged: Optional[bool] = None,
    plant_site: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """List alerts for the current tenant with filtering."""
    qs = Alert.objects.filter(
        tenant=ctx.tenant,
    ).select_related('alert_rule', 'detection', 'acknowledged_by').order_by('-created_at')

    if severity:
        qs = qs.filter(severity=severity)
    if is_acknowledged is not None:
        qs = qs.filter(is_acknowledged=is_acknowledged)
    if plant_site:
        qs = qs.filter(plant_site=plant_site)
    if date_from:
        qs = qs.filter(created_at__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__lte=date_to)

    total = await sync_to_async(qs.count)()
    total_pages = max(1, (total + page_size - 1) // page_size)
    offset = (page - 1) * page_size

    items = await sync_to_async(list)(qs[offset:offset + page_size])
    return PaginatedAlerts(
        items=[_build_alert_response(a) for a in items],
        pagination=PaginationInfo(
            page=page,
            page_size=page_size,
            total_items=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        ),
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    ctx: RequestContext = Depends(require_permission('read')),
):
    """Return count of unacknowledged alerts for notification badge."""
    count = await sync_to_async(
        Alert.objects.filter(tenant=ctx.tenant, is_acknowledged=False).count
    )()
    return UnreadCountResponse(count=count)


@router.post("/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: int,
    ctx: RequestContext = Depends(require_permission('write')),
):
    """Acknowledge a single alert."""
    try:
        alert = await sync_to_async(
            Alert.objects.select_related('alert_rule', 'detection', 'acknowledged_by').get
        )(id=alert_id, tenant=ctx.tenant)
    except Alert.DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found.")

    if not alert.is_acknowledged:
        alert.is_acknowledged = True
        alert.acknowledged_by = ctx.user
        alert.acknowledged_at = timezone.now()
        await sync_to_async(alert.save)(
            update_fields=['is_acknowledged', 'acknowledged_by', 'acknowledged_at', 'updated_at']
        )
        logger.info(f"Alert {alert_id} acknowledged by {ctx.user.email}")

    return _build_alert_response(alert)


@router.post("/acknowledge-all", response_model=dict)
async def acknowledge_all_alerts(
    ctx: RequestContext = Depends(require_permission('write')),
):
    """Acknowledge all unread alerts for the current tenant."""
    count = await sync_to_async(
        Alert.objects.filter(
            tenant=ctx.tenant, is_acknowledged=False,
        ).update
    )(
        is_acknowledged=True,
        acknowledged_by=ctx.user,
        acknowledged_at=timezone.now(),
    )
    logger.info(f"Acknowledged {count} alerts for tenant {ctx.tenant.name}")
    return {"acknowledged": count}


# ---------------------------------------------------------------------------
# Alert Rule Endpoints
# ---------------------------------------------------------------------------

@router.get("/rules/", response_model=PaginatedAlertRules)
async def list_alert_rules(
    ctx: RequestContext = Depends(require_permission('admin')),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    is_active: Optional[bool] = None,
):
    """List alert rules for the current tenant."""
    qs = AlertRule.objects.filter(tenant=ctx.tenant).order_by('-created_at')
    if is_active is not None:
        qs = qs.filter(is_active=is_active)

    total = await sync_to_async(qs.count)()
    total_pages = max(1, (total + page_size - 1) // page_size)
    offset = (page - 1) * page_size

    items = await sync_to_async(list)(qs[offset:offset + page_size])
    return PaginatedAlertRules(
        items=[_build_rule_response(r) for r in items],
        pagination=PaginationInfo(
            page=page,
            page_size=page_size,
            total_items=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        ),
    )


@router.post("/rules/", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_alert_rule(
    body: AlertRuleCreate,
    ctx: RequestContext = Depends(require_permission('admin')),
):
    """Create a new alert rule."""
    exists = await sync_to_async(
        AlertRule.objects.filter(tenant=ctx.tenant, name=body.name).exists
    )()
    if exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An alert rule named '{body.name}' already exists for this tenant.",
        )

    obj = await sync_to_async(AlertRule.objects.create)(
        tenant=ctx.tenant,
        name=body.name,
        label_pattern=body.label_pattern,
        min_confidence=body.min_confidence,
        plant_site=body.plant_site,
        is_active=body.is_active,
        webhook_url=body.webhook_url,
        notify_websocket=body.notify_websocket,
        cooldown_minutes=body.cooldown_minutes,
        created_by=ctx.user,
    )
    logger.info(f"Created alert rule '{body.name}' for tenant {ctx.tenant.name}")
    return _build_rule_response(obj)


@router.put("/rules/{rule_id}", response_model=AlertRuleResponse)
async def update_alert_rule(
    rule_id: int,
    body: AlertRuleUpdate,
    ctx: RequestContext = Depends(require_permission('admin')),
):
    """Update an alert rule."""
    try:
        obj = await sync_to_async(
            AlertRule.objects.get
        )(id=rule_id, tenant=ctx.tenant)
    except AlertRule.DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found.")

    update_fields = ['updated_at']
    data = body.model_dump(exclude_unset=True)

    if 'name' in data and data['name'] != obj.name:
        exists = await sync_to_async(
            AlertRule.objects.filter(tenant=ctx.tenant, name=data['name']).exclude(pk=obj.pk).exists
        )()
        if exists:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"An alert rule named '{data['name']}' already exists.",
            )

    for field_name, value in data.items():
        setattr(obj, field_name, value)
        update_fields.append(field_name)

    await sync_to_async(obj.save)(update_fields=update_fields)
    logger.info(f"Updated alert rule {rule_id} for tenant {ctx.tenant.name}")
    return _build_rule_response(obj)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert_rule(
    rule_id: int,
    ctx: RequestContext = Depends(require_permission('admin')),
):
    """Delete an alert rule."""
    try:
        obj = await sync_to_async(
            AlertRule.objects.get
        )(id=rule_id, tenant=ctx.tenant)
    except AlertRule.DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found.")

    await sync_to_async(obj.delete)()
    logger.info(f"Deleted alert rule {rule_id} for tenant {ctx.tenant.name}")
