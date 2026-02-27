# infrastructure/vectordb/qdrant_client.py

from typing import List, Dict, Any, Optional
import numpy as np
from infrastructure.vectordb.base import (
    BaseVectorDB,
    VectorPoint,
    SearchResult,
    VectorDBException,
    CollectionNotFoundError,
    ConnectionError
)
import logging

logger = logging.getLogger(__name__)


class QdrantClient(BaseVectorDB):
    """Qdrant vector database client using perceptra."""
    
    def connect(self):
        """Initialize connection to Qdrant."""
        try:
            from perceptra.core.vector_store.qdrant_store import QdrantVectorStore as QdrantVectorDB
            
            host = self.config.get('host', 'localhost')
            port = self.config.get('port', 6333)
            api_key = self.config.get('api_key')
            use_https = self.config.get('use_https', False)
            
            # Connect to Qdrant
            self._client = QdrantVectorDB(
                collection_name=self.collection_name,
                host=host,
                port=port,
                api_key=api_key,
                https=use_https,
                dim=self.config.get('dimension', 512)
            )
            
            logger.info(f"Connected to Qdrant: {host}:{port}, collection: {self.collection_name}")
            
        except Exception as e:
            logger.error(f"Failed to connect to Qdrant: {str(e)}")
            raise ConnectionError(f"Qdrant connection failed: {str(e)}")
    
    def create_collection(self, dimension: int, distance_metric: str = 'cosine') -> bool:
        """
        Create a new Qdrant collection.
        
        Args:
            dimension: Vector dimension
            distance_metric: 'cosine', 'euclidean', or 'dot'
        """
        if self._client is None:
            self.connect()
        
        try:
            # Map distance metrics
            distance_map = {
                'cosine': 'Cosine',
                'euclidean': 'Euclid',
                'dot': 'Dot'
            }
            
            qdrant_distance = distance_map.get(distance_metric, 'Cosine')
            
            # Create collection using perceptra
            self._client.create_collection(
                vector_size=dimension,
                distance=qdrant_distance
            )
            
            logger.info(
                f"Qdrant collection created: {self.collection_name}, "
                f"dimension: {dimension}, metric: {distance_metric}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to create Qdrant collection: {str(e)}")
            raise VectorDBException(f"Collection creation failed: {str(e)}")
    
    def collection_exists(self) -> bool:
        """Check if collection exists."""
        if self._client is None:
            self.connect()
        
        try:
            return self._client.collection_exists()
        except Exception as e:
            logger.error(f"Failed to check collection existence: {str(e)}")
            return False
    
    def delete_collection(self) -> bool:
        """Delete collection."""
        if self._client is None:
            self.connect()
        
        try:
            self._client.delete_collection()
            logger.info(f"Qdrant collection deleted: {self.collection_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete collection: {str(e)}")
            return False
    
    def upsert(self, points: List[VectorPoint]) -> bool:
        """
        Insert or update vector points in Qdrant.
        
        Args:
            points: List of VectorPoint objects
        """
        if self._client is None:
            self.connect()
        
        if not self.collection_exists():
            raise CollectionNotFoundError(f"Collection {self.collection_name} does not exist")
        
        try:
            # Prepare points for Qdrant
            ids = [point.id for point in points]
            vectors = [point.vector.tolist() if isinstance(point.vector, np.ndarray) else point.vector 
                      for point in points]
            payloads = [point.payload for point in points]
            
            # Upsert using perceptra
            self._client.upsert(
                ids=ids,
                vectors=vectors,
                payloads=payloads
            )
            
            logger.info(f"Upserted {len(points)} points to Qdrant collection: {self.collection_name}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to upsert points: {str(e)}")
            raise VectorDBException(f"Upsert failed: {str(e)}")
    
    def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """
        Search for similar vectors in Qdrant.
        
        Args:
            query_vector: Query embedding vector
            top_k: Number of results to return
            filters: Optional payload filters
        """
        if self._client is None:
            self.connect()
        
        if not self.collection_exists():
            raise CollectionNotFoundError(f"Collection {self.collection_name} does not exist")
        
        try:
            # Convert numpy array to list
            query_list = query_vector.tolist() if isinstance(query_vector, np.ndarray) else query_vector
            
            # Build Qdrant filter
            qdrant_filter = self._build_qdrant_filter(filters) if filters else None
            
            # Search using perceptra
            results = self._client.search(
                query_vector=query_list,
                limit=top_k,
                filter=qdrant_filter
            )
            
            # Convert to SearchResult objects
            search_results = []
            for result in results:
                search_results.append(SearchResult(
                    id=result.id,
                    score=result.score,
                    payload=result.payload or {}
                ))
            
            logger.info(
                f"Qdrant search completed: {len(search_results)} results, "
                f"collection: {self.collection_name}"
            )
            
            return search_results
            
        except Exception as e:
            logger.error(f"Search failed: {str(e)}")
            raise VectorDBException(f"Search failed: {str(e)}")
    
    def _build_qdrant_filter(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build Qdrant filter from simple filter dict.
        
        Supports:
        - Exact match: {'label': 'metal_scrap'}
        - Range: {'confidence': {'$gte': 0.8}}
        - In list: {'plant_site': {'$in': ['Plant_A', 'Plant_B']}}
        """
        if not filters:
            return None
        
        must_conditions = []
        
        for key, value in filters.items():
            if isinstance(value, dict):
                # Range or list conditions
                if '$gte' in value:
                    must_conditions.append({
                        'key': key,
                        'range': {'gte': value['$gte']}
                    })
                elif '$lte' in value:
                    must_conditions.append({
                        'key': key,
                        'range': {'lte': value['$lte']}
                    })
                elif '$in' in value:
                    must_conditions.append({
                        'key': key,
                        'match': {'any': value['$in']}
                    })
            else:
                # Exact match
                must_conditions.append({
                    'key': key,
                    'match': {'value': value}
                })
        
        if not must_conditions:
            return None
        
        return {'must': must_conditions}
    
    def delete(self, point_ids: List[str]) -> bool:
        """Delete points by IDs."""
        if self._client is None:
            self.connect()
        
        try:
            self._client.delete(ids=point_ids)
            logger.info(f"Deleted {len(point_ids)} points from Qdrant")
            return True
        except Exception as e:
            logger.error(f"Failed to delete points: {str(e)}")
            return False
    
    def get_by_id(self, point_id: str) -> Optional[VectorPoint]:
        """Get point by ID."""
        if self._client is None:
            self.connect()
        
        try:
            result = self._client.retrieve(ids=[point_id])
            
            if not result:
                return None
            
            point = result[0]
            return VectorPoint(
                id=point.id,
                vector=np.array(point.vector),
                payload=point.payload or {}
            )
        except Exception as e:
            logger.error(f"Failed to get point by ID: {str(e)}")
            return None
    
    def count(self) -> int:
        """Get total number of vectors in collection."""
        if self._client is None:
            self.connect()
        
        try:
            info = self._client.get_collection_info()
            return info.get('vectors_count', 0)
        except Exception as e:
            logger.error(f"Failed to get count: {str(e)}")
            return 0
    
    def get_info(self) -> Dict[str, Any]:
        """Get collection information."""
        if self._client is None:
            self.connect()
        
        try:
            return self._client.get_collection_info()
        except Exception as e:
            logger.error(f"Failed to get collection info: {str(e)}")
            return {}