# api/routers/media/queries/bulk.py

"""Bulk operations for media items (delete, tag)."""

from fastapi import APIRouter, Depends, HTTPException, status
from asgiref.sync import sync_to_async
from django.db import transaction

from tenants.context import RequestContext
from api.dependencies import require_permission
from media.models import Image, Video, Detection, Tag, ImageTag, VideoTag, DetectionTag
from infrastructure.storage.client import get_storage_manager
from api.routers.media.schemas import (
    BulkDeleteRequest, BulkDeleteResponse,
    BulkTagRequest, BulkTagResponse,
)

import logging

router = APIRouter(prefix="/media", tags=["Media Library - Bulk"])
logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────

def _get_or_create_tags(tenant, tag_names):
    """Get or create Tag objects for the given names, scoped to tenant."""
    tags = []
    for name in tag_names:
        tag, _ = Tag.objects.get_or_create(
            tenant=tenant,
            name=name.strip(),
            defaults={'color': '#3B82F6'},
        )
        tags.append(tag)
    return tags


def _bulk_delete_storage(items, backend_field='storage_backend', key_field='storage_key'):
    """Delete storage files for a list of model instances. Logs failures but doesn't raise."""
    for item in items:
        backend = getattr(item, backend_field, None)
        key = getattr(item, key_field, None)
        if not backend or not key:
            continue
        try:
            storage = get_storage_manager(backend=backend)
            storage.delete_sync(key)
        except Exception as e:
            logger.warning(f"Failed to delete storage file {key}: {e}")


# ── Bulk Delete ───────────────────────────────────────────────

@router.post("/images/bulk-delete", response_model=BulkDeleteResponse)
async def bulk_delete_images(
    body: BulkDeleteRequest,
    ctx: RequestContext = Depends(require_permission('write')),
):
    """Delete multiple images and their associated detections."""
    images = await sync_to_async(list)(
        Image.objects.filter(id__in=body.ids, tenant=ctx.tenant)
    )

    if not images:
        return BulkDeleteResponse(deleted=0)

    # Delete storage files (best-effort, outside transaction)
    await sync_to_async(_bulk_delete_storage)(images)

    # Delete from DB (cascades to detections, embeddings)
    deleted_count = len(images)
    await sync_to_async(
        Image.objects.filter(id__in=[img.id for img in images]).delete
    )()

    logger.info(f"Bulk deleted {deleted_count} images for tenant {ctx.tenant.name}")
    return BulkDeleteResponse(deleted=deleted_count)


@router.post("/videos/bulk-delete", response_model=BulkDeleteResponse)
async def bulk_delete_videos(
    body: BulkDeleteRequest,
    ctx: RequestContext = Depends(require_permission('write')),
):
    """Delete multiple videos and their associated frames/detections."""
    videos = await sync_to_async(list)(
        Video.objects.filter(id__in=body.ids, tenant=ctx.tenant)
    )

    if not videos:
        return BulkDeleteResponse(deleted=0)

    await sync_to_async(_bulk_delete_storage)(videos)

    deleted_count = len(videos)
    await sync_to_async(
        Video.objects.filter(id__in=[v.id for v in videos]).delete
    )()

    logger.info(f"Bulk deleted {deleted_count} videos for tenant {ctx.tenant.name}")
    return BulkDeleteResponse(deleted=deleted_count)


@router.post("/detections/bulk-delete", response_model=BulkDeleteResponse)
async def bulk_delete_detections(
    body: BulkDeleteRequest,
    ctx: RequestContext = Depends(require_permission('write')),
):
    """Delete multiple detections."""
    detections = await sync_to_async(list)(
        Detection.objects.filter(id__in=body.ids, tenant=ctx.tenant)
    )

    if not detections:
        return BulkDeleteResponse(deleted=0)

    await sync_to_async(_bulk_delete_storage)(detections)

    deleted_count = len(detections)
    await sync_to_async(
        Detection.objects.filter(id__in=[d.id for d in detections]).delete
    )()

    logger.info(f"Bulk deleted {deleted_count} detections for tenant {ctx.tenant.name}")
    return BulkDeleteResponse(deleted=deleted_count)


# ── Bulk Tag ──────────────────────────────────────────────────

@router.post("/images/bulk-tag", response_model=BulkTagResponse)
async def bulk_tag_images(
    body: BulkTagRequest,
    ctx: RequestContext = Depends(require_permission('write')),
):
    """Add or remove tags on multiple images."""
    images = await sync_to_async(list)(
        Image.objects.filter(id__in=body.ids, tenant=ctx.tenant)
    )
    if not images:
        return BulkTagResponse(updated=0, tags=body.tag_names)

    tags = await sync_to_async(_get_or_create_tags)(ctx.tenant, body.tag_names)

    def _apply():
        with transaction.atomic():
            for image in images:
                if body.action == 'add':
                    for tag in tags:
                        ImageTag.objects.get_or_create(image=image, tag=tag)
                else:
                    ImageTag.objects.filter(image=image, tag__in=tags).delete()

    await sync_to_async(_apply)()

    logger.info(f"Bulk {body.action} tags {body.tag_names} on {len(images)} images")
    return BulkTagResponse(updated=len(images), tags=body.tag_names)


@router.post("/videos/bulk-tag", response_model=BulkTagResponse)
async def bulk_tag_videos(
    body: BulkTagRequest,
    ctx: RequestContext = Depends(require_permission('write')),
):
    """Add or remove tags on multiple videos."""
    videos = await sync_to_async(list)(
        Video.objects.filter(id__in=body.ids, tenant=ctx.tenant)
    )
    if not videos:
        return BulkTagResponse(updated=0, tags=body.tag_names)

    tags = await sync_to_async(_get_or_create_tags)(ctx.tenant, body.tag_names)

    def _apply():
        with transaction.atomic():
            for video in videos:
                if body.action == 'add':
                    for tag in tags:
                        VideoTag.objects.get_or_create(video=video, tag=tag)
                else:
                    VideoTag.objects.filter(video=video, tag__in=tags).delete()

    await sync_to_async(_apply)()

    logger.info(f"Bulk {body.action} tags {body.tag_names} on {len(videos)} videos")
    return BulkTagResponse(updated=len(videos), tags=body.tag_names)


@router.post("/detections/bulk-tag", response_model=BulkTagResponse)
async def bulk_tag_detections(
    body: BulkTagRequest,
    ctx: RequestContext = Depends(require_permission('write')),
):
    """Add or remove tags on multiple detections."""
    detections = await sync_to_async(list)(
        Detection.objects.filter(id__in=body.ids, tenant=ctx.tenant)
    )
    if not detections:
        return BulkTagResponse(updated=0, tags=body.tag_names)

    tags = await sync_to_async(_get_or_create_tags)(ctx.tenant, body.tag_names)

    def _apply():
        with transaction.atomic():
            for detection in detections:
                if body.action == 'add':
                    for tag in tags:
                        DetectionTag.objects.get_or_create(detection=detection, tag=tag)
                else:
                    DetectionTag.objects.filter(detection=detection, tag__in=tags).delete()

    await sync_to_async(_apply)()

    logger.info(f"Bulk {body.action} tags {body.tag_names} on {len(detections)} detections")
    return BulkTagResponse(updated=len(detections), tags=body.tag_names)
