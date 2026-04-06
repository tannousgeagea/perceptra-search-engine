import logging
from typing import Dict, Optional

from .base import BaseDetectionBackend

logger = logging.getLogger(__name__)


class DetectionBackendRegistry:
    """Singleton registry for detection backends.

    Caches loaded model instances per ``(backend_name, device)`` key so
    that heavyweight models (e.g. SAM3) are loaded only once per worker
    process.
    """

    _instance: Optional['DetectionBackendRegistry'] = None
    _backends: Dict[str, BaseDetectionBackend]

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._backends = {}
        return cls._instance

    def get_backend(
        self,
        backend_name: str,
        device: Optional[str] = None,
        **kwargs,
    ) -> BaseDetectionBackend:
        """Get or create a detection backend instance.

        The backend model is loaded on first access and cached for
        subsequent calls with the same ``(backend_name, device)`` key.
        """
        cache_key = f"{backend_name}_{device or 'auto'}"

        if cache_key in self._backends:
            logger.debug(f"Returning cached detection backend: {cache_key}")
            return self._backends[cache_key]

        backend = self._create_backend(backend_name, device, **kwargs)
        backend.load()
        self._backends[cache_key] = backend

        logger.info(f"Detection backend loaded and cached: {cache_key}")
        return backend

    def _create_backend(
        self,
        backend_name: str,
        device: Optional[str] = None,
        **kwargs,
    ) -> BaseDetectionBackend:
        """Instantiate a backend by name (without loading weights)."""
        if backend_name == 'sam3_perceptra':
            from .sam3_perceptra import SAM3PerceptraBackend
            return SAM3PerceptraBackend(device=device, **kwargs)
        else:
            raise ValueError(
                f"Unknown detection backend: {backend_name!r}. "
                f"Available: ['sam3_perceptra']"
            )

    def clear(self) -> None:
        """Unload all cached backends and free resources."""
        for key, backend in self._backends.items():
            logger.info(f"Unloading detection backend: {key}")
            backend.unload()
        self._backends.clear()

    def list_backends(self) -> list:
        """Return names of all registered backend types."""
        return ['sam3_perceptra']


def get_detection_registry() -> DetectionBackendRegistry:
    """Get the singleton detection backend registry."""
    return DetectionBackendRegistry()
