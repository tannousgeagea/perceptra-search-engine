# ml/video_processing.py

from typing import List, Tuple, Optional
import cv2
import numpy as np
from PIL import Image
import io
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class VideoFrame:
    """Represents an extracted video frame."""
    frame_number: int
    timestamp: float  # In seconds
    image: Image.Image
    width: int
    height: int
    
    def to_bytes(self, format: str = 'JPEG', quality: int = 95) -> bytes:
        """Convert frame to bytes."""
        buffer = io.BytesIO()
        self.image.save(buffer, format=format, quality=quality)
        return buffer.getvalue()


class VideoProcessor:
    """
    Video processing utilities for frame extraction.
    Uses OpenCV for efficient video processing.
    """
    
    @staticmethod
    def extract_frames_from_bytes(
        video_bytes: bytes,
        fps: Optional[float] = None,
        max_frames: Optional[int] = None,
        start_time: float = 0.0,
        end_time: Optional[float] = None,
        target_size: Optional[Tuple[int, int]] = None
    ) -> List[VideoFrame]:
        """
        Extract frames from video bytes.
        
        Args:
            video_bytes: Video content as bytes
            fps: Frames per second to extract (None = extract all frames)
            max_frames: Maximum number of frames to extract
            start_time: Start time in seconds
            end_time: End time in seconds (None = until end)
            target_size: Resize frames to (width, height) (None = keep original)
            
        Returns:
            List of VideoFrame objects
        """
        try:
            # Save bytes to temporary file
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_file:
                tmp_file.write(video_bytes)
                tmp_path = tmp_file.name
            
            try:
                frames = VideoProcessor.extract_frames_from_file(
                    tmp_path,
                    fps=fps,
                    max_frames=max_frames,
                    start_time=start_time,
                    end_time=end_time,
                    target_size=target_size
                )
                return frames
            finally:
                # Clean up temp file
                import os
                os.unlink(tmp_path)
                
        except Exception as e:
            logger.error(f"Failed to extract frames from bytes: {str(e)}")
            raise
    
    @staticmethod
    def extract_frames_from_file(
        video_path: str,
        fps: Optional[float] = None,
        max_frames: Optional[int] = None,
        start_time: float = 0.0,
        end_time: Optional[float] = None,
        target_size: Optional[Tuple[int, int]] = None
    ) -> List[VideoFrame]:
        """
        Extract frames from video file.
        
        Args:
            video_path: Path to video file
            fps: Frames per second to extract (None = extract all frames)
            max_frames: Maximum number of frames to extract
            start_time: Start time in seconds
            end_time: End time in seconds (None = until end)
            target_size: Resize frames to (width, height) (None = keep original)
            
        Returns:
            List of VideoFrame objects
        """
        try:
            # Open video
            cap = cv2.VideoCapture(video_path)
            
            if not cap.isOpened():
                raise ValueError(f"Failed to open video: {video_path}")
            
            # Get video properties
            video_fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            video_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            video_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = total_frames / video_fps if video_fps > 0 else 0
            
            logger.info(
                f"Video info: {total_frames} frames, {video_fps:.2f} fps, "
                f"{duration:.2f}s, {video_width}x{video_height}"
            )
            
            # Calculate frame sampling
            if fps is not None:
                # Extract at specified fps
                frame_interval = int(video_fps / fps) if fps < video_fps else 1
            else:
                # Extract all frames
                frame_interval = 1
            
            # Calculate frame range
            start_frame = int(start_time * video_fps)
            if end_time is not None:
                end_frame = int(end_time * video_fps)
            else:
                end_frame = total_frames
            
            # Extract frames
            frames = []
            frame_count = 0
            current_frame = 0
            
            cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            
            while True:
                ret, frame = cap.read()
                
                if not ret:
                    break
                
                current_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1
                
                # Check if we've passed end_frame
                if current_frame >= end_frame:
                    break
                
                # Check frame interval
                if (current_frame - start_frame) % frame_interval != 0:
                    continue
                
                # Convert BGR to RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Resize if needed
                if target_size:
                    frame_rgb = cv2.resize(frame_rgb, target_size)
                    width, height = target_size
                else:
                    height, width = frame_rgb.shape[:2]
                
                # Convert to PIL Image
                pil_image = Image.fromarray(frame_rgb)
                
                # Calculate timestamp
                timestamp = current_frame / video_fps
                
                # Create VideoFrame object
                video_frame = VideoFrame(
                    frame_number=current_frame,
                    timestamp=timestamp,
                    image=pil_image,
                    width=width,
                    height=height
                )
                
                frames.append(video_frame)
                frame_count += 1
                
                # Check max frames limit
                if max_frames and frame_count >= max_frames:
                    break
            
            cap.release()
            
            logger.info(f"Extracted {len(frames)} frames from video")
            
            return frames
            
        except Exception as e:
            logger.error(f"Failed to extract frames: {str(e)}")
            raise
    
    @staticmethod
    def get_video_info(video_bytes: bytes) -> dict:
        """
        Get video metadata without extracting frames.
        
        Args:
            video_bytes: Video content as bytes
            
        Returns:
            Dict with video metadata
        """
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_file:
                tmp_file.write(video_bytes)
                tmp_path = tmp_file.name
            
            try:
                cap = cv2.VideoCapture(tmp_path)
                
                if not cap.isOpened():
                    raise ValueError("Failed to open video")
                
                fps = cap.get(cv2.CAP_PROP_FPS)
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                duration = total_frames / fps if fps > 0 else 0
                
                cap.release()
                
                return {
                    'fps': fps,
                    'total_frames': total_frames,
                    'width': width,
                    'height': height,
                    'duration_seconds': duration
                }
                
            finally:
                import os
                os.unlink(tmp_path)
                
        except Exception as e:
            logger.error(f"Failed to get video info: {str(e)}")
            raise


# Convenience function
def extract_frames_from_video(
    video_bytes: bytes,
    fps: float = 1.0,
    max_frames: Optional[int] = None
) -> List[VideoFrame]:
    """
    Extract frames from video at specified fps.
    
    Args:
        video_bytes: Video content as bytes
        fps: Frames per second to extract (default: 1 fps)
        max_frames: Maximum frames to extract
        
    Returns:
        List of VideoFrame objects
    """
    processor = VideoProcessor()
    return processor.extract_frames_from_bytes(
        video_bytes,
        fps=fps,
        max_frames=max_frames
    )