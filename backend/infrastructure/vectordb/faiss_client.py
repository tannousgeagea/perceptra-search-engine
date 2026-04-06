# infrastructure/vectordb/faiss_client.py

from typing import List, Dict, Any, Optional, Union
import numpy as np
import faiss
import json
import os
import shutil
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

    Storage layout per collection (all under storage_path/collection_name/):
        index.faiss          — FAISS index (native binary format)
        metadata.json        — id↔idx mappings + payloads (JSON, not pickle)
        config.json          — dimension, metric, index type
        vectors.npy          — raw float32 vectors for retrieval (numpy native)

    Design decisions:
    - Writes are batched: _save_* is called once per upsert() call, not per point.
    - Atomic saves: write to a temp file then rename — a crash never leaves a
      corrupt index file half-written.
    - Metadata is JSON: human-readable, version-stable, no pickle safety issues.
    - Vectors stored in numpy .npy format: compact, fast, no duplication risk.
    - Deleted points are tracked in a tombstone set and excluded from search
      results immediately, without rebuilding the FAISS index.
    - The threading Lock guards in-memory structures within a single worker
      process. Across Celery workers (separate processes), each worker holds
      its own in-memory state; persistence is the coordination mechanism.
    """

    def __init__(
        self,
        collection_name: str,
        dimension: Optional[int] = None,
        distance_metric: DistanceMetric = DistanceMetric.COSINE,
        storage_path: str = "/tmp/faiss_indices",
        index_type: str = "Flat",
        use_gpu: bool = False,
        nlist: int = 100,
        nprobe: int = 10,
        **config
    ):
        super().__init__(collection_name, dimension, distance_metric, **config)

        self.storage_path = Path(storage_path) / collection_name
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.index_type = index_type
        self.use_gpu = use_gpu
        self.nlist = nlist
        self.nprobe = nprobe

        # One directory per collection — clean layout
        self._index_file    = self.storage_path / "index.faiss"
        self._metadata_file = self.storage_path / "metadata.json"
        self._config_file   = self.storage_path / "config.json"
        self._vectors_file  = self.storage_path / "vectors.npy"

        # In-memory structures
        self._id_to_idx: Dict[str, int] = {}
        self._idx_to_id: Dict[int, str] = {}
        self._payloads:  Dict[str, Dict[str, Any]] = {}
        self._deleted:   set = set()          # tombstone — fast exclusion on search
        self._vectors:   Optional[np.ndarray] = None
        self._next_idx = 0

        self._lock = Lock()
        self._gpu_resources = None

    # -------------------------------------------------------------------------
    # Connection
    # -------------------------------------------------------------------------

    def connect(self) -> bool:
        try:
            logger.info(f"Connecting to FAISS collection: {self.collection_name}")
            if self.collection_exists():
                self._load_config()     # sets self.dimension — must be first
                self._load_index()
                self._load_metadata()
                self._load_vectors()
                logger.info(f"Loaded FAISS collection: {self.collection_name}")
            else:
                logger.info(f"No existing FAISS collection: {self.collection_name}")
            self._is_connected = True
            return True
        except Exception as e:
            logger.error(f"Failed to connect to FAISS: {e}")
            raise ConnectionError(f"FAISS connection failed: {e}")

    def disconnect(self):
        if self.use_gpu and self._gpu_resources:
            del self._gpu_resources
            self._gpu_resources = None
        self._client = None
        self._is_connected = False
        logger.info(f"Disconnected from FAISS: {self.collection_name}")

    # -------------------------------------------------------------------------
    # Collection management
    # -------------------------------------------------------------------------

    def create_collection(
        self,
        dimension: int,
        distance_metric: DistanceMetric = DistanceMetric.COSINE,
        **kwargs
    ) -> bool:
        try:
            self.dimension = dimension
            self.distance_metric = distance_metric
            self._client = self._create_index(dimension, distance_metric)

            with self._lock:
                self._id_to_idx = {}
                self._idx_to_id = {}
                self._payloads  = {}
                self._deleted   = set()
                self._vectors   = None
                self._next_idx  = 0

            self._save_config()
            self._save_index()
            self._save_metadata()

            logger.info(
                f"FAISS collection created: {self.collection_name} "
                f"dim={dimension} metric={distance_metric} type={self.index_type}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to create FAISS collection: {e}")
            raise VectorDBException(f"Collection creation failed: {e}")

    def delete_collection(self) -> bool:
        try:
            with self._lock:
                shutil.rmtree(self.storage_path, ignore_errors=True)
                self._client    = None
                self._id_to_idx = {}
                self._idx_to_id = {}
                self._payloads  = {}
                self._deleted   = set()
                self._vectors   = None
                self._next_idx  = 0
            logger.info(f"FAISS collection deleted: {self.collection_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete collection: {e}")
            return False

    def collection_exists(self) -> bool:
        return (
            self._index_file.exists()
            and self._metadata_file.exists()
            and self._config_file.exists()
        )

    def get_collection_info(self) -> CollectionInfo:
        if not self._is_connected:
            self.connect()
        try:
            with self._lock:
                live_count = len(self._id_to_idx) - len(self._deleted)
            return CollectionInfo(
                name=self.collection_name,
                vector_count=live_count,
                dimension=self.dimension or 0,
                distance_metric=self.distance_metric.value,
                indexed=self._client is not None,
                metadata={
                    "index_type":    self.index_type,
                    "use_gpu":       self.use_gpu,
                    "storage_path":  str(self.storage_path),
                    "deleted_count": len(self._deleted),
                },
            )
        except Exception as e:
            raise CollectionNotFoundError(f"Collection not found: {self.collection_name}")

    # -------------------------------------------------------------------------
    # Write
    # -------------------------------------------------------------------------

    def upsert(self, points: List[VectorPoint], batch_size: int = 1000) -> bool:
        if not self._is_connected:
            self.connect()
        if self._client is None:
            raise CollectionNotFoundError(f"Index {self.collection_name} does not exist")

        try:
            t0 = time.time()
            new_vectors: List[np.ndarray] = []
            new_ids:     List[int]        = []

            with self._lock:
                for point in points:
                    self._validate_dimension(point.vector)
                    vec = self._to_numpy(point.vector)

                    if self.distance_metric == DistanceMetric.COSINE:
                        norm = np.linalg.norm(vec)
                        if norm > 0:
                            vec = vec / norm

                    if point.id in self._id_to_idx:
                        # Update payload only — FAISS has no efficient in-place
                        # vector update; for payload-only changes this is fine.
                        self._payloads[point.id] = point.payload
                        # Un-tombstone if previously deleted and re-inserted
                        self._deleted.discard(point.id)
                    else:
                        idx = self._next_idx
                        self._id_to_idx[point.id] = idx
                        self._idx_to_id[idx]       = point.id
                        self._payloads[point.id]   = point.payload
                        self._deleted.discard(point.id)
                        self._next_idx += 1
                        new_vectors.append(vec)
                        new_ids.append(idx)

                if new_vectors:
                    arr  = np.vstack(new_vectors).astype('float32')
                    ids  = np.array(new_ids, dtype=np.int64)

                    if hasattr(self._client, 'is_trained') and not self._client.is_trained:
                        if len(new_vectors) >= self.nlist:
                            logger.info("Training FAISS IVF index...")
                            self._client.train(arr)
                        else:
                            logger.warning(
                                f"Skipping training: {len(new_vectors)} vectors < "
                                f"nlist={self.nlist}. Use a Flat index for small datasets."
                            )

                    self._client.add_with_ids(arr, ids)

                    # Append to the vectors store — one contiguous array
                    self._vectors = (
                        arr if self._vectors is None
                        else np.vstack([self._vectors, arr])
                    ).astype('float32')

            # Persist once per upsert() call, not per point
            self._save_index()
            self._save_metadata()
            self._save_vectors()

            elapsed = time.time() - t0
            logger.info(
                f"Upserted {len(points)} points to FAISS in {elapsed:.2f}s "
                f"({len(points)/max(elapsed, 1e-6):.0f} pts/s)"
            )
            return True

        except Exception as e:
            logger.error(f"FAISS upsert failed: {e}")
            raise VectorDBException(f"Upsert failed: {e}")

    def delete(self, point_ids: List[str]) -> bool:
        """
        Soft-delete via tombstone set.

        FAISS has no efficient single-point removal. Rebuilding the index on
        every delete is O(n) and unacceptable in production. The tombstone
        approach excludes deleted points from search results immediately at
        near-zero cost. The index is compacted (rebuilt without tombstoned
        points) by calling compact() explicitly — e.g. as a periodic
        maintenance task when len(_deleted) / total > 0.1.
        """
        try:
            with self._lock:
                for pid in point_ids:
                    if pid in self._id_to_idx:
                        self._deleted.add(pid)
            self._save_metadata()
            logger.info(f"Tombstoned {len(point_ids)} points in FAISS")
            return True
        except Exception as e:
            logger.error(f"Failed to tombstone points: {e}")
            return False

    def compact(self) -> bool:
        """
        Rebuild the index without tombstoned points.
        Call periodically when deletion ratio is high — not on every delete.
        """
        if not self._is_connected:
            self.connect()
        try:
            with self._lock:
                live_ids = [
                    pid for pid in self._id_to_idx
                    if pid not in self._deleted
                ]
                if not live_ids:
                    logger.info("compact(): no live points, clearing index")
                    self.create_collection(self.dimension, self.distance_metric)
                    return True

                live_vectors = np.vstack([
                    self._vectors[self._id_to_idx[pid]]
                    for pid in live_ids
                    if self._vectors is not None and self._id_to_idx[pid] < len(self._vectors)
                ]).astype('float32')

                # Rebuild clean structures
                self._client    = self._create_index(self.dimension, self.distance_metric)
                self._id_to_idx = {}
                self._idx_to_id = {}
                self._deleted   = set()
                self._next_idx  = 0

                new_ids = np.arange(len(live_ids), dtype=np.int64)
                self._client.add_with_ids(live_vectors, new_ids)

                for i, pid in enumerate(live_ids):
                    self._id_to_idx[pid] = i
                    self._idx_to_id[i]   = pid
                self._vectors = live_vectors

            self._save_index()
            self._save_metadata()
            self._save_vectors()
            logger.info(f"Compacted FAISS index: {len(live_ids)} live points retained")
            return True

        except Exception as e:
            logger.error(f"Compact failed: {e}")
            raise VectorDBException(f"Compact failed: {e}")

    # -------------------------------------------------------------------------
    # Read
    # -------------------------------------------------------------------------

    def search(
        self,
        query_vector: Union[np.ndarray, List[float]],
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None,
        return_vectors: bool = False,
    ) -> List[SearchResult]:
        if not self._is_connected:
            self.connect()
        if self._client is None:
            raise CollectionNotFoundError(f"Index {self.collection_name} does not exist")

        try:
            t0 = time.time()
            self._validate_dimension(query_vector)
            query = self._to_numpy(query_vector)

            if self.distance_metric == DistanceMetric.COSINE:
                norm = np.linalg.norm(query)
                if norm > 0:
                    query = query / norm

            query = query.reshape(1, -1).astype('float32')

            with self._lock:
                total_live = len(self._id_to_idx) - len(self._deleted)

            if total_live == 0:
                return []

            # Fetch extra candidates to account for tombstoned points
            k = min(limit + len(self._deleted) + 10, total_live)

            with self._lock:
                distances, indices = self._client.search(query, k)

            results: List[SearchResult] = []

            for dist, idx in zip(distances[0], indices[0]):
                if idx == -1:
                    continue
                idx = int(idx)

                with self._lock:
                    point_id = self._idx_to_id.get(idx)
                    if not point_id or point_id in self._deleted:
                        continue
                    payload = self._payloads.get(point_id, {})

                if filters and not self._matches_filters(payload, filters):
                    continue

                if self.distance_metric == DistanceMetric.COSINE:
                    score = float(1.0 - dist / 2.0)
                elif self.distance_metric == DistanceMetric.EUCLIDEAN:
                    score = float(1.0 / (1.0 + dist))
                elif self.distance_metric == DistanceMetric.DOT_PRODUCT:
                    score = float(dist)
                else:
                    score = float(1.0 / (1.0 + dist))

                if score_threshold is not None and score < score_threshold:
                    continue

                vec = None
                if return_vectors and self._vectors is not None and idx < len(self._vectors):
                    vec = self._vectors[idx]

                results.append(SearchResult(
                    id=point_id, score=score, payload=payload, vector=vec
                ))

                if len(results) >= limit:
                    break

            elapsed = (time.time() - t0) * 1000
            logger.debug(f"FAISS search: {len(results)} results in {elapsed:.2f}ms")
            return results

        except Exception as e:
            logger.error(f"FAISS search failed: {e}")
            raise VectorDBException(f"Search failed: {e}")

    def get(self, point_ids: List[str]) -> List[VectorPoint]:
        if not self._is_connected:
            self.connect()
        try:
            results = []
            with self._lock:
                for pid in point_ids:
                    if pid not in self._id_to_idx or pid in self._deleted:
                        continue
                    idx     = self._id_to_idx[pid]
                    payload = self._payloads.get(pid, {})
                    vec     = (
                        self._vectors[idx]
                        if self._vectors is not None and idx < len(self._vectors)
                        else np.array([], dtype=np.float32)
                    )
                    results.append(VectorPoint(id=pid, vector=vec, payload=payload))
            return results
        except Exception as e:
            logger.error(f"FAISS get failed: {e}")
            raise VectorDBException(f"Retrieve failed: {e}")

    def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        if not self._is_connected:
            self.connect()
        try:
            with self._lock:
                live_ids = [
                    pid for pid in self._id_to_idx
                    if pid not in self._deleted
                ]
                if not filters:
                    return len(live_ids)
                return sum(
                    1 for pid in live_ids
                    if self._matches_filters(self._payloads.get(pid, {}), filters)
                )
        except Exception as e:
            logger.error(f"FAISS count failed: {e}")
            return 0

    def scroll(
        self,
        limit: int = 100,
        offset: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> tuple[List[VectorPoint], Optional[str]]:
        if not self._is_connected:
            self.connect()
        try:
            # FIX: validate offset before casting — bad input previously raised ValueError
            start = 0
            if offset is not None:
                if not offset.isdigit():
                    raise VectorDBException(f"Invalid scroll offset: '{offset}'")
                start = int(offset)

            with self._lock:
                live_ids = [
                    pid for pid in self._id_to_idx
                    if pid not in self._deleted
                ]

            if filters:
                live_ids = [
                    pid for pid in live_ids
                    if self._matches_filters(self._payloads.get(pid, {}), filters)
                ]

            page      = live_ids[start:start + limit]
            next_off  = str(start + limit) if (start + limit) < len(live_ids) else None

            results = []
            with self._lock:
                for pid in page:
                    idx = self._id_to_idx[pid]
                    vec = (
                        self._vectors[idx]
                        if self._vectors is not None and idx < len(self._vectors)
                        else np.array([], dtype=np.float32)
                    )
                    results.append(VectorPoint(
                        id=pid,
                        vector=vec,
                        payload=self._payloads.get(pid, {}),
                    ))

            return results, next_off

        except VectorDBException:
            raise
        except Exception as e:
            logger.error(f"FAISS scroll failed: {e}")
            raise VectorDBException(f"Scroll failed: {e}")

    # -------------------------------------------------------------------------
    # Persistence — atomic writes via temp file + rename
    # -------------------------------------------------------------------------

    def _atomic_write(self, path: Path, write_fn):
        """
        Write to a temp file then rename to the target path.
        Guarantees the target is never left half-written if the process
        crashes mid-save — rename is atomic on POSIX filesystems.
        """
        tmp = path.with_suffix(path.suffix + '.tmp')
        try:
            write_fn(tmp)
            tmp.replace(path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

    def _save_index(self):
        if self._client is None:
            return
        index_to_save = self._client
        if self.use_gpu and self._gpu_resources:
            index_to_save = faiss.index_gpu_to_cpu(self._client)

        def write(tmp):
            faiss.write_index(index_to_save, str(tmp))

        self._atomic_write(self._index_file, write)
        logger.debug(f"FAISS index saved: {self._index_file}")

    def _load_index(self):
        self._client = faiss.read_index(str(self._index_file))
        if self.use_gpu and faiss.get_num_gpus() > 0:
            self._gpu_resources = faiss.StandardGpuResources()
            self._client = faiss.index_cpu_to_gpu(self._gpu_resources, 0, self._client)

    def _save_metadata(self):
        """
        Persist id↔idx mappings, payloads, tombstones, and next_idx.
        JSON instead of pickle: human-readable, no deserialisation risk,
        stable across Python versions.
        """
        data = {
            'id_to_idx': self._id_to_idx,
            'idx_to_id': {str(k): v for k, v in self._idx_to_id.items()},
            'payloads':  self._payloads,
            'deleted':   list(self._deleted),
            'next_idx':  self._next_idx,
        }

        def write(tmp):
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, separators=(',', ':'), default=str)

        self._atomic_write(self._metadata_file, write)
        logger.debug(f"FAISS metadata saved: {self._metadata_file}")

    def _load_metadata(self):
        with open(self._metadata_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self._id_to_idx = data.get('id_to_idx', {})
        self._idx_to_id = {int(k): v for k, v in data.get('idx_to_id', {}).items()}
        self._payloads  = data.get('payloads', {})
        self._deleted   = set(data.get('deleted', []))
        self._next_idx  = data.get('next_idx', 0)

    def _save_vectors(self):
        """
        Save vectors as a numpy .npy file — compact binary, no duplication,
        loads in O(1) with memory mapping if needed.
        """
        if self._vectors is None:
            return

        def write(tmp):
            np.save(str(tmp), self._vectors)

        self._atomic_write(self._vectors_file, write)
        logger.debug(f"FAISS vectors saved: {self._vectors_file}")

    def _load_vectors(self):
        if self._vectors_file.exists():
            self._vectors = np.load(str(self._vectors_file))
        else:
            self._vectors = None

    def _save_config(self):
        data = {
            'collection_name': self.collection_name,
            'dimension':       self.dimension,
            'distance_metric': self.distance_metric.value if self.distance_metric else None,
            'index_type':      self.index_type,
            'nlist':           self.nlist,
            'nprobe':          self.nprobe,
        }

        def write(tmp):
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

        self._atomic_write(self._config_file, write)

    def _load_config(self):
        with open(self._config_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.dimension      = data.get('dimension')
        metric_str          = data.get('distance_metric')
        self.distance_metric = DistanceMetric(metric_str) if metric_str else DistanceMetric.COSINE
        self.index_type     = data.get('index_type', 'Flat')
        self.nlist          = data.get('nlist', 100)
        self.nprobe         = data.get('nprobe', 10)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _create_index(self, dimension: int, distance_metric: DistanceMetric) -> faiss.Index:
        metric = (
            faiss.METRIC_INNER_PRODUCT
            if distance_metric == DistanceMetric.DOT_PRODUCT
            else faiss.METRIC_L2
        )

        if self.index_type == "Flat":
            base = (
                faiss.IndexFlatIP(dimension)
                if metric == faiss.METRIC_INNER_PRODUCT
                else faiss.IndexFlatL2(dimension)
            )
        elif self.index_type == "IVFFlat":
            quantizer = faiss.IndexFlatL2(dimension)
            base = faiss.IndexIVFFlat(quantizer, dimension, self.nlist, metric)
            base.nprobe = self.nprobe
        elif self.index_type == "HNSW":
            M    = self.config.get('hnsw_m', 32)
            base = faiss.IndexHNSWFlat(dimension, M, metric)
        elif self.index_type == "IVFFlat,PQ":
            m         = self.config.get('pq_m', 8)
            quantizer = faiss.IndexFlatL2(dimension)
            base      = faiss.IndexIVFPQ(quantizer, dimension, self.nlist, m, 8, metric)
            base.nprobe = self.nprobe
        else:
            logger.warning(f"Unknown index type '{self.index_type}', using Flat")
            base = faiss.IndexFlatL2(dimension)

        index = faiss.IndexIDMap(base)

        if self.use_gpu and faiss.get_num_gpus() > 0:
            self._gpu_resources = faiss.StandardGpuResources()
            index = faiss.index_cpu_to_gpu(self._gpu_resources, 0, index)

        return index

    def _matches_filters(self, payload: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        for key, value in filters.items():
            if key not in payload:
                return False
            pv = payload[key]
            if isinstance(value, dict):
                if '$gte'   in value and not (pv >= value['$gte']):    return False
                if '$lte'   in value and not (pv <= value['$lte']):    return False
                if '$gt'    in value and not (pv >  value['$gt']):     return False
                if '$lt'    in value and not (pv <  value['$lt']):     return False
                if '$in'    in value and pv not in value['$in']:       return False
                if '$range' in value:
                    r = value['$range']
                    if 'gte' in r and not (pv >= r['gte']): return False
                    if 'lte' in r and not (pv <= r['lte']): return False
                    if 'gt'  in r and not (pv >  r['gt']):  return False
                    if 'lt'  in r and not (pv <  r['lt']):  return False
            else:
                if pv != value:
                    return False
        return True