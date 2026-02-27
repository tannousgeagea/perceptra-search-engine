# apps/embeddings/utils/monitoring.py

from embeddings.models import EmbeddingJob
from media.models import Image, Detection
from celery.result import AsyncResult
import logging

logger = logging.getLogger(__name__)


def get_job_status(job_id: str) -> dict:
    """
    Get status of an embedding job.
    
    Args:
        job_id: EmbeddingJob UUID
        
    Returns:
        dict with job status and progress
    """
    try:
        job = EmbeddingJob.objects.get(id=job_id)
        
        return {
            'job_id': str(job.id),  #type: ignore
            'status': job.status,
            'total': job.total_detections,
            'processed': job.processed_detections,
            'failed': job.failed_detections,
            'progress_percent': (job.processed_detections / job.total_detections * 100) if job.total_detections > 0 else 0,
            'started_at': job.started_at.isoformat() if job.started_at else None,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'model_version': job.model_version.name
        }
    except EmbeddingJob.DoesNotExist:
        return {'error': 'Job not found'}


def get_tenant_embedding_stats(tenant_id: str) -> dict:
    """
    Get embedding statistics for a tenant.
    
    Args:
        tenant_id: Tenant UUID
        
    Returns:
        dict with embedding stats
    """
    from tenants.models import Tenant
    
    tenant = Tenant.objects.get(id=tenant_id)
    
    # Image stats
    total_images = Image.objects.filter(tenant=tenant).count()
    embedded_images = Image.objects.filter(tenant=tenant, embedding_generated=True).count()
    
    # Detection stats
    total_detections = Detection.objects.filter(tenant=tenant).count()
    embedded_detections = Detection.objects.filter(tenant=tenant, embedding_generated=True).count()
    
    return {
        'tenant_id': tenant_id,
        'tenant_name': tenant.name,
        'images': {
            'total': total_images,
            'embedded': embedded_images,
            'pending': total_images - embedded_images,
            'percent_complete': (embedded_images / total_images * 100) if total_images > 0 else 0
        },
        'detections': {
            'total': total_detections,
            'embedded': embedded_detections,
            'pending': total_detections - embedded_detections,
            'percent_complete': (embedded_detections / total_detections * 100) if total_detections > 0 else 0
        }
    }