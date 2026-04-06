"""SAM3 detection backend using the ``perceptra-seg`` package.

This is the **only** module that imports from ``perceptra-seg``, so any
upstream API changes are isolated here.

perceptra-seg API summary (SAM v3 backend):
    from perceptra_seg import Segmentor, SegmentorConfig

    config = SegmentorConfig()
    config.model.name = "sam_v3"
    config.runtime.backend = "torch"
    config.runtime.device = "cuda"            # or "cpu"
    config.outputs.min_area_ratio = 0.0001

    seg = Segmentor(config=config)

    # Multi-text batch (returns dict[str, List[Result]]):
    results_dict = seg.segment_from_text_batch(image, ["pipe", "rust"], min_score=0.5)

    # Merged with IoU dedup (returns List[Result]):
    all_results = seg.segment_from_text_batch_merged(image, prompts, iou_threshold=0.7)

    # Each Result has: .text_label, .score, .bbox (x1,y1,x2,y2 absolute), .area, .latency_ms
"""

import logging
import time
from typing import Dict, List, Optional

import numpy as np
from PIL import Image

from .base import BaseDetectionBackend, DetectionError, DetectionResult, ModelLoadError

logger = logging.getLogger(__name__)

try:
    from perceptra_seg import Segmentor, SegmentorConfig
    PERCEPTRA_SEG_AVAILABLE = True
except ImportError:
    PERCEPTRA_SEG_AVAILABLE = False
    logger.debug("perceptra-seg not installed — SAM3PerceptraBackend unavailable")


class SAM3PerceptraBackend(BaseDetectionBackend):
    """Detection backend using perceptra-seg's SAM v3 with multi-text prompts.

    This backend:
    - Loads the SAM v3 segmentation model (heavyweight, ~1 GB+)
    - Accepts a list of text prompts (hazard class names)
    - Runs all prompts in a single merged forward pass with IoU dedup
    - Returns bounding boxes + optional masks for each detected object
    - Normalises all bbox coordinates to [0, 1]
    """

    def __init__(
        self,
        device: Optional[str] = None,
        min_area_ratio: float = 0.0001,
        iou_threshold: float = 0.7,
        **kwargs,
    ):
        super().__init__(device=device, **kwargs)
        self.min_area_ratio = min_area_ratio
        self.iou_threshold = iou_threshold
        self._segmentor: Optional['Segmentor'] = None

    # ------------------------------------------------------------------
    # BaseDetectionBackend interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return 'sam3_perceptra'

    def load(self) -> None:
        if not PERCEPTRA_SEG_AVAILABLE:
            raise ModelLoadError(
                "perceptra-seg is not installed.\n"
                "Install with: pip3 install perceptra-seg[all]"
            )

        start = time.time()
        try:
            config = SegmentorConfig()
            config.model.name = "sam_v3"
            config.runtime.backend = "torch"
            config.runtime.device = self.device_str
            config.outputs.min_area_ratio = self.min_area_ratio

            self._segmentor = Segmentor(config=config)
        except Exception as e:
            raise ModelLoadError(f"Failed to load SAM3 perceptra model: {e}") from e

        load_ms = (time.time() - start) * 1000
        logger.info(f"SAM3 perceptra model loaded in {load_ms:.0f}ms on {self.device_str}")
        self._is_loaded = True

    def detect(
        self,
        image: Image.Image,
        prompts: List[str],
        confidence_threshold: float = 0.3,
        **kwargs,
    ) -> List[DetectionResult]:
        if not self._is_loaded:
            self.load()

        iou_threshold = kwargs.get('iou_threshold', self.iou_threshold)
        w, h = image.size

        start = time.time()
        try:
            # Use merged batch to deduplicate overlapping detections
            # across different prompts in a single pass.
            raw_results = self._segmentor.segment_from_text_batch_merged(
                image,
                prompts,
                iou_threshold=iou_threshold,
            )
        except Exception as e:
            raise DetectionError(f"SAM3 detection failed: {e}") from e
        finally:
            inference_ms = (time.time() - start) * 1000
            logger.debug(f"SAM3 detection took {inference_ms:.1f}ms for {len(prompts)} prompts")

        # Convert perceptra-seg results to normalised DetectionResult
        detections: List[DetectionResult] = []
        for r in raw_results:
            if r.score < confidence_threshold:
                continue

            # r.bbox is (x1, y1, x2, y2) in absolute pixels
            x1, y1, x2, y2 = r.bbox
            bbox_x = x1 / w
            bbox_y = y1 / h
            bbox_width = (x2 - x1) / w
            bbox_height = (y2 - y1) / h

            # Clamp to [0, 1]
            bbox_x = max(0.0, min(1.0, bbox_x))
            bbox_y = max(0.0, min(1.0, bbox_y))
            bbox_width = max(0.0, min(1.0 - bbox_x, bbox_width))
            bbox_height = max(0.0, min(1.0 - bbox_y, bbox_height))

            # Skip degenerate boxes
            if bbox_width < 1e-4 or bbox_height < 1e-4:
                continue

            detections.append(DetectionResult(
                label=r.text_label,
                confidence=r.score,
                bbox_x=bbox_x,
                bbox_y=bbox_y,
                bbox_width=bbox_width,
                bbox_height=bbox_height,
                mask=getattr(r, 'mask', None),
            ))

        logger.info(
            f"SAM3 detection: {len(raw_results)} raw -> "
            f"{len(detections)} above threshold {confidence_threshold}"
        )
        return detections

    def detect_batch(
        self,
        images: List[Image.Image],
        prompts: List[str],
        confidence_threshold: float = 0.3,
        **kwargs,
    ) -> List[List[DetectionResult]]:
        # perceptra-seg processes one image at a time; iterate.
        return [
            self.detect(img, prompts, confidence_threshold, **kwargs)
            for img in images
        ]

    def unload(self) -> None:
        if self._segmentor is not None:
            del self._segmentor
            self._segmentor = None
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass
        super().unload()
