# infrastructure/storage/client.py

from typing import Optional, BinaryIO
import os
from django.conf import settings
from perceptra_storage import get_storage_adapter
from media.models import StorageBackend as StorageBackendChoice
import hashlib
import logging
from io import BytesIO

logger = logging.getLogger(__name__)


class StorageManager:
    """
    Unified storage manager using perceptra-storage.
    Handles Azure, S3, MinIO, and Local storage.
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
        logger.warning(f"Initializing storage client for backend: {self.backend}")
        if self.backend == StorageBackendChoice.AZURE:
            config = {
                'container_name': settings.AZURE_STORAGE_CONTAINER,
                'account_name': settings.AZURE_STORAGE_ACCOUNT_NAME,
            }

            credentials = {
                'connection_string': settings.AZURE_STORAGE_CONNECTION_STRING,
                'account_key': settings.AZURE_STORAGE_ACCOUNT_KEY,
                'sas_token': settings.AZURE_STORAGE_SAS_TOKEN,
            }


            self._client = get_storage_adapter(
                backend='azure',
                config=config,
                credentials=credentials
            )
        
        elif self.backend == StorageBackendChoice.S3:
            config = {
                'bucket_name': settings.AWS_S3_BUCKET,
                'region': settings.AWS_S3_REGION,
            }

            credentials = {
                'access_key_id': settings.AWS_ACCESS_KEY_ID,
                'secret_access_key': settings.AWS_SECRET_ACCESS_KEY,
                'session_token': None,  # Optional, if using temporary credentials
            }

            self._client = get_storage_adapter(
                backend='s3',
                config=config,
                credentials=credentials
            )
        
        elif self.backend == StorageBackendChoice.MINIO:
            self._client = get_storage_adapter(
                backend='minio',
                config={
                    'endpoint_url': settings.MINIO_ENDPOINT,
                    'bucket_name': settings.MINIO_BUCKET,
                    'secure': settings.MINIO_SECURE
                },
                credentials={
                    'access_key': settings.MINIO_ACCESS_KEY,
                    'secret_key': settings.MINIO_SECRET_KEY
                }
            )
        
        elif self.backend == StorageBackendChoice.LOCAL:
            self._client = get_storage_adapter(
                backend='local',
                config={
                    'base_path': os.path.join(settings.BASE_DIR, 'local_storage'),
                    'create_dirs': True
                },
                credentials={}
            )
        
        else:
            raise ValueError(f"Unsupported storage backend: {self.backend}")
    
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
        try:
            # Calculate checksum
            checksum = hashlib.sha256(content).hexdigest()
            
            if not self._client:
                raise RuntimeError("Storage client is not initialized.")
            
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
        try:
            if not self._client:
                raise RuntimeError("Storage client is not initialized.")
            
            self._client.delete_file(storage_key)
            logger.info(f"File deleted: {storage_key}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete {storage_key}: {str(e)}")
            return False
    
    async def exists(self, storage_key: str) -> bool:
        """Check if file exists."""
        try:
            if not self._client:
                raise RuntimeError("Storage client is not initialized.")
            
            return self._client.file_exists(storage_key)
        except Exception as e:
            logger.error(f"Failed to check existence of {storage_key}: {str(e)}")
            return False
    
    async def get_download_url(self, storage_key: str, expiry: int = 3600) -> str:
        """
        Generate pre-signed download URL.
        
        Args:
            storage_key: File path/key
            expiry: URL expiry time in seconds (default 1 hour)
        """
        try:

            if not self._client:
                raise RuntimeError("Storage client is not initialized.")
            
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