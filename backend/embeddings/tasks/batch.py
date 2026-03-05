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


@shared_task(base=EmbeddingTask, name='embeddings.batch_process_images')
def batch_process_images_task(tenant_id: str, filter_params: dict = None):   # type: ignore
    """
    Batch process multiple images for embedding generation.
    
    Args:
        tenant_id: Tenant UUID
        filter_params: Optional filters (e.g., {'plant_site': 'Plant_A', 'embedding_generated': False})
        
    Returns:
        dict with job info
    """
    try:
        from tenants.models import Tenant
        tenant = Tenant.objects.get(id=tenant_id)
        
        # Get model version
        model_version = get_active_model_version()
        
        # Build queryset
        queryset = Image.objects.filter(tenant=tenant)
        
        if filter_params:
            queryset = queryset.filter(**filter_params)
        
        # Get image IDs
        image_ids = list(queryset.values_list('id', flat=True))
        total_count = len(image_ids)
        
        logger.info(f"Starting batch image processing: {total_count} images for tenant {tenant.name}")
        
        # Create embedding job record
        job = EmbeddingJob.objects.create(
            tenant=tenant,
            model_version=model_version,
            job_type='images',
            total_items=total_count,  # Reusing field for images
            status='running',
            started_at=timezone.now()
        )
        
        # Create task group
        task_group = group(process_image_task.s(image_id) for image_id in image_ids)    # type: ignore

        # Execute tasks with callback
        callback = finalize_batch_job.s(job_id=str(job.id))
        chord(task_group)(callback)

        # Execute tasks
        result = task_group.apply_async()
        
        logger.info(f"Batch job {job.id} started: {total_count} image tasks queued")   #type: ignore
        
        return {
            'status': 'started',
            'job_id': str(job.id),    #type: ignore
            'total_images': total_count,
            'task_group_id': result.id
        }
        
    except Exception as e:
        logger.error(f"Failed to start batch image processing: {str(e)}")
        raise


@shared_task(base=EmbeddingTask, name='embeddings.batch_process_detections')
def batch_process_detections_task(tenant_id: str, filter_params: dict = None):
    """
    Batch process multiple detections for embedding generation.
    
    Args:
        tenant_id: Tenant UUID
        filter_params: Optional filters
        
    Returns:
        dict with job info
    """
    try:
        from tenants.models import Tenant
        tenant = Tenant.objects.get(id=tenant_id)
        
        # Get model version
        model_version = get_active_model_version()
        
        # Build queryset
        queryset = Detection.objects.filter(tenant=tenant, embedding_generated=False)
        
        if filter_params:
            queryset = queryset.filter(**filter_params)
        
        # Get detection IDs
        detection_ids = list(queryset.values_list('id', flat=True))
        total_count = len(detection_ids)
        
        logger.info(f"Starting batch detection processing: {total_count} detections for tenant {tenant.name}")
        
        # Create embedding job record
        job = EmbeddingJob.objects.create(
            tenant=tenant,
            model_version=model_version,
            job_type='detections',
            total_items=total_count,
            status='running',
            started_at=timezone.now()
        )
        
        # Process in chunks to avoid overwhelming the queue
        chunk_size = 100
        task_groups = []
        
        for i in range(0, len(detection_ids), chunk_size):
            chunk = detection_ids[i:i + chunk_size]
            task_group = group(process_detection_task.s(det_id) for det_id in chunk)
            task_groups.append(task_group)
        
        # Execute chunks with callback
        for task_group in task_groups:
            task_group.apply_async()
        
        # Schedule job finalization
        finalize_batch_job.apply_async(
            args=[None],
            kwargs={'job_id': str(job.id)},
            countdown=60  # Check after 1 minute
        )
        
        logger.info(f"Batch job {job.id} started: {total_count} detection tasks queued")
        
        return {
            'status': 'started',
            'job_id': str(job.id),
            'total_detections': total_count
        }
        
    except Exception as e:
        logger.error(f"Failed to start batch detection processing: {str(e)}")
        raise

@shared_task(name='embeddings.finalize_batch_job')
def finalize_batch_job(results, job_id: str):
    """
    Finalize batch embedding job.
    Called as chord callback.
    
    Args:
        results: Results from task group
        job_id: EmbeddingJob UUID
    """
    try:
        job = EmbeddingJob.objects.get(id=job_id)
        
        # Count successes and failures
        if results:
            successful = sum(1 for r in results if r and r.get('status') == 'success')
            failed = len(results) - successful
        else:
            # If called manually, check database
            if job.job_type == 'images':
                successful = Image.objects.filter(
                    tenant=job.tenant,
                    status='completed'
                ).count()
            else:
                successful = Detection.objects.filter(
                    tenant=job.tenant,
                    embedding_generated=True
                ).count()
            failed = job.total_items - successful
        
        # Update job
        job.processed_items = successful
        job.failed_items = failed
        job.status = 'completed' if failed == 0 else 'completed'
        job.completed_at = timezone.now()
        job.save()
        
        logger.info(
            f"Batch job {job_id} completed: "
            f"{successful} successful, {failed} failed"
        )
        
        return {
            'job_id': job_id,
            'successful': successful,
            'failed': failed
        }
        
    except Exception as e:
        logger.error(f"Failed to finalize batch job {job_id}: {str(e)}")
        raise


@shared_task(base=EmbeddingTask, name='embeddings.reembed_with_new_model')
def reembed_with_new_model_task(tenant_id: str, model_version_id: str, media_type: str = 'all'):
    """
    Re-generate embeddings with a new model version.
    
    Args:
        tenant_id: Tenant UUID
        model_version_id: New model version UUID
        media_type: 'images', 'detections', or 'all'
        
    Returns:
        dict with job info
    """
    try:
        from tenants.models import Tenant
        from embeddings.models import ModelVersion
        
        tenant = Tenant.objects.get(id=tenant_id)
        model_version = ModelVersion.objects.get(id=model_version_id)
        
        logger.info(f"Re-embedding for tenant {tenant.name} with model {model_version.name}")
        
        jobs_started = []
        
        # Process images
        if media_type in ['images', 'all']:
            filter_params = {'embedding_model_version__ne': model_version.name}
            result = batch_process_images_task.delay(tenant_id, filter_params)   #type: ignore
            jobs_started.append({'type': 'images', 'result': result.id})
        
        # Process detections
        if media_type in ['detections', 'all']:
            filter_params = {'embedding_model_version__ne': model_version.name}
            result = batch_process_detections_task.delay(tenant_id, filter_params)  #type: ignore
            jobs_started.append({'type': 'detections', 'result': result.id})
        
        return {
            'status': 'started',
            'tenant_id': tenant_id,
            'model_version': model_version.name,
            'jobs': jobs_started
        }
        
    except Exception as e:
        logger.error(f"Failed to start re-embedding: {str(e)}")
        raise