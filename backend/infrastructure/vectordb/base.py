# infrastructure/vectordb/base.py

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class VectorPoint:
    """Represents a vector point with metadata."""
    id: str
    vector: np.ndarray
    payload: Dict[str, Any]


@dataclass
class SearchResult:
    """Represents a search result."""
    id: str
    score: float
    payload: Dict[str, Any]


class BaseVectorDB(ABC):
    """Abstract base class for vector database clients."""
    
    def __init__(self, collection_name: str, config: Optional[Dict[str, Any]] = None):
        self.collection_name = collection_name
        self.config = config or {}
        self._client = None
    
    @abstractmethod
    def connect(self):
        """Initialize connection to vector database."""
        pass
    
    @abstractmethod
    def create_collection(self, dimension: int, distance_metric: str = 'cosine') -> bool:
        """
        Create a new collection.
        
        Args:
            dimension: Vector dimension
            distance_metric: 'cosine', 'euclidean', or 'dot'
            
        Returns:
            True if created successfully
        """
        pass
    
    @abstractmethod
    def collection_exists(self) -> bool:
        """Check if collection exists."""
        pass
    
    @abstractmethod
    def delete_collection(self) -> bool:
        """Delete collection."""
        pass
    
    @abstractmethod
    def upsert(self, points: List[VectorPoint]) -> bool:
        """
        Insert or update vector points.
        
        Args:
            points: List of VectorPoint objects
            
        Returns:
            True if successful
        """
        pass
    
    @abstractmethod
    def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """
        Search for similar vectors.
        
        Args:
            query_vector: Query embedding vector
            top_k: Number of results to return
            filters: Optional payload filters
            
        Returns:
            List of SearchResult objects
        """
        pass
    
    @abstractmethod
    def delete(self, point_ids: List[str]) -> bool:
        """
        Delete points by IDs.
        
        Args:
            point_ids: List of point IDs to delete
            
        Returns:
            True if successful
        """
        pass
    
    @abstractmethod
    def get_by_id(self, point_id: str) -> Optional[VectorPoint]:
        """Get point by ID."""
        pass
    
    @abstractmethod
    def count(self) -> int:
        """Get total number of vectors in collection."""
        pass
    
    @abstractmethod
    def get_info(self) -> Dict[str, Any]:
        """Get collection information."""
        pass


class VectorDBException(Exception):
    """Base exception for vector database operations."""
    pass


class CollectionNotFoundError(VectorDBException):
    """Raised when collection doesn't exist."""
    pass


class ConnectionError(VectorDBException):
    """Raised when connection to vector DB fails."""
    pass