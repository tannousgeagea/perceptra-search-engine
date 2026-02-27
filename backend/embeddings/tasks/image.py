# apps/embeddings/tasks/image.py

from celery import shared_task
from embeddings.tasks.base import EmbeddingTask, get_active_model_version
from media.models import Image, Detection, StatusChoices
from infrastructure.storage.client import get_storage_manager
# from infrastructure.qdrant.client import QdrantClient
import logging
import uuid

logger = logging.getLogger(__name__)


@shared_task(base=EmbeddingTask, name='embeddings.process_image')
def process_image_task(image_id: int):
    """
    Process image: generate embedding and store in vector DB.
    
    Args:
        image_id: Image database ID
        
    Returns:
        dict with status and vector_point_id
    """
    try:
        # Get image
        image = Image.objects.select_related('tenant', 'video').get(id=image_id)
        
        logger.info(f"Processing image {image_id}: {image.filename}")
        
        # Update status
        image.status = StatusChoices.PROCESSING
        image.save(update_fields=['status', 'updated_at'])
        
        # Get active model version
        model_version = get_active_model_version()
        
        # Get storage manager
        storage = get_storage_manager(backend=image.storage_backend)
        
        # TODO: Download image from storage
        # image_bytes = await storage.download(image.storage_key)
        
        # TODO: Generate embedding using ML model
        # from ml.embeddings import EmbeddingGenerator
        # generator = EmbeddingGenerator(model_version=model_version.name)
        # embedding_vector = generator.generate_image_embedding(image_bytes)
        
        # Placeholder embedding (512-dim vector)
        embedding_vector = [0.0] * 512
        
        # Generate unique vector point ID
        vector_point_id = f"img_{image.image_id}"
        
        # Get Qdrant client
        # qdrant = QdrantClient(collection_name=image.tenant.vector_collection_name)
        
        # Prepare payload metadata
        payload = {
            'type': 'image',
            'image_id': image.id,  #type: ignore
            'image_uuid': str(image.image_id),  
            'tenant_id': str(image.tenant.id), #type: ignore
            'filename': image.filename,
            'plant_site': image.plant_site,
            'shift': image.shift,
            'inspection_line': image.inspection_line,
            'captured_at': image.captured_at.isoformat(),
            'width': image.width,
            'height': image.height,
            'storage_key': image.storage_key,
            'storage_backend': image.storage_backend,
            'model_version': model_version.name, #type: ignore
            
            # Video linkage if exists
            'video_id': image.video.id if image.video else None,  #type: ignore
            'video_uuid': str(image.video.video_id) if image.video else None,
            'frame_number': image.frame_number,
            'timestamp_in_video': image.timestamp_in_video,
        }
        
        # TODO: Insert point into Qdrant
        # qdrant.upsert_point(
        #     point_id=vector_point_id,
        #     vector=embedding_vector,
        #     payload=payload
        # )
        
        # Update image record (placeholder - would be done after actual embedding)
        # image.embedding_generated = True
        # image.embedding_model_version = model_version.name
        # image.save(update_fields=['embedding_generated', 'embedding_model_version', 'updated_at'])
        
        # Update status
        image.status = StatusChoices.COMPLETED
        image.save(update_fields=['status', 'updated_at'])
        
        logger.info(f"Image {image_id} embedding generated: {vector_point_id}")
        
        # If image has detections, trigger detection embedding tasks
        detection_ids = list(Detection.objects.filter(image=image).values_list('id', flat=True))
        for detection_id in detection_ids:
            process_detection_task.delay(detection_id)   # type: ignore
        
        return {
            'status': 'success',
            'image_id': image_id,
            'vector_point_id': vector_point_id,
            'detections_triggered': len(detection_ids)
        }
        
    except Image.DoesNotExist:
        logger.error(f"Image {image_id} not found")
        raise
    
    except Exception as e:
        # Mark image as failed
        try:
            image = Image.objects.get(id=image_id)
            image.status = StatusChoices.FAILED
            image.save(update_fields=['status', 'updated_at'])
        except:
            pass
        
        logger.error(f"Failed to process image {image_id}: {str(e)}")
        raise