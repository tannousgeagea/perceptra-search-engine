# apps/embeddings/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver
from media.models import Video, Image, Detection
from embeddings.tasks.video import process_video_task
from embeddings.tasks.image import process_image_task
from embeddings.tasks.detection import process_detection_task
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Video)
def trigger_video_processing(sender, instance, created, **kwargs):
    """Trigger video processing task when video is created."""
    if created and instance.status == 'uploaded':
        logger.info(f"Triggering video processing for video {instance.id}")
        process_video_task.delay(instance.id)   #type: ignore


@receiver(post_save, sender=Image)
def trigger_image_embedding(sender, instance, created, **kwargs):
    """Trigger image embedding task when image is created."""
    if created and instance.status == 'uploaded':
        logger.info(f"Triggering image embedding for image {instance.id}")
        process_image_task.delay(instance.id)  #type: ignore


@receiver(post_save, sender=Detection)
def trigger_detection_embedding(sender, instance, created, **kwargs):
    """Trigger detection embedding task when detection is created."""
    if created:
        logger.info(f"Triggering detection embedding for detection {instance.id}")
        process_detection_task.delay(instance.id) #type: ignore