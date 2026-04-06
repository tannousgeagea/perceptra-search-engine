# infrastructure/embeddings/generator.py

from typing import Optional, Dict, Any
import logging
from .base import BaseEmbeddingModel
from .clip import CLIPEmbedding, CLIP_AVAILABLE
from .perception import PerceptionEncoder, PERCEPTION_AVAILABLE

try:
    from .dinov2 import DINOv2Embedding
    DINOV2_AVAILABLE = True
except ImportError:
    DINOV2_AVAILABLE = False

try:
    from .sam3_encoder import SAM3Embedding, SAM3_AVAILABLE
except ImportError:
    SAM3_AVAILABLE = False

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """
    Unified embedding generator that manages model instances.
    Singleton pattern with model caching.
    """
    
    _instance = None
    _current_model: Optional[BaseEmbeddingModel] = None
    _current_model_name: Optional[str] = None
    _attention_pooler = None  # Lazy-loaded auxiliary model for saliency
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        self._available_models = self._discover_models()
    
    def _discover_models(self) -> Dict[str, type]:
        """Discover available embedding models."""
        models = {}
        
        if CLIP_AVAILABLE:
            models['clip'] = CLIPEmbedding
            logger.info("CLIP models available")
        
        if PERCEPTION_AVAILABLE:
            models['perception'] = PerceptionEncoder
            logger.info("Perception Encoder models available")

        if DINOV2_AVAILABLE:
            models['dinov2'] = DINOv2Embedding
            logger.info("DINOv2 models available")

        if SAM3_AVAILABLE:
            models['sam3'] = SAM3Embedding
            logger.info("SAM3 models available")
        
        if not models:
            logger.warning("No embedding models available!")
        
        return models
    
    def get_model(
        self,
        model_type: str,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
        force_reload: bool = False,
        **kwargs
    ) -> BaseEmbeddingModel:
        """
        Get or create embedding model instance.
        
        Args:
            model_type: 'clip' or 'perception'
            model_variant: Specific model variant
            device: Device to run on
            force_reload: Force reload even if cached
            **kwargs: Additional model-specific parameters
            
        Returns:
            Embedding model instance
        """
        model_key = f"{model_type}_{model_name or 'default'}_{device or 'auto'}"
        
        # Return cached model if same configuration and not forcing reload
        if (not force_reload and 
            self._current_model is not None and 
            self._current_model_name == model_key):
            logger.debug(f"Returning cached model: {model_key}")
            return self._current_model
        
        # Unload previous model if different
        if self._current_model is not None and self._current_model_name != model_key:
            logger.info(f"Switching from {self._current_model_name} to {model_key}")
            self._current_model.unload()
            self._current_model = None
        
        # Validate model type
        if model_type not in self._available_models:
            available = ', '.join(self._available_models.keys())
            raise ValueError(
                f"Unsupported model type: {model_type}. Available: {available}"
            )
        
        # Create new model
        model_class = self._available_models[model_type]
        
        # Model-specific defaults
        defaults = {
            'clip': 'ViT-B-32',
            'perception': 'PE-Core-B-16',
            'dinov2': 'vits14',
            'sam3': 'SAM3',
        }
        default_name = defaults.get(model_type)

        if default_name or model_name:
            model = model_class(
                model_name=model_name or default_name,
                device=device,
                **kwargs
            )
        else:
            model = model_class(device=device, **kwargs)
        
        # Load model
        model.load()
        
        # Cache model
        self._current_model = model
        self._current_model_name = model_key
        
        logger.info(f"Model loaded and cached: {model_key}")
        
        return model
    
    def get_attention_pooler(self, device: Optional[str] = None):
        """Get the shared attention pooler (lazy-loaded DINOv2-small).

        The pooler coexists with the primary model — it is lightweight
        (~22M params) and runs a single forward pass for saliency.
        """
        if self._attention_pooler is None:
            from infrastructure.embeddings.attention_pooling import AttentionPooler
            self._attention_pooler = AttentionPooler(device=device)
        return self._attention_pooler

    def clear_cache(self):
        """Clear cached model."""
        if self._current_model is not None:
            self._current_model.unload()
            self._current_model = None
            self._current_model_name = None
        if self._attention_pooler is not None:
            self._attention_pooler.unload()
            self._attention_pooler = None
        logger.info("Model cache cleared")
    
    def list_available_models(self) -> Dict[str, Any]:
        """List all available models and their variants."""
        available = {}
        
        if CLIP_AVAILABLE:
            available['clip'] = {
                'class': 'CLIPEmbedding',
                'variants': list(CLIPEmbedding.AVAILABLE_MODELS.keys()),
                'supports_text': True
            }
        
        if PERCEPTION_AVAILABLE:
            available['perception'] = {
                'class': 'PerceptionEncoder',
                'variants': list(PerceptionEncoder.AVAILABLE_MODELS.keys()),
                'supports_text': 'conditional'
            }

        if DINOV2_AVAILABLE:
            available['dinov2'] = {
                'class': 'DINOv2Embedding',
                'variants': list(DINOv2Embedding.AVAILABLE_MODELS.keys()),
                'supports_text': False
            }

        if SAM3_AVAILABLE:
            available['sam3'] = {
                'class': 'SAM3Embedding',
                'variants': list(SAM3Embedding.AVAILABLE_MODELS.keys()),
                'supports_text': False
            }

        return available


# Singleton accessor
def get_embedding_generator() -> EmbeddingGenerator:
    """Get singleton embedding generator instance."""
    return EmbeddingGenerator()