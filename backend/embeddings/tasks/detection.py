# apps/embeddings/tasks/detection.py

from celery import shared_task
from embeddings.tasks.base import EmbeddingTask, get_active_model_version
from media.models import Detection, Image
from infrastructure.storage.client import get_storage_manager
# from infrastructure.qdrant.client import QdrantClient
import logging

logger = logging.getLogger(__name__)


@shared_task(base=EmbeddingTask, name='embeddings.process_detection')
def process_detection_task(detection_id: int):
    """
    Process detection: crop region, generate embedding, store in vector DB.
    
    Args:
        detection_id: Detection database ID
        
    Returns:
        dict with status and vector_point_id
    """
    try:
        # Get detection with related data
        detection = Detection.objects.select_related(
            'tenant', 'image', 'image__video'
        ).get(id=detection_id)
        
        logger.info(f"Processing detection {detection_id}: {detection.label}")
        
        # Get active model version
        model_version = get_active_model_version()
        
        # Get storage manager
        storage = get_storage_manager(backend=detection.image.storage_backend)
        
        # TODO: Download parent image from storage
        # image_bytes = await storage.download(detection.image.storage_key)
        
        # TODO: Crop detection region
        # from ml.preprocessing import crop_detection_region
        # cropped_bytes = crop_detection_region(
        #     image_bytes,
        #     bbox_x=detection.bbox_x,
        #     bbox_y=detection.bbox_y,
        #     bbox_width=detection.bbox_width,
        #     bbox_height=detection.bbox_height,
        #     bbox_format=detection.bbox_format,
        #     image_width=detection.image.width,
        #     image_height=detection.image.height
        # )
        
        # TODO: Optionally save cropped image
        # if detection.storage_key:
        #     await storage.save(detection.storage_key, cropped_bytes)
        
        # TODO: Generate embedding from cropped region
        # from ml.embeddings import EmbeddingGenerator
        # generator = EmbeddingGenerator(model_version=model_version.name)
        # embedding_vector = generator.generate_image_embedding(cropped_bytes)
        
        # Placeholder embedding (512-dim vector)
        embedding_vector = [0.0] * 512
        
        # Generate unique vector point ID
        vector_point_id = f"det_{detection.detection_id}"
        
        # Get Qdrant client
        # qdrant = QdrantClient(collection_name=detection.tenant.vector_collection_name)
        
        # Prepare payload metadata
        payload = {
            'type': 'detection', 
            'detection_id': detection.id,   #type: ignore
            'detection_uuid': str(detection.detection_id),
            'tenant_id': str(detection.tenant.id), #type: ignore
            
            # Detection metadata
            'label': detection.label,
            'confidence': detection.confidence,
            'bbox_x': detection.bbox_x,
            'bbox_y': detection.bbox_y,
            'bbox_width': detection.bbox_width,
            'bbox_height': detection.bbox_height,
            'bbox_format': detection.bbox_format,
            
            # Image metadata
            'image_id': detection.image.id,   #type: ignore
            'image_uuid': str(detection.image.image_id),
            'image_filename': detection.image.filename,
            'image_storage_key': detection.image.storage_key,
            
            # Context metadata
            'plant_site': detection.image.plant_site,
            'shift': detection.image.shift,
            'inspection_line': detection.image.inspection_line,
            'captured_at': detection.image.captured_at.isoformat(),
            
            # Video linkage if exists
            'video_id': detection.image.video.id if detection.image.video else None,   #type: ignore
            'video_uuid': str(detection.image.video.video_id) if detection.image.video else None,
            'frame_number': detection.image.frame_number,
            'timestamp_in_video': detection.image.timestamp_in_video,
            
            # Model info
            'model_version': model_version.name,   #type: ignore
            
            # Tags
            'tags': list(detection.tags.values_list('name', flat=True))
        }
        
        # TODO: Insert point into Qdrant
        # qdrant.upsert_point(
        #     point_id=vector_point_id,
        #     vector=embedding_vector,
        #     payload=payload
        # )
        
        # Update detection record
        detection.vector_point_id = vector_point_id
        detection.embedding_generated = True
        detection.embedding_model_version = model_version.name   # type: ignore
        detection.save(update_fields=[
            'vector_point_id',
            'embedding_generated', 
            'embedding_model_version',
            'updated_at'
        ])
        
        logger.info(f"Detection {detection_id} embedding generated: {vector_point_id}")
        
        return {
            'status': 'success',
            'detection_id': detection_id,
            'vector_point_id': vector_point_id,
            'label': detection.label
        }
        
    except Detection.DoesNotExist:
        logger.error(f"Detection {detection_id} not found")
        raise
    
    except Exception as e:
        logger.error(f"Failed to process detection {detection_id}: {str(e)}")
        raise