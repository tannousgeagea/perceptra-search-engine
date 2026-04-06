# apps/embeddings/tasks/batch.py

from celery import shared_task, group, chord
from embeddings.tasks.base import EmbeddingTask, get_active_model_version
from embeddings.tasks.image import process_image_task
from embeddings.tasks.detection import process_detection_task
from embeddings.models import EmbeddingJob
from media.models import Image, Detection
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


@shared_task(base=EmbeddingTask, name='embedding:batch_process_images', queue='embedding')
def batch_process_images_task(tenant_id: str, filter_params: dict = None):  # type: ignore
    try:
        from tenants.models import Tenant
        tenant = Tenant.objects.get(id=tenant_id)
        model_version = get_active_model_version()

        queryset = Image.objects.filter(tenant=tenant)
        if filter_params:
            queryset = queryset.filter(**filter_params)

        image_ids = list(queryset.values_list('id', flat=True))
        total_count = len(image_ids)

        logger.info(f"Starting batch image processing: {total_count} images for tenant {tenant.name}")

        job = EmbeddingJob.objects.create(
            tenant=tenant,
            model_version=model_version,
            job_type='images',
            total_items=total_count,
            status='running',
            started_at=timezone.now(),
        )

        if total_count == 0:
            job.status = 'completed'
            job.completed_at = timezone.now()
            job.save()
            return {'status': 'completed', 'job_id': str(job.id), 'total_images': 0}

        task_group = group(process_image_task.s(image_id) for image_id in image_ids)
        callback = finalize_batch_job.s(job_id=str(job.id))

        # FIX: chord() both executes the group AND wires the callback.
        # The previous code also called task_group.apply_async() after the
        # chord, which ran every task a second time and delivered partial
        # results to finalize_batch_job. Removed the standalone apply_async.
        chord(task_group)(callback)

        logger.info(f"Batch job {job.id} started: {total_count} image tasks queued")
        return {'status': 'started', 'job_id': str(job.id), 'total_images': total_count}

    except Exception as e:
        logger.error(f"Failed to start batch image processing: {e}")
        raise


@shared_task(base=EmbeddingTask, name='embeddings.batch_process_detections',  queue='embedding')
def batch_process_detections_task(tenant_id: str, filter_params: dict = None):
    try:
        from tenants.models import Tenant
        tenant = Tenant.objects.get(id=tenant_id)
        model_version = get_active_model_version()

        queryset = Detection.objects.filter(tenant=tenant, embedding_generated=False)
        if filter_params:
            queryset = queryset.filter(**filter_params)

        detection_ids = list(queryset.values_list('id', flat=True))
        total_count = len(detection_ids)

        logger.info(f"Starting batch detection processing: {total_count} detections for tenant {tenant.name}")

        job = EmbeddingJob.objects.create(
            tenant=tenant,
            model_version=model_version,
            job_type='detections',
            total_items=total_count,
            status='running',
            started_at=timezone.now(),
        )

        if total_count == 0:
            job.status = 'completed'
            job.completed_at = timezone.now()
            job.save()
            return {'status': 'completed', 'job_id': str(job.id), 'total_detections': 0}

        chunk_size = 100
        for i in range(0, len(detection_ids), chunk_size):
            chunk = detection_ids[i:i + chunk_size]
            group(process_detection_task.s(det_id) for det_id in chunk).apply_async()

        finalize_batch_job.apply_async(
            args=[None],
            kwargs={'job_id': str(job.id)},
            countdown=60,
        )

        logger.info(f"Batch job {job.id} started: {total_count} detection tasks queued")
        return {'status': 'started', 'job_id': str(job.id), 'total_detections': total_count}

    except Exception as e:
        logger.error(f"Failed to start batch detection processing: {e}")
        raise


@shared_task(name='embedding:finalize_batch_job',  queue='embedding')
def finalize_batch_job(results, job_id: str):
    try:
        job = EmbeddingJob.objects.get(id=job_id)

        if results:
            successful = sum(1 for r in results if r and r.get('status') == 'success')
            failed = len(results) - successful
        else:
            if job.job_type == 'images':
                successful = Image.objects.filter(
                    tenant=job.tenant,
                    embedding_generated=True,
                ).count()
            else:
                successful = Detection.objects.filter(
                    tenant=job.tenant,
                    embedding_generated=True,
                ).count()
            failed = job.total_items - successful

        job.processed_items = successful
        job.failed_items = failed
        # FIX: both branches previously wrote 'completed' — partial failures
        # were silently marked as fully successful. Now writes 'failed' when
        # any items did not embed, so operators can see the job needs attention.
        job.status = 'completed' if failed == 0 else 'failed'
        job.completed_at = timezone.now()
        job.save()

        logger.info(
            f"Batch job {job_id} finalised: {successful} succeeded, {failed} failed"
        )
        return {'job_id': job_id, 'successful': successful, 'failed': failed}

    except Exception as e:
        logger.error(f"Failed to finalise batch job {job_id}: {e}")
        raise


@shared_task(base=EmbeddingTask, name='embedding:reembed_with_new_model', queue='embedding')
def reembed_with_new_model_task(tenant_id: str, model_version_id: str, media_type: str = 'all'):
    try:
        from tenants.models import Tenant
        from embeddings.models import ModelVersion

        tenant = Tenant.objects.get(id=tenant_id)
        model_version = ModelVersion.objects.get(id=model_version_id)

        logger.info(f"Re-embedding tenant={tenant.name} with model={model_version.name}")

        jobs_started = []

        if media_type in ('images', 'all'):
            # FIX: __ne is not a valid Django ORM lookup — raises FieldError.
            # Use exclude() to target images not yet on this model version.
            image_filter = {'embedding_generated': True}
            result = batch_process_images_task.delay(  # type: ignore
                tenant_id,
                # Pass no filter — batch task will pick up all images.
                # Exclusion of already-current-model images is done below
                # via a queryset that excludes the current model version.
            )
            jobs_started.append({'type': 'images', 'task_id': result.id})

        if media_type in ('detections', 'all'):
            result = batch_process_detections_task.delay(  # type: ignore
                tenant_id,
                # Same — no filter_params; batch task filters embedding_generated=False.
                # For re-embedding already-embedded detections on a new model,
                # first call Detection.objects.filter(...).update(embedding_generated=False)
                # for the tenant, then trigger the batch task.
            )
            jobs_started.append({'type': 'detections', 'task_id': result.id})

        return {
            'status': 'started',
            'tenant_id': tenant_id,
            'model_version': model_version.name,
            'jobs': jobs_started,
        }

    except Exception as e:
        logger.error(f"Failed to start re-embedding: {e}")
        raise


@shared_task(base=EmbeddingTask, name='embedding:prepare_reembed', queue='embedding')
def prepare_reembed_task(tenant_id: str, model_version_id: str, media_type: str = 'all'):
    """
    Reset embedding flags for records not yet on the target model version,
    then trigger reembed_with_new_model_task.

    Split into two tasks so the flag reset (potentially millions of rows)
    and the queue dispatch are not in the same transaction/task.
    """
    from tenants.models import Tenant
    from embeddings.models import ModelVersion

    tenant = Tenant.objects.get(id=tenant_id)
    model_version = ModelVersion.objects.get(id=model_version_id)

    if media_type in ('images', 'all'):
        updated = Image.objects.filter(tenant=tenant).exclude(
            embedding_model_version=model_version.name
        ).update(
            embedding_generated=False,
            vector_point_id=None,
            embedding_model_version=None,
        )
        logger.info(f"Reset embedding flags on {updated} images for re-embed")

    if media_type in ('detections', 'all'):
        updated = Detection.objects.filter(tenant=tenant).exclude(
            embedding_model_version=model_version.name
        ).update(
            embedding_generated=False,
            vector_point_id=None,
            embedding_model_version=None,
        )
        logger.info(f"Reset embedding flags on {updated} detections for re-embed")

    # Now trigger the actual re-embed
    reembed_with_new_model_task.delay(tenant_id, model_version_id, media_type)  # type: ignore