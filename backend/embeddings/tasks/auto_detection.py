# apps/embeddings/tasks/auto_detection.py

"""
Celery task for automatic hazard detection using SAM3 / perceptra-seg.

Triggered after ``process_image_task`` completes embedding for an image.
Runs on the dedicated ``detection`` queue with its own worker process
(concurrency=1, CPU by default on single-GPU deployments).

Flow:
    1. Load Image + tenant's active TenantHazardConfig
    2. Create a DetectionJob record
    3. Download image from storage
    4. Run detection backend (model cached in worker)
    5. For each detection: crop, save to storage, create Detection record
    6. Detection.post_save signal triggers process_detection_task (embedding)
"""

import hashlib
import io
import logging
import time
import uuid
from datetime import datetime

from django.db import IntegrityError

import numpy as np
from celery import shared_task
from django.conf import settings
from django.db.models import F
from django.utils import timezone
from PIL import Image as PILImage

from embeddings.models import (
    DetectionJob,
    DetectionJobStatus,
    TenantHazardConfig,
)
from embeddings.tasks.base import DetectionTask
from infrastructure.storage.client import get_storage_manager
from media.models import Detection, Image, Video

logger = logging.getLogger(__name__)


def _generate_storage_key(tenant, filename: str, media_type: str = 'detections') -> str:
    """Build a storage key following the existing convention.

    Pattern: ``org-{slug}/{media_type}/{year}/{month}/{filename}``
    """
    now = timezone.now()
    slug = tenant.slug if hasattr(tenant, 'slug') else str(tenant.tenant_id).replace('-', '')[:12]
    return f"org-{slug}/{media_type}/{now.year}/{now.month:02d}/{filename}"


def _bbox_overlaps(a, b, tolerance: float = 0.05) -> bool:
    """Check whether two normalised bboxes (x, y, w, h) overlap significantly.

    Used for deduplication — if a detection with the same label already
    exists at roughly the same location, skip creating a duplicate.
    """
    return (
        abs(a[0] - b[0]) < tolerance
        and abs(a[1] - b[1]) < tolerance
        and abs(a[2] - b[2]) < tolerance
        and abs(a[3] - b[3]) < tolerance
    )


@shared_task(
    base=DetectionTask,
    name='detection:auto_detect_image',
    queue='detection',
    soft_time_limit=300,   # 5 min soft
    time_limit=600,        # 10 min hard
)
def auto_detect_image_task(image_id: int, hazard_config_id: int = None):
    """Run automatic hazard detection on an image.

    Args:
        image_id: Primary key of the ``Image`` to analyse.
        hazard_config_id: Optional specific ``TenantHazardConfig.id``.
            If ``None``, the tenant's default active config is used.

    Returns:
        dict with status, number of detections created, and job ID.
    """
    job = None

    try:
        # ── 1. Load image ────────────────────────────────────────
        image = Image.objects.select_related('tenant', 'video').get(id=image_id)
        tenant = image.tenant
        logger.info(f"Auto-detection starting for image {image_id}: {image.filename}")

        # ── 2. Resolve hazard config ─────────────────────────────
        if hazard_config_id:
            config = TenantHazardConfig.objects.get(
                id=hazard_config_id,
                tenant=tenant,
                is_active=True,
            )
        else:
            config = TenantHazardConfig.objects.filter(
                tenant=tenant,
                is_active=True,
                is_default=True,
            ).first()

            # Fallback: any active config for this tenant
            if config is None:
                config = TenantHazardConfig.objects.filter(
                    tenant=tenant,
                    is_active=True,
                ).first()

        if config is None:
            logger.info(f"No active hazard config for tenant {tenant.name} — skipping")
            return {'status': 'skipped', 'reason': 'no_hazard_config', 'image_id': image_id}

        # ── 3. Create detection job ──────────────────────────────
        job = DetectionJob.objects.create(
            tenant=tenant,
            image=image,
            hazard_config=config,
            detection_backend=config.detection_backend,
            status=DetectionJobStatus.RUNNING,
            started_at=timezone.now(),
        )

        # ── 4. Download image ────────────────────────────────────
        storage = get_storage_manager(backend=image.storage_backend)
        image_bytes = storage.download_sync(image.storage_key)
        pil_image = PILImage.open(io.BytesIO(image_bytes)).convert('RGB')
        img_arr = np.array(pil_image)

        # ── 5. Run detection ─────────────────────────────────────
        detection_device = getattr(settings, 'DETECTION_DEVICE', 'cpu')
        registry = auto_detect_image_task.detection_registry  # type: ignore
        backend = registry.get_backend(
            backend_name=config.detection_backend,
            device=detection_device,
        )

        t0 = time.time()
        results = backend.detect(
            image=pil_image,
            prompts=config.prompts,
            confidence_threshold=config.confidence_threshold,
        )
        inference_ms = (time.time() - t0) * 1000
        logger.info(
            f"Detection completed in {inference_ms:.1f}ms — "
            f"{len(results)} detections for image {image_id}"
        )

        # ── 6. Fetch existing detections for dedup ───────────────
        existing_dets = list(
            Detection.objects.filter(image=image).values_list(
                'label', 'bbox_x', 'bbox_y', 'bbox_width', 'bbox_height',
            )
        )

        # ── 7. Create Detection records ──────────────────────────
        created_ids = []

        for det in results:
            # Dedup: skip if a detection with the same label and
            # overlapping bbox already exists for this image.
            is_duplicate = any(
                ex[0] == det.label
                and _bbox_overlaps(
                    (det.bbox_x, det.bbox_y, det.bbox_width, det.bbox_height),
                    (ex[1], ex[2], ex[3], ex[4]),
                )
                for ex in existing_dets
            )
            if is_duplicate:
                logger.debug(f"Skipping duplicate detection: {det.label} at ({det.bbox_x:.3f}, {det.bbox_y:.3f})")
                continue

            # Crop region
            x, y, w, h = det.to_absolute(image.width, image.height)
            x, y = max(0, x), max(0, y)
            w = max(1, min(w, image.width - x))
            h = max(1, min(h, image.height - y))

            crop = PILImage.fromarray(img_arr[y:y + h, x:x + w])
            buf = io.BytesIO()
            crop.save(buf, format='JPEG', quality=95)
            crop_bytes = buf.getvalue()
            checksum = hashlib.sha256(crop_bytes).hexdigest()

            crop_filename = f"{image.image_id}_autodet_{uuid.uuid4().hex[:12]}.jpg"
            storage_key = _generate_storage_key(tenant, crop_filename, 'detections')

            storage.upload_sync(storage_key, crop_bytes, content_type='image/jpeg')

            # Create Detection record.
            # The post_save signal in embeddings/signals.py will
            # automatically dispatch process_detection_task on the
            # embedding queue.
            detection = Detection(
                tenant=tenant,
                image=image,
                bbox_x=det.bbox_x,
                bbox_y=det.bbox_y,
                bbox_width=det.bbox_width,
                bbox_height=det.bbox_height,
                bbox_format='normalized',
                label=det.label,
                confidence=det.confidence,
                storage_backend=image.storage_backend,
                storage_key=storage_key,
                checksum=checksum,
                source='auto',
                detection_job=job,
            )
            try:
                detection.save()
                created_ids.append(detection.pk)
            except IntegrityError:
                logger.debug(f"Skipping duplicate detection: {det.label} (checksum match)")
                continue

            # Track for dedup within this batch
            existing_dets.append(
                (det.label, det.bbox_x, det.bbox_y, det.bbox_width, det.bbox_height)
            )

        # ── 8. Update job status ─────────────────────────────────
        job.total_detections = len(created_ids)
        job.status = DetectionJobStatus.COMPLETED
        job.completed_at = timezone.now()
        job.inference_time_ms = inference_ms
        job.save(update_fields=[
            'total_detections', 'status', 'completed_at',
            'inference_time_ms', 'updated_at',
        ])

        # ── 9. Update counters atomically ────────────────────────
        if created_ids:
            Image.objects.filter(pk=image.pk).update(
                detection_count=F('detection_count') + len(created_ids),
            )
            if image.video_id:
                Video.objects.filter(pk=image.video_id).update(
                    detection_count=F('detection_count') + len(created_ids),
                )

        logger.info(
            f"Auto-detection complete for image {image_id}: "
            f"{len(created_ids)} detections created (job {job.detection_job_id})"
        )

        return {
            'status': 'success',
            'image_id': image_id,
            'detection_job_id': str(job.detection_job_id),
            'detections_created': len(created_ids),
            'detections_skipped_dedup': len(results) - len(created_ids),
            'inference_time_ms': inference_ms,
        }

    except TenantHazardConfig.DoesNotExist:
        logger.warning(f"Hazard config {hazard_config_id} not found or inactive")
        if job:
            job.status = DetectionJobStatus.SKIPPED
            job.error_message = f"Hazard config {hazard_config_id} not found or inactive"
            job.completed_at = timezone.now()
            job.save(update_fields=['status', 'error_message', 'completed_at', 'updated_at'])
        return {'status': 'skipped', 'reason': 'config_not_found', 'image_id': image_id}

    except Image.DoesNotExist:
        logger.error(f"Image {image_id} not found")
        raise

    except Exception as e:
        logger.error(f"Auto-detection failed for image {image_id}: {e}")
        if job:
            job.status = DetectionJobStatus.FAILED
            job.error_message = str(e)[:2000]
            job.completed_at = timezone.now()
            job.save(update_fields=['status', 'error_message', 'completed_at', 'updated_at'])
        raise
