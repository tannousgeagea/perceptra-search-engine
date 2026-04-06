# =============================================================================
# 1. api/routers/media_ledger.py
#    Query all media in one place regardless of type.
#    Intentionally thin — no joins back to Video/Image/Detection.
#    Filtering, sorting, pagination follow the same pattern as media.py.
# =============================================================================

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Optional, List, Literal
from datetime import datetime
from asgiref.sync import sync_to_async
from django.core.paginator import Paginator
from django.db.models import Q

from tenants.context import RequestContext
from media.models import Media, MediaType, StatusChoices, StorageBackend
from api.dependencies import require_permission
from pydantic import BaseModel, Field
from api.routers.media.schemas import MediaLedgerItem, MediaLedgerListResponse

router = APIRouter(prefix="/media-ledger", tags=["Media Ledger"])


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("/", response_model=MediaLedgerListResponse)
async def list_all_media(
    # Type filter
    media_type: Optional[str] = None,
    # Status filter
    status: Optional[str] = None,
    # Soft-delete filter — default excludes deleted records
    include_deleted: bool = False,
    # Storage filter
    storage_backend: Optional[str] = None,
    # Search by filename
    search: Optional[str] = None,
    # Date range
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    # Sorting
    sort_by: Literal['created_at', 'file_size_bytes', 'filename', 'media_type'] = 'created_at',
    sort_order: Literal['asc', 'desc'] = 'desc',
    # Pagination
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    ctx: RequestContext = Depends(require_permission('read')),
):
    """
    List all media across types (video, image, detection crop) in one request.
    This is a ledger view — it does not join back to Video/Image/Detection.
    Use the /media endpoints for type-specific detail and relationships.
    """
    # Validate enum values early with clear errors
    if media_type and media_type not in MediaType.values:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid media_type '{media_type}'. "
                   f"Valid values: {', '.join(MediaType.values)}",
        )
    if status and status not in StatusChoices.values:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{status}'. "
                   f"Valid values: {', '.join(StatusChoices.values)}",
        )
    if storage_backend and storage_backend not in StorageBackend.values:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid storage_backend '{storage_backend}'. "
                   f"Valid values: {', '.join(StorageBackend.values)}",
        )

    filters_applied = {}

    def build_queryset():
        qs = Media.objects.filter(tenant=ctx.tenant)

        if not include_deleted:
            qs = qs.filter(is_deleted=False)
        else:
            filters_applied['include_deleted'] = True

        if media_type:
            qs = qs.filter(media_type=media_type)
            filters_applied['media_type'] = media_type

        if status:
            qs = qs.filter(status=status)
            filters_applied['status'] = status

        if storage_backend:
            qs = qs.filter(storage_backend=storage_backend)
            filters_applied['storage_backend'] = storage_backend

        if search:
            qs = qs.filter(filename__icontains=search)
            filters_applied['search'] = search

        if date_from:
            qs = qs.filter(created_at__gte=date_from)
            filters_applied['date_from'] = date_from.isoformat()

        if date_to:
            qs = qs.filter(created_at__lte=date_to)
            filters_applied['date_to'] = date_to.isoformat()

        order_field = f"-{sort_by}" if sort_order == 'desc' else sort_by
        qs = qs.order_by(order_field)

        paginator = Paginator(qs, page_size)
        page_obj = paginator.get_page(page)

        pagination = {
            'page': page,
            'page_size': page_size,
            'total_items': paginator.count,
            'total_pages': paginator.num_pages,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
        }

        return list(page_obj.object_list), pagination

    items, pagination = await sync_to_async(build_queryset)()

    return MediaLedgerListResponse(
        items=[
            MediaLedgerItem(
                id=m.id,
                media_id=str(m.media_id),
                media_type=m.media_type,
                storage_backend=m.storage_backend,
                storage_key=m.storage_key,
                filename=m.filename,
                file_size_bytes=m.file_size_bytes,
                file_size_mb=round(m.file_size_mb, 2),
                content_type=m.content_type,
                file_format=m.file_format,
                checksum=m.checksum,
                status=m.status,
                is_deleted=m.is_deleted,
                created_at=m.created_at,
                updated_at=m.updated_at,
            )
            for m in items
        ],
        pagination=pagination,
        filters_applied=filters_applied,
    )


@router.get("/{media_id}", response_model=MediaLedgerItem)
async def get_media_item(
    media_id: str,
    ctx: RequestContext = Depends(require_permission('read')),
):
    """Get a single media ledger entry by its UUID."""
    try:
        m = await Media.objects.aget(media_id=media_id, tenant=ctx.tenant)
    except Media.DoesNotExist:
        raise HTTPException(status_code=404, detail="Media not found")

    return MediaLedgerItem(
        id=m.id,
        media_id=str(m.media_id),
        media_type=m.media_type,
        storage_backend=m.storage_backend,
        storage_key=m.storage_key,
        filename=m.filename,
        file_size_bytes=m.file_size_bytes,
        file_size_mb=round(m.file_size_mb, 2),
        content_type=m.content_type,
        file_format=m.file_format,
        checksum=m.checksum,
        status=m.status,
        is_deleted=m.is_deleted,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )