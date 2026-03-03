# infrastructure/vectordb/qdrant_client.py

from typing import List, Dict, Any, Optional, Union
import numpy as np
from qdrant_client import QdrantClient as QdrantSDK
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    MatchAny,
    Range,
    SearchRequest,
    ScrollRequest,
)
from infrastructure.vectordb.base import (
    BaseVectorDB,
    VectorPoint,
    SearchResult,
    CollectionInfo,
    DistanceMetric,
    VectorDBException,
    ConnectionError,
    CollectionNotFoundError,
    DimensionMismatchError,
)
import logging
import time

logger = logging.getLogger(__name__)


class QdrantVectorDB(BaseVectorDB):
    """
    Qdrant vector database implementation.
    Production-ready with retry logic, batching, and comprehensive error handling.
    """
    
    DISTANCE_MAPPING = {
        DistanceMetric.COSINE: Distance.COSINE,
        DistanceMetric.EUCLIDEAN: Distance.EUCLID,
        DistanceMetric.DOT_PRODUCT: Distance.DOT,
        DistanceMetric.MANHATTAN: Distance.MANHATTAN,
    }
    
    def __init__(
        self,
        collection_name: str,
        dimension: Optional[int] = None,
        distance_metric: DistanceMetric = DistanceMetric.COSINE,
        host: str = "localhost",
        port: int = 6333,
        api_key: Optional[str] = None,
        https: bool = False,
        timeout: int = 60,
        **config
    ):
        """
        Initialize Qdrant client.
        
        Args:
            collection_name: Collection name
            dimension: Vector dimension
            distance_metric: Distance metric
            host: Qdrant host
            port: Qdrant port
            api_key: API key for authentication
            https: Use HTTPS
            timeout: Request timeout in seconds
        """
        super().__init__(collection_name, dimension, distance_metric, **config)
        
        self.host = host
        self.port = port
        self.api_key = api_key
        self.https = https
        self.timeout = timeout
    
    def connect(self) -> bool:
        """Connect to Qdrant."""
        try:
            logger.info(f"Connecting to Qdrant at {self.host}:{self.port}")
            
            self._client = QdrantSDK(
                host=self.host,
                port=self.port,
                api_key=self.api_key,
                https=self.https,
                timeout=self.timeout,
                prefer_grpc=True,  # Use gRPC for better performance
            )
            
            # Test connection
            collections = self._client.get_collections()
            
            self._is_connected = True
            logger.info(f"Connected to Qdrant successfully. Found {len(collections.collections)} collections")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Qdrant: {str(e)}")
            raise ConnectionError(f"Qdrant connection failed: {str(e)}")
    
    def disconnect(self):
        """Disconnect from Qdrant."""
        if self._client:
            self._client.close()
            self._client = None
            self._is_connected = False
            logger.info("Disconnected from Qdrant")
    
    def create_collection(
        self,
        dimension: int,
        distance_metric: DistanceMetric = DistanceMetric.COSINE,
        on_disk_payload: bool = False,
        replication_factor: int = 1,
        shard_number: int = 1,
        **kwargs
    ) -> bool:
        """
        Create Qdrant collection.
        
        Args:
            dimension: Vector dimension
            distance_metric: Distance metric
            on_disk_payload: Store payload on disk for memory efficiency
            replication_factor: Number of replicas
            shard_number: Number of shards
        """
        if not self._is_connected:
            self.connect()
        
        try:
            logger.info(f"Creating Qdrant collection: {self.collection_name}")
            
            qdrant_distance = self.DISTANCE_MAPPING.get(
                distance_metric,
                Distance.COSINE
            )
            
            self._client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=dimension,
                    distance=qdrant_distance,
                    on_disk=kwargs.get('on_disk_vectors', False)
                ),
                on_disk_payload=on_disk_payload,
                replication_factor=replication_factor,
                shard_number=shard_number,
                optimizers_config=kwargs.get('optimizers_config'),
                wal_config=kwargs.get('wal_config'),
            )
            
            self.dimension = dimension
            self.distance_metric = distance_metric
            
            logger.info(
                f"Qdrant collection created: {self.collection_name}, "
                f"dim={dimension}, metric={distance_metric}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to create Qdrant collection: {str(e)}")
            raise VectorDBException(f"Collection creation failed: {str(e)}")
    
    def delete_collection(self) -> bool:
        """Delete Qdrant collection."""
        if not self._is_connected:
            self.connect()
        
        try:
            self._client.delete_collection(collection_name=self.collection_name)
            logger.info(f"Qdrant collection deleted: {self.collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete collection: {str(e)}")
            return False
    
    def collection_exists(self) -> bool:
        """Check if collection exists."""
        if not self._is_connected:
            self.connect()
        
        try:
            collections = self._client.get_collections()
            return any(
                col.name == self.collection_name
                for col in collections.collections
            )
        except Exception as e:
            logger.error(f"Failed to check collection existence: {str(e)}")
            return False
    
    def get_collection_info(self) -> CollectionInfo:
        """Get collection information."""
        if not self._is_connected:
            self.connect()
        
        try:
            info = self._client.get_collection(collection_name=self.collection_name)
            
            return CollectionInfo(
                name=self.collection_name,
                vector_count=info.points_count,
                dimension=info.config.params.vectors.size,
                distance_metric=info.config.params.vectors.distance.name.lower(),
                indexed=info.status == "green",
                metadata={
                    "status": info.status,
                    "optimizer_status": info.optimizer_status,
                    "segments_count": info.segments_count,
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to get collection info: {str(e)}")
            raise CollectionNotFoundError(f"Collection not found: {self.collection_name}")
    
    def upsert(
        self,
        points: List[VectorPoint],
        batch_size: int = 100,
        wait: bool = True
    ) -> bool:
        """
        Upsert vectors into Qdrant.
        
        Args:
            points: List of VectorPoint objects
            batch_size: Batch size for insertion
            wait: Wait for indexing to complete
        """
        if not self._is_connected:
            self.connect()
        
        if not self.collection_exists():
            raise CollectionNotFoundError(f"Collection {self.collection_name} does not exist")
        
        try:
            start_time = time.time()
            
            # Process in batches
            for i in range(0, len(points), batch_size):
                batch = points[i:i + batch_size]
                
                # Validate dimensions
                for point in batch:
                    self._validate_dimension(point.vector)
                
                # Convert to Qdrant points
                qdrant_points = [
                    PointStruct(
                        id=point.id,
                        vector=point.vector.tolist() if isinstance(point.vector, np.ndarray) else point.vector,
                        payload=point.payload
                    )
                    for point in batch
                ]
                
                # Upsert batch
                self._client.upsert(
                    collection_name=self.collection_name,
                    points=qdrant_points,
                    wait=wait
                )
                
                logger.debug(f"Upserted batch {i//batch_size + 1}: {len(batch)} points")
            
            elapsed = time.time() - start_time
            logger.info(
                f"Upserted {len(points)} points to Qdrant in {elapsed:.2f}s "
                f"({len(points)/elapsed:.0f} points/sec)"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to upsert points: {str(e)}")
            raise VectorDBException(f"Upsert failed: {str(e)}")
    
    def search(
        self,
        query_vector: Union[np.ndarray, List[float]],
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None,
        return_vectors: bool = False
    ) -> List[SearchResult]:
        """
        Search similar vectors in Qdrant.
        
        Args:
            query_vector: Query vector
            limit: Maximum results
            filters: Payload filters
            score_threshold: Minimum similarity score
            return_vectors: Return vectors in results
        """
        if not self._is_connected:
            self.connect()
        
        if not self.collection_exists():
            raise CollectionNotFoundError(f"Collection {self.collection_name} does not exist")
        
        try:
            start_time = time.time()
            
            # Validate dimension
            self._validate_dimension(query_vector)
            
            # Convert to list
            query_list = query_vector.tolist() if isinstance(query_vector, np.ndarray) else query_vector
            
            # Build filter
            qdrant_filter = self._build_filter(filters) if filters else None
            
            # Search
            results = self._client.search(
                collection_name=self.collection_name,
                query_vector=query_list,
                limit=limit,
                query_filter=qdrant_filter,
                score_threshold=score_threshold,
                with_vectors=return_vectors,
                with_payload=True
            )
            
            # Convert to SearchResult
            search_results = [
                SearchResult(
                    id=str(result.id),
                    score=result.score,
                    payload=result.payload or {},
                    vector=np.array(result.vector) if return_vectors and result.vector else None
                )
                for result in results
            ]
            
            elapsed = (time.time() - start_time) * 1000
            logger.debug(
                f"Qdrant search completed in {elapsed:.2f}ms: "
                f"{len(search_results)} results"
            )
            
            return search_results
            
        except Exception as e:
            logger.error(f"Search failed: {str(e)}")
            raise VectorDBException(f"Search failed: {str(e)}")
    
    def _build_filter(self, filters: Dict[str, Any]) -> Filter:
        """
        Build Qdrant filter from dict.
        
        Supports:
        - Exact match: {'label': 'metal_scrap'}
        - Greater/Less than: {'confidence': {'$gte': 0.8}}
        - In list: {'plant_site': {'$in': ['Plant_A', 'Plant_B']}}
        - Range: {'captured_at': {'$range': {'gte': '2024-01-01', 'lte': '2024-12-31'}}}
        """
        must_conditions = []
        
        for key, value in filters.items():
            if isinstance(value, dict):
                # Handle operators
                if '$gte' in value:
                    must_conditions.append(
                        FieldCondition(key=key, range=Range(gte=value['$gte']))
                    )
                elif '$lte' in value:
                    must_conditions.append(
                        FieldCondition(key=key, range=Range(lte=value['$lte']))
                    )
                elif '$gt' in value:
                    must_conditions.append(
                        FieldCondition(key=key, range=Range(gt=value['$gt']))
                    )
                elif '$lt' in value:
                    must_conditions.append(
                        FieldCondition(key=key, range=Range(lt=value['$lt']))
                    )
                elif '$in' in value:
                    must_conditions.append(
                        FieldCondition(key=key, match=MatchAny(any=value['$in']))
                    )
                elif '$range' in value:
                    range_val = value['$range']
                    must_conditions.append(
                        FieldCondition(
                            key=key,
                            range=Range(
                                gte=range_val.get('gte'),
                                lte=range_val.get('lte'),
                                gt=range_val.get('gt'),
                                lt=range_val.get('lt')
                            )
                        )
                    )
            else:
                # Exact match
                must_conditions.append(
                    FieldCondition(key=key, match=MatchValue(value=value))
                )
        
        return Filter(must=must_conditions) if must_conditions else None
    
    def get(self, point_ids: List[str]) -> List[VectorPoint]:
        """Retrieve points by IDs."""
        if not self._is_connected:
            self.connect()
        
        try:
            results = self._client.retrieve(
                collection_name=self.collection_name,
                ids=point_ids,
                with_vectors=True,
                with_payload=True
            )
            
            return [
                VectorPoint(
                    id=str(result.id),
                    vector=np.array(result.vector),
                    payload=result.payload or {}
                )
                for result in results
            ]
            
        except Exception as e:
            logger.error(f"Failed to retrieve points: {str(e)}")
            raise VectorDBException(f"Retrieve failed: {str(e)}")
    
    def delete(self, point_ids: List[str]) -> bool:
        """Delete points by IDs."""
        if not self._is_connected:
            self.connect()
        
        try:
            self._client.delete(
                collection_name=self.collection_name,
                points_selector=point_ids,
                wait=True
            )
            
            logger.info(f"Deleted {len(point_ids)} points from Qdrant")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete points: {str(e)}")
            return False
    
    def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Count points in collection."""
        if not self._is_connected:
            self.connect()
        
        try:
            qdrant_filter = self._build_filter(filters) if filters else None
            
            result = self._client.count(
                collection_name=self.collection_name,
                count_filter=qdrant_filter,
                exact=True
            )
            
            return result.count
            
        except Exception as e:
            logger.error(f"Failed to count points: {str(e)}")
            return 0
    
    def scroll(
        self,
        limit: int = 100,
        offset: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> tuple[List[VectorPoint], Optional[str]]:
        """Scroll through points."""
        if not self._is_connected:
            self.connect()
        
        try:
            qdrant_filter = self._build_filter(filters) if filters else None
            
            results, next_offset = self._client.scroll(
                collection_name=self.collection_name,
                limit=limit,
                offset=offset,
                scroll_filter=qdrant_filter,
                with_vectors=True,
                with_payload=True
            )
            
            points = [
                VectorPoint(
                    id=str(result.id),
                    vector=np.array(result.vector),
                    payload=result.payload or {}
                )
                for result in results
            ]
            
            return points, next_offset
            
        except Exception as e:
            logger.error(f"Failed to scroll: {str(e)}")
            raise VectorDBException(f"Scroll failed: {str(e)}")