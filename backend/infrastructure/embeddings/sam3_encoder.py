import logging
import os
import time
from typing import Union, List, Optional

import numpy as np
from PIL import Image

from infrastructure.embeddings.base import (
    BaseEmbeddingModel,
    ModelLoadError,
    EncodingError,
    TORCH_AVAILABLE,
)

# Optional Torch imports
if TORCH_AVAILABLE:
    import torch
    from torchvision.ops import roi_align

    try:
        from sam3 import build_sam3_image_model
        from sam3.model.sam3_image_processor import Sam3Processor
        SAM3_AVAILABLE = True
    except ImportError:
        SAM3_AVAILABLE = False
        logging.warning("sam3 is not available.")
else:
    SAM3_AVAILABLE = False

logger = logging.getLogger(__name__)

class SAM3Embedding(BaseEmbeddingModel):
    AVAILABLE_MODELS = {
        'SAM3': {'embedding_dim': 256, 'pretrained': 'facebook'},
    }
    """Embedding backend using SAM3 model."""
    def __init__(
        self, 
        model_name: str = 'SAM3',
        device: Optional[str] = None,    
        pretrained: Optional[str] = None,
        **kwargs
    ):
        if not SAM3_AVAILABLE:
            raise ImportError(
                "SAM3 not installed.\n"
                "Install with:\n"
                "git clone https://github.com/facebookresearch/sam3.git /opt/sam3\n"
                "pip install -e /opt/sam3\n"
                "pip install -e /opt/sam3[notebooks]"
            )
        if model_name not in self.AVAILABLE_MODELS:
            raise ValueError(
                f"Invalid SAM3 variant: {model_name}. "
                f"Available: {list(self.AVAILABLE_MODELS.keys())}"
            )

        self.model_name = model_name
        self.model_config = self.AVAILABLE_MODELS[model_name]
        self._embedding_dim = self.model_config['embedding_dim']
        self.pretrained = pretrained or self.model_config['pretrained']
        
        super().__init__(
            model_name=f"sam3-{model_name.replace('/', '-').lower()}",
            device=device,
            **kwargs
        )

    
    def load(self):
        start_time = time.time()
        try:    
            sam3_dir = "/opt/checkpoints/huggingface/facebook/sam3"
            if not os.path.exists(sam3_dir):
                raise ValueError(f"Weights for model {self.model_name} at path {sam3_dir} doesn't exist")
            self.model = build_sam3_image_model(
                bpe_path=None, 
                device=self.device_str,
                enable_inst_interactivity=False,
                checkpoint_path="/opt/checkpoints/huggingface/facebook/sam3/sam3.pt",
                load_from_HF=False,
            )
            self.model.eval()
            self.preprocessor = Sam3Processor(self.model)

            # Verify embedding dimension
            if hasattr(self.model, 'hidden_dim'):
                actual_dim = self.model.hidden_dim
            else:
                raise AttributeError("SAM3 model does not have 'hidden_dim' attribute to determine embedding dimension.")
            
            if actual_dim != self._embedding_dim:
                logger.warning(
                    f"Expected dimension {self._embedding_dim}, got {actual_dim}. "
                    f"Updating embedding dimension."
                )
                self._embedding_dim = actual_dim
            
            self._is_loaded = True
            
            logger.info(
                f"SAM3 model with Image Encoder PE loaded successfully: {self.model_name} "
                f"({self._embedding_dim}-d embeddings)"
            )
            loading_time = (time.time() - start_time) * 1000
            logger.debug(f"Loading model into device: {self.device} took: {loading_time:.2f}ms")
        except Exception as e:
            logger.error(f"Failed to load SAM3 model: {e}")
            raise ModelLoadError(f"Failed to load SAM3 model: {e}")

    def _preprocess_image(
        self, image: Union[bytes, np.ndarray, Image.Image]
    ) -> Image.Image:
        if isinstance(image, bytes):
            image = self._bytes_to_image(image)    
        elif isinstance(image, np.ndarray):
            image = Image.fromarray(image.astype("uint8"), "RGB")
        elif not isinstance(image, Image.Image):
            logger.error("Unsupported image format. Must be byte encoded image, numpy array, or PIL Image.")
            raise ValueError(
                "Unsupported image format. Must be file path, numpy array, or PIL Image."
            )

        return image

    def _preprocess_boxes(self, boxes: List[tuple]) -> List[torch.Tensor]:
        """Preprocess box batch for ROI extraction. Boxes should be in normalized [x_min, y_min, x_max, y_max] format."""

        start_time = time.time()
        if len(boxes) == 0:
            raise ValueError("Box batch cannot be empty.")
        
        for box in boxes:
            if box[0] > box[2] or box[1] > box[3]:
                logger.error(f"Invalid box coordinates: {box}. x_min must be <= x_max and y_min must be <= y_max.")
                raise ValueError(f"Invalid box coordinates: {box}. x_min must be <= x_max and y_min must be <= y_max.")
            if any(coord < 0 for coord in box):
                logger.error(f"Box coordinates must be non-negative: {box}.")
                raise ValueError(f"Box coordinates must be non-negative: {box}.")
            if any(coord > 1 for coord in box):
                logger.error(f"Box coordinates must be normalized between 0 and 1: {box}.")
                raise ValueError(f"Box coordinates must be normalized between 0 and 1: {box}.")
        
        image_resolution = self.preprocessor.resolution
        boxes_tensor = torch.Tensor(boxes).to(self.device)
        boxes_tensor[:, [0, 2]] *= image_resolution  # Absolute x coordinates
        boxes_tensor[:, [1, 3]] *= image_resolution  # Absolute y coordinates

        processing_time = (time.time() - start_time) * 1000
        logger.debug(f"Transforming boxes into absolute xyxy format took: {processing_time:.2f}ms")
        return boxes_tensor

    def _encode_images(self, images: List[Union[bytes, Image.Image, np.ndarray]]):
        start_time = time.time()

        try:
            """Extract image features from PE Vision Encoder"""
            preprocessed_images = [self._preprocess_image(img) for img in images]
            inference_state = self.preprocessor.set_image_batch(preprocessed_images)
            image_features = inference_state["backbone_out"]["vision_features"]
            
            inference_time = (time.time() - start_time) * 1000
            logger.debug(f"SAM3 encoding took {inference_time:.2f}ms")
            return image_features
        
        except Exception as e:
            logger.error(f"Encountered error while encoding image: {e}")
            raise EncodingError(f"Encountered error while encoding image: {e}")

    MAX_BATCH_SIZE = 8

    def _encode_images_chunk(self, chunk: list) -> list:
        """Encode a single chunk of images."""
        image_features = self._encode_images(chunk)
        image_features = image_features.mean(dim=(-2, -1))
        image_features = image_features / (image_features.norm(dim=-1, keepdim=True) + 1e-10)
        return list(self._to_numpy(image_features))

    def encode_images_batch(self, images: List[Union[bytes, Image.Image, np.ndarray]]) -> list:
        if not self._is_loaded:
            self.load()

        if len(images) <= self.MAX_BATCH_SIZE:
            return self._encode_images_chunk(images)

        results: list = []
        for i in range(0, len(images), self.MAX_BATCH_SIZE):
            chunk = images[i:i + self.MAX_BATCH_SIZE]
            results.extend(self._encode_images_chunk(chunk))
        return results
    
    def encode_image(self, image):
        if not self._is_loaded:
            self.load()

        image_features = self._encode_images(images=[image])

        start_time = time.time()
        image_features = image_features.mean(dim=(-2, -1)) # Global average pooling over spatial dimensions
        image_features = image_features / (image_features.norm(dim=-1, keepdim=True) + 1e-10)  # Normalize to unit length
        embeddings = self._to_numpy(image_features[0]) # Get the single image embedding
        
        processing_time = (time.time() - start_time) * 1000
        logger.debug(f"Postprocessing of image features took: {processing_time:.2f}ms")
        return list(embeddings)
        
    def encode_image_with_rois(
        self, 
        image: torch.Tensor, 
        boxes: List[tuple],
        roi_output_size: tuple = (7, 7)
    ) -> np.ndarray:
        if not self._is_loaded:
            self.load()

        preprocessed_box_batch =  [self._preprocess_boxes(boxes)]
        image_features = self._encode_images([image])
        start_time = time.time()
        image_resolution = self.preprocessor.resolution # Squared resolution of the input image (1008 for 1008x1008 input)
       
        spatial_scale = image_resolution / image_features.shape[1]  # Assuming embeddings shape is [N, Embedding_dim, H', W']
        roi_embeddings = roi_align(
            image_features,
            preprocessed_box_batch,      
            output_size=roi_output_size,
            spatial_scale=spatial_scale,
            aligned=True
        )

        roi_embeddings = roi_embeddings.mean(dim=[-2, -1])  # Average pool to get [N, Embedding_dim]
        roi_embeddings = roi_embeddings / (roi_embeddings.norm(dim=-1, keepdim=True) + 1e-10)  # Normalize to unit length
        roi_embeddings = self._to_numpy(roi_embeddings)

        processing_time = (time.time() - start_time) * 1000
        logger.debug(f"Postprocessing of image roi features took: {processing_time:.2f}ms")
        return list(roi_embeddings)
    

    def encode_images_batch_with_rois(
        self, 
        images: List[Union[bytes, Image.Image, np.ndarray]], 
        box_batch: List[tuple],
        roi_output_size: tuple = (7, 7)
    ):
        if not self._is_loaded:
            self.load()

        preprocessed_box_batch = [self._preprocess_boxes(boxes) for boxes in box_batch]
        image_features = self._encode_images(images)

        start_time = time.time()
        image_resolution = self.preprocessor.resolution # Squared resolution of the input image (1008 for 1008x1008 input)
        
        spatial_scale = image_resolution / image_features.shape[1]  # Assuming embeddings shape is [N, C, H', W']
        roi_embeddings = roi_align(
            image_features,
            preprocessed_box_batch,      
            output_size=roi_output_size,
            spatial_scale=spatial_scale,
            aligned=True
        )

        roi_embeddings = roi_embeddings.mean(dim=[-2, -1])  # Average pool to get [N, Embedding_dim]
        roi_embeddings = roi_embeddings / (roi_embeddings.norm(dim=-1, keepdim=True) + 1e-10)  # Normalize to unit length
        roi_embeddings = self._to_numpy(roi_embeddings)

        batched_roi_embeddings = []
        for i, boxes in enumerate(box_batch):
            batched_roi_embeddings.append(list(roi_embeddings[i*len(boxes):i*len(boxes)+len(boxes)]))

        processing_time = (time.time() - start_time) * 1000
        logger.debug(f"Postprocessing of image roi features took: {processing_time:.2f}ms")
        return batched_roi_embeddings
    
    def encode_detection_with_context(
        self,
        image: Union[bytes, Image.Image, np.ndarray],
        bbox: tuple,
        halo_ratio: float = 0.5,
        roi_weight: float = 0.7,
    ) -> list:
        """Encode a detection region with surrounding structural context.

        Instead of cropping the bounding box and encoding it in isolation,
        this method extracts two ROI embeddings from the full image's feature
        map via ``roi_align``:

        1. The **tight ROI** — the detection bounding box itself.
        2. The **context halo** — the bbox expanded by ``halo_ratio`` in each
           direction, clamped to image bounds.

        The final embedding is the weighted blend of both, capturing what the
        defect looks like *and* where it sits structurally.

        Args:
            image: Full parent image (bytes, PIL, or ndarray).
            bbox: Normalized ``(x, y, width, height)`` with values in ``[0, 1]``.
            halo_ratio: How much to expand the bbox for context (0.5 = 50%).
            roi_weight: Weight of the tight ROI vs. halo (default 0.7).

        Returns:
            L2-normalised embedding as a Python list of floats.
        """
        if not self._is_loaded:
            self.load()

        x, y, w, h = bbox

        # Tight ROI in [x_min, y_min, x_max, y_max] normalised format
        x_min = max(0.0, x)
        y_min = max(0.0, y)
        x_max = min(1.0, x + w)
        y_max = min(1.0, y + h)
        tight_box = (x_min, y_min, x_max, y_max)

        # Context halo — expand by halo_ratio in each direction
        expand_w = w * halo_ratio
        expand_h = h * halo_ratio
        halo_box = (
            max(0.0, x_min - expand_w),
            max(0.0, y_min - expand_h),
            min(1.0, x_max + expand_w),
            min(1.0, y_max + expand_h),
        )

        # Single forward pass — both ROIs extracted from the same feature map
        roi_embeddings = self.encode_image_with_rois(image, [tight_box, halo_box])

        # Weighted fusion
        tight_emb = np.array(roi_embeddings[0], dtype=np.float32)
        halo_emb = np.array(roi_embeddings[1], dtype=np.float32)
        fused = roi_weight * tight_emb + (1.0 - roi_weight) * halo_emb

        # L2-normalise
        norm = np.linalg.norm(fused)
        if norm > 0:
            fused = fused / norm

        return list(fused)

    def encode_text(self, text: str) -> np.ndarray:
        """SAM3 does not support text encoding."""
        raise NotImplementedError("This embedding backend is using the PE Encois a vision-only model and does not support text encoding")

    @property
    def embedding_dim(self) -> int:
        """Return the embedding dimension of the SAM3 model."""
        # Return the actual embedding dimension based on the model (pseudo-code)
        return self.model.hidden_dim

    def get_dimension(self) -> int:
        """Get PE Encoder embedding dimension from SAM3 model."""
        return self.embedding_dim
    
    def supports_text(self) -> bool:
        """SAM3 supports text encoding."""
        return False
    
    def supports_batch(self) -> bool:
        """SAM3 supports batch processing."""
        return True

if __name__ == "__main__":
    # Example usage
    encoder = SAM3Embedding(
        model_name='SAM3',
        device="cuda",    
    )
    image = Image.fromarray(np.zeros((1008, 1008, 3), dtype=np.uint8)).convert("RGB")

    embedding = encoder.encode_image(image)
    assert len(embedding) == encoder.embedding_dim
    print("SAM3 image embedding generated successfully with dimension:", len(embedding))

    embeddings = encoder.encode_images_batch([image, image])
    assert len(embeddings) == 2
    assert len(embeddings[0]) == encoder.embedding_dim
    assert len(embeddings[1]) == encoder.embedding_dim
    print("SAM3 batch image embeddings generated successfully with dimension:", len(embeddings[0]))

    embeddings_with_rois = encoder.encode_image_with_rois(
        image=image,
        boxes=[(0.1, 0.1, 0.5, 0.5), (0.5, 0.5, 0.9, 0.9)]
    )
    assert len(embeddings_with_rois) == 2
    assert len(embeddings_with_rois[0]) == encoder.embedding_dim
    assert len(embeddings_with_rois[1]) == encoder.embedding_dim
    print("SAM3 image embeddings with ROIs generated successfully with dimension:", len(embeddings_with_rois[0]))

    embeddings_with_rois_batch = encoder.encode_images_batch_with_rois(
        images=[image, image],
        box_batch=[
            [(0.1, 0.1, 0.5, 0.5), (0.5, 0.5, 0.9, 0.9)], # Two ROIs First Image
            [(0.2, 0.2, 0.6, 0.6), (0.6, 0.6, 0.8, 0.8)], # Two ROIs Second Image
        ]
    )

    assert len(embeddings_with_rois_batch) == 2
    assert len(embeddings_with_rois_batch[0]) == 2  # 2 ROIs for first image
    assert len(embeddings_with_rois_batch[1]) == 2  # 2 ROIs for second image
    assert len(embeddings_with_rois_batch[0][0]) == encoder.embedding_dim  # First ROI of first image
    assert len(embeddings_with_rois_batch[0][1]) == encoder.embedding_dim  # Second ROI of first image
    assert len(embeddings_with_rois_batch[1][0]) == encoder.embedding_dim  # First ROI of second image
    assert len(embeddings_with_rois_batch[1][1]) == encoder.embedding_dim  # Second ROI of second image
    print("SAM3 batch image embeddings with ROIs generated successfully with dimension:", len(embeddings_with_rois_batch[0][0]))
   