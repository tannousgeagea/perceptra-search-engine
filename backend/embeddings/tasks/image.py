# apps/embeddings/tasks/image.py

from celery import shared_task
from embeddings.tasks.base import EmbeddingTask, get_active_model_version, get_or_create_collection
from media.models import Image, Detection, StatusChoices
from embeddings.models import TenantVectorCollection
from infrastructure.storage.client import get_storage_manager
from infrastructure.vectordb.base import VectorPoint
from django.conf import settings
from django.db.models import F
import logging
import time
import uuid
import numpy as np

logger = logging.getLogger(__name__)

@shared_task(base=EmbeddingTask, name='embedding:process_image', queue='embedding')
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
        image = Image.objects.select_related('tenant', 'video').prefetch_related('tags').get(id=image_id)
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
        image_bytes = storage.download_sync(image.storage_key)

        # Generate embedding
        # task = process_image_task

        # Determine model type and variant from model_version
        model_config = model_version.config or {}
        embedding_gen = process_image_task.embedding_generator
        model = embedding_gen.get_model(
            model_type=model_version.model_type,
            model_name=model_config.get('variant', 'ViT-B-32'),
            device=getattr(settings, 'EMBEDDING_DEVICE', 'cuda'),
        )
        
        t0 = time.time()

        # Attention-weighted encoding: use DINOv2 saliency to focus on
        # defect regions instead of uniform pooling over the full image.
        attention_pooling = model_config.get('attention_pooling', False)
        if attention_pooling:
            try:
                pooler = embedding_gen.get_attention_pooler(
                    device=getattr(settings, 'EMBEDDING_DEVICE', 'cuda'),
                )
                saliency = pooler.get_saliency_map(image_bytes)
                if saliency is not None:
                    # For CLIP/Perception: soft-mask the image then encode
                    import io as _io
                    from PIL import Image as PILImage
                    pil = PILImage.open(_io.BytesIO(image_bytes)).convert('RGB')
                    enhanced = pooler.enhance_image(np.array(pil), saliency)
                    embedding_vector = model.encode_image(enhanced)
                    logger.debug("Used attention-weighted encoding via saliency mask")
                else:
                    embedding_vector = model.encode_image(image_bytes)
            except Exception as e:
                logger.warning(f"Attention pooling failed, using standard encoding: {e}")
                embedding_vector = model.encode_image(image_bytes)
        else:
            embedding_vector = model.encode_image(image_bytes)

        inference_ms = (time.time() - t0) * 1000
        logger.info(f"Image embedding generated in {inference_ms:.2f}ms (attention_pooling={attention_pooling})")
        
        # Generate unique vector point ID
        vector_point_id = str(image.image_id)
        
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

            # Tags
            'tags': list(image.tags.values_list('name', flat=True)),
        }
        
        # Get vector DB client
        vector_db = process_image_task.get_vector_db_client(   # type: ignore
            collection_name=collection.collection_name,
            dimension=model_version.vector_dimension
        )
        
        vector_db.upsert([VectorPoint(id=vector_point_id, vector=embedding_vector, payload=payload)])
        logger.info(f"Image vector stored: {vector_point_id}")
        
        # With a single atomic UPDATE — no read-modify-write in application memory:
        TenantVectorCollection.objects.filter(pk=collection.pk).update(
            total_vectors=F('total_vectors') + 1
        )

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

        if detection_ids:
            logger.info(f"Triggered {len(detection_ids)} detection embedding tasks")

        # ── Trigger temporal delta computation ──
        try:
            from embeddings.tasks.delta import compute_delta_embedding_task
            compute_delta_embedding_task.delay(image_id)  # type: ignore
            logger.debug(f"Queued delta embedding for image {image_id}")
        except Exception as e:
            logger.warning(f"Failed to queue delta embedding for image {image_id}: {e}")

        # ── Trigger auto-detection if tenant has a hazard config ──
        auto_detection_queued = False
        try:
            from embeddings.models import TenantHazardConfig
            has_config = TenantHazardConfig.objects.filter(
                tenant=image.tenant, is_active=True,
            ).exists()
            if has_config:
                from embeddings.tasks.auto_detection import auto_detect_image_task
                auto_detect_image_task.delay(image_id)
                auto_detection_queued = True
                logger.info(f"Queued auto-detection for image {image_id}")
        except Exception as e:
            logger.warning(f"Failed to queue auto-detection for image {image_id}: {e}")

        return {
            'status': 'success',
            'image_id': image_id,
            'vector_point_id': vector_point_id,
            'inference_time_ms': inference_ms,
            'detections_triggered': len(detection_ids),
            'auto_detection_queued': auto_detection_queued,
        }
        
    except Image.DoesNotExist:
        logger.error(f"Image {image_id} not found")
        raise
    
    except Exception as e:
        # Mark image as failed
        logger.error(f"Failed to process image {image_id}: {str(e)}")
        try:
            Image.objects.filter(id=image_id).update(status=StatusChoices.FAILED)
        except:
            pass
        
        raise