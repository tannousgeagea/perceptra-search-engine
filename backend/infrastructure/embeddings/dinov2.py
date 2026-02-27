# infrastructure/embeddings/dinov2.py

from typing import Union, List, Optional
import numpy as np
from PIL import Image
try:
    import torch
    import torch.nn.functional as F
    from torchvision import transforms
    from PIL import Image
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

from infrastructure.embeddings.base import (
    BaseEmbeddingModel,
    ModelLoadError,
    EncodingError
)
import time
import logging

logger = logging.getLogger(__name__)


class DINOv2Embedding(BaseEmbeddingModel):
    """Meta's DINOv2 self-supervised vision encoder.
    
    DINOv2 models from Meta AI:
    - dinov2_vits14: Small, 384-d embeddings, fastest
    - dinov2_vitb14: Base, 768-d embeddings, balanced
    - dinov2_vitl14: Large, 1024-d embeddings, high quality
    - dinov2_vitg14: Giant, 1536-d embeddings, best quality
    
    All models use 14x14 patch size and 518x518 image resolution.
    
    Advantages:
    - Self-supervised pretraining (no manual labels needed)
    - Excellent for fine-grained object features
    - Fast inference
    - Strong transfer learning capabilities
    - Works great for object detection and retrieval
    """
    
    AVAILABLE_MODELS = {
        "dinov2_vits14": {
            "torch_hub": "facebookresearch/dinov2",
            "model_name": "dinov2_vits14",
            "embedding_dim": 384,
            "image_size": 518
        },
        "dinov2_vitb14": {
            "torch_hub": "facebookresearch/dinov2",
            "model_name": "dinov2_vitb14",
            "embedding_dim": 768,
            "image_size": 518
        },
        "dinov2_vitl14": {
            "torch_hub": "facebookresearch/dinov2",
            "model_name": "dinov2_vitl14",
            "embedding_dim": 1024,
            "image_size": 518
        },
        "dinov2_vitg14": {
            "torch_hub": "facebookresearch/dinov2",
            "model_name": "dinov2_vitg14",
            "embedding_dim": 1536,
            "image_size": 518
        },
        # Register variants with different backbones
        "dinov2_vits14_reg": {
            "torch_hub": "facebookresearch/dinov2",
            "model_name": "dinov2_vits14_reg",
            "embedding_dim": 384,
            "image_size": 518
        },
        "dinov2_vitb14_reg": {
            "torch_hub": "facebookresearch/dinov2",
            "model_name": "dinov2_vitb14_reg",
            "embedding_dim": 768,
            "image_size": 518
        },
        "dinov2_vitl14_reg": {
            "torch_hub": "facebookresearch/dinov2",
            "model_name": "dinov2_vitl14_reg",
            "embedding_dim": 1024,
            "image_size": 518
        },
        "dinov2_vitg14_reg": {
            "torch_hub": "facebookresearch/dinov2",
            "model_name": "dinov2_vitg14_reg",
            "embedding_dim": 1536,
            "image_size": 518
        }
    }
    
    
    def __init__(
        self,
        model_name: str = "dinov2_vitb14",
        device: str = "cpu",
        use_registers: bool = False,
        **kwargs
    ):
        if not TORCH_AVAILABLE:
            raise ImportError(
                "PyTorch and torchvision not installed. "
                "Install with: pip install torch torchvision"
            )
        
        if model_name not in self.AVAILABLE_MODELS:
            raise ValueError(
                f"Model {model_name} not supported. "
                f"Choose from: {list(self.AVAILABLE_MODELS.keys())}"
            )

        super().__init__(
            model_name=f"{model_name}",
            device=device,
            **kwargs
        )

        self.device_obj = torch.device(device)
        self.model_config = self.AVAILABLE_MODELS[model_name]
        self._embedding_dim = self.model_config["embedding_dim"]
    

    def load(self):
        """Load DINOv2 model from torch hub."""
        try:
            logger.info(f"Loading DINOv2 model: {self.model_name} on device: {self.device}")
            
            # Load model from torch hub
            self.model = torch.hub.load(
                self.model_config["torch_hub"],
                self.model_config["model_name"]
            )
            
            self.model.to(self.device_obj)
            self.model.eval()

            # Image preprocessing
            self.image_size = self.model_config["image_size"]
            self.preprocessor = transforms.Compose([
                transforms.Resize((self.image_size, self.image_size), interpolation=transforms.InterpolationMode.BICUBIC),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
            ])

            self._is_loaded = True
            
            logger.info(f"DINOv2 model loaded successfully: {self.model_name}")
            
        except Exception as e:
            logger.error(f"Failed to load DINOv2 model: {str(e)}")
            raise ModelLoadError(f"DINOv2 load failed: {str(e)}")
    
    def encode_image(self, image: Union[bytes, Image.Image, np.ndarray]) -> np.ndarray:
        """Encode image using DINOv2."""
        if not self._is_loaded:
            self.load()
        
        start_time = time.time()
        
        try:
            # Convert to PIL Image
            if isinstance(image, bytes):
                image = self._bytes_to_image(image)
            elif isinstance(image, np.ndarray):
                image = Image.fromarray(image)
            
            # Preprocess
            image_tensor = self.preprocessor(image).unsqueeze(0).to(self.device_obj)
            
            # Encode
            with torch.no_grad():
                features = self.model(image_tensor)
            
            # Convert to numpy and normalize
            embedding = self._to_numpy(features[0])
            embedding = self._normalize_embedding(embedding)
            
            inference_time = (time.time() - start_time) * 1000
            logger.debug(f"DINOv2 encoding took {inference_time:.2f}ms")
            
            return embedding
            
        except Exception as e:
            logger.error(f"DINOv2 encoding failed: {str(e)}")
            raise EncodingError(f"DINOv2 encoding failed: {str(e)}")
    
    def encode_text(self, text: str) -> np.ndarray:
        """DINOv2 does not support text encoding."""
        raise NotImplementedError("DINOv2 is a vision-only model and does not support text encoding")
    
    def encode_images_batch(self, images: List[Union[bytes, Image.Image, np.ndarray]]) -> List[np.ndarray]:
        """Encode multiple images in batch."""
        if not self._is_loaded:
            self.load()
        
        try:
            # Convert all to PIL Images
            pil_images = []
            for img in images:
                if isinstance(img, bytes):
                    pil_images.append(self._bytes_to_image(img))
                elif isinstance(img, np.ndarray):
                    pil_images.append(Image.fromarray(img))
                else:
                    pil_images.append(img)
            
            # Preprocess batch
            image_tensors = torch.stack([
                self.preprocessor(img) for img in pil_images
            ]).to(self.device_obj)
            
            # Encode batch
            with torch.no_grad():
                features = self.model(image_tensors)
            
            # Convert to numpy and normalize
            embeddings = self._to_numpy(features)
            embeddings = np.array([self._normalize_embedding(emb) for emb in embeddings])
            
            return list(embeddings)
            
        except Exception as e:
            logger.error(f"DINOv2 batch encoding failed: {str(e)}")
            raise EncodingError(f"DINOv2 batch encoding failed: {str(e)}")
    
    def get_dimension(self) -> int:
        """Get DINOv2 embedding dimension."""
        return self.embedding_dim
    
    @property
    def embedding_dim(self) -> int:
        return self._embedding_dim

    def supports_text(self) -> bool:
        """DINOv2 does not support text."""
        return False
    
    def supports_batch(self) -> bool:
        """DINOv2 supports batch processing."""
        return True
    
    def _preprocess_images(self, images: List[np.ndarray]) -> torch.Tensor:
        """Preprocess images for DINOv2.
        
        Args:
            images: List of RGB images [H, W, 3] in range [0, 255]
        
        Returns:
            Preprocessed tensor [N, 3, 518, 518]
        """
        # Convert to PIL Images
        pil_images = [Image.fromarray(img) for img in images]
        
        # Apply transforms
        tensors = [self.preprocessor(img) for img in pil_images]
        
        # Stack into batch
        batch = torch.stack(tensors).to(self.device_obj)
        
        return batch

    def get_attention_maps(self, images: List[np.ndarray]) -> np.ndarray:
        """Extract attention maps from the model.
        
        Useful for visualization and interpretability.
        
        Args:
            images: List of RGB images
        
        Returns:
            Attention maps [N, num_heads, num_patches, num_patches]
        """
        batch = self._preprocess_images(images)
        
        # Store attention maps
        attention_maps = []
        
        def hook_fn(module, input, output):
            # Extract attention weights from the last layer
            attention_maps.append(output)
        
        # Register hook on last attention layer
        # Note: This is model-specific and might need adjustment
        handle = None
        for name, module in self.model.named_modules():
            if 'attn' in name and 'blocks' in name:
                handle = module.register_forward_hook(hook_fn)
        
        with torch.no_grad():
            _ = self.model(batch)
        
        if handle:
            handle.remove()
        
        if attention_maps:
            return attention_maps[-1].cpu().numpy()
        return None
    
    def compute_similarity(
        self,
        images1: List[Union[bytes, Image.Image, np.ndarray]],
        images2: List[Union[bytes, Image.Image, np.ndarray]]
    ) -> np.ndarray:
        """Compute pairwise cosine similarity between two sets of images.
        
        Args:
            images1: First set of images
            images2: Second set of images
        
        Returns:
            Similarity matrix [len(images1), len(images2)]
        """
        emb1 = self.encode_images_batch(images1)
        emb2 = self.encode_images_batch(images2)
        
        # Compute cosine similarity
        similarity = np.dot(emb1, emb2.T)
        
        return similarity