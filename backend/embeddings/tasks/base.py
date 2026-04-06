# apps/embeddings/tasks/base.py

import django
django.setup()
from celery import Task
from embeddings.models import EmbeddingJob, ModelVersion, TenantVectorCollection
from media.models import Image, Detection
from infrastructure.embeddings.generator import get_embedding_generator
from infrastructure.vectordb.manager import VectorDBManager
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class EmbeddingTask(Task):
    """Base task with common functionality for embedding generation."""
    
    autoretry_for = (Exception,)
    retry_kwargs = {'max_retries': 3, 'countdown': 60}  # Retry 3 times, wait 60s between retries
    retry_backoff = True
    retry_backoff_max = 600  # Max 10 minutes between retries
    retry_jitter = True
    
    # Shared resources (lazy loaded)
    _embedding_generator = None
    _cached_model_version_id = None
    _vector_db_clients = {}

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
    
        # Clean up stale connections on failure — the client state after a
        # failed upsert/search is unknown; force reconnect on next task.
        self.cleanup_vector_db_clients()

    def on_success(self, retval, task_id, args, kwargs):
        """Handle task success."""
        logger.info(
            f"Task {self.name} succeeded",
            extra={
                'task_id': task_id,
                'result': retval
            }
        )

    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        """
        Called after on_success or on_failure regardless of outcome.
        Disconnect vector DB clients so connections are not leaked between
        tasks in the same worker process.

        Note: the embedding_generator is intentionally kept alive — model
        weights are expensive to reload and the generator is stateless
        between tasks (no connection to close).
        """
        self.cleanup_vector_db_clients()

    @property
    def embedding_generator(self):
        """Get or create embedding generator, reloading if active model changed."""
        try:
            current_version = get_active_model_version()
            current_id = current_version.id if current_version else None
        except Exception:
            current_id = None

        if (self._embedding_generator is None or
                self._cached_model_version_id != current_id):
            if self._embedding_generator is not None:
                logger.info(f"Active model changed (was {self._cached_model_version_id}, now {current_id}). Reloading.")
                self._embedding_generator.clear_cache()
            self._embedding_generator = get_embedding_generator()
            self._cached_model_version_id = current_id

        return self._embedding_generator

    def get_vector_db_client(self, collection_name: str, dimension: int):
        """
        Get or create vector DB client for collection.
        Caches clients per collection.
        """
        if collection_name not in self._vector_db_clients:
            # Get default DB type from settings
            db_type = getattr(settings, 'DEFAULT_VECTOR_DB', 'qdrant')
            
            # Create client
            client = VectorDBManager.create(
                db_type=db_type,
                collection_name=collection_name,
                dimension=dimension
            )
            
            # Connect
            client.connect()
            
            # Ensure collection exists
            if not client.collection_exists():
                logger.info(f"Creating collection: {collection_name}")
                client.create_collection(dimension=dimension)
            
            self._vector_db_clients[collection_name] = client
            logger.info(f"Vector DB client cached: {collection_name}")
        
        return self._vector_db_clients[collection_name]

    def cleanup_vector_db_clients(self):
        """Cleanup all vector DB clients."""
        for collection_name, client in self._vector_db_clients.items():
            try:
                client.disconnect()
                logger.info(f"Vector DB client disconnected: {collection_name}")
            except Exception as e:
                logger.error(f"Failed to disconnect client {collection_name}: {str(e)}")
        
        self._vector_db_clients.clear()

class DetectionTask(Task):
    """Base task for auto-detection workers.

    Caches the ``DetectionBackendRegistry`` singleton so that
    heavyweight detection models (e.g. SAM3) are loaded only once per
    worker process and reused across tasks.
    """

    autoretry_for = (Exception,)
    retry_kwargs = {'max_retries': 2, 'countdown': 120}
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True

    _detection_registry = None

    @property
    def detection_registry(self):
        """Lazy-load the detection backend registry singleton."""
        if self._detection_registry is None:
            from infrastructure.detections.registry import get_detection_registry
            self._detection_registry = get_detection_registry()
        return self._detection_registry

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(
            f"Detection task {self.name} failed: {exc}",
            extra={'task_id': task_id, 'args': args, 'error': str(exc)},
        )

    def on_success(self, retval, task_id, args, kwargs):
        logger.info(
            f"Detection task {self.name} succeeded",
            extra={'task_id': task_id, 'result': retval},
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
    
def get_or_create_collection(tenant, model_version, purpose='embeddings') -> TenantVectorCollection:
    """Get or create vector collection for tenant, model, and purpose."""
    collection, created = TenantVectorCollection.objects.get_or_create(
        tenant=tenant,
        model_version=model_version,
        purpose=purpose,
        defaults={
            'db_type': getattr(settings, 'DEFAULT_VECTOR_DB', 'qdrant'),
            'is_active': True,
            'is_searchable': True
        }
    )

    if created:
        logger.info(f"Created new collection: {collection.collection_name} (purpose={purpose})")

    return collection