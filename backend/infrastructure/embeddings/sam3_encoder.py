import logging
import os
from os import getenv as env
import time
from typing import Union, List, Optional
import subprocess

import numpy as np
from PIL import Image

from base import (
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
        model_variant: str = 'SAM3',
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
        if model_variant not in self.AVAILABLE_MODELS:
            raise ValueError(
                f"Invalid SAM3 variant: {model_variant}. "
                f"Available: {list(self.AVAILABLE_MODELS.keys())}"
            )

        sam3_dir = "/opt/checkpoints/sam3"
        weight_file = os.path.join(sam3_dir, "sam3.pt")
        config_file = os.path.join(sam3_dir, "config.json")
         # Skip download if files exist
        if os.path.exists(weight_file) and os.path.exists(config_file):
            logging.info("SAM3 weights already exist. Skipping download.")
        else:
            self._download_weights(sam3_dir)

        self.model_variant = model_variant
        self.model_config = self.AVAILABLE_MODELS[model_variant]
        self._embedding_dim = self.model_config['embedding_dim']
        self.pretrained = pretrained or self.model_config['pretrained']
        
        super().__init__(
            model_name=f"sam3-{model_variant.replace('/', '-').lower()}",
            device=device,
            **kwargs
        )

    def _download_weights(self, sam3_dir):
        weight_file = os.path.join(sam3_dir, "sam3.pt")
        config_file = os.path.join(sam3_dir, "config.json")

        os.makedirs(sam3_dir)

        # Skip download if files exist
        if os.path.exists(weight_file) and os.path.exists(config_file):
            logging.info("SAM3 weights already exist. Skipping download.")
            return

        hf_token = env("HF_TOKEN", None)
        if hf_token is None:
            raise ValueError("HF_TOKEN should be set in environmental variables")

        logging.info("Downloading SAM3 weights...")

        subprocess.run(
            [
                "hf",
                "download",
                "--token",
                hf_token,
                "facebook/sam3",
                "sam3.pt",
                "config.json",
                "--local-dir",
                sam3_dir,
            ],
            check=True,
        )

        logging.info("SAM3 weights downloaded.")
    
    def load(self):
        start_time = time.time()
        try:    
            self.model = build_sam3_image_model(
                bpe_path=None, 
                device=self.device_str,
                enable_inst_interactivity=False,
                checkpoint_path="/opt/checkpoints/sam3/sam3.pt",
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
                f"SAM3 model with Image Encoder PE loaded successfully: {self.model_variant} "
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
            logger.error(f"Encountered error while encoding image: str{e}")
            raise EncodingError(f"Encountered error while encoding image: str{e}")

    def encode_images_batch(self, images: List[Union[bytes, Image.Image, np.ndarray]]) -> np.ndarray:
        image_features = self._encode_images(images)

        start_time = time.time()
        image_features = image_features.mean(dim=(-2, -1)) # Global average pooling over spatial dimensions
        image_features = image_features / image_features.norm(dim=-1, keepdim=True) + 1e-10 # Normalize to unit length
        embeddings = self._to_numpy(image_features)

        processing_time = (time.time() - start_time) * 1000
        logger.debug(f"Postprocessing of batched image features took: {processing_time:.2f}ms")
        return list(embeddings)
    
    def encode_image(self, image):
        image_features = self._encode_images(images=[image])

        start_time = time.time()
        image_features = image_features.mean(dim=(-2, -1)) # Global average pooling over spatial dimensions
        image_features = image_features / image_features.norm(dim=-1, keepdim=True) + 1e-10 # Normalize to unit length
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
        roi_embeddings = roi_embeddings / roi_embeddings.norm(dim=-1, keepdim=True) + 1e-10 # Normalize to unit length
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
        roi_embeddings = roi_embeddings / roi_embeddings.norm(dim=-1, keepdim=True) + 1e-10 # Normalize to unit length
        roi_embeddings = self._to_numpy(roi_embeddings)

        batched_roi_embeddings = []
        for i, boxes in enumerate(box_batch):
            batched_roi_embeddings.append(list(roi_embeddings[i*len(boxes):i*len(boxes)+len(boxes)]))

        processing_time = (time.time() - start_time) * 1000
        logger.debug(f"Postprocessing of image roi features took: {processing_time:.2f}ms")
        return batched_roi_embeddings
    
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
        model_variant='SAM3',
        device="cuda",    
    )
    encoder.load()
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
   