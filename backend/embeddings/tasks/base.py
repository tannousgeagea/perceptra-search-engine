# apps/embeddings/tasks/base.py

from celery import Task
from embeddings.models import EmbeddingJob, ModelVersion
from media.models import Image, Detection
import logging

logger = logging.getLogger(__name__)


class EmbeddingTask(Task):
    """Base task with common functionality for embedding generation."""
    
    autoretry_for = (Exception,)
    retry_kwargs = {'max_retries': 3, 'countdown': 60}  # Retry 3 times, wait 60s between retries
    retry_backoff = True
    retry_backoff_max = 600  # Max 10 minutes between retries
    retry_jitter = True
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        logger.error(
            f"Task {self.name} failed: {exc}",
            extra={
                'task_id': task_id,
                'args': args,
                'kwargs': kwargs,
                'error': str(exc)
            }
        )
    
    def on_success(self, retval, task_id, args, kwargs):
        """Handle task success."""
        logger.info(
            f"Task {self.name} succeeded",
            extra={
                'task_id': task_id,
                'result': retval
            }
        )


def get_active_model_version() -> ModelVersion | None:
    """Get the currently active embedding model version."""
    try:
        return ModelVersion.objects.get(is_active=True)
    except ModelVersion.DoesNotExist:
        raise ValueError("No active embedding model configured")
    except ModelVersion.MultipleObjectsReturned:
        # If multiple active, return the latest
        return ModelVersion.objects.filter(is_active=True).order_by('-created_at').first()