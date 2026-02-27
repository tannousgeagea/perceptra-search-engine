# infrastructure/embeddings/perception.py

from typing import Union, List, Optional
import numpy as np
from PIL import Image
import logging

import time
from .base import (
    BaseEmbeddingModel,
    ModelLoadError,
    EncodingError,
    TORCH_AVAILABLE
)

if TORCH_AVAILABLE:
    import torch
    try:
        import open_clip
        PERCEPTION_AVAILABLE = True
    except ImportError:
        PERCEPTION_AVAILABLE = False
        logging.warning("open_clip not available for Perception Encoder")
else:
    PERCEPTION_AVAILABLE = False

logger = logging.getLogger(__name__)


class PerceptionEncoder(BaseEmbeddingModel):
    """Meta's Perception Encoder from Facebook Research.
    
    The Perception Encoder (PE) is designed for:
    - Dense visual understanding
    - Object-centric embeddings
    - Fine-grained image features
    - Zero-shot transfer to downstream tasks
    
    Available models:
    - PE-Core-B-16: 768-d, 224x224 input
    - PE-Core-L-14-336: 1024-d, 336x336 input
    - PE-Core-bigG-14-448: 1280-d, 448x448 input
    """
    
    AVAILABLE_MODELS = {
        "PE-Core-L-14-336": {
            "model_id": "hf-hub:timm/PE-Core-L-14-336",
            "embedding_dim": 1024,
            "input_size": 336
        },
        "PE-Core-B-16": {
            "model_id": "hf-hub:timm/PE-Core-B-16",
            "embedding_dim": 1024,
            "input_size": 224
        },
        'PE-Core-bigG-14-448': {
            "model_id": "hf-hub:timm/PE-Core-bigG-14-448",
            "embedding_dim": 1280,
            "input_size": 448
        }
    }
    
    def __init__(
        self,
        model_name: str = "PE-Core-L14-336",
        device: str = "cpu",
        **kwargs
    ):
        if not PERCEPTION_AVAILABLE:
            raise ImportError(
                "OpenCLIP not installed for Perception Encoder. "
                "Install with: pip install open-clip-torch"
            )
        
        if model_name not in self.AVAILABLE_MODELS:
            raise ValueError(
                f"Model {model_name} not supported. "
                f"Choose from: {list(self.AVAILABLE_MODELS.keys())}"
            )
        
        self.model_config = self.AVAILABLE_MODELS[model_name]
        self._embedding_dim = self.model_config["embedding_dim"]

        super().__init__(
            model_name,
            device=device,
            **kwargs
        )

    @property
    def embedding_dim(self) -> int:
        return self._embedding_dim
    
    def load(self):
        """Load Perception Encoder model."""
        model_id = self.model_config["model_id"]
        
        logger.info(f"Loading Perception Encoder: {model_id}")
        
        try:
            # Load model and preprocessor
            self.model, _, self.preprocessor = open_clip.create_model_and_transforms(
                model_id,
            )
            
            self.model.to(self.device)
            self.model.eval()
            
            self._is_loaded = True
            
            logger.info(
                f"Perception Encoder loaded successfully "
                f"({self._embedding_dim}-d embeddings)"
            )
            
        except Exception as e:
            logger.error(f"Failed to load Perception Encoder: {str(e)}")
            logger.info(
                "Tip: You may need to install timm: pip install timm\n"
                "Or login to HuggingFace: huggingface-cli login"
            )
            raise ModelLoadError(f"Perception Encoder load failed: {str(e)}")
    
    def encode_image(self, image: Union[bytes, Image.Image, np.ndarray]) -> np.ndarray:
        """Encode image using Perception Encoder."""
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
            image_tensor = self.preprocessor(image).unsqueeze(0).to(self.device)
            
            # Encode with normalization
            with torch.no_grad():
                features = self.model.encode_image(image_tensor, normalize=True)
            
            # Convert to numpy
            embedding = self._to_numpy(features[0])
            
            inference_time = (time.time() - start_time) * 1000
            logger.debug(f"Perception Encoder encoding took {inference_time:.2f}ms")
            
            return embedding
            
        except Exception as e:
            logger.error(f"Perception Encoder encoding failed: {str(e)}")
            raise EncodingError(f"Perception Encoder encoding failed: {str(e)}")
    
    def encode_text(self, text: str) -> np.ndarray:
        """
        Encode text using Perception Encoder.
        Note: Some Perception models support text, others don't.
        """
        if not self._is_loaded:
            self.load()
        
        if self.model is None:
            raise RuntimeError("Model not loaded")
        
        # Check if model has text encoding capability
        if not hasattr(self.model, 'encode_text'):
            raise NotImplementedError(
                f"{self.model_name} does not support text encoding"
            )
        
        start_time = time.time()
        
        try:
            # Tokenize
            model_id = self.model_config["model_id"]
            tokenizer = open_clip.get_tokenizer(model_id)
            text_tokens = tokenizer([text]).to(self.device)
            
            # Encode
            with torch.no_grad():
                text_features = self.model.encode_text(text_tokens, normalize=True)
            
            # Convert to numpy
            embedding = self._to_numpy(text_features[0])
            
            inference_time = (time.time() - start_time) * 1000
            logger.debug(f"Perception text encoding took {inference_time:.2f}ms")
            
            return embedding
            
        except Exception as e:
            logger.error(f"Perception text encoding failed: {str(e)}")
            raise EncodingError(f"Perception text encoding failed: {str(e)}")
    
    def encode_images_batch(
        self,
        images: List[Union[bytes, Image.Image, np.ndarray]]
    ) -> List[np.ndarray]:
        """Encode multiple images in batch."""
        if not self._is_loaded:
            self.load()
        
        if self.preprocessor is None or self.model is None:
            raise RuntimeError("Model or preprocessor not loaded")
        
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
            ]).to(self.device)
            
            # Encode batch
            with torch.no_grad():
                features = self.model.encode_image(image_tensors, normalize=True)
            
            # Convert to numpy
            embeddings = self._to_numpy(features)
            
            return list(embeddings)
            
        except Exception as e:
            logger.error(f"Perception batch encoding failed: {str(e)}")
            raise EncodingError(f"Perception batch encoding failed: {str(e)}")
    
    def encode_texts_batch(self, texts: List[str]) -> List[np.ndarray]:
        """Encode multiple texts in batch."""
        if not self._is_loaded:
            self.load()
        
        if self.model is None:
            raise RuntimeError("Model not loaded")
        
        if not hasattr(self.model, 'encode_text'):
            raise NotImplementedError(
                f"{self.model_name} does not support text encoding"
            )
        
        try:
            # Tokenize batch
            model_id = self.model_config["model_id"]
            tokenizer = open_clip.get_tokenizer(model_id)
            text_tokens = tokenizer(texts).to(self.device)
            
            # Encode batch
            with torch.no_grad():
                text_features = self.model.encode_text(text_tokens, normalize=True)
            
            # Convert to numpy
            embeddings = self._to_numpy(text_features)
            
            return list(embeddings)
            
        except Exception as e:
            logger.error(f"Perception batch text encoding failed: {str(e)}")
            raise EncodingError(f"Perception batch text encoding failed: {str(e)}")
    
    def get_dimension(self) -> int:
        """Get embedding dimension."""
        return self.embedding_dim
    
    def supports_text(self) -> bool:
        """Check if this specific model supports text."""
        if not self._is_loaded:
            return False
        return hasattr(self.model, 'encode_text')
    
    def supports_batch(self) -> bool:
        """Perception Encoder supports batch processing."""
        return True
    
if __name__ == "__main__":
    from PIL import Image
    import numpy as np

    # Initialize encoder
    encoder = PerceptionEncoder(
        model_name="PE-Core-B-16",
        device="cpu"  # change to "cuda" if GPU available
    )

    # Test 1: Text (should fail or be disabled if supports_text=False)
    print("\n--- Testing Text Encoding ---")
    try:
        text_embedding = encoder.encode_text("A photo of a dog")
        print("Text embedding shape:", text_embedding.shape)
    except Exception as e:
        print("Text encoding not supported:", e)

    # Test 2: Image from file
    print("\n--- Testing Image File Encoding ---")
    image = Image.open("/home/appuser/src/dog.webp").convert("RGB")
    image_embedding = encoder.encode_image(image)
    print("Image embedding shape:", image_embedding.shape)
    print("Embedding dimension:", encoder.get_dimension())

    # Test 3: Image from numpy array
    print("\n--- Testing Numpy Image Encoding ---")
    np_image = np.array(image)
    np_embedding = encoder.encode_image(np_image)
    print("Numpy embedding shape:", np_embedding.shape)

    # Test 4: Batch encoding
    print("\n--- Testing Batch Encoding ---")
    batch_embeddings = encoder.encode_images_batch([image, image])
    print("Batch size:", len(batch_embeddings))
    print("Single embedding shape:", batch_embeddings[0].shape)

    print("\n✓ All tests completed successfully.")