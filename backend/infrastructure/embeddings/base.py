# infrastructure/embeddings/base.py

from abc import ABC, abstractmethod
from typing import Union, List, Optional, Tuple
import numpy as np
from PIL import Image
import io
import logging

logger = logging.getLogger(__name__)

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger.warning("PyTorch not available. Embedding models will not work.")


class BaseEmbeddingModel(ABC):
    """Abstract base class for all embedding models."""
    
    def __init__(
        self,
        model_name: str,
        device: Optional[str] = None,
        **kwargs
    ):
        if not TORCH_AVAILABLE:
            raise ImportError(
                "PyTorch is required for embedding models. "
                "Install with: pip install torch"
            )
        
        self.model_name = model_name
        self.device_str = device or self._get_device()
        self.device = torch.device(self.device_str)
        self.model = None
        self.preprocessor = None
        self._is_loaded = False
        
        logger.info(f"Initializing {self.__class__.__name__} on device: {self.device_str}")
    
    def _get_device(self) -> str:
        """Auto-detect optimal device."""
        if not TORCH_AVAILABLE:
            return 'cpu'
        
        if torch.cuda.is_available():
            return 'cuda'
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            return 'mps'
        else:
            return 'cpu'
    
    @abstractmethod
    def load(self):
        """Load model weights and preprocessor."""
        pass
    
    @abstractmethod
    def encode_image(self, image: Union[bytes, Image.Image, np.ndarray]) -> np.ndarray:
        """
        Encode image to embedding vector.
        
        Args:
            image: Image as bytes, PIL Image, or numpy array
            
        Returns:
            Normalized embedding vector
        """
        pass
    
    @abstractmethod
    def encode_text(self, text: str) -> np.ndarray:
        """
        Encode text to embedding vector.
        
        Args:
            text: Text string
            
        Returns:
            Normalized embedding vector
        """
        pass
    
    @abstractmethod
    def get_dimension(self) -> int:
        """Get embedding dimension."""
        pass
    
    @abstractmethod
    def supports_text(self) -> bool:
        """Check if model supports text encoding."""
        pass
    
    @abstractmethod
    def supports_batch(self) -> bool:
        """Check if model supports batch processing."""
        pass
    
    @property
    @abstractmethod
    def embedding_dim(self) -> int:
        """Get embedding dimension as property."""
        pass
    
    def encode_images_batch(
        self,
        images: List[Union[bytes, Image.Image, np.ndarray]]
    ) -> List[np.ndarray]:
        """
        Encode multiple images in batch (if supported).
        
        Args:
            images: List of images
            
        Returns:
            List of embedding vectors
        """
        if not self.supports_batch():
            return [self.encode_image(img) for img in images]
        
        raise NotImplementedError("Batch encoding must be implemented by subclass")
    
    def encode_texts_batch(self, texts: List[str]) -> List[np.ndarray]:
        """
        Encode multiple texts in batch (if supported).
        
        Args:
            texts: List of text strings
            
        Returns:
            List of embedding vectors
        """
        if not self.supports_text():
            raise NotImplementedError(f"{self.model_name} does not support text encoding")
        
        # Default implementation - override for better performance
        return [self.encode_text(text) for text in texts]
    
    def _bytes_to_image(self, image_bytes: bytes) -> Image.Image:
        """Convert bytes to PIL Image."""
        try:
            image = Image.open(io.BytesIO(image_bytes))
            return self._ensure_rgb(image)
        except Exception as e:
            logger.error(f"Failed to convert bytes to image: {str(e)}")
            raise ValueError(f"Invalid image bytes: {str(e)}")
    
    def _ensure_rgb(self, image: Image.Image) -> Image.Image:
        """Ensure image is in RGB format."""
        if image.mode != 'RGB':
            return image.convert('RGB')
        return image
    
    def _normalize_embedding(self, embedding: np.ndarray) -> np.ndarray:
        """L2 normalize embedding for cosine similarity."""
        norm = np.linalg.norm(embedding)
        if norm == 0:
            logger.warning("Zero norm embedding detected")
            return embedding
        return embedding / norm
    
    def _to_numpy(self, tensor: 'torch.Tensor') -> np.ndarray:
        """Convert torch tensor to numpy array."""
        return tensor.cpu().detach().numpy()
    
    def unload(self):
        """Unload model from memory."""
        if self.model is not None:
            del self.model
            self.model = None
            
        if self.preprocessor is not None:
            del self.preprocessor
            self.preprocessor = None
            
        self._is_loaded = False
        
        if TORCH_AVAILABLE and torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        logger.info(f"Model unloaded: {self.model_name}")
    
    def __del__(self):
        """Cleanup on deletion."""
        self.unload()
    
    def __enter__(self):
        """Context manager entry."""
        if not self._is_loaded:
            self.load()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.unload()


class EmbeddingModelException(Exception):
    """Base exception for embedding model errors."""
    pass


class ModelLoadError(EmbeddingModelException):
    """Raised when model fails to load."""
    pass


class EncodingError(EmbeddingModelException):
    """Raised when encoding fails."""
    pass