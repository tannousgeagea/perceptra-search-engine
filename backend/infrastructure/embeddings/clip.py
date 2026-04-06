# infrastructure/embeddings/clip.py


from typing import Union, List, Optional
import numpy as np
from PIL import Image
import time
import logging

from infrastructure.embeddings.base import (
    BaseEmbeddingModel,
    ModelLoadError,
    EncodingError,
    TORCH_AVAILABLE
)

if TORCH_AVAILABLE:
    import torch
    try:
        import open_clip
        CLIP_AVAILABLE = True
    except ImportError:
        CLIP_AVAILABLE = False
        logging.warning("open_clip not available. Install with: pip install open-clip-torch")
else:
    CLIP_AVAILABLE = False

logger = logging.getLogger(__name__)


class CLIPEmbedding(BaseEmbeddingModel):
    """
    CLIP (Contrastive Language-Image Pre-training) embedding model using OpenCLIP.
    Supports both image and text encoding.
    
    Available models:
    - ViT-B-32: 512-d, fastest
    - ViT-B-16: 512-d, better accuracy
    - ViT-L-14: 768-d, high accuracy
    - ViT-L-14-336: 768-d, highest accuracy (336px input)
    """
    
    AVAILABLE_MODELS = {
        'ViT-B-32': {'embedding_dim': 512, 'pretrained': 'openai'},
        'ViT-B-16': {'embedding_dim': 512, 'pretrained': 'openai'},
        'ViT-L-14': {'embedding_dim': 768, 'pretrained': 'openai'},
        'ViT-L-14-336': {'embedding_dim': 768, 'pretrained': 'openai'},
        'ViT-H-14': {'embedding_dim': 1024, 'pretrained': 'laion2b_s32b_b79k'},
        'ViT-g-14': {'embedding_dim': 1024, 'pretrained': 'laion2b_s12b_b42k'},
    }
    
    def __init__(
        self,
        model_name: str = 'ViT-B-32',
        device: Optional[str] = None,
        pretrained: Optional[str] = None,
        **kwargs
    ):
        if not CLIP_AVAILABLE:
            raise ImportError(
                "OpenCLIP not installed. "
                "Install with: pip install open-clip-torch"
            )
        
        
        if model_name not in self.AVAILABLE_MODELS:
            raise ValueError(
                f"Invalid CLIP variant: {model_name}. "
                f"Available: {list(self.AVAILABLE_MODELS.keys())}"
            )
        
        self.model_variant = model_name
        self.model_config = self.AVAILABLE_MODELS[model_name]
        self._embedding_dim = self.model_config['embedding_dim']
        self.pretrained = pretrained or self.model_config['pretrained']

        super().__init__(
            model_name=f"clip-{model_name.replace('/', '-').lower()}",
            device=device,
            **kwargs
        )

    @property
    def embedding_dim(self) -> int:
        return self._embedding_dim
    
    def load(self):
        """Load CLIP model."""
        try:
            logger.info(f"Loading CLIP model: {self.model_variant} (pretrained={self.pretrained})")
            
            # Load model and preprocessor
            self.model, _, self.preprocessor = open_clip.create_model_and_transforms(
                self.model_variant,
                pretrained=self.pretrained,
                device=self.device,
            )
            
            self.model.eval()
            
            # Verify embedding dimension
            if hasattr(self.model, 'visual'):
                actual_dim = self.model.visual.output_dim
            else:
                actual_dim = getattr(self.model, 'output_dim', self._embedding_dim)
            
            if actual_dim != self._embedding_dim:
                logger.warning(
                    f"Expected dimension {self._embedding_dim}, got {actual_dim}. "
                    f"Updating embedding dimension."
                )
                self._embedding_dim = actual_dim
            
            self._is_loaded = True
            
            logger.info(
                f"CLIP model loaded successfully: {self.model_variant} "
                f"({self._embedding_dim}-d embeddings)"
            )
            
        except Exception as e:
            logger.error(f"Failed to load CLIP model: {str(e)}")
            raise ModelLoadError(f"CLIP load failed: {str(e)}")
    
    def encode_image(self, image: Union[bytes, Image.Image, np.ndarray]) -> np.ndarray:
        """Encode image using CLIP."""
        if not self._is_loaded:
            self.load()
        
        if self.preprocessor is None or self.model is None:
            raise RuntimeError("Model or preprocessor not loaded")
        
        start_time = time.time()
        
        try:
            # Convert to PIL Image
            if isinstance(image, bytes):
                image = self._bytes_to_image(image)
            elif isinstance(image, np.ndarray):
                image = Image.fromarray(image)
            
            # Preprocess
            preprocessed = self.preprocessor(image).unsqueeze(0).to(self.device)
            
            # Encode
            with torch.no_grad():
                image_features = self.model.encode_image(preprocessed)
                # Normalize
                image_features = image_features / image_features.norm(dim=-1, keepdim=True)
            
            # Convert to numpy
            embedding = self._to_numpy(image_features[0])
            
            inference_time = (time.time() - start_time) * 1000
            logger.debug(f"CLIP image encoding took {inference_time:.2f}ms")
            
            return embedding
            
        except Exception as e:
            logger.error(f"CLIP image encoding failed: {str(e)}")
            raise EncodingError(f"CLIP image encoding failed: {str(e)}")
    
    def encode_text(self, text: str) -> np.ndarray:
        """Encode text using CLIP."""
        if not self._is_loaded:
            self.load()
        
        if self.model is None:
            raise RuntimeError("Model not loaded")
        
        start_time = time.time()
        
        try:
            # Tokenize
            tokenizer = open_clip.get_tokenizer(self.model_variant)
            text_tokens = tokenizer([text]).to(self.device)
            
            # Encode
            with torch.no_grad():
                text_features = self.model.encode_text(text_tokens)
                # Normalize
                text_features = text_features / text_features.norm(dim=-1, keepdim=True)
            
            # Convert to numpy
            embedding = self._to_numpy(text_features[0])
            
            inference_time = (time.time() - start_time) * 1000
            logger.debug(f"CLIP text encoding took {inference_time:.2f}ms")
            
            return embedding
            
        except Exception as e:
            logger.error(f"CLIP text encoding failed: {str(e)}")
            raise EncodingError(f"CLIP text encoding failed: {str(e)}")
    
    MAX_BATCH_SIZE = 32

    def _encode_images_chunk(self, pil_images: list) -> list:
        """Encode a single chunk of PIL images."""
        image_tensors = torch.stack([
            self.preprocessor(img) for img in pil_images
        ]).to(self.device)

        with torch.no_grad():
            image_features = self.model.encode_image(image_tensors)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)

        return list(self._to_numpy(image_features))

    def encode_images_batch(
        self,
        images: List[Union[bytes, Image.Image, np.ndarray]]
    ) -> List[np.ndarray]:
        """Encode multiple images in batch, automatically chunked to avoid OOM."""
        if not self._is_loaded:
            self.load()

        if self.preprocessor is None or self.model is None:
            raise RuntimeError("Model or preprocessor not loaded")

        try:
            pil_images = []
            for img in images:
                if isinstance(img, bytes):
                    pil_images.append(self._bytes_to_image(img))
                elif isinstance(img, np.ndarray):
                    pil_images.append(Image.fromarray(img))
                else:
                    pil_images.append(img)

            if len(pil_images) <= self.MAX_BATCH_SIZE:
                return self._encode_images_chunk(pil_images)

            results: list = []
            for i in range(0, len(pil_images), self.MAX_BATCH_SIZE):
                chunk = pil_images[i:i + self.MAX_BATCH_SIZE]
                results.extend(self._encode_images_chunk(chunk))
            return results

        except Exception as e:
            logger.error(f"CLIP batch encoding failed: {str(e)}")
            raise EncodingError(f"CLIP batch encoding failed: {str(e)}")
    
    def encode_texts_batch(self, texts: List[str]) -> List[np.ndarray]:
        """Encode multiple texts in batch."""
        if not self._is_loaded:
            self.load()
        
        if self.model is None:
            raise RuntimeError("Model not loaded")
        
        try:
            # Tokenize batch
            tokenizer = open_clip.get_tokenizer(self.model_variant)
            text_tokens = tokenizer(texts).to(self.device)
            
            # Encode batch
            with torch.no_grad():
                text_features = self.model.encode_text(text_tokens)
                # Normalize
                text_features = text_features / text_features.norm(dim=-1, keepdim=True)
            
            # Convert to numpy
            embeddings = self._to_numpy(text_features)
            
            return list(embeddings)
            
        except Exception as e:
            logger.error(f"CLIP batch text encoding failed: {str(e)}")
            raise EncodingError(f"CLIP batch text encoding failed: {str(e)}")
    
    def get_dimension(self) -> int:
        """Get CLIP embedding dimension."""
        return self.embedding_dim
    
    def supports_text(self) -> bool:
        """CLIP supports text encoding."""
        return True
    
    def supports_batch(self) -> bool:
        """CLIP supports batch processing."""
        return True

if __name__ == "__main__":
    # Example usage
    clip_embedder = CLIPEmbedding(model_variant='ViT-B-32', device='cpu')
    text_embedding = clip_embedder.encode_text("A photo of a cat")
    print(f"Text embedding shape: {text_embedding.shape}")

    image = Image.open("/home/appuser/src/dog.webp")
    image_embedding = clip_embedder.encode_image(image)
    print(f"Image embedding shape: {image_embedding.shape}")
