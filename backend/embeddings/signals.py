# apps/embeddings/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver
from media.models import Video, Image, Detection
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Video)
def trigger_video_processing(sender, instance, created, **kwargs):
    """Trigger video processing task when video is created."""
    if created and instance.status == 'uploaded':
        try:
            from embeddings.tasks.video import process_video_task
            logger.info(f"Triggering video processing for video {instance.id}")
            process_video_task.delay(instance.id)   #type: ignore
        except Exception as e:
            logger.warning(f"Failed to dispatch video processing for video {instance.id}: {e}")


@receiver(post_save, sender=Image)
def trigger_image_embedding(sender, instance, created, **kwargs):
    """Trigger image embedding task when image is created."""
    if created and instance.status == 'uploaded':
        try:
            from embeddings.tasks.image import process_image_task
            logger.info(f"Triggering image embedding for image {instance.id}")
            process_image_task.delay(instance.id)  #type: ignore
        except Exception as e:
            logger.warning(f"Failed to dispatch image embedding for image {instance.id}: {e}")


@receiver(post_save, sender=Detection)
def trigger_detection_embedding(sender, instance, created, **kwargs):
    """Trigger detection embedding task when detection is created."""
    if created:
        try:
            from embeddings.tasks.detection import process_detection_task
            logger.info(f"Triggering detection embedding for detection {instance.id}")
            process_detection_task.delay(instance.id) #type: ignore
        except Exception as e:
            logger.warning(f"Failed to dispatch detection embedding for detection {instance.id}: {e}")


@receiver(post_save, sender=Detection)
def check_alert_on_detection(sender, instance, created, **kwargs):
    """Trigger alert check when a detection is created."""
    if created:
        try:
            from embeddings.tasks.alert_check import check_detection_alert_task
            logger.info(f"Triggering alert check for detection {instance.id}")
            check_detection_alert_task.delay(instance.id)  #type: ignore
        except Exception as e:
            logger.warning(f"Failed to dispatch alert check for detection {instance.id}: {e}")
