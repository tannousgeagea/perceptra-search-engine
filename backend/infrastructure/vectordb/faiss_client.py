# infrastructure/vectordb/faiss_client.py

from typing import List, Dict, Any, Optional, Union
import numpy as np
import faiss
import pickle
import json
import os
from pathlib import Path
from threading import Lock
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


class FAISSVectorDB(BaseVectorDB):
    """
    FAISS vector database implementation.
    Production-ready with persistence, thread-safety, and optimized indexing.
    """
    
    def __init__(
        self,
        collection_name: str,
        dimension: Optional[int] = None,
        distance_metric: DistanceMetric = DistanceMetric.COSINE,
        storage_path: str = "/tmp/faiss_indices",
        index_type: str = "Flat",
        use_gpu: bool = False,
        nlist: int = 100,  # For IVF indices
        nprobe: int = 10,  # For IVF search
        **config
    ):
        """
        Initialize FAISS client.
        
        Args:
            collection_name: Collection name
            dimension: Vector dimension
            distance_metric: Distance metric
            storage_path: Path to store indices
            index_type: FAISS index type ('Flat', 'IVFFlat', 'HNSW', 'IVFFlat,PQ')
            use_gpu: Use GPU acceleration
            nlist: Number of clusters for IVF
            nprobe: Number of clusters to search in IVF
        """
        super().__init__(collection_name, dimension, distance_metric, **config)
        
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self.index_type = index_type
        self.use_gpu = use_gpu
        self.nlist = nlist
        self.nprobe = nprobe
        
        # File paths
        self.index_file = self.storage_path / f"{collection_name}.index"
        self.metadata_file = self.storage_path / f"{collection_name}.meta.pkl"
        self.config_file = self.storage_path / f"{collection_name}.config.json"
        
        # In-memory structures
        self._id_to_idx: Dict[str, int] = {}
        self._idx_to_id: Dict[int, str] = {}
        self._payloads: Dict[str, Dict[str, Any]] = {}
        self._vectors: Optional[np.ndarray] = None
        self._next_idx = 0
        
        # Thread safety
        self._lock = Lock()
        
        # GPU resources
        self._gpu_resources = None
        self._gpu_index = None
    
    def connect(self) -> bool:
        """Connect to FAISS (load existing index)."""
        try:
            logger.info(f"Connecting to FAISS collection: {self.collection_name}")
            
            # Load existing index if exists
            if self.index_file.exists():
                self._load_index()
                self._load_metadata()
                self._load_config()
                logger.info(f"Loaded existing FAISS index: {self.collection_name}")
            else:
                logger.info(f"No existing index found for: {self.collection_name}")
            
            self._is_connected = True
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to FAISS: {str(e)}")
            raise ConnectionError(f"FAISS connection failed: {str(e)}")
    
    def disconnect(self):
        """Disconnect from FAISS (cleanup)."""
        if self._gpu_resources:
            del self._gpu_resources
            del self._gpu_index
            self._gpu_resources = None
            self._gpu_index = None
        
        self._client = None
        self._is_connected = False
        logger.info(f"Disconnected from FAISS collection: {self.collection_name}")
    
    def create_collection(
        self,
        dimension: int,
        distance_metric: DistanceMetric = DistanceMetric.COSINE,
        **kwargs
    ) -> bool:
        """
        Create FAISS index.
        
        Args:
            dimension: Vector dimension
            distance_metric: Distance metric
        """
        try:
            logger.info(f"Creating FAISS index: {self.collection_name}")
            
            self.dimension = dimension
            self.distance_metric = distance_metric
            
            # Create FAISS index
            self._client = self._create_index(dimension, distance_metric)
            
            # Initialize metadata structures
            with self._lock:
                self._id_to_idx = {}
                self._idx_to_id = {}
                self._payloads = {}
                self._vectors = None
                self._next_idx = 0
            
            # Save empty index
            self._save_index()
            self._save_metadata()
            self._save_config()
            
            logger.info(
                f"FAISS index created: {self.collection_name}, "
                f"dim={dimension}, metric={distance_metric}, type={self.index_type}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to create FAISS index: {str(e)}")
            raise VectorDBException(f"Index creation failed: {str(e)}")
    
    def _create_index(self, dimension: int, distance_metric: DistanceMetric) -> faiss.Index:
        """Create FAISS index based on configuration."""
        
        # Choose metric type
        if distance_metric == DistanceMetric.COSINE:
            # For cosine similarity, normalize vectors and use L2
            metric_type = faiss.METRIC_L2
        elif distance_metric == DistanceMetric.EUCLIDEAN:
            metric_type = faiss.METRIC_L2
        elif distance_metric == DistanceMetric.DOT_PRODUCT:
            metric_type = faiss.METRIC_INNER_PRODUCT
        else:
            metric_type = faiss.METRIC_L2
        
        # Create index based on type
        if self.index_type == "Flat":
            # Exact search
            index = faiss.IndexFlatL2(dimension) if metric_type == faiss.METRIC_L2 else faiss.IndexFlatIP(dimension)
        
        elif self.index_type == "IVFFlat":
            # Inverted file with flat encoding
            quantizer = faiss.IndexFlatL2(dimension)
            index = faiss.IndexIVFFlat(quantizer, dimension, self.nlist, metric_type)
            index.nprobe = self.nprobe
        
        elif self.index_type == "HNSW":
            # Hierarchical Navigable Small World
            M = self.config.get('hnsw_m', 32)
            index = faiss.IndexHNSWFlat(dimension, M, metric_type)
        
        elif self.index_type == "IVFFlat,PQ":
            # IVF with Product Quantization (compression)
            m = self.config.get('pq_m', 8)  # Number of sub-quantizers
            quantizer = faiss.IndexFlatL2(dimension)
            index = faiss.IndexIVFPQ(quantizer, dimension, self.nlist, m, 8, metric_type)
            index.nprobe = self.nprobe
        
        else:
            # Default to flat index
            logger.warning(f"Unknown index type: {self.index_type}, using Flat")
            index = faiss.IndexFlatL2(dimension)
        
        # Add ID mapping
        index = faiss.IndexIDMap(index)
        
        # GPU support
        if self.use_gpu and faiss.get_num_gpus() > 0:
            logger.info("Moving FAISS index to GPU")
            self._gpu_resources = faiss.StandardGpuResources()
            index = faiss.index_cpu_to_gpu(self._gpu_resources, 0, index)
            self._gpu_index = index
        
        return index
    
    def delete_collection(self) -> bool:
        """Delete FAISS index and metadata."""
        try:
            with self._lock:
                # Delete files
                if self.index_file.exists():
                    self.index_file.unlink()
                if self.metadata_file.exists():
                    self.metadata_file.unlink()
                if self.config_file.exists():
                    self.config_file.unlink()
                
                # Clear memory
                self._client = None
                self._id_to_idx = {}
                self._idx_to_id = {}
                self._payloads = {}
                self._vectors = None
                self._next_idx = 0
            
            logger.info(f"FAISS index deleted: {self.collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete index: {str(e)}")
            return False
    
    def collection_exists(self) -> bool:
        """Check if index exists."""
        return self.index_file.exists() and self.metadata_file.exists()
    
    def get_collection_info(self) -> CollectionInfo:
        """Get index information."""
        if not self._is_connected:
            self.connect()
        
        try:
            vector_count = len(self._id_to_idx)
            
            return CollectionInfo(
                name=self.collection_name,
                vector_count=vector_count,
                dimension=self.dimension or 0,
                distance_metric=self.distance_metric.value,
                indexed=self._client is not None and self._client.is_trained if hasattr(self._client, 'is_trained') else True,
                metadata={
                    "index_type": self.index_type,
                    "use_gpu": self.use_gpu,
                    "storage_path": str(self.storage_path),
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to get collection info: {str(e)}")
            raise CollectionNotFoundError(f"Collection not found: {self.collection_name}")
    
    def upsert(
        self,
        points: List[VectorPoint],
        batch_size: int = 1000
    ) -> bool:
        """
        Upsert vectors into FAISS.
        
        Args:
            points: List of VectorPoint objects
            batch_size: Batch size for processing
        """
        if not self._is_connected:
            self.connect()
        
        if self._client is None:
            raise CollectionNotFoundError(f"Index {self.collection_name} does not exist")
        
        try:
            start_time = time.time()
            
            with self._lock:
                new_vectors = []
                new_ids = []
                
                for point in points:
                    # Validate dimension
                    self._validate_dimension(point.vector)
                    
                    # Convert to numpy
                    vector = self._to_numpy(point.vector)
                    
                    # Normalize for cosine similarity
                    if self.distance_metric == DistanceMetric.COSINE:
                        norm = np.linalg.norm(vector)
                        if norm > 0:
                            vector = vector / norm
                    
                    point_id = point.id
                    
                    # Check if point exists (update)
                    if point_id in self._id_to_idx:
                        # Update payload only (FAISS doesn't support efficient vector updates)
                        self._payloads[point_id] = point.payload
                    else:
                        # Add new point
                        idx = self._next_idx
                        self._id_to_idx[point_id] = idx
                        self._idx_to_id[idx] = point_id
                        self._payloads[point_id] = point.payload
                        self._next_idx += 1
                        
                        new_vectors.append(vector)
                        new_ids.append(idx)
                
                # Add new vectors to index
                if new_vectors:
                    vectors_array = np.vstack(new_vectors).astype('float32')
                    ids_array = np.array(new_ids, dtype=np.int64)
                    
                    # Train index if needed (for IVF indices)
                    if hasattr(self._client, 'is_trained') and not self._client.is_trained:
                        logger.info("Training FAISS index...")
                        # Need enough vectors to train
                        if len(new_vectors) >= self.nlist:
                            self._client.train(vectors_array)
                        else:
                            logger.warning(f"Not enough vectors to train index ({len(new_vectors)} < {self.nlist})")
                    
                    # Add to index
                    self._client.add_with_ids(vectors_array, ids_array)
                    
                    # Store vectors for later retrieval
                    if self._vectors is None:
                        self._vectors = vectors_array
                    else:
                        self._vectors = np.vstack([self._vectors, vectors_array])
            
            # Save index and metadata
            self._save_index()
            self._save_metadata()
            
            elapsed = time.time() - start_time
            logger.info(
                f"Upserted {len(points)} points to FAISS in {elapsed:.2f}s "
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
        Search similar vectors in FAISS.
        
        Args:
            query_vector: Query vector
            limit: Maximum results
            filters: Payload filters (applied post-search)
            score_threshold: Minimum similarity score
            return_vectors: Return vectors in results
        """
        if not self._is_connected:
            self.connect()
        
        if self._client is None:
            raise CollectionNotFoundError(f"Index {self.collection_name} does not exist")
        
        try:
            start_time = time.time()
            
            # Validate dimension
            self._validate_dimension(query_vector)
            
            # Convert to numpy
            query = self._to_numpy(query_vector)
            
            # Normalize for cosine similarity
            if self.distance_metric == DistanceMetric.COSINE:
                norm = np.linalg.norm(query)
                if norm > 0:
                    query = query / norm
            
            # Reshape for FAISS
            query = query.reshape(1, -1).astype('float32')
            
            # Search (get more results if filters applied)
            k = limit * 10 if filters else limit
            k = min(k, self.count())
            
            if k == 0:
                return []
            
            with self._lock:
                distances, indices = self._client.search(query, k)
            
            # Convert to SearchResult
            search_results = []
            
            for dist, idx in zip(distances[0], indices[0]):
                if idx == -1:  # FAISS returns -1 for invalid indices
                    continue
                
                idx = int(idx)
                
                # Get point ID
                point_id = self._idx_to_id.get(idx)
                if not point_id:
                    continue
                
                # Get payload
                payload = self._payloads.get(point_id, {})
                
                # Apply filters
                if filters and not self._matches_filters(payload, filters):
                    continue
                
                # Convert distance to similarity score
                if self.distance_metric == DistanceMetric.COSINE:
                    # L2 distance on normalized vectors -> cosine similarity
                    score = 1.0 - (float(dist) / 2.0)
                elif self.distance_metric == DistanceMetric.EUCLIDEAN:
                    # Convert L2 distance to similarity
                    score = 1.0 / (1.0 + float(dist))
                elif self.distance_metric == DistanceMetric.DOT_PRODUCT:
                    score = float(dist)
                else:
                    score = 1.0 / (1.0 + float(dist))
                
                # Apply score threshold
                if score_threshold and score < score_threshold:
                    continue
                
                # Get vector if requested
                vector = None
                if return_vectors and self._vectors is not None and idx < len(self._vectors):
                    vector = self._vectors[idx]
                
                search_results.append(SearchResult(
                    id=point_id,
                    score=score,
                    payload=payload,
                    vector=vector
                ))
                
                # Stop when we have enough results
                if len(search_results) >= limit:
                    break
            
            elapsed = (time.time() - start_time) * 1000
            logger.debug(
                f"FAISS search completed in {elapsed:.2f}ms: "
                f"{len(search_results)} results"
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
                # Handle operators
                if '$gte' in value and payload[key] < value['$gte']:
                    return False
                if '$lte' in value and payload[key] > value['$lte']:
                    return False
                if '$gt' in value and payload[key] <= value['$gt']:
                    return False
                if '$lt' in value and payload[key] >= value['$lt']:
                    return False
                if '$in' in value and payload[key] not in value['$in']:
                    return False
                if '$range' in value:
                    range_val = value['$range']
                    if 'gte' in range_val and payload[key] < range_val['gte']:
                        return False
                    if 'lte' in range_val and payload[key] > range_val['lte']:
                        return False
            else:
                # Exact match
                if payload[key] != value:
                    return False
        
        return True
    
    def get(self, point_ids: List[str]) -> List[VectorPoint]:
        """Retrieve points by IDs."""
        if not self._is_connected:
            self.connect()
        
        try:
            results = []
            
            with self._lock:
                for point_id in point_ids:
                    if point_id not in self._id_to_idx:
                        continue
                    
                    idx = self._id_to_idx[point_id]
                    payload = self._payloads.get(point_id, {})
                    
                    # Get vector if available
                    vector = self._vectors[idx] if self._vectors is not None and idx < len(self._vectors) else np.array([])
                    
                    results.append(VectorPoint(
                        id=point_id,
                        vector=vector,
                        payload=payload
                    ))
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to retrieve points: {str(e)}")
            raise VectorDBException(f"Retrieve failed: {str(e)}")
    
    def delete(self, point_ids: List[str]) -> bool:
        """
        Delete points by IDs.
        Note: FAISS doesn't support efficient deletion, so we remove from metadata.
        """
        try:
            with self._lock:
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
    
    def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Count points in index."""
        if not self._is_connected:
            self.connect()
        
        try:
            with self._lock:
                if filters:
                    # Count with filters
                    count = sum(
                        1 for point_id in self._id_to_idx.keys()
                        if self._matches_filters(self._payloads.get(point_id, {}), filters)
                    )
                    return count
                else:
                    return len(self._id_to_idx)
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
            results = []
            start_idx = int(offset) if offset else 0
            
            with self._lock:
                point_ids = list(self._id_to_idx.keys())
                
                # Apply filters
                if filters:
                    point_ids = [
                        pid for pid in point_ids
                        if self._matches_filters(self._payloads.get(pid, {}), filters)
                    ]
                
                # Paginate
                end_idx = start_idx + limit
                page_ids = point_ids[start_idx:end_idx]
                
                for point_id in page_ids:
                    idx = self._id_to_idx[point_id]
                    payload = self._payloads.get(point_id, {})
                    vector = self._vectors[idx] if self._vectors is not None and idx < len(self._vectors) else np.array([])
                    
                    results.append(VectorPoint(
                        id=point_id,
                        vector=vector,
                        payload=payload
                    ))
                
                # Calculate next offset
                next_offset = str(end_idx) if end_idx < len(point_ids) else None
            
            return results, next_offset
            
        except Exception as e:
            logger.error(f"Failed to scroll: {str(e)}")
            raise VectorDBException(f"Scroll failed: {str(e)}")
    
    def _save_index(self):
        """Save FAISS index to disk."""
        if self._client is None:
            return
        
        try:
            # Move to CPU if on GPU
            index_to_save = self._client
            if self.use_gpu and self._gpu_index:
                index_to_save = faiss.index_gpu_to_cpu(self._gpu_index)
            
            faiss.write_index(index_to_save, str(self.index_file))
            logger.debug(f"FAISS index saved: {self.index_file}")
        except Exception as e:
            logger.error(f"Failed to save index: {str(e)}")
    
    def _load_index(self):
        """Load FAISS index from disk."""
        try:
            self._client = faiss.read_index(str(self.index_file))
            
            # Move to GPU if configured
            if self.use_gpu and faiss.get_num_gpus() > 0:
                self._gpu_resources = faiss.StandardGpuResources()
                self._gpu_index = faiss.index_cpu_to_gpu(self._gpu_resources, 0, self._client)
                self._client = self._gpu_index
            
            logger.debug(f"FAISS index loaded: {self.index_file}")
        except Exception as e:
            logger.error(f"Failed to load index: {str(e)}")
            raise
    
    def _save_metadata(self):
        """Save metadata to disk."""
        try:
            metadata = {
                'id_to_idx': self._id_to_idx,
                'idx_to_id': self._idx_to_id,
                'payloads': self._payloads,
                'next_idx': self._next_idx,
                'vectors': self._vectors
            }
            
            with open(self.metadata_file, 'wb') as f:
                pickle.dump(metadata, f)
            
            logger.debug(f"Metadata saved: {self.metadata_file}")
        except Exception as e:
            logger.error(f"Failed to save metadata: {str(e)}")
    
    def _load_metadata(self):
        """Load metadata from disk."""
        try:
            with open(self.metadata_file, 'rb') as f:
                metadata = pickle.load(f)
            
            self._id_to_idx = metadata.get('id_to_idx', {})
            self._idx_to_id = metadata.get('idx_to_id', {})
            self._payloads = metadata.get('payloads', {})
            self._next_idx = metadata.get('next_idx', 0)
            self._vectors = metadata.get('vectors')
            
            logger.debug(f"Metadata loaded: {self.metadata_file}")
        except Exception as e:
            logger.error(f"Failed to load metadata: {str(e)}")
            raise
    
    def _save_config(self):
        """Save configuration to disk."""
        try:
            config = {
                'collection_name': self.collection_name,
                'dimension': self.dimension,
                'distance_metric': self.distance_metric.value if self.distance_metric else None,
                'index_type': self.index_type,
                'nlist': self.nlist,
                'nprobe': self.nprobe,
            }
            
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            
            logger.debug(f"Config saved: {self.config_file}")
        except Exception as e:
            logger.error(f"Failed to save config: {str(e)}")
    
    def _load_config(self):
        """Load configuration from disk."""
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
            
            self.dimension = config.get('dimension')
            metric_str = config.get('distance_metric')
            self.distance_metric = DistanceMetric(metric_str) if metric_str else DistanceMetric.COSINE
            self.index_type = config.get('index_type', 'Flat')
            self.nlist = config.get('nlist', 100)
            self.nprobe = config.get('nprobe', 10)
            
            logger.debug(f"Config loaded: {self.config_file}")
        except Exception as e:
            logger.error(f"Failed to load config: {str(e)}")