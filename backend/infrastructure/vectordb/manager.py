# infrastructure/vectordb/manager.py

from typing import List, Dict, Any, Optional, Union
import numpy as np
from infrastructure.vectordb.base import (
    BaseVectorDB,
    VectorPoint,
    SearchResult,
    CollectionInfo,
    DistanceMetric,
    VectorDBException
)
from infrastructure.vectordb.qdrant_client import QdrantVectorDB
from infrastructure.vectordb.faiss_client import FAISSVectorDB
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class VectorDBManager:
    """
    Unified vector database manager.
    Factory pattern for creating appropriate vector DB client.
    """
    
    DB_TYPES = {
        'qdrant': QdrantVectorDB,
        'faiss': FAISSVectorDB,
    }
    
    @staticmethod
    def create(
        db_type: str,
        collection_name: str,
        dimension: Optional[int] = None,
        distance_metric: DistanceMetric = DistanceMetric.COSINE,
        **config
    ) -> BaseVectorDB:
        """
        Create vector DB client.
        
        Args:
            db_type: 'qdrant' or 'faiss'
            collection_name: Collection/index name
            dimension: Vector dimension
            distance_metric: Distance metric
            **config: DB-specific configuration
            
        Returns:
            Vector DB client instance
        """
        db_type = db_type.lower()
        
        if db_type not in VectorDBManager.DB_TYPES:
            raise ValueError(
                f"Unsupported vector DB type: {db_type}. "
                f"Available: {list(VectorDBManager.DB_TYPES.keys())}"
            )
        
        # Get configuration from settings if not provided
        if db_type == 'qdrant':
            default_config = {
                'host': getattr(settings, 'QDRANT_HOST', 'localhost'),
                'port': getattr(settings, 'QDRANT_PORT', 6333),
                'api_key': getattr(settings, 'QDRANT_API_KEY', None),
                'https': getattr(settings, 'QDRANT_USE_HTTPS', False),
                'timeout': getattr(settings, 'QDRANT_TIMEOUT', 60),
            }
        elif db_type == 'faiss':
            default_config = {
                'storage_path': getattr(settings, 'FAISS_STORAGE_PATH', '/tmp/faiss_indices'),
                'index_type': getattr(settings, 'FAISS_INDEX_TYPE', 'Flat'),
                'use_gpu': getattr(settings, 'FAISS_USE_GPU', False),
            }
        else:
            default_config = {}
        
        # Merge with provided config
        final_config = {**default_config, **config}
        
        # Create client
        client_class = VectorDBManager.DB_TYPES[db_type]
        client = client_class(
            collection_name=collection_name,
            dimension=dimension,
            distance_metric=distance_metric,
            **final_config
        )
        
        logger.info(f"Created {db_type} vector DB client: {collection_name}")
        
        return client
    
    @staticmethod
    def create_from_tenant_config(
        tenant_collection_name: str,
        dimension: int,
        distance_metric: DistanceMetric = DistanceMetric.COSINE
    ) -> BaseVectorDB:
        """
        Create vector DB client using default system configuration.
        
        Args:
            tenant_collection_name: Tenant's collection name
            dimension: Vector dimension
            distance_metric: Distance metric
            
        Returns:
            Vector DB client instance
        """
        default_db_type = getattr(settings, 'DEFAULT_VECTOR_DB', 'qdrant')
        
        return VectorDBManager.create(
            db_type=default_db_type,
            collection_name=tenant_collection_name,
            dimension=dimension,
            distance_metric=distance_metric
        )


def get_vector_db(
    collection_name: str,
    db_type: Optional[str] = None,
    dimension: Optional[int] = None,
    **config
) -> BaseVectorDB:
    """
    Convenience function to get vector DB client.
    
    Args:
        collection_name: Collection name
        db_type: 'qdrant' or 'faiss' (defaults to settings)
        dimension: Vector dimension
        **config: Additional configuration
        
    Returns:
        Connected vector DB client
    """
    if db_type is None:
        db_type = getattr(settings, 'DEFAULT_VECTOR_DB', 'qdrant')
    
    client = VectorDBManager.create(
        db_type=db_type,   #type: ignore
        collection_name=collection_name,
        dimension=dimension,
        **config
    )
    
    client.connect()
    
    return client