# infrastructure/vectordb/faiss_client.py

from typing import List, Dict, Any, Optional
import numpy as np
import pickle
import os
from pathlib import Path
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


class FAISSClient(BaseVectorDB):
    """FAISS vector database client using perceptra."""
    
    def __init__(self, collection_name: str, config: Dict[str, Any] = None):
        super().__init__(collection_name, config)
        
        # FAISS storage path
        self.storage_path = self.config.get('storage_path', '/tmp/faiss_indices')
        Path(self.storage_path).mkdir(parents=True, exist_ok=True)
        
        # Index file paths
        self.index_file = os.path.join(self.storage_path, f"{collection_name}.index")
        self.metadata_file = os.path.join(self.storage_path, f"{collection_name}.metadata.pkl")
        
        # In-memory metadata store
        self._id_to_idx = {}  # Map point_id to FAISS index
        self._idx_to_id = {}  # Map FAISS index to point_id
        self._payloads = {}   # Map point_id to payload
        self._next_idx = 0
    
    def connect(self):
        """Initialize FAISS client."""
        try:
            from perceptra.core.vector_store.faiss_store import FAISSVectorStore as FAISSVectorDB
            self._client = FAISSVectorDB(dim=self.config.get('dimension', 512), index_type='Flat')
            # Load existing index if exists
            if os.path.exists(self.index_file):
                self._client = FAISSVectorDB.load(path=self.index_file)
                self._load_metadata()
                logger.info(f"Loaded existing FAISS index: {self.collection_name}")
            else:
                self._client = None
                logger.info(f"FAISS client initialized (no existing index): {self.collection_name}")
            
        except Exception as e:
            logger.error(f"Failed to connect to FAISS: {str(e)}")
            raise ConnectionError(f"FAISS connection failed: {str(e)}")
    
    def create_collection(self, dimension: int, distance_metric: str = 'cosine') -> bool:
        """
        Create a new FAISS index.
        
        Args:
            dimension: Vector dimension
            distance_metric: 'cosine', 'euclidean', or 'dot'
        """
        try:
            from perceptra.vectordb.faiss import FAISSVectorDB
            
            # Map distance metrics to FAISS index types
            if distance_metric == 'cosine':
                # For cosine similarity, use L2 distance on normalized vectors
                index_type = 'Flat'  # Exact search
            elif distance_metric == 'euclidean':
                index_type = 'Flat'
            elif distance_metric == 'dot':
                index_type = 'FlatIP'  # Inner Product
            else:
                index_type = 'Flat'
            
            # Create FAISS index
            self._client = FAISSVectorDB(
                dimension=dimension,
                index_type=index_type
            )
            
            # Initialize metadata
            self._id_to_idx = {}
            self._idx_to_id = {}
            self._payloads = {}
            self._next_idx = 0
            
            # Save empty index
            self._save_index()
            self._save_metadata()
            
            logger.info(
                f"FAISS index created: {self.collection_name}, "
                f"dimension: {dimension}, metric: {distance_metric}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to create FAISS index: {str(e)}")
            raise VectorDBException(f"Index creation failed: {str(e)}")
    
    def collection_exists(self) -> bool:
        """Check if FAISS index exists."""
        return os.path.exists(self.index_file) and os.path.exists(self.metadata_file)
    
    def delete_collection(self) -> bool:
        """Delete FAISS index and metadata."""
        try:
            if os.path.exists(self.index_file):
                os.remove(self.index_file)
            if os.path.exists(self.metadata_file):
                os.remove(self.metadata_file)
            
            self._client = None
            self._id_to_idx = {}
            self._idx_to_id = {}
            self._payloads = {}
            self._next_idx = 0
            
            logger.info(f"FAISS index deleted: {self.collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete FAISS index: {str(e)}")
            return False
    
    def upsert(self, points: List[VectorPoint]) -> bool:
        """
        Insert or update vector points in FAISS.
        
        Args:
            points: List of VectorPoint objects
        """
        if self._client is None:
            self.connect()
        
        if self._client is None:
            raise CollectionNotFoundError(f"Index {self.collection_name} does not exist")
        
        try:
            vectors_to_add = []
            
            for point in points:
                point_id = point.id
                vector = point.vector if isinstance(point.vector, np.ndarray) else np.array(point.vector)
                
                # Check if point already exists (update)
                if point_id in self._id_to_idx:
                    # FAISS doesn't support updates efficiently
                    # For now, we'll just update payload
                    self._payloads[point_id] = point.payload
                else:
                    # Add new point
                    idx = self._next_idx
                    self._id_to_idx[point_id] = idx
                    self._idx_to_id[idx] = point_id
                    self._payloads[point_id] = point.payload
                    self._next_idx += 1
                    
                    vectors_to_add.append(vector)
            
            # Add vectors to FAISS index
            if vectors_to_add:
                vectors_array = np.vstack(vectors_to_add).astype('float32')
                self._client.add(vectors_array)
            
            # Save index and metadata
            self._save_index()
            self._save_metadata()
            
            logger.info(f"Upserted {len(points)} points to FAISS index: {self.collection_name}")
            
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
        Search for similar vectors in FAISS.
        
        Args:
            query_vector: Query embedding vector
            top_k: Number of results to return
            filters: Optional payload filters (applied post-search)
        """
        if self._client is None:
            self.connect()
        
        if self._client is None:
            raise CollectionNotFoundError(f"Index {self.collection_name} does not exist")
        
        try:
            # Prepare query vector
            query = query_vector.reshape(1, -1).astype('float32')
            
            # Search FAISS (get more results if filters applied)
            k = top_k * 10 if filters else top_k
            k = min(k, self.count())  # Don't request more than available
            
            distances, indices = self._client.search(query, k=k)
            
            # Convert to SearchResult objects
            search_results = []
            
            for dist, idx in zip(distances[0], indices[0]):
                if idx == -1:  # FAISS returns -1 for invalid indices
                    continue
                
                # Get point ID from index
                point_id = self._idx_to_id.get(int(idx))
                if not point_id:
                    continue
                
                # Get payload
                payload = self._payloads.get(point_id, {})
                
                # Apply filters if specified
                if filters and not self._matches_filters(payload, filters):
                    continue
                
                # Convert distance to similarity score (for cosine)
                # FAISS L2 distance: convert to similarity score
                score = 1.0 / (1.0 + float(dist))
                
                search_results.append(SearchResult(
                    id=point_id,
                    score=score,
                    payload=payload
                ))
                
                # Stop when we have enough results
                if len(search_results) >= top_k:
                    break
            
            logger.info(
                f"FAISS search completed: {len(search_results)} results, "
                f"collection: {self.collection_name}"
            )
            
            return search_results
            
        except Exception as e:
            logger.error(f"Search failed: {str(e)}")
            raise VectorDBException(f"Search failed: {str(e)}")
    
    def _matches_filters(self, payload: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """Check if payload matches filters."""
        for key, value in filters.items():
            if key not in payload:
                return False
            
            if isinstance(value, dict):
                # Range conditions
                if '$gte' in value and payload[key] < value['$gte']:
                    return False
                if '$lte' in value and payload[key] > value['$lte']:
                    return False
                if '$in' in value and payload[key] not in value['$in']:
                    return False
            else:
                # Exact match
                if payload[key] != value:
                    return False
        
        return True
    
    def delete(self, point_ids: List[str]) -> bool:
        """
        Delete points by IDs.
        Note: FAISS doesn't support efficient deletion, so we just remove from metadata.
        """
        try:
            for point_id in point_ids:
                if point_id in self._id_to_idx:
                    idx = self._id_to_idx[point_id]
                    del self._id_to_idx[point_id]
                    del self._idx_to_id[idx]
                    if point_id in self._payloads:
                        del self._payloads[point_id]
            
            self._save_metadata()
            
            logger.info(f"Deleted {len(point_ids)} points from FAISS metadata")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete points: {str(e)}")
            return False
    
    def get_by_id(self, point_id: str) -> Optional[VectorPoint]:
        """Get point by ID (FAISS doesn't support this efficiently)."""
        if point_id not in self._id_to_idx:
            return None
        
        # We can't easily retrieve the vector from FAISS
        # Return just the payload
        return VectorPoint(
            id=point_id,
            vector=np.array([]),  # Empty vector
            payload=self._payloads.get(point_id, {})
        )
    
    def count(self) -> int:
        """Get total number of vectors in index."""
        if self._client is None:
            return 0
        return self._client.ntotal if hasattr(self._client, 'ntotal') else len(self._id_to_idx)
    
    def get_info(self) -> Dict[str, Any]:
        """Get index information."""
        return {
            'collection_name': self.collection_name,
            'total_vectors': self.count(),
            'index_type': 'FAISS',
            'storage_path': self.storage_path
        }
    
    def _save_index(self):
        """Save FAISS index to disk."""
        if self._client:
            self._client.save(self.index_file)
    
    def _save_metadata(self):
        """Save metadata to disk."""
        metadata = {
            'id_to_idx': self._id_to_idx,
            'idx_to_id': self._idx_to_id,
            'payloads': self._payloads,
            'next_idx': self._next_idx
        }
        
        with open(self.metadata_file, 'wb') as f:
            pickle.dump(metadata, f)
    
    def _load_metadata(self):
        """Load metadata from disk."""
        if os.path.exists(self.metadata_file):
            with open(self.metadata_file, 'rb') as f:
                metadata = pickle.load(f)
            
            self._id_to_idx = metadata.get('id_to_idx', {})
            self._idx_to_id = metadata.get('idx_to_id', {})
            self._payloads = metadata.get('payloads', {})
            self._next_idx = metadata.get('next_idx', 0)