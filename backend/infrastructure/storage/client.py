# infrastructure/storage/client.py

from typing import Optional
from pathlib import Path
from django.conf import settings
from perceptra_storage import get_storage_adapter
from media.models import StorageBackend as StorageBackendChoice
import hashlib
import logging
import asyncio
from io import BytesIO

logger = logging.getLogger(__name__)

class StorageManagerSyncMixin:
    """
    Synchronous wrappers for async storage methods.
    Used by Celery tasks which run in a standard sync worker.
    Creates a new event loop per call — acceptable in a Celery worker
    because workers are single-threaded per process and there is no
    running loop to conflict with.
    """

    def download_sync(self, storage_key: str) -> bytes:
        return asyncio.run(self.download(storage_key))  # type: ignore

    def save_sync(
        self,
        storage_key: str,
        content: bytes,
        content_type: str = 'application/octet-stream',
        metadata: Optional[dict] = None,
    ) -> None:
        asyncio.run(self.save(storage_key, content, content_type, metadata or {}))  # type: ignore

    def delete_sync(self, storage_key: str) -> bool:
        return asyncio.run(self.delete(storage_key))  # type: ignore

    def get_download_url_sync(self, storage_key: str, expiry: int = 3600) -> str:
        return asyncio.run(self.get_download_url(storage_key, expiry))  # type: ignore

    def exists_sync(self, storage_key: str) -> bool:
        return asyncio.run(self.exists(storage_key))  # type: ignore

class StorageManager(StorageManagerSyncMixin):
    """
    Unified storage manager using perceptra-storage.
    Handles Azure, S3, MinIO, and Local storage.

    Async methods are used by FastAPI handlers.
    Sync methods (via StorageManagerSyncMixin) are used by Celery tasks.

    Note: the underlying perceptra_storage adapter is synchronous. The async
    methods here are thin coroutine wrappers so FastAPI can await them without
    blocking. No actual async I/O occurs inside the adapter itself.
    """
    
    def __init__(self, backend: Optional[str] = None):
        """
        Initialize storage client based on backend type.
        
        Args:
            backend: Storage backend type ('azure', 's3', 'minio', 'local')
                    If None, uses STORAGE_BACKEND from settings
        """
        self.backend = backend or settings.STORAGE_BACKEND
        self._client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the appropriate storage client."""
        logger.info(f"Initializing storage client for backend: {self.backend}")
        if self.backend == StorageBackendChoice.AZURE:
            self._client = get_storage_adapter(
                backend='azure',
                config={
                    'container_name': settings.AZURE_STORAGE_CONTAINER,
                    'account_name': settings.AZURE_STORAGE_ACCOUNT_NAME,
                },
                credentials={
                    'connection_string': settings.AZURE_STORAGE_CONNECTION_STRING,
                    'account_key': settings.AZURE_STORAGE_ACCOUNT_KEY,
                    'sas_token': settings.AZURE_STORAGE_SAS_TOKEN,
                },
            )
        
        elif self.backend == StorageBackendChoice.S3:
            self._client = get_storage_adapter(
                backend='s3',
                config={
                    'bucket_name': settings.AWS_S3_BUCKET,
                    'region': settings.AWS_S3_REGION,
                },
                credentials={
                    'access_key_id': settings.AWS_ACCESS_KEY_ID,
                    'secret_access_key': settings.AWS_SECRET_ACCESS_KEY,
                    'session_token': None,
                },
            )
        
        elif self.backend == StorageBackendChoice.MINIO:
            self._client = get_storage_adapter(
                backend='minio',
                config={
                    'endpoint_url': settings.MINIO_ENDPOINT,
                    'bucket_name': settings.MINIO_BUCKET,
                    'secure': settings.MINIO_SECURE,
                },
                credentials={
                    'access_key': settings.MINIO_ACCESS_KEY,
                    'secret_key': settings.MINIO_SECRET_KEY,
                },
            )
        
        elif self.backend == StorageBackendChoice.LOCAL:
            self._client = get_storage_adapter(
                backend='local',
                config={
                    'base_path': settings.STORAGE_PATH,
                    'create_dirs': True
                },
                credentials={}
            )
        
        else:
            raise ValueError(f"Unsupported storage backend: {self.backend}")
    
    def _assert_client(self):
        if not self._client:
            raise RuntimeError("Storage client is not initialized.")

    async def save(
        self, 
        storage_key: str, 
        content: bytes, 
        content_type: Optional[str],
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Save file to storage.
        
        Args:
            storage_key: Path/key where file will be stored
            content: File content as bytes
            
        Returns:
            dict with 'storage_key', 'size', 'checksum'
        """
        self._assert_client()
        try:
            # Calculate checksum
            checksum = hashlib.sha256(content).hexdigest()
            
            # Save to storage
            self._client.upload_file(
                BytesIO(content),
                key=storage_key,
                content_type=content_type or 'image/jpeg',  # Default to JPEG if content type is not provided,
                metadata=metadata or {}
            )
            
            logger.info(f"File saved: {storage_key} ({len(content)} bytes)")
            
            return {
                'storage_key': storage_key,
                'size': len(content),
                'checksum': checksum
            }
        
        except Exception as e:
            logger.error(f"Failed to save {storage_key}: {str(e)}")
            raise
    
    async def delete(self, storage_key: str) -> bool:
        """Delete file from storage."""
        self._assert_client()
        try:
            self._client.delete_file(storage_key)
            logger.info(f"File deleted: {storage_key}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete {storage_key}: {str(e)}")
            return False
    
    async def exists(self, storage_key: str) -> bool:
        """Check if file exists."""
        self._assert_client()
        try:
            return self._client.file_exists(storage_key)
        except Exception as e:
            logger.error(f"Failed to check existence of {storage_key}: {str(e)}")
            return False
    
    async def download(self, storage_key: str, destination: Optional[Path] = None) -> bytes:
        """
        Download file from storage.
        
        Args:
            storage_key: File path/key to download
            destination: Optional local path to save the file
            
        Returns:
            File content as bytes (if destination is None)
        """
        self._assert_client()
        try:            
            logger.info(f"Downloading file: {storage_key}")
            
            # Download file using perceptra-storage
            # If destination is provided, it saves to file and returns bytes
            # If destination is None, it just returns bytes
            content = self._client.download_file(
                key=storage_key,
                destination=destination
            )
            
            logger.info(f"File downloaded: {storage_key} ({len(content)} bytes)")
            
            return content
            
        except Exception as e:
            logger.error(f"Failed to download {storage_key}: {str(e)}")
            raise

    async def get_download_url(self, storage_key: str, expiry: int = 3600) -> str:
        """
        Generate pre-signed download URL.
        
        Args:
            storage_key: File path/key
            expiry: URL expiry time in seconds (default 1 hour)
        """
        self._assert_client()
        try:
            return self._client.generate_presigned_url(
                storage_key,
                expiration=expiry,
                method='GET'
            ).url
        except Exception as e:
            logger.error(f"Failed to generate URL for {storage_key}: {str(e)}")
            return ""
    
    def get_backend_type(self) -> str:
        """Get current backend type."""
        return self.backend

def get_storage_manager(backend: Optional[str] = None) -> StorageManager:
    """Factory function to get storage manager instance."""
    return StorageManager(backend=backend)