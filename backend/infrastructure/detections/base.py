import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Union

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


class DetectionError(Exception):
    """Raised when detection inference fails."""
    pass


class ModelLoadError(Exception):
    """Raised when a detection model fails to load."""
    pass


@dataclass
class DetectionResult:
    """Single detection output from a backend.

    All bounding box coordinates are **normalized** to [0, 1] in
    (x, y, width, height) format — the same convention used by the
    ``Detection`` Django model when ``bbox_format='normalized'``.
    """
    label: str
    confidence: float
    bbox_x: float
    bbox_y: float
    bbox_width: float
    bbox_height: float
    mask: Optional[np.ndarray] = field(default=None, repr=False)

    def to_absolute(self, image_width: int, image_height: int) -> tuple:
        """Convert normalized bbox to absolute pixel coordinates (x, y, w, h)."""
        return (
            int(self.bbox_x * image_width),
            int(self.bbox_y * image_height),
            int(self.bbox_width * image_width),
            int(self.bbox_height * image_height),
        )


class BaseDetectionBackend(ABC):
    """Abstract base class for object detection backends.

    Implementations must provide:
    - ``load()``: load model weights into memory
    - ``detect()``: run detection on a single image with text prompts
    - ``detect_batch()``: run detection on multiple images

    The backend is expected to cache its model in memory after ``load()``.
    The ``DetectionBackendRegistry`` singleton ensures only one instance
    per (backend_name, device) pair exists in a worker process.
    """

    def __init__(self, device: Optional[str] = None, **kwargs):
        self.device_str = device or self._auto_device()
        self._is_loaded = False

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def load(self) -> None:
        """Load model weights. Called once per worker lifetime."""
        ...

    @abstractmethod
    def detect(
        self,
        image: Image.Image,
        prompts: List[str],
        confidence_threshold: float = 0.3,
        **kwargs,
    ) -> List[DetectionResult]:
        """Detect objects in *image* matching the given text *prompts*.

        All prompts should be batched in a single forward pass where the
        backend supports it.

        Returns a list of ``DetectionResult`` with **normalized** bboxes.
        """
        ...

    @abstractmethod
    def detect_batch(
        self,
        images: List[Image.Image],
        prompts: List[str],
        confidence_threshold: float = 0.3,
        **kwargs,
    ) -> List[List[DetectionResult]]:
        """Batch detection across multiple images.

        Returns one ``List[DetectionResult]`` per input image.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this backend (e.g. ``'sam3_perceptra'``)."""
        ...

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------

    def unload(self) -> None:
        """Release model resources. Override if cleanup is needed."""
        self._is_loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _auto_device() -> str:
        try:
            import torch
            if torch.cuda.is_available():
                return 'cuda'
            if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                return 'mps'
        except ImportError:
            pass
        return 'cpu'
