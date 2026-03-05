# apps/embeddings/tasks/detection.py

from celery import shared_task
from embeddings.tasks.base import EmbeddingTask, get_active_model_version, get_or_create_collection
from media.models import Detection, Image
from infrastructure.storage.client import get_storage_manager
from infrastructure.embeddings.generator import EmbeddingGenerator
from infrastructure.vectordb.base import VectorPoint
from PIL import Image as PILImage

from django.conf import settings
import io
import numpy as np
import logging
import time

logger = logging.getLogger(__name__)


@shared_task(base=EmbeddingTask, name='embeddings.process_detection')
async def process_detection_task(detection_id: int):
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
        if model_version is None:
            raise ValueError("No active embedding model configured")
        
        # Get or create collection
        collection = get_or_create_collection(detection.tenant, model_version)
        
        # Get storage manager
        storage = get_storage_manager(backend=detection.image.storage_backend)
        
        # TODO: Download parent image from storage
        image_bytes = await storage.download(detection.image.storage_key)
        
        # Download parent image
        logger.debug(f"Downloading image from: {detection.image.storage_key}")


        # Load image
        image = PILImage.open(io.BytesIO(image_bytes)).convert('RGB')
        image_array = np.array(image)
        # Crop detection region
        if detection.bbox_format == 'normalized':
            # Convert normalized to absolute
            x = int(detection.bbox_x * detection.image.width)
            y = int(detection.bbox_y * detection.image.height)
            w = int(detection.bbox_width * detection.image.width)
            h = int(detection.bbox_height * detection.image.height)
        else:
            # Already absolute
            x = int(detection.bbox_x)
            y = int(detection.bbox_y)
            w = int(detection.bbox_width)
            h = int(detection.bbox_height)
        
        # Ensure bounds are valid
        x = max(0, min(x, detection.image.width))
        y = max(0, min(y, detection.image.height))
        w = max(1, min(w, detection.image.width - x))
        h = max(1, min(h, detection.image.height - y))
        
        # Crop
        cropped_array = image_array[y:y+h, x:x+w]
        cropped_image = PILImage.fromarray(cropped_array)
        
        logger.debug(f"Cropped detection region: {w}x{h}")
        
        # Optionally save cropped image
        if detection.storage_key:
            # Save crop to storage
            crop_buffer = io.BytesIO()
            cropped_image.save(crop_buffer, format='JPEG', quality=95)
            crop_bytes = crop_buffer.getvalue()
            
            # Upload to storage
            # await storage.save(detection.storage_key, crop_bytes)
            logger.debug(f"Saved crop to: {detection.storage_key}")
        
        # Generate embedding
        task = process_detection_task
        embedding_gen = task.embedding_generator
        
        # Get model config
        model_config = model_version.config or {}
        model_type = model_config.get('type', 'clip')
        model_variant = model_config.get('variant', 'ViT-B-32')
        
        model = embedding_gen.get_model(    # type: ignore
            model_type=model_type,
            model_variant=model_variant,
            device=getattr(settings, 'EMBEDDING_DEVICE', 'cuda')
        )
        
        start_time = time.time()
        embedding_vector = model.encode_image(cropped_image)
        inference_time = (time.time() - start_time) * 1000
        
        logger.info(f"Detection embedding generated in {inference_time:.2f}ms")
        
        # Generate unique vector point ID
        vector_point_id = f"det_{detection.detection_id}"
        
        # Prepare payload metadata
        payload = {
            'type': 'detection',
            'detection_id': detection.id,   # type: ignore
            'detection_uuid': str(detection.detection_id),
            'tenant_id': str(detection.tenant.id),   # type: ignore
            
            # Detection metadata
            'label': detection.label,
            'confidence': detection.confidence,
            'bbox_x': detection.bbox_x,
            'bbox_y': detection.bbox_y,
            'bbox_width': detection.bbox_width,
            'bbox_height': detection.bbox_height,
            'bbox_format': detection.bbox_format,
            
            # Image metadata
            'image_id': detection.image.id,   # type: ignore
            'image_uuid': str(detection.image.image_id),
            'image_filename': detection.image.filename,
            'image_storage_key': detection.image.storage_key,
            
            # Context metadata
            'plant_site': detection.image.plant_site,
            'shift': detection.image.shift,
            'inspection_line': detection.image.inspection_line,
            'captured_at': detection.image.captured_at.isoformat(),
            
            # Video linkage if exists
            'video_id': detection.image.video.id if detection.image.video else None,   # type: ignore
            'video_uuid': str(detection.image.video.video_id) if detection.image.video else None,
            'frame_number': detection.image.frame_number,
            'timestamp_in_video': detection.image.timestamp_in_video,
            
            # Model info
            'model_version': model_version.name,
            
            # Tags
            'tags': list(detection.tags.values_list('name', flat=True))
        }
        
        # Get vector DB client
        vector_db = task.get_vector_db_client(     #type: ignore
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
        
        logger.info(f"Detection vector stored: {vector_point_id}")
        
        # Update collection stats
        collection.total_vectors += 1
        collection.save(update_fields=['total_vectors', 'updated_at'])
        
        # Update detection record
        detection.vector_point_id = vector_point_id
        detection.embedding_generated = True
        detection.embedding_model_version = model_version.name
        detection.save(update_fields=[
            'vector_point_id',
            'embedding_generated',
            'embedding_model_version',
            'updated_at'
        ])
        
        logger.info(f"Detection {detection_id} embedding completed: {vector_point_id}")
        
        return {
            'status': 'success',
            'detection_id': detection_id,
            'vector_point_id': vector_point_id,
            'label': detection.label,
            'inference_time_ms': inference_time
        }
        
    except Detection.DoesNotExist:
        logger.error(f"Detection {detection_id} not found")
        raise
    
    except Exception as e:
        logger.error(f"Failed to process detection {detection_id}: {str(e)}")
        raise