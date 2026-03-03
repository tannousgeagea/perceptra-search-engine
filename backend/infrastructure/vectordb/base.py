# infrastructure/vectordb/base.py

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union
import numpy as np
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class DistanceMetric(str, Enum):
    """Supported distance metrics."""
    COSINE = "cosine"
    EUCLIDEAN = "euclidean"
    DOT_PRODUCT = "dot"
    MANHATTAN = "manhattan"


@dataclass
class VectorPoint:
    """Represents a vector point with metadata."""
    id: str
    vector: Union[np.ndarray, List[float]]
    payload: Dict[str, Any]
    
    def __post_init__(self):
        """Ensure vector is numpy array."""
        if isinstance(self.vector, list):
            self.vector = np.array(self.vector, dtype=np.float32)
        elif isinstance(self.vector, np.ndarray):
            self.vector = self.vector.astype(np.float32)


@dataclass
class SearchResult:
    """Represents a search result."""
    id: str
    score: float
    payload: Dict[str, Any]
    vector: Optional[np.ndarray] = None
    
    def __repr__(self):
        return f"SearchResult(id={self.id}, score={self.score:.4f})"


@dataclass
class CollectionInfo:
    """Collection metadata."""
    name: str
    vector_count: int
    dimension: int
    distance_metric: str
    indexed: bool
    metadata: Dict[str, Any]


class FilterOperator(str, Enum):
    """Filter operators for payload filtering."""
    EQ = "eq"  # Equal
    NE = "ne"  # Not equal
    GT = "gt"  # Greater than
    GTE = "gte"  # Greater than or equal
    LT = "lt"  # Less than
    LTE = "lte"  # Less than or equal
    IN = "in"  # In list
    NOT_IN = "not_in"  # Not in list
    CONTAINS = "contains"  # String contains
    RANGE = "range"  # Range query


class BaseVectorDB(ABC):
    """Abstract base class for vector database implementations."""
    
    def __init__(
        self,
        collection_name: str,
        dimension: Optional[int] = None,
        distance_metric: DistanceMetric = DistanceMetric.COSINE,
        **config
    ):
        """
        Initialize vector database client.
        
        Args:
            collection_name: Name of the collection/index
            dimension: Vector dimension
            distance_metric: Distance metric to use
            **config: Additional configuration parameters
        """
        self.collection_name = collection_name
        self.dimension = dimension
        self.distance_metric = distance_metric
        self.config = config
        self._client = None
        self._is_connected = False
    
    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to vector database.
        
        Returns:
            True if connection successful
        """
        pass
    
    @abstractmethod
    def disconnect(self):
        """Close connection to vector database."""
        pass
    
    @abstractmethod
    def create_collection(
        self,
        dimension: int,
        distance_metric: DistanceMetric = DistanceMetric.COSINE,
        **kwargs
    ) -> bool:
        """
        Create a new collection/index.
        
        Args:
            dimension: Vector dimension
            distance_metric: Distance metric
            **kwargs: Additional parameters
            
        Returns:
            True if created successfully
        """
        pass
    
    @abstractmethod
    def delete_collection(self) -> bool:
        """
        Delete the collection/index.
        
        Returns:
            True if deleted successfully
        """
        pass
    
    @abstractmethod
    def collection_exists(self) -> bool:
        """
        Check if collection exists.
        
        Returns:
            True if collection exists
        """
        pass
    
    @abstractmethod
    def get_collection_info(self) -> CollectionInfo:
        """
        Get collection metadata.
        
        Returns:
            CollectionInfo object
        """
        pass
    
    @abstractmethod
    def upsert(
        self,
        points: List[VectorPoint],
        batch_size: int = 100
    ) -> bool:
        """
        Insert or update vectors.
        
        Args:
            points: List of VectorPoint objects
            batch_size: Batch size for insertion
            
        Returns:
            True if successful
        """
        pass
    
    @abstractmethod
    def search(
        self,
        query_vector: Union[np.ndarray, List[float]],
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None,
        return_vectors: bool = False
    ) -> List[SearchResult]:
        """
        Search for similar vectors.
        
        Args:
            query_vector: Query vector
            limit: Maximum number of results
            filters: Payload filters
            score_threshold: Minimum similarity score
            return_vectors: Whether to return vectors in results
            
        Returns:
            List of SearchResult objects
        """
        pass
    
    @abstractmethod
    def get(self, point_ids: List[str]) -> List[VectorPoint]:
        """
        Retrieve vectors by IDs.
        
        Args:
            point_ids: List of point IDs
            
        Returns:
            List of VectorPoint objects
        """
        pass
    
    @abstractmethod
    def delete(self, point_ids: List[str]) -> bool:
        """
        Delete vectors by IDs.
        
        Args:
            point_ids: List of point IDs
            
        Returns:
            True if successful
        """
        pass
    
    @abstractmethod
    def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """
        Count vectors in collection.
        
        Args:
            filters: Optional filters
            
        Returns:
            Number of vectors
        """
        pass
    
    @abstractmethod
    def scroll(
        self,
        limit: int = 100,
        offset: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> tuple[List[VectorPoint], Optional[str]]:
        """
        Scroll through all vectors.
        
        Args:
            limit: Number of vectors per page
            offset: Pagination offset
            filters: Optional filters
            
        Returns:
            Tuple of (vectors, next_offset)
        """
        pass
    
    def _validate_dimension(self, vector: Union[np.ndarray, List[float]]):
        """Validate vector dimension."""
        vec_dim = len(vector) if isinstance(vector, list) else vector.shape[0]
        
        if self.dimension and vec_dim != self.dimension:
            raise ValueError(
                f"Vector dimension mismatch: expected {self.dimension}, got {vec_dim}"
            )
    
    def _to_numpy(self, vector: Union[np.ndarray, List[float]]) -> np.ndarray:
        """Convert vector to numpy array."""
        if isinstance(vector, list):
            return np.array(vector, dtype=np.float32)
        return vector.astype(np.float32)
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
    
    def __del__(self):
        """Cleanup on deletion."""
        if self._is_connected:
            try:
                self.disconnect()
            except:
                pass


class VectorDBException(Exception):
    """Base exception for vector DB operations."""
    pass


class ConnectionError(VectorDBException):
    """Connection failed."""
    pass


class CollectionNotFoundError(VectorDBException):
    """Collection doesn't exist."""
    pass


class DimensionMismatchError(VectorDBException):
    """Vector dimension mismatch."""
    pass


class InvalidFilterError(VectorDBException):
    """Invalid filter format."""
    pass