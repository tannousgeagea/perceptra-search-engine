# ml/preprocessing.py

from PIL import Image
import io
from typing import Tuple


async def get_image_dimensions(image_bytes: bytes) -> Tuple[int, int]:
    """
    Get image width and height from bytes.
    
    Returns:
        Tuple of (width, height)
    """
    image = Image.open(io.BytesIO(image_bytes))
    return image.size


async def validate_image(image_bytes: bytes) -> bool:
    """
    Validate that bytes represent a valid image.
    
    Returns:
        True if valid image, False otherwise
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image.verify()
        return True
    except Exception:
        return False


async def validate_video(video_bytes: bytes) -> bool:
    """
    Basic video validation.
    TODO: Implement proper video validation using ffmpeg or similar.
    
    For now, just check common video file signatures.
    """
    # Check file signatures
    video_signatures = [
        b'\x00\x00\x00\x18ftypmp4',  # MP4
        b'\x00\x00\x00\x20ftypiso',  # MP4 ISO
        b'\x1a\x45\xdf\xa3',          # MKV/WebM
        b'RIFF',                       # AVI (followed by file size and 'AVI ')
    ]
    
    for signature in video_signatures:
        if video_bytes.startswith(signature):
            return True
    
    # Check if starts with RIFF and contains AVI
    if video_bytes.startswith(b'RIFF') and b'AVI ' in video_bytes[:20]:
        return True
    
    return False