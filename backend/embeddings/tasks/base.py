# apps/embeddings/tasks/base.py

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
    
    def on_success(self, retval, task_id, args, kwargs):
        """Handle task success."""
        logger.info(
            f"Task {self.name} succeeded",
            extra={
                'task_id': task_id,
                'result': retval
            }
        )

    @property
    def embedding_generator(self):
        """Get or create embedding generator (singleton)."""
        if self._embedding_generator is None:
            self._embedding_generator = get_embedding_generator()
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

def get_active_model_version() -> ModelVersion | None:
    """Get the currently active embedding model version."""
    try:
        return ModelVersion.objects.get(is_active=True)
    except ModelVersion.DoesNotExist:
        raise ValueError("No active embedding model configured")
    except ModelVersion.MultipleObjectsReturned:
        # If multiple active, return the latest
        return ModelVersion.objects.filter(is_active=True).order_by('-created_at').first()
    
def get_or_create_collection(tenant, model_version) -> TenantVectorCollection:
    """Get or create vector collection for tenant and model."""
    collection, created = TenantVectorCollection.objects.get_or_create(
        tenant=tenant,
        model_version=model_version,
        defaults={
            'db_type': getattr(settings, 'DEFAULT_VECTOR_DB', 'qdrant'),
            'is_active': True,
            'is_searchable': True
        }
    )
    
    if created:
        logger.info(f"Created new collection: {collection.collection_name}")
    
    return collection