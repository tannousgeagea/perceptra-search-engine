# apps/embeddings/tasks.py

"""
Celery tasks for embedding generation.

Task Flow:
1. Video Upload → process_video_task → extract frames → process_image_task (per frame)
2. Image Upload → process_image_task → generate embedding → store in vector DB
3. Detection Creation → process_detection_task → crop region → generate embedding → store in vector DB

Each task is independent and can be retried on failure.

Main Tasks:
- process_video_task(video_id): Process video, extract frames
- process_image_task(image_id): Generate image embedding
- process_detection_task(detection_id): Generate detection embedding

Batch Tasks:
- batch_process_images_task(tenant_id, filter_params): Batch process images
- batch_process_detections_task(tenant_id, filter_params): Batch process detections
- reembed_with_new_model_task(tenant_id, model_version_id, media_type): Re-embed with new model

Automatic Triggers:
- Video upload → process_video_task (via signal)
- Image upload → process_image_task (via signal)
- Detection creation → process_detection_task (via signal)

Usage:
    # Manual trigger
    from embeddings.tasks import process_image_task
    process_image_task.delay(image_id=123)
    
    # Batch processing
    from embeddings.tasks import batch_process_detections_task
    batch_process_detections_task.delay(tenant_id='uuid', filter_params={'label': 'metal_scrap'})
"""

from .video import process_video_task
from .image import process_image_task
from .detection import process_detection_task
from .batch import (
    batch_process_images_task,
    batch_process_detections_task,
    reembed_with_new_model_task
)

__all__ = [
    'process_video_task',
    'process_image_task',
    'process_detection_task',
    'batch_process_images_task',
    'batch_process_detections_task',
    'reembed_with_new_model_task'
]