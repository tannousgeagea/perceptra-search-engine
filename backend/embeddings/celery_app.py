from embeddings.config.celery_utils import celery_app
from embeddings.tasks import (
    process_image_task,
    process_video_task,
    process_detection_task,
    batch_process_images_task,
    batch_process_detections_task,
)

celery = celery_app
celery.autodiscover_tasks(['embeddings.tasks'])