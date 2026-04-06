# apps/embeddings/tasks/video.py

from celery import shared_task
from typing import Optional
from embeddings.tasks.base import EmbeddingTask, get_active_model_version
from embeddings.tasks.image import process_image_task
from media.models import Video, Image, StatusChoices
from infrastructure.storage.client import get_storage_manager
from ml.video_processing import extract_frames_from_video, VideoProcessor
import logging

logger = logging.getLogger(__name__)


@shared_task(base=EmbeddingTask, name='embedding:process_video', queue='embedding')
def process_video_task(video_id: int, fps:float=1.0, max_frames:Optional[int]=None):
    """
    Process video: extract frames and trigger image embedding tasks.
    
    Args:
        video_id: Video database ID
        
    Returns:
        dict with status and frame count
    """
    try:
        # Get video
        video = Video.objects.select_related('tenant').get(id=video_id)
        logger.info(f"Processing video {video_id}: {video.filename}")
        
        # Update status
        video.status = StatusChoices.PROCESSING
        video.save(update_fields=['status', 'updated_at'])
        
        # Get storage manager
        storage = get_storage_manager(backend=video.storage_backend)
        
        # Download video from storage
        logger.info(f"Downloading video from storage: {video.storage_key}")
        video_bytes = storage.download_sync(video.storage_key)
        
        # Get video info and update video record
        video_info = VideoProcessor.get_video_info(video_bytes)
        Video.objects.filter(pk=video.pk).update(
            duration_seconds=video_info['duration_seconds']
        )

        logger.info(
            f"Video info: {video_info['total_frames']} frames, "
            f"{video_info['fps']:.2f} fps, "
            f"{video_info['duration_seconds']:.2f}s"
        )
        
        # Extract frames
        logger.info(f"Extracting frames at {fps} fps...")
        frames = extract_frames_from_video(
            video_bytes,
            fps=fps,
            max_frames=max_frames
        )
        
        logger.info(f"Extracted {len(frames)} frames")

        # Placeholder: Simulate frame extraction
        frames_created = 0
        frame_objects = []
        for frame in frames:
            try:
                # Generate storage key for frame
                year = video.recorded_at.year
                month = f"{video.recorded_at.month:02d}"
                frame_filename = f"{video.video_id}_frame_{frame.frame_number:06d}.jpg"
                storage_key = f"{video.tenant.tenant_id}/frames/{year}/{month}/{frame_filename}"  
                
                # Convert frame to bytes
                frame_bytes = frame.to_bytes(format='JPEG', quality=95)
                
                # Upload frame to storage
                storage.save_sync(
                    storage_key=storage_key,
                    content=frame_bytes,
                    content_type='image/jpeg',
                    metadata={
                        'video_id': str(video.video_id),
                        'frame_number': frame.frame_number,
                        'timestamp': frame.timestamp
                    }
                )
                # Create Image record
                frame_objects.append(Image(
                    tenant=video.tenant,
                    video=video,
                    filename=frame_filename,
                    storage_key=storage_key,
                    storage_backend=video.storage_backend,
                    file_size_bytes=len(frame_bytes),
                    width=frame.width,
                    height=frame.height,
                    frame_number=frame.frame_number,
                    timestamp_in_video=frame.timestamp,
                    plant_site=video.plant_site,
                    shift=video.shift,
                    inspection_line=video.inspection_line,
                    captured_at=video.recorded_at,
                    status=StatusChoices.UPLOADED,
                    created_by=video.created_by,
                    updated_by=video.updated_by,
                    created_by_api_key=video.created_by_api_key,
                ))
                
                frames_created += 1
                logger.debug(f"Frame {frame.frame_number} saved and queued for embedding")
                
            except Exception as e:
                logger.error(f"Failed to process frame {frame.frame_number}: {str(e)}")
                continue

        # Bulk insert all frame Image records in one query
        created_images = Image.objects.bulk_create(frame_objects)
        logger.info(f"Bulk created {len(created_images)} frame Image records")

        # Dispatch embedding task per frame
        for img in created_images:
            process_image_task.delay(img.id)  # type: ignore

        Video.objects.filter(pk=video.pk).update(
            frame_count=len(created_images),
            status=StatusChoices.COMPLETED,
        )
        
        logger.info(
            f"Video {video_id} processing completed: "
            f"{frames_created} frames created and queued for embedding"
        )
        
        return {
            'status': 'success',
            'video_id': video_id,
            'frames_created': frames_created,
            'frames_queued': frames_created,
            'video_duration': video_info['duration_seconds'],
            'extraction_fps': fps
        }
        
    except Video.DoesNotExist:
        logger.error(f"Video {video_id} not found")
        raise
    
    except Exception as e:
        # Mark video as failed
        logger.error(f"Failed to process video {video_id}: {str(e)}")
        try:
            Video.objects.filter(id=video_id).update(status=StatusChoices.FAILED)
        except:
            pass
        raise