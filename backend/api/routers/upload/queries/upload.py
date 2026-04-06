# api/routers/upload.py

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from typing import Annotated, Optional
from datetime import datetime, timezone
from tenants.context import RequestContext
from media.models import (
    Video, 
    Image, 
    Detection, 
    StorageBackend as StorageBackendChoice,
    StatusChoices,
    MediaType
)
from media.ledger import record_media
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
    TagResponse,
)
from django.db.models import F
from django.db import transaction
from embeddings.tasks.image import process_image_task
from embeddings.tasks.video import process_video_task
from embeddings.tasks.detection import process_detection_task

from PIL import Image as PILImage
import hashlib
import io
import numpy as np
from asgiref.sync import sync_to_async
from infrastructure.storage.client import get_storage_manager
from ml.preprocessing import (
    get_image_dimensions,
    validate_image,
    validate_video,
    calculate_checksum,
    get_image_format,
)
import uuid
import json
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["upload"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_storage_key(tenant: Tenant, filename: str, media_type: str = 'images') -> str:
    from django.utils import timezone as tz
    now = tz.now()
    unique_id = str(uuid.uuid4())[:8]
    safe_filename = filename.replace(' ', '_').replace('/', '_')
    return (
        f"org-{tenant.slug}/{media_type}"
        f"/{now.strftime('%Y')}/{now.strftime('%m')}"
        f"/{unique_id}_{safe_filename}"
    )


@sync_to_async
def _find_existing_video(checksum: str, tenant: Tenant) -> Optional[Video]:
    return Video.objects.filter(tenant=tenant, checksum=checksum).first()


@sync_to_async
def _find_existing_image(checksum: str, tenant: Tenant) -> Optional[Image]:
    return Image.objects.filter(tenant=tenant, checksum=checksum).first()


@sync_to_async
def _find_existing_detection(
    image: Image,
    req: DetectionCreateRequest,
    checksum: str,
) -> Optional[Detection]:
    return (
        Detection.objects.filter(
            image=image,
            bbox_x=req.bbox_x,
            bbox_y=req.bbox_y,
            bbox_width=req.bbox_width,
            bbox_height=req.bbox_height,
            bbox_format=req.bbox_format,
            label=req.label,
        ).first()
        or Detection.objects.filter(image=image, checksum=checksum).first()
    )


async def _crop_and_upload(
    req: DetectionCreateRequest,
    image: Image,
    tenant: Tenant,
    created_by,
    raw_bytes: Optional[bytes] = None,
    created_by_api_key = None,
) -> tuple[bytes, str, str]:
    """
    Crop detection region from parent image, upload crop to storage.
    Returns (crop_bytes, checksum, storage_key).
    storage_key is '' if the upload fails — non-fatal, crop can be regenerated.
    """
    if raw_bytes is None:
        storage = get_storage_manager(backend=image.storage_backend)
        raw_bytes = await storage.download(image.storage_key)

    arr = np.array(PILImage.open(io.BytesIO(raw_bytes)).convert('RGB'))

    if req.bbox_format == 'normalized':
        x = int(req.bbox_x * image.width)
        y = int(req.bbox_y * image.height)
        w = int(req.bbox_width * image.width)
        h = int(req.bbox_height * image.height)
    else:
        x, y, w, h = int(req.bbox_x), int(req.bbox_y), int(req.bbox_width), int(req.bbox_height)

    x = max(0, min(x, image.width))
    y = max(0, min(y, image.height))
    w = max(1, min(w, image.width - x))
    h = max(1, min(h, image.height - y))

    buf = io.BytesIO()
    PILImage.fromarray(arr[y:y + h, x:x + w]).save(buf, format='JPEG', quality=95)
    crop_bytes = buf.getvalue()
    checksum = hashlib.sha256(crop_bytes).hexdigest()

    crop_filename = f"{image.image_id}_det_{uuid.uuid4()}.jpg"
    storage_key = _generate_storage_key(tenant, crop_filename, 'detections')

    try:
        storage = get_storage_manager(backend=image.storage_backend)
        await storage.save(
            storage_key=storage_key,
            content=crop_bytes,
            content_type='image/jpeg',
            metadata={
                'image_id': str(image.image_id),
                'label': req.label,
                'confidence': str(req.confidence),
            },
        )

        # Ledger row — crop is now in storage
        await record_media(
            tenant=tenant,
            media_type=MediaType.DETECTION,
            storage_backend=image.storage_backend,
            storage_key=storage_key,
            filename=crop_filename,
            file_size_bytes=len(crop_bytes),
            content_type='image/jpeg',
            file_format='jpg',
            checksum=checksum,
            created_by=created_by,
            created_by_api_key=created_by_api_key,
        )

    except Exception as e:
        logger.error(f"Failed to save detection crop to storage: {e}")
        storage_key = ''

    return crop_bytes, checksum, storage_key


def _validate_backend(backend: str) -> None:
    if backend not in [c.value for c in StorageBackendChoice]:
        raise HTTPException(status_code=400, detail=f"Invalid storage backend: {backend}")

@sync_to_async
def _get_or_create_detection(image, req, checksum, storage_key, tenant, created_by, created_by_api_key):
    """
    Atomic duplicate guard. select_for_update locks the image row so
    concurrent requests with identical detections serialize here rather
    than both passing the existence check and creating two records.
    """
    with transaction.atomic():
        # Lock the parent image row for the duration of this check+create
        Image.objects.select_for_update().get(pk=image.pk)

        existing = (
            Detection.objects.filter(
                image=image,
                bbox_x=req.bbox_x, bbox_y=req.bbox_y,
                bbox_width=req.bbox_width, bbox_height=req.bbox_height,
                bbox_format=req.bbox_format, label=req.label,
            ).first()
            or Detection.objects.filter(image=image, checksum=checksum).first()
        )
        if existing:
            return existing, False   # (instance, created)

        detection = Detection.objects.create(
            tenant=tenant,
            image=image,
            bbox_x=req.bbox_x, bbox_y=req.bbox_y,
            bbox_width=req.bbox_width, bbox_height=req.bbox_height,
            bbox_format=req.bbox_format,
            label=req.label,
            confidence=req.confidence,
            storage_backend=image.storage_backend,
            storage_key=storage_key,
            checksum=checksum,
            embedding_generated=False,
            created_by=created_by,
            updated_by=created_by,
            created_by_api_key=created_by_api_key,
        )
        return detection, True       # (instance, created)


# ---------------------------------------------------------------------------
# Video upload
# ---------------------------------------------------------------------------

@router.post("/video", status_code=status.HTTP_201_CREATED)
async def upload_video(
    file: Annotated[UploadFile, File(...)],
    plant_site: Annotated[str, Form(...)],
    recorded_at: Annotated[str, Form(...)],
    shift: Annotated[Optional[str], Form()] = None,
    inspection_line: Annotated[Optional[str], Form()] = None,
    tags: Annotated[Optional[str], Form()] = None,
    storage_backend: Annotated[Optional[str], Form()] = None,
    ctx: RequestContext = Depends(require_permission('write')),
):
    filename = file.filename or f"video_{uuid.uuid4()}.mp4"

    if not file.content_type or not file.content_type.startswith('video/'):
        raise HTTPException(status_code=400, detail=f"Invalid file type: {file.content_type}")

    file_format = get_image_format(filename)
    if file_format not in ('mp4', 'mov', 'avi', 'webm'):
        raise HTTPException(status_code=400, detail=f"Unsupported format: {file_format}")

    file_bytes = await file.read()
    if len(file_bytes) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds 50 MB limit")

    checksum = calculate_checksum(file_bytes)

    # --- duplicate check: skip embedding, record already exists ---
    existing = await _find_existing_video(checksum, ctx.tenant)
    if existing:
        tags_out = [
            TagResponse(id=t.id, name=t.name, description=t.description, color=t.color)
            for t in await sync_to_async(list)(existing.tags.all())
        ]
        return _video_dict(existing, tags_out, duplicate=True)

    if not await validate_video(file_bytes):
        raise HTTPException(status_code=400, detail="Invalid video file")

    try:
        recorded_dt = datetime.fromisoformat(recorded_at).replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid datetime — use ISO 8601")

    backend = storage_backend or settings.STORAGE_BACKEND
    _validate_backend(backend)

    video_info = VideoProcessor.get_video_info(file_bytes)
    duration_seconds = video_info.get('duration_seconds')

    storage_key = _generate_storage_key(ctx.tenant, filename, 'videos')
    storage = get_storage_manager(backend=backend)
    await storage.save(
        storage_key, file_bytes,
        content_type=file.content_type,
        metadata={
            'filename': filename, 'plant_site': plant_site,
            'shift': shift, 'inspection_line': inspection_line,
            'recorded_at': recorded_dt.isoformat(),
            'tags': tags,
        },
    )

    # Ledger row — file is now in storage
    await record_media(
        tenant=ctx.tenant,
        media_type=MediaType.VIDEO,
        storage_backend=backend,
        storage_key=storage_key,
        filename=filename,
        file_size_bytes=len(file_bytes),
        content_type=file.content_type or 'video/mp4',
        file_format=file_format,
        checksum=checksum,
        created_by=ctx.effective_user,
        created_by_api_key=ctx.effective_api_key,
    )

    tag_list = []
    if tags:
        try:
            tag_data = json.loads(tags)
            if isinstance(tag_data, list):
                tag_list = await get_or_create_tags(tag_data, ctx.tenant, ctx.effective_user)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid tags JSON")

    video = await Video.objects.acreate(
        tenant=ctx.tenant,
        storage_key=storage_key,
        storage_backend=backend,
        filename=filename,
        file_size_bytes=len(file_bytes),
        plant_site=plant_site,
        shift=shift,
        file_format=file_format,
        checksum=checksum,
        duration_seconds=duration_seconds,
        inspection_line=inspection_line,
        recorded_at=recorded_dt,
        status=StatusChoices.UPLOADED,
        created_by=ctx.effective_user,
        updated_by=ctx.effective_user,
        created_by_api_key=ctx.effective_api_key,
    )

    if tag_list:
        await sync_to_async(video.tags.set)(tag_list)

    # Trigger after acreate + tags.set — worker is guaranteed to see a fully
    # committed, tagged record. process_video_task owns the full pipeline:
    # frame extraction → process_image_task per frame → process_detection_task
    # per detection. One dispatch point, one pipeline entry.
    process_video_task.delay(video.pk)  # type: ignore
    logger.info(f"Queued process_video_task for video pk={video.pk}")

    await video.arefresh_from_db()
    tags_out = [
        TagResponse(id=t.id, name=t.name, description=t.description, color=t.color)
        for t in await sync_to_async(list)(video.tags.all())
    ]
    return _video_dict(video, tags_out, duplicate=False)


# ---------------------------------------------------------------------------
# Image upload
# ---------------------------------------------------------------------------

@router.post("/image", status_code=status.HTTP_201_CREATED)
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
    ctx: RequestContext = Depends(require_permission('write')),
):
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")

    filename = file.filename or f"image_{uuid.uuid4()}.jpg"

    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail=f"Invalid file type: {file.content_type}")

    file_format = get_image_format(filename)
    if file_format not in ('jpg', 'jpeg', 'png', 'tiff', 'tif', 'bmp', 'webp'):
        raise HTTPException(status_code=400, detail=f"Unsupported format: {file_format}")

    file_bytes = await file.read()
    if len(file_bytes) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds 50 MB limit")

    if not await validate_image(file_bytes):
        raise HTTPException(status_code=400, detail="Invalid image file")

    width, height = await get_image_dimensions(file_bytes)
    checksum = calculate_checksum(file_bytes)

    try:
        captured_dt = datetime.fromisoformat(captured_at).replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid datetime — use ISO 8601")

    # --- duplicate check: skip embedding, record already exists ---
    existing = await _find_existing_image(checksum, ctx.tenant)
    if existing:
        tags_out = [
            TagResponse(id=t.id, name=t.name, description=t.description, color=t.color)
            for t in await sync_to_async(list)(existing.tags.all())
        ]
        return _image_dict(existing, tags_out, duplicate=True)

    video = None
    if video_id:
        try:
            video = await Video.objects.aget(id=video_id, tenant=ctx.tenant)
        except Video.DoesNotExist:
            raise HTTPException(status_code=404, detail=f"Video {video_id} not found")

    backend = storage_backend or settings.STORAGE_BACKEND
    _validate_backend(backend)

    storage_key = _generate_storage_key(ctx.tenant, filename, 'images')
    storage = get_storage_manager(backend=backend)
    await storage.save(
        storage_key, file_bytes,
        content_type=file.content_type,
        metadata={
            'filename': filename, 'plant_site': plant_site,
            'shift': shift, 'inspection_line': inspection_line,
            'captured_at': captured_dt.isoformat(),
            'tags': tags,
        },
    )

    # Ledger row — file is now in storage
    await record_media(
        tenant=ctx.tenant,
        media_type=MediaType.IMAGE,
        storage_backend=backend,
        storage_key=storage_key,
        filename=filename,
        file_size_bytes=len(file_bytes),
        content_type=file.content_type or 'image/jpeg',
        file_format=file_format,
        checksum=checksum,
        created_by=ctx.effective_user,
        created_by_api_key=ctx.effective_api_key,
    )

    tag_list = []
    if tags:
        try:
            tag_data = json.loads(tags)
            if isinstance(tag_data, list):
                tag_list = await get_or_create_tags(tag_data, ctx.tenant, ctx.effective_user)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid tags JSON")

    image = await Image.objects.acreate(
        tenant=ctx.tenant,
        video=video,
        storage_key=storage_key,
        storage_backend=backend,
        filename=filename,
        file_size_bytes=len(file_bytes),
        width=width,
        height=height,
        file_format=file_format,
        frame_number=frame_number,
        plant_site=plant_site,
        shift=shift,
        inspection_line=inspection_line,
        captured_at=captured_dt,
        checksum=checksum,
        status=StatusChoices.UPLOADED,
        created_by=ctx.effective_user,
        updated_by=ctx.effective_user,
        created_by_api_key=ctx.effective_api_key,
    )

    if tag_list:
        await sync_to_async(image.tags.set)(tag_list)

    # Trigger after acreate + tags.set. process_image_task also triggers
    # process_detection_task for any detections already on this image,
    # so standalone image uploads that have pre-existing detections are covered.
    process_image_task.delay(image.pk)  # type: ignore
    logger.info(f"Queued process_image_task for image pk={image.pk}")

    await image.arefresh_from_db()
    tags_out = [
        TagResponse(id=t.id, name=t.name, description=t.description, color=t.color)
        for t in await sync_to_async(list)(image.tags.all())
    ]
    return _image_dict(image, tags_out, duplicate=False, video=video)


# ---------------------------------------------------------------------------
# Single detection
# ---------------------------------------------------------------------------

@router.post("/detection", response_model=DetectionResponse, status_code=status.HTTP_201_CREATED)
async def create_detection(
    request: DetectionCreateRequest,
    ctx: RequestContext = Depends(require_permission('write')),
):
    try:
        image = await Image.objects.aget(id=request.image_id, tenant=ctx.tenant)
    except Image.DoesNotExist:
        raise HTTPException(status_code=404, detail=f"Image {request.image_id} not found")

    if request.bbox_format == 'normalized':
        if not (0 <= request.bbox_x <= 1 and 0 <= request.bbox_y <= 1):
            raise HTTPException(status_code=400, detail="Normalized bbox x/y must be in [0, 1]")
        if not (0 < request.bbox_width <= 1 and 0 < request.bbox_height <= 1):
            raise HTTPException(status_code=400, detail="Normalized bbox dimensions must be in (0, 1]")

    _, checksum, storage_key = await _crop_and_upload(request, image, ctx.tenant, ctx.effective_user, created_by_api_key=ctx.effective_api_key,)

    existing = await _find_existing_detection(image, request, checksum)
    if existing:
        # Already exists — if already embedded, do not re-queue.
        # If not yet embedded (e.g. previous task failed), re-queue so it
        # gets another attempt rather than silently staying unembedded.
        if not existing.embedding_generated:
            process_detection_task.delay(existing.pk)  # type: ignore
            logger.info(f"Re-queued process_detection_task for existing detection pk={existing.pk}")
        tags_out = await sync_to_async(list)(existing.tags.all())
        return _detection_response(existing, image, tags_out)

    tag_list = []
    if request.tags:
        tag_list = await get_or_create_tags(
            [t.model_dump() for t in request.tags], ctx.tenant, ctx.effective_user
        )

    detection, created = await _get_or_create_detection(
        image, request, checksum, storage_key,
        ctx.tenant, ctx.effective_user, ctx.effective_api_key
    )

    if created:
        # Increment detection_count on Image atomically.
        # Also propagate to the parent Video if this image is a frame.
        await sync_to_async(
            Image.objects.filter(pk=image.pk).update
        )(detection_count=F('detection_count') + 1)

        if image.video_id:
            await sync_to_async(
                Video.objects.filter(pk=image.video_id).update
            )(detection_count=F('detection_count') + 1)


    if not created:
        if not detection.embedding_generated:
            process_detection_task.delay(detection.pk)  # type: ignore
        tags_out = await sync_to_async(list)(detection.tags.all())
        return _detection_response(detection, image, tags_out)
    
    if tag_list:
        await sync_to_async(detection.tags.set)(tag_list)

    # Trigger after acreate + tags.set.
    process_detection_task.delay(detection.pk)  # type: ignore
    logger.info(f"Queued process_detection_task for detection pk={detection.pk}")

    await detection.arefresh_from_db()
    tags_out = await sync_to_async(list)(detection.tags.all())
    return _detection_response(detection, image, tags_out)


# ---------------------------------------------------------------------------
# Bulk detections
# ---------------------------------------------------------------------------

@router.post("/detections/bulk", response_model=BulkDetectionResponse, status_code=status.HTTP_201_CREATED)
async def create_detections_bulk(
    request: BulkDetectionCreateRequest,
    ctx: RequestContext = Depends(require_permission('write')),
):
    created_ids: list[int] = []
    skipped_ids: list[int] = []
    errors: list[str] = []

    image_ids = list({d.image_id for d in request.detections})
    images = await sync_to_async(list)(
        Image.objects.filter(id__in=image_ids, tenant=ctx.tenant)
    )
    image_map = {img.pk: img for img in images}

    missing = [d.image_id for d in request.detections if d.image_id not in image_map]
    if missing:
        raise HTTPException(
            status_code=400,
            detail={"errors": [f"Image {i} not found" for i in missing]},
        )

    # Cache raw image bytes per image_id — avoids re-downloading the same
    # image for every detection that references it.
    raw_cache: dict[int, bytes] = {}
    created_per_image: dict[int, int] = {}

    for det_req in request.detections:
        image = image_map[det_req.image_id]
        try:
            if det_req.image_id not in raw_cache:
                storage = get_storage_manager(backend=image.storage_backend)
                raw_cache[det_req.image_id] = await storage.download(image.storage_key)

            _, checksum, storage_key = await _crop_and_upload(
                det_req, image, ctx.tenant, ctx.effective_user, raw_bytes=raw_cache[det_req.image_id], created_by_api_key=ctx.effective_api_key,
            )
        except Exception as e:
            errors.append(f"Image {det_req.image_id}: crop failed — {e}")
            continue

        existing = await _find_existing_detection(image, det_req, checksum)
        if existing:
            if not existing.embedding_generated:
                process_detection_task.delay(existing.pk)  # type: ignore
            skipped_ids.append(existing.pk)
            continue

        tag_list = []
        if det_req.tags:
            tag_list = await get_or_create_tags(
                [t.model_dump() for t in det_req.tags], ctx.tenant, ctx.effective_user
            )

        try:
            detection, created = await _get_or_create_detection(
                image, request, checksum, storage_key,
                ctx.tenant, ctx.effective_user, ctx.effective_api_key
            )

            if created:
                created_per_image[det_req.image_id] = (
                    created_per_image.get(det_req.image_id, 0) + 1
                )

            if not created:
                if not detection.embedding_generated:
                    process_detection_task.delay(detection.pk)  # type: ignore
                tags_out = await sync_to_async(list)(detection.tags.all())
                return _detection_response(detection, image, tags_out)

            if tag_list:
                await sync_to_async(detection.tags.set)(tag_list)

            # Trigger after acreate + tags.set.
            process_detection_task.delay(detection.pk)  # type: ignore
            logger.info(f"Queued process_detection_task for detection pk={detection.pk}")

            created_ids.append(detection.pk)
        except Exception as e:
            errors.append(f"Image {det_req.image_id}: DB create failed — {e}")

    # Batch-update Image.detection_count — one UPDATE per unique image
    # rather than one per detection.
    if created_per_image:
        for img_id, count in created_per_image.items():
            await sync_to_async(
                Image.objects.filter(pk=img_id).update
            )(detection_count=F('detection_count') + count)

        # Propagate to parent videos — load video_id for affected images once
        affected_images = await sync_to_async(list)(
            Image.objects.filter(pk__in=created_per_image.keys())
            .exclude(video_id=None)
            .values('video_id', 'pk')
        )
        video_counts: dict[int, int] = {}
        for row in affected_images:
            video_counts[row['video_id']] = (
                video_counts.get(row['video_id'], 0)
                + created_per_image[row['pk']]
            )
        for vid_id, count in video_counts.items():
            await sync_to_async(
                Video.objects.filter(pk=vid_id).update
            )(detection_count=F('detection_count') + count)

    return BulkDetectionResponse(
        total=len(request.detections),
        created=len(created_ids),
        skipped=len(skipped_ids),
        failed=len(errors),
        detection_ids=created_ids,
        skipped_ids=skipped_ids,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------

def _detection_response(detection: Detection, image: Image, tags: list) -> DetectionResponse:
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
        storage_key=detection.storage_key or None,
        storage_backend=detection.storage_backend,
        checksum=detection.checksum,
        embedding_generated=detection.embedding_generated,
        tags=[
            TagResponse(id=t.id, name=t.name, description=t.description, color=t.color)
            for t in tags
        ],
        created_at=detection.created_at,
    )


def _video_dict(video: Video, tags: list, *, duplicate: bool) -> dict:
    return {
        "message": "Video already exists" if duplicate else "Video uploaded successfully",
        "id": str(video.pk),
        "video_id": str(video.video_id),
        "filename": video.filename,
        "storage_key": video.storage_key,
        "file_size_bytes": video.file_size_bytes,
        "file_size_mb": round(video.file_size_mb, 2),
        "format": video.file_format,
        "checksum": video.checksum,
        "download_url": video.get_download_url(),
        "created_at": video.created_at.isoformat(),
        "plant_site": video.plant_site,
        "shift": video.shift,
        "inspection_line": video.inspection_line,
        "status": video.status,
        "duration_seconds": video.duration_seconds,
        "recorded_at": video.recorded_at.isoformat(),
        "duplicate": duplicate,
        "tags": tags,
    }


def _image_dict(
    image: Image,
    tags: list,
    *,
    duplicate: bool,
    video: Optional[Video] = None,
) -> dict:
    return {
        "message": "Image already exists" if duplicate else "Image uploaded successfully",
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
        "duplicate": duplicate,
        "tags": tags,
    }