# api/routers/checklists/queries/checklists.py

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from asgiref.sync import sync_to_async
from pydantic import BaseModel, Field
from django.utils import timezone
from django.db.models import Count, Q, Avg

from tenants.context import RequestContext
from api.dependencies import require_permission
from checklists.models import ChecklistTemplate, ChecklistInstance, ChecklistItemResult

router = APIRouter(prefix="/checklists", tags=["Checklists"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ChecklistItemSchema(BaseModel):
    description: str
    required_photo: bool = False
    auto_detect: bool = False


class TemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    plant_site: str = Field(..., min_length=1)
    inspection_line: Optional[str] = None
    shift: Optional[str] = None
    items: List[ChecklistItemSchema] = Field(..., min_length=1)
    is_active: bool = True


class TemplateUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    plant_site: Optional[str] = None
    inspection_line: Optional[str] = None
    shift: Optional[str] = None
    items: Optional[List[ChecklistItemSchema]] = None
    is_active: Optional[bool] = None


class TemplateResponse(BaseModel):
    id: int
    name: str
    plant_site: str
    inspection_line: Optional[str]
    shift: Optional[str]
    items: list
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ItemResultResponse(BaseModel):
    item_index: int
    description: str
    required_photo: bool
    auto_detect: bool
    status: str
    image_id: Optional[int]
    notes: Optional[str]
    detection_count: int
    completed_at: Optional[datetime]


class InstanceResponse(BaseModel):
    id: int
    template_id: int
    template_name: str
    plant_site: str
    shift: str
    date: str
    operator_email: Optional[str]
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    notes: Optional[str]
    items: List[ItemResultResponse]
    progress: float
    created_at: datetime


class InstanceCreate(BaseModel):
    template_id: int
    shift: str = Field(..., pattern='^(morning|afternoon|night)$')
    date: str
    notes: Optional[str] = None


class ItemSubmit(BaseModel):
    image_id: Optional[int] = None
    status: str = Field(..., pattern='^(passed|failed|flagged)$')
    notes: Optional[str] = None


class PaginationInfo(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_previous: bool


class PaginatedTemplates(BaseModel):
    items: List[TemplateResponse]
    pagination: PaginationInfo


class PaginatedInstances(BaseModel):
    items: List[InstanceResponse]
    pagination: PaginationInfo


class ComplianceStats(BaseModel):
    total_instances: int
    completed: int
    completion_rate: float
    overdue: int
    by_plant: list
    by_shift: list


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_template_response(obj: ChecklistTemplate) -> TemplateResponse:
    return TemplateResponse(
        id=obj.pk,
        name=obj.name,
        plant_site=obj.plant_site,
        inspection_line=obj.inspection_line,
        shift=obj.shift,
        items=obj.items,
        is_active=obj.is_active,
        created_at=obj.created_at,
        updated_at=obj.updated_at,
    )


def _build_instance_response(obj: ChecklistInstance, results: list) -> InstanceResponse:
    template_items = obj.template.items if obj.template.items else []
    item_responses = []
    total_items = len(template_items)
    completed_items = 0

    for i, tmpl_item in enumerate(template_items):
        result = next((r for r in results if r.item_index == i), None)
        item_resp = ItemResultResponse(
            item_index=i,
            description=tmpl_item.get('description', ''),
            required_photo=tmpl_item.get('required_photo', False),
            auto_detect=tmpl_item.get('auto_detect', False),
            status=result.status if result else 'pending',
            image_id=result.image_id if result else None,
            notes=result.notes if result else None,
            detection_count=result.detection_count if result else 0,
            completed_at=result.completed_at if result else None,
        )
        item_responses.append(item_resp)
        if result and result.status != 'pending':
            completed_items += 1

    progress = (completed_items / total_items * 100) if total_items > 0 else 0

    return InstanceResponse(
        id=obj.pk,
        template_id=obj.template_id,
        template_name=obj.template.name,
        plant_site=obj.template.plant_site,
        shift=obj.shift,
        date=str(obj.date),
        operator_email=obj.operator.email if obj.operator else None,
        status=obj.status,
        started_at=obj.started_at,
        completed_at=obj.completed_at,
        notes=obj.notes,
        items=item_responses,
        progress=round(progress, 1),
        created_at=obj.created_at,
    )


# ---------------------------------------------------------------------------
# Template CRUD
# ---------------------------------------------------------------------------

@router.get("/templates/", response_model=PaginatedTemplates)
async def list_templates(
    ctx: RequestContext = Depends(require_permission('read')),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    is_active: Optional[bool] = None,
    plant_site: Optional[str] = None,
):
    qs = ChecklistTemplate.objects.filter(tenant=ctx.tenant).order_by('-created_at')
    if is_active is not None:
        qs = qs.filter(is_active=is_active)
    if plant_site:
        qs = qs.filter(plant_site=plant_site)

    total = await sync_to_async(qs.count)()
    total_pages = max(1, (total + page_size - 1) // page_size)
    offset = (page - 1) * page_size
    items = await sync_to_async(list)(qs[offset:offset + page_size])

    return PaginatedTemplates(
        items=[_build_template_response(t) for t in items],
        pagination=PaginationInfo(
            page=page, page_size=page_size, total_items=total,
            total_pages=total_pages, has_next=page < total_pages, has_previous=page > 1,
        ),
    )


@router.post("/templates/", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    body: TemplateCreate,
    ctx: RequestContext = Depends(require_permission('admin')),
):
    exists = await sync_to_async(
        ChecklistTemplate.objects.filter(tenant=ctx.tenant, name=body.name).exists
    )()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Template '{body.name}' already exists.")

    obj = await sync_to_async(ChecklistTemplate.objects.create)(
        tenant=ctx.tenant,
        name=body.name,
        plant_site=body.plant_site,
        inspection_line=body.inspection_line,
        shift=body.shift,
        items=[item.model_dump() for item in body.items],
        is_active=body.is_active,
        created_by=ctx.user,
    )
    return _build_template_response(obj)


@router.put("/templates/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: int,
    body: TemplateUpdate,
    ctx: RequestContext = Depends(require_permission('admin')),
):
    try:
        obj = await sync_to_async(ChecklistTemplate.objects.get)(id=template_id, tenant=ctx.tenant)
    except ChecklistTemplate.DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found.")

    data = body.model_dump(exclude_unset=True)
    update_fields = ['updated_at']
    if 'items' in data and data['items'] is not None:
        data['items'] = [item if isinstance(item, dict) else item.model_dump() for item in data['items']]
    for field, value in data.items():
        setattr(obj, field, value)
        update_fields.append(field)

    await sync_to_async(obj.save)(update_fields=update_fields)
    return _build_template_response(obj)


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: int,
    ctx: RequestContext = Depends(require_permission('admin')),
):
    try:
        obj = await sync_to_async(ChecklistTemplate.objects.get)(id=template_id, tenant=ctx.tenant)
    except ChecklistTemplate.DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found.")
    await sync_to_async(obj.delete)()


# ---------------------------------------------------------------------------
# Instance CRUD
# ---------------------------------------------------------------------------

@router.get("/", response_model=PaginatedInstances)
async def list_instances(
    ctx: RequestContext = Depends(require_permission('read')),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    date: Optional[str] = None,
    shift: Optional[str] = None,
    status_filter: Optional[str] = Query(default=None, alias='status'),
):
    qs = ChecklistInstance.objects.filter(
        tenant=ctx.tenant,
    ).select_related('template', 'operator').order_by('-date', '-created_at')

    if date:
        qs = qs.filter(date=date)
    if shift:
        qs = qs.filter(shift=shift)
    if status_filter:
        qs = qs.filter(status=status_filter)

    total = await sync_to_async(qs.count)()
    total_pages = max(1, (total + page_size - 1) // page_size)
    offset = (page - 1) * page_size
    instances = await sync_to_async(list)(qs[offset:offset + page_size])

    items = []
    for inst in instances:
        results = await sync_to_async(list)(
            ChecklistItemResult.objects.filter(instance=inst).order_by('item_index')
        )
        items.append(_build_instance_response(inst, results))

    return PaginatedInstances(
        items=items,
        pagination=PaginationInfo(
            page=page, page_size=page_size, total_items=total,
            total_pages=total_pages, has_next=page < total_pages, has_previous=page > 1,
        ),
    )


@router.post("/", response_model=InstanceResponse, status_code=status.HTTP_201_CREATED)
async def create_instance(
    body: InstanceCreate,
    ctx: RequestContext = Depends(require_permission('write')),
):
    try:
        template = await sync_to_async(
            ChecklistTemplate.objects.get
        )(id=body.template_id, tenant=ctx.tenant, is_active=True)
    except ChecklistTemplate.DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found or inactive.")

    from datetime import date as date_type
    inst = await sync_to_async(ChecklistInstance.objects.create)(
        tenant=ctx.tenant,
        template=template,
        shift=body.shift,
        date=date_type.fromisoformat(body.date),
        operator=ctx.user,
        status='pending',
        notes=body.notes,
    )
    return _build_instance_response(inst, [])


@router.get("/{instance_id}", response_model=InstanceResponse)
async def get_instance(
    instance_id: int,
    ctx: RequestContext = Depends(require_permission('read')),
):
    try:
        inst = await sync_to_async(
            ChecklistInstance.objects.select_related('template', 'operator').get
        )(id=instance_id, tenant=ctx.tenant)
    except ChecklistInstance.DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checklist instance not found.")

    results = await sync_to_async(list)(
        ChecklistItemResult.objects.filter(instance=inst).order_by('item_index')
    )
    return _build_instance_response(inst, results)


@router.post("/{instance_id}/items/{item_index}/submit", response_model=InstanceResponse)
async def submit_item(
    instance_id: int,
    item_index: int,
    body: ItemSubmit,
    ctx: RequestContext = Depends(require_permission('write')),
):
    try:
        inst = await sync_to_async(
            ChecklistInstance.objects.select_related('template', 'operator').get
        )(id=instance_id, tenant=ctx.tenant)
    except ChecklistInstance.DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checklist not found.")

    if item_index < 0 or item_index >= len(inst.template.items):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid item index.")

    # Update instance status if first item
    if inst.status == 'pending':
        inst.status = 'in_progress'
        inst.started_at = timezone.now()
        await sync_to_async(inst.save)(update_fields=['status', 'started_at', 'updated_at'])

    # Create or update result
    def _save_result():
        result, created = ChecklistItemResult.objects.update_or_create(
            instance=inst, item_index=item_index, tenant=ctx.tenant,
            defaults={
                'status': body.status,
                'image_id': body.image_id,
                'notes': body.notes,
                'completed_at': timezone.now(),
            },
        )
        return result

    result = await sync_to_async(_save_result)()

    # Trigger auto-detection if configured and image provided
    tmpl_item = inst.template.items[item_index]
    if tmpl_item.get('auto_detect') and body.image_id:
        try:
            from embeddings.tasks.auto_detection import auto_detect_image_task
            auto_detect_image_task.delay(body.image_id)
        except Exception as e:
            logger.warning(f"Failed to trigger auto-detection for checklist item: {e}")

    results = await sync_to_async(list)(
        ChecklistItemResult.objects.filter(instance=inst).order_by('item_index')
    )
    return _build_instance_response(inst, results)


@router.post("/{instance_id}/complete", response_model=InstanceResponse)
async def complete_instance(
    instance_id: int,
    ctx: RequestContext = Depends(require_permission('write')),
):
    try:
        inst = await sync_to_async(
            ChecklistInstance.objects.select_related('template', 'operator').get
        )(id=instance_id, tenant=ctx.tenant)
    except ChecklistInstance.DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checklist not found.")

    inst.status = 'completed'
    inst.completed_at = timezone.now()
    await sync_to_async(inst.save)(update_fields=['status', 'completed_at', 'updated_at'])

    results = await sync_to_async(list)(
        ChecklistItemResult.objects.filter(instance=inst).order_by('item_index')
    )
    return _build_instance_response(inst, results)


@router.get("/compliance", response_model=ComplianceStats)
async def get_compliance(
    ctx: RequestContext = Depends(require_permission('read')),
    days: int = Query(default=30, ge=7, le=365),
):
    from datetime import timedelta
    cutoff = timezone.now().date() - timedelta(days=days)

    def _compute():
        qs = ChecklistInstance.objects.filter(tenant=ctx.tenant, date__gte=cutoff)
        total = qs.count()
        completed = qs.filter(status='completed').count()
        overdue = qs.filter(status='overdue').count()
        rate = (completed / total * 100) if total > 0 else 0

        by_plant = list(
            qs.values('template__plant_site')
            .annotate(total=Count('id'), completed=Count('id', filter=Q(status='completed')))
            .order_by('template__plant_site')
        )
        by_shift = list(
            qs.values('shift')
            .annotate(total=Count('id'), completed=Count('id', filter=Q(status='completed')))
            .order_by('shift')
        )

        return ComplianceStats(
            total_instances=total,
            completed=completed,
            completion_rate=round(rate, 1),
            overdue=overdue,
            by_plant=[{'plant_site': r['template__plant_site'], 'total': r['total'], 'completed': r['completed']} for r in by_plant],
            by_shift=[{'shift': r['shift'], 'total': r['total'], 'completed': r['completed']} for r in by_shift],
        )

    return await sync_to_async(_compute)()
