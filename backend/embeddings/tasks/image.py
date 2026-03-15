# apps/embeddings/tasks/image.py

from celery import shared_task
from embeddings.tasks.base import EmbeddingTask, get_active_model_version, get_or_create_collection
from media.models import Image, Detection, StatusChoices
from infrastructure.storage.client import get_storage_manager
from infrastructure.vectordb.base import VectorPoint
from django.conf import settings
import logging
import time
import uuid

logger = logging.getLogger(__name__)


@shared_task(base=EmbeddingTask, name='embeddings.process_image')
async def process_image_task(image_id: int):
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
        if model_version is None:
            raise ValueError("No active embedding model configured")
        
        # Get or create collection
        collection = get_or_create_collection(image.tenant, model_version)

        # Get storage manager
        storage = get_storage_manager(backend=image.storage_backend)
        
        # Download image from storage
        logger.debug(f"Downloading image from: {image.storage_key}")
        # Note: Implement actual download in storage client
        image_bytes = await storage.download(image.storage_key)

        # Generate embedding
        task = process_image_task
        embedding_gen = task.embedding_generator

        # Determine model type and variant from model_version
        model_config = model_version.config or {}
        model_type = model_config.get('type', 'clip')
        model_variant = model_config.get('variant', 'ViT-B-32')

        logger.info(f"Generating embedding with {model_type}/{model_variant}")
        
        model = embedding_gen.get_model(  # type: ignore
            model_type=model_type,
            model_variant=model_variant,
            device=getattr(settings, 'EMBEDDING_DEVICE', 'cuda')
        )
        
        start_time = time.time()
        embedding_vector = model.encode_image(image_bytes)
        inference_time = (time.time() - start_time) * 1000
        
        logger.info(f"Embedding generated in {inference_time:.2f}ms")
        
        # Generate unique vector point ID
        vector_point_id = f"img_{image.image_id}"
        
        # Prepare payload metadata
        payload = {
            'type': 'image',
            'image_id': image.id,  #type: ignore
            'image_uuid': str(image.image_id),   #type: ignore
            'tenant_id': str(image.tenant.id),   #type: ignore
            'filename': image.filename,
            'plant_site': image.plant_site,
            'shift': image.shift,
            'inspection_line': image.inspection_line,
            'captured_at': image.captured_at.isoformat(),
            'width': image.width,
            'height': image.height,
            'storage_key': image.storage_key,
            'storage_backend': image.storage_backend,
            'model_version': model_version.name,
            
            # Video linkage if exists
            'video_id': image.video.id if image.video else None,     #type: ignore
            'video_uuid': str(image.video.video_id) if image.video else None,
            'frame_number': image.frame_number,
            'timestamp_in_video': image.timestamp_in_video,
        }
        
        # Get vector DB client
        vector_db = task.get_vector_db_client(   # type: ignore
            collection_name=collection.collection_name,
            dimension=model_version.vector_dimension
        )
        
        # Insert into vector DB
        vector_point = VectorPoint(
            id=vector_point_id,
            vector=embedding_vector,
            payload=payload
        )
        
        vector_db.upsert([vector_point])
        
        logger.info(f"Vector stored: {vector_point_id}")
        
        # Update collection stats
        collection.total_vectors += 1
        collection.save(update_fields=['total_vectors', 'updated_at'])
        
        # Update image status (mark as embedded)
        image.status = StatusChoices.COMPLETED
        image.embedding_generated = True
        image.vector_point_id = vector_point_id
        image.embedding_model_version = model_version.name
        image.save(update_fields=[
            'status',
            'embedding_generated',
            'vector_point_id',
            'embedding_model_version',
            'updated_at',
        ])
        
        logger.info(f"Image {image_id} embedding completed: {vector_point_id}")
        
        # Trigger detection embedding tasks if image has detections
        detection_ids = list(Detection.objects.filter(image=image).values_list('id', flat=True))
        if detection_ids:
            from embeddings.tasks.detection import process_detection_task
            for detection_id in detection_ids:
                process_detection_task.delay(detection_id)   #type: ignore
            logger.info(f"Triggered {len(detection_ids)} detection embedding tasks")
        
        return {
            'status': 'success',
            'image_id': image_id,
            'vector_point_id': vector_point_id,
            'inference_time_ms': inference_time,
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