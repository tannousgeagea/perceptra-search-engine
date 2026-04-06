# api/routers/collaboration/queries/collaboration.py

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from asgiref.sync import sync_to_async
from pydantic import BaseModel, Field
from django.utils import timezone

from tenants.context import RequestContext
from api.dependencies import require_permission
from collaboration.models import Comment, Assignment, ActivityEvent

router = APIRouter(prefix="/collaboration", tags=["Collaboration"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CommentCreate(BaseModel):
    content_type: str = Field(..., pattern='^(image|detection|video)$')
    object_id: int
    text: str = Field(..., min_length=1, max_length=2000)
    mentions: List[int] = Field(default_factory=list)


class CommentResponse(BaseModel):
    id: int
    content_type: str
    object_id: int
    author_id: int
    author_email: str
    author_name: Optional[str]
    text: str
    mentions: list
    created_at: datetime
    updated_at: datetime


class AssignmentCreate(BaseModel):
    detection_id: int
    assigned_to_id: int
    priority: str = Field(default='medium', pattern='^(low|medium|high|critical)$')
    due_date: Optional[str] = None
    notes: Optional[str] = None


class AssignmentUpdate(BaseModel):
    status: Optional[str] = Field(default=None, pattern='^(open|in_progress|resolved|wont_fix)$')
    priority: Optional[str] = Field(default=None, pattern='^(low|medium|high|critical)$')
    notes: Optional[str] = None


class AssignmentResponse(BaseModel):
    id: int
    detection_id: int
    detection_label: Optional[str]
    detection_crop_url: Optional[str]
    assigned_to_id: int
    assigned_to_email: str
    assigned_by_email: str
    status: str
    priority: str
    due_date: Optional[str]
    notes: Optional[str]
    resolved_at: Optional[datetime]
    created_at: datetime


class ActivityResponse(BaseModel):
    id: int
    user_email: str
    user_name: Optional[str]
    action: str
    target_type: str
    target_id: int
    metadata: dict
    created_at: datetime


class UserResponse(BaseModel):
    id: int
    email: str
    name: Optional[str]


class PaginationInfo(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_previous: bool


class PaginatedComments(BaseModel):
    items: List[CommentResponse]
    pagination: PaginationInfo


class PaginatedAssignments(BaseModel):
    items: List[AssignmentResponse]
    pagination: PaginationInfo


class PaginatedActivity(BaseModel):
    items: List[ActivityResponse]
    pagination: PaginationInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_comment(c: Comment) -> CommentResponse:
    return CommentResponse(
        id=c.pk, content_type=c.content_type, object_id=c.object_id,
        author_id=c.author_id, author_email=c.author.email,
        author_name=getattr(c.author, 'first_name', None) or None,
        text=c.text, mentions=c.mentions,
        created_at=c.created_at, updated_at=c.updated_at,
    )


def _build_assignment(a: Assignment) -> AssignmentResponse:
    crop_url = None
    try:
        if a.detection and a.detection.storage_key:
            crop_url = f'/api/v1/media/files/{a.detection.storage_key}'
    except Exception:
        pass

    return AssignmentResponse(
        id=a.pk, detection_id=a.detection_id,
        detection_label=a.detection.label if a.detection else None,
        detection_crop_url=crop_url,
        assigned_to_id=a.assigned_to_id, assigned_to_email=a.assigned_to.email,
        assigned_by_email=a.assigned_by.email,
        status=a.status, priority=a.priority,
        due_date=str(a.due_date) if a.due_date else None,
        notes=a.notes, resolved_at=a.resolved_at,
        created_at=a.created_at,
    )


def _build_activity(e: ActivityEvent) -> ActivityResponse:
    return ActivityResponse(
        id=e.pk, user_email=e.user.email,
        user_name=getattr(e.user, 'first_name', None) or None,
        action=e.action, target_type=e.target_type,
        target_id=e.target_id, metadata=e.metadata,
        created_at=e.created_at,
    )


def _log_activity(tenant, user, action, target_type, target_id, metadata=None):
    """Create an activity event (sync context)."""
    ActivityEvent.objects.create(
        tenant=tenant, user=user, action=action,
        target_type=target_type, target_id=target_id,
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

@router.get("/comments", response_model=PaginatedComments)
async def list_comments(
    ctx: RequestContext = Depends(require_permission('read')),
    content_type: str = Query(..., pattern='^(image|detection|video)$'),
    object_id: int = Query(...),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
):
    qs = Comment.objects.filter(
        tenant=ctx.tenant, content_type=content_type, object_id=object_id,
    ).select_related('author').order_by('created_at')

    total = await sync_to_async(qs.count)()
    total_pages = max(1, (total + page_size - 1) // page_size)
    offset = (page - 1) * page_size
    items = await sync_to_async(list)(qs[offset:offset + page_size])

    return PaginatedComments(
        items=[_build_comment(c) for c in items],
        pagination=PaginationInfo(
            page=page, page_size=page_size, total_items=total,
            total_pages=total_pages, has_next=page < total_pages, has_previous=page > 1,
        ),
    )


@router.post("/comments", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
async def create_comment(
    body: CommentCreate,
    ctx: RequestContext = Depends(require_permission('write')),
):
    def _create():
        c = Comment.objects.create(
            tenant=ctx.tenant, content_type=body.content_type,
            object_id=body.object_id, author=ctx.user,
            text=body.text, mentions=body.mentions,
        )
        _log_activity(ctx.tenant, ctx.user, 'commented', body.content_type, body.object_id,
                      {'text_preview': body.text[:100]})
        return c

    c = await sync_to_async(_create)()
    # Re-fetch with author
    c = await sync_to_async(Comment.objects.select_related('author').get)(pk=c.pk)
    return _build_comment(c)


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    comment_id: int,
    ctx: RequestContext = Depends(require_permission('write')),
):
    try:
        c = await sync_to_async(Comment.objects.get)(id=comment_id, tenant=ctx.tenant)
    except Comment.DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found.")
    if c.author_id != ctx.user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Can only delete your own comments.")
    await sync_to_async(c.delete)()


# ---------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------

@router.get("/assignments/", response_model=PaginatedAssignments)
async def list_assignments(
    ctx: RequestContext = Depends(require_permission('read')),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    assigned_to: Optional[int] = None,
    status_filter: Optional[str] = Query(default=None, alias='status'),
    priority: Optional[str] = None,
):
    qs = Assignment.objects.filter(
        tenant=ctx.tenant,
    ).select_related('detection', 'assigned_to', 'assigned_by').order_by('-created_at')

    if assigned_to:
        qs = qs.filter(assigned_to_id=assigned_to)
    if status_filter:
        qs = qs.filter(status=status_filter)
    if priority:
        qs = qs.filter(priority=priority)

    total = await sync_to_async(qs.count)()
    total_pages = max(1, (total + page_size - 1) // page_size)
    offset = (page - 1) * page_size
    items = await sync_to_async(list)(qs[offset:offset + page_size])

    return PaginatedAssignments(
        items=[_build_assignment(a) for a in items],
        pagination=PaginationInfo(
            page=page, page_size=page_size, total_items=total,
            total_pages=total_pages, has_next=page < total_pages, has_previous=page > 1,
        ),
    )


@router.get("/assignments/mine", response_model=PaginatedAssignments)
async def my_assignments(
    ctx: RequestContext = Depends(require_permission('read')),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    qs = Assignment.objects.filter(
        tenant=ctx.tenant, assigned_to=ctx.user,
    ).select_related('detection', 'assigned_to', 'assigned_by').order_by('-created_at')

    total = await sync_to_async(qs.count)()
    total_pages = max(1, (total + page_size - 1) // page_size)
    offset = (page - 1) * page_size
    items = await sync_to_async(list)(qs[offset:offset + page_size])

    return PaginatedAssignments(
        items=[_build_assignment(a) for a in items],
        pagination=PaginationInfo(
            page=page, page_size=page_size, total_items=total,
            total_pages=total_pages, has_next=page < total_pages, has_previous=page > 1,
        ),
    )


@router.post("/assignments/", response_model=AssignmentResponse, status_code=status.HTTP_201_CREATED)
async def create_assignment(
    body: AssignmentCreate,
    ctx: RequestContext = Depends(require_permission('write')),
):
    from media.models import Detection
    from django.contrib.auth import get_user_model
    User = get_user_model()

    def _create():
        detection = Detection.objects.get(id=body.detection_id, tenant=ctx.tenant)
        assigned_to = User.objects.get(id=body.assigned_to_id)
        due = None
        if body.due_date:
            from datetime import date
            due = date.fromisoformat(body.due_date)

        a = Assignment.objects.create(
            tenant=ctx.tenant, detection=detection,
            assigned_to=assigned_to, assigned_by=ctx.user,
            priority=body.priority, due_date=due, notes=body.notes,
        )
        _log_activity(ctx.tenant, ctx.user, 'assigned', 'detection', detection.pk,
                      {'assigned_to': assigned_to.email, 'label': detection.label})
        return a

    try:
        a = await sync_to_async(_create)()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    a = await sync_to_async(
        Assignment.objects.select_related('detection', 'assigned_to', 'assigned_by').get
    )(pk=a.pk)
    return _build_assignment(a)


@router.patch("/assignments/{assignment_id}", response_model=AssignmentResponse)
async def update_assignment(
    assignment_id: int,
    body: AssignmentUpdate,
    ctx: RequestContext = Depends(require_permission('write')),
):
    try:
        a = await sync_to_async(
            Assignment.objects.select_related('detection', 'assigned_to', 'assigned_by').get
        )(id=assignment_id, tenant=ctx.tenant)
    except Assignment.DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found.")

    data = body.model_dump(exclude_unset=True)
    update_fields = ['updated_at']

    if 'status' in data:
        a.status = data['status']
        update_fields.append('status')
        if data['status'] == 'resolved':
            a.resolved_at = timezone.now()
            update_fields.append('resolved_at')

            def _log():
                _log_activity(ctx.tenant, ctx.user, 'resolved', 'detection', a.detection_id,
                              {'label': a.detection.label})
            await sync_to_async(_log)()

    if 'priority' in data:
        a.priority = data['priority']
        update_fields.append('priority')
    if 'notes' in data:
        a.notes = data['notes']
        update_fields.append('notes')

    await sync_to_async(a.save)(update_fields=update_fields)
    return _build_assignment(a)


# ---------------------------------------------------------------------------
# Activity Feed
# ---------------------------------------------------------------------------

@router.get("/activity/", response_model=PaginatedActivity)
async def get_activity(
    ctx: RequestContext = Depends(require_permission('read')),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    action: Optional[str] = None,
):
    qs = ActivityEvent.objects.filter(
        tenant=ctx.tenant,
    ).select_related('user').order_by('-created_at')

    if action:
        qs = qs.filter(action=action)

    total = await sync_to_async(qs.count)()
    total_pages = max(1, (total + page_size - 1) // page_size)
    offset = (page - 1) * page_size
    items = await sync_to_async(list)(qs[offset:offset + page_size])

    return PaginatedActivity(
        items=[_build_activity(e) for e in items],
        pagination=PaginationInfo(
            page=page, page_size=page_size, total_items=total,
            total_pages=total_pages, has_next=page < total_pages, has_previous=page > 1,
        ),
    )


# ---------------------------------------------------------------------------
# Users (for @mention autocomplete)
# ---------------------------------------------------------------------------

@router.get("/users/", response_model=List[UserResponse])
async def list_users(
    ctx: RequestContext = Depends(require_permission('read')),
):
    from tenants.models import TenantMembership
    def _query():
        memberships = TenantMembership.objects.filter(
            tenant=ctx.tenant, is_active=True,
        ).select_related('user')
        return [
            UserResponse(
                id=m.user.id,
                email=m.user.email,
                name=m.user.first_name or None,
            )
            for m in memberships
        ]

    return await sync_to_async(_query)()
