# infrastructure/embeddings/attention_pooling.py
"""Attention-weighted spatial pooling for image embeddings.

Uses DINOv2's self-attention maps as a saliency signal to weight
spatial features during pooling.  Defect regions (high attention)
contribute more to the final embedding than uniform background.
"""

import logging
from typing import Optional, Union

import numpy as np
from PIL import Image

from infrastructure.embeddings.base import TORCH_AVAILABLE

if TORCH_AVAILABLE:
    import torch
    import torch.nn.functional as F

logger = logging.getLogger(__name__)


class AttentionPooler:
    """Compute saliency-weighted embeddings using DINOv2 attention maps.

    This class is designed to be used alongside a primary embedding model
    (CLIP, SAM3, etc.).  It loads a lightweight DINOv2-small as an
    auxiliary model purely for saliency extraction.  The saliency map can
    then be applied to:

    * **Spatial feature maps** (SAM3, DINOv2) — replace global average
      pooling with attention-weighted pooling.
    * **Raw images** (CLIP) — soft-mask the image so that CLIP "sees"
      high-saliency regions more prominently.
    """

    def __init__(self, device: Optional[str] = None):
        self._dinov2 = None
        self._device = device

    def _ensure_loaded(self):
        """Lazy-load DINOv2-small for saliency extraction."""
        if self._dinov2 is not None:
            return

        try:
            from infrastructure.embeddings.dinov2 import DINOv2Embedding
            self._dinov2 = DINOv2Embedding(
                model_name='dinov2_vits14',
                device=self._device,
            )
            self._dinov2.load()
            logger.info("AttentionPooler: DINOv2-small loaded for saliency")
        except Exception as e:
            logger.warning(f"AttentionPooler: Failed to load DINOv2-small: {e}")
            self._dinov2 = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_saliency_map(
        self,
        image: Union[bytes, Image.Image, np.ndarray],
    ) -> Optional[np.ndarray]:
        """Extract a spatial saliency map from DINOv2's attention heads.

        Returns:
            2-D numpy array ``[H', W']`` with values summing to 1, or
            ``None`` if saliency extraction is unavailable.
        """
        self._ensure_loaded()
        if self._dinov2 is None:
            return None

        try:
            if isinstance(image, bytes):
                from PIL import Image as PILImage
                import io
                image = PILImage.open(io.BytesIO(image)).convert('RGB')
            if isinstance(image, Image.Image):
                image = np.array(image)

            # Get attention maps: [N, heads, patches, patches]
            attn = self._dinov2.get_attention_maps([image])
            if attn is None:
                return None

            # Average across heads and take last CLS-token row → per-patch attention
            # attn shape: [heads, patches, patches] (single image)
            if len(attn.shape) == 4:
                attn = attn[0]  # Remove batch dim
            avg_attn = attn.mean(axis=0)  # Average heads → [patches, patches]

            # CLS token attention over spatial tokens (row 0, skip CLS col 0)
            cls_attn = avg_attn[0, 1:]  # [num_spatial_patches]

            # Reshape to spatial grid
            num_patches = cls_attn.shape[0]
            h = w = int(num_patches ** 0.5)
            if h * w != num_patches:
                # Non-square — find closest factorisation
                h = w = int(round(num_patches ** 0.5))

            saliency = cls_attn[:h * w].reshape(h, w)

            # Normalise to probability distribution
            saliency = saliency - saliency.min()
            total = saliency.sum()
            if total > 0:
                saliency = saliency / total

            return saliency.astype(np.float32)

        except Exception as e:
            logger.warning(f"Saliency extraction failed: {e}")
            return None

    def weighted_pool(
        self,
        feature_map: 'torch.Tensor',
        saliency: np.ndarray,
    ) -> np.ndarray:
        """Apply attention-weighted pooling to a spatial feature map.

        Args:
            feature_map: Tensor of shape ``[1, C, H', W']`` or ``[C, H', W']``.
            saliency: 2-D saliency map ``[Hs, Ws]`` (will be resized to match).

        Returns:
            L2-normalised embedding vector ``[C]``.
        """
        if not TORCH_AVAILABLE:
            raise RuntimeError("PyTorch not available")

        if feature_map.dim() == 3:
            feature_map = feature_map.unsqueeze(0)
        _, C, H, W = feature_map.shape

        # Resize saliency to match feature map spatial dims
        sal = torch.from_numpy(saliency).unsqueeze(0).unsqueeze(0).float()
        sal = F.interpolate(sal, size=(H, W), mode='bilinear', align_corners=False)
        sal = sal.squeeze(0).squeeze(0)  # [H, W]

        # Re-normalise after interpolation
        sal = sal / (sal.sum() + 1e-10)
        sal = sal.to(feature_map.device)

        # Weighted sum: [1, C, H, W] * [H, W] → [C]
        weighted = (feature_map[0] * sal.unsqueeze(0)).sum(dim=(-2, -1))

        # L2-normalise
        norm = weighted.norm()
        if norm > 0:
            weighted = weighted / norm

        return weighted.cpu().numpy()

    def enhance_image(
        self,
        image: np.ndarray,
        saliency: np.ndarray,
        floor: float = 0.3,
    ) -> np.ndarray:
        """Soft-mask an image using the saliency map for CLIP encoding.

        High-saliency regions are preserved, low-saliency regions are
        darkened to ``floor`` brightness.  This biases CLIP towards the
        salient content without hard cropping.

        Args:
            image: RGB uint8 ``[H, W, 3]``.
            saliency: 2-D saliency map (any resolution, will be resized).
            floor: Minimum brightness multiplier for low-saliency regions.

        Returns:
            Saliency-enhanced RGB uint8 image ``[H, W, 3]``.
        """
        H, W = image.shape[:2]

        # Resize saliency to image resolution
        from PIL import Image as PILImage
        sal_pil = PILImage.fromarray((saliency * 255).astype(np.uint8))
        sal_resized = np.array(sal_pil.resize((W, H), PILImage.BILINEAR)).astype(np.float32) / 255.0

        # Scale to [floor, 1.0] range
        sal_max = sal_resized.max()
        if sal_max > 0:
            sal_resized = sal_resized / sal_max
        mask = floor + (1.0 - floor) * sal_resized  # [H, W]

        # Apply mask to each channel
        enhanced = image.astype(np.float32) * mask[:, :, np.newaxis]
        return np.clip(enhanced, 0, 255).astype(np.uint8)

    def unload(self):
        """Release the auxiliary DINOv2 model."""
        if self._dinov2 is not None:
            self._dinov2.unload()
            self._dinov2 = None
            logger.info("AttentionPooler: DINOv2-small unloaded")
