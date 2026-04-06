# apps/search/services.py

from typing import List, Dict, Any, Optional, Union, Tuple
import numpy as np
from tenants.models import Tenant
from media.models import Image, Detection
from embeddings.models import TenantVectorCollection, ModelVersion
from search.models import SearchQuery
from infrastructure.embeddings.generator import get_embedding_generator
from infrastructure.vectordb.manager import VectorDBManager
from infrastructure.vectordb.base import SearchResult as VectorSearchResult
from infrastructure.storage.client import get_storage_manager
from search.reranker import MetadataReranker
from django.conf import settings
from django.contrib.auth import get_user_model
import logging
import time
import uuid

User = get_user_model()
logger = logging.getLogger(__name__)


class SearchService:
    """
    Service layer for search operations.
    Handles embedding generation and vector DB queries.
    """

    # Module-level client pool: avoids creating a new TCP connection per request.
    # Keyed by collection_name → connected BaseVectorDB client.
    _client_pool: Dict[str, Any] = {}

    def __init__(self, tenant: Tenant, user: Optional[User] = None):  #type: ignore
        self.tenant = tenant
        self.user = user
        self.embedding_generator = get_embedding_generator()

    def _get_active_collection(self, purpose: str = 'embeddings') -> TenantVectorCollection:
        """Get active vector collection for tenant and purpose."""
        try:
            # Get active model version
            model_version = ModelVersion.objects.get(is_active=True)

            # Get collection for this model and purpose
            collection = TenantVectorCollection.objects.get(
                tenant=self.tenant,
                model_version=model_version,
                purpose=purpose,
                is_searchable=True
            )

            return collection

        except ModelVersion.DoesNotExist:
            raise ValueError("No active embedding model configured")
        except TenantVectorCollection.DoesNotExist:
            raise ValueError(f"No searchable {purpose} collection found for tenant {self.tenant.name}")

    def _get_vector_db_client(self, collection: TenantVectorCollection):
        """Get or reuse a cached vector DB client for collection."""
        cache_key = collection.collection_name

        if cache_key in self._client_pool:
            return self._client_pool[cache_key]

        client = VectorDBManager.create(
            db_type=collection.db_type,
            collection_name=collection.collection_name,
            dimension=collection.model_version.vector_dimension
        )
        client.connect()
        self._client_pool[cache_key] = client
        logger.debug(f"Vector DB client cached for collection: {cache_key}")
        return client
    
    def _build_vector_filters(self, filters: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Build vector DB filters from search filters."""
        if not filters:
            return {}
        
        vector_filters = {}
        
        # Direct field matches
        if filters.get('plant_site'):
            vector_filters['plant_site'] = filters['plant_site']
        
        if filters.get('shift'):
            vector_filters['shift'] = filters['shift']
        
        if filters.get('inspection_line'):
            vector_filters['inspection_line'] = filters['inspection_line']
        
        # Label filtering
        if filters.get('labels'):
            vector_filters['label'] = {'$in': filters['labels']}
        
        # Confidence range
        if filters.get('min_confidence') is not None:
            vector_filters['confidence'] = vector_filters.get('confidence', {})
            vector_filters['confidence']['$gte'] = filters['min_confidence']
        
        if filters.get('max_confidence') is not None:
            vector_filters['confidence'] = vector_filters.get('confidence', {})
            vector_filters['confidence']['$lte'] = filters['max_confidence']
        
        # Date range
        if filters.get('date_from') or filters.get('date_to'):
            date_filter = {}
            if filters.get('date_from'):
                date_filter['$gte'] = filters['date_from'].isoformat()
            if filters.get('date_to'):
                date_filter['$lte'] = filters['date_to'].isoformat()
            vector_filters['captured_at'] = {'$range': date_filter}
        
        # Video filtering
        if filters.get('video_id'):
            vector_filters['video_id'] = filters['video_id']

        # Tag filtering
        if filters.get('tags'):
            vector_filters['tags'] = {'$in': filters['tags']}

        return vector_filters
    
    def _get_reranker(self, alpha: float = 0.8) -> MetadataReranker:
        """Build a metadata reranker using the current model if text-capable."""
        try:
            model_version = ModelVersion.objects.get(is_active=True)
            model_config = model_version.config or {}
            model = self.embedding_generator.get_model(
                model_type=model_config.get('type', 'clip'),
                model_variant=model_config.get('variant', 'ViT-B-32'),
                device=getattr(settings, 'EMBEDDING_DEVICE', 'cuda'),
            )
            return MetadataReranker(model=model, alpha=alpha)
        except Exception:
            return MetadataReranker(model=None, alpha=alpha)

    def _generate_query_embedding(
        self,
        query: Union[bytes, str],
        query_type: str
    ) -> np.ndarray:
        """Generate embedding for search query."""
        # Get active model
        model_version = ModelVersion.objects.get(is_active=True)
        model_config = model_version.config or {}
        
        model_type = model_config.get('type', 'clip')
        model_variant = model_config.get('variant', 'ViT-B-32')
        
        # Get model
        model = self.embedding_generator.get_model(
            model_type=model_type,
            model_variant=model_variant,
            device=getattr(settings, 'EMBEDDING_DEVICE', 'cuda')
        )
        
        # Generate embedding
        if query_type == 'image':
            embedding = model.encode_image(query)   #type: ignore
        elif query_type == 'text':
            if not model.supports_text():
                raise ValueError(f"Model {model_type} does not support text search")
            embedding = model.encode_text(query)  # type: ignore
        else:
            raise ValueError(f"Invalid query type: {query_type}")
        
        return embedding
    
    def search_by_image(
        self,
        image_bytes: bytes,
        top_k: int = 10,
        search_type: str = 'detections',
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None,
        enable_reranking: bool = True,
        reranking_alpha: float = 0.8,
    ) -> Tuple[List[VectorSearchResult], int, str]:
        """
        Search by image.

        Returns:
            Tuple of (results, execution_time_ms, query_id)
        """
        start_time = time.time()

        # Get active collection
        collection = self._get_active_collection()

        # Generate query embedding
        query_embedding = self._generate_query_embedding(image_bytes, 'image')

        # Build filters
        vector_filters = self._build_vector_filters(filters)

        # Add type filter
        if search_type == 'images':
            vector_filters['type'] = 'image'
        elif search_type == 'detections':
            vector_filters['type'] = 'detection'
        # 'both' means no type filter

        # Over-fetch for re-ranking (3x candidates)
        fetch_limit = top_k * 3 if enable_reranking else top_k

        # Get vector DB client
        vector_db = self._get_vector_db_client(collection)

        try:
            # Search
            results = vector_db.search(
                query_vector=query_embedding,
                limit=fetch_limit,
                filters=vector_filters,
                score_threshold=score_threshold,
                return_vectors=False
            )

            # Re-rank with label-semantic boost
            if enable_reranking and len(results) > top_k:
                reranker = self._get_reranker(alpha=reranking_alpha)
                results = reranker.rerank(query_embedding, results, top_k)
            else:
                results = results[:top_k]

            execution_time = int((time.time() - start_time) * 1000)

            # Log search query
            query_id = uuid.uuid4()
            SearchQuery.objects.create(
                id=query_id,
                tenant=self.tenant,
                user=self.user,
                query_type='image',
                filters=filters or {},
                results_count=len(results),
                execution_time_ms=execution_time
            )

            return results, execution_time, str(query_id)

        finally:
            vector_db.disconnect()
    
    def search_by_text(
        self,
        query_text: str,
        top_k: int = 10,
        search_type: str = 'detections',
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None,
        enable_reranking: bool = True,
        reranking_alpha: float = 0.8,
    ) -> Tuple[List[VectorSearchResult], int, str]:
        """
        Search by text query.

        Returns:
            Tuple of (results, execution_time_ms, query_id)
        """
        start_time = time.time()

        # Get active collection
        collection = self._get_active_collection()

        # Generate query embedding
        query_embedding = self._generate_query_embedding(query_text, 'text')

        # Build filters
        vector_filters = self._build_vector_filters(filters)

        # Add type filter
        if search_type == 'images':
            vector_filters['type'] = 'image'
        elif search_type == 'detections':
            vector_filters['type'] = 'detection'

        fetch_limit = top_k * 3 if enable_reranking else top_k

        # Get vector DB client
        vector_db = self._get_vector_db_client(collection)

        try:
            # Search
            results = vector_db.search(
                query_vector=query_embedding,
                limit=fetch_limit,
                filters=vector_filters,
                score_threshold=score_threshold,
                return_vectors=False
            )

            # Re-rank with label-semantic boost
            if enable_reranking and len(results) > top_k:
                reranker = self._get_reranker(alpha=reranking_alpha)
                results = reranker.rerank(query_embedding, results, top_k)
            else:
                results = results[:top_k]

            execution_time = int((time.time() - start_time) * 1000)

            # Log search query
            query_id = uuid.uuid4()
            SearchQuery.objects.create(
                id=query_id,
                tenant=self.tenant,
                user=self.user,
                query_type='text',
                query_text=query_text,
                filters=filters or {},
                results_count=len(results),
                execution_time_ms=execution_time
            )

            return results, execution_time, str(query_id)

        finally:
            vector_db.disconnect()
    
    def search_hybrid(
        self,
        image_bytes: bytes,
        query_text: str,
        text_weight: float = 0.5,
        top_k: int = 10,
        search_type: str = 'detections',
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None,
        enable_reranking: bool = True,
        reranking_alpha: float = 0.8,
    ) -> Tuple[List[VectorSearchResult], int, str]:
        """
        Hybrid search combining image and text.

        Returns:
            Tuple of (results, execution_time_ms, query_id)
        """
        start_time = time.time()

        # Generate both embeddings
        image_embedding = self._generate_query_embedding(image_bytes, 'image')
        text_embedding = self._generate_query_embedding(query_text, 'text')

        # Combine embeddings with weighted average
        image_weight = 1.0 - text_weight
        combined_embedding = (image_weight * image_embedding) + (text_weight * text_embedding)

        # Normalize
        norm = np.linalg.norm(combined_embedding)
        if norm > 0:
            combined_embedding = combined_embedding / norm

        # Get active collection
        collection = self._get_active_collection()

        # Build filters
        vector_filters = self._build_vector_filters(filters)

        # Add type filter
        if search_type == 'images':
            vector_filters['type'] = 'image'
        elif search_type == 'detections':
            vector_filters['type'] = 'detection'

        fetch_limit = top_k * 3 if enable_reranking else top_k

        # Get vector DB client
        vector_db = self._get_vector_db_client(collection)

        try:
            # Search
            results = vector_db.search(
                query_vector=combined_embedding,
                limit=fetch_limit,
                filters=vector_filters,
                score_threshold=score_threshold,
                return_vectors=False
            )

            # Re-rank with label-semantic boost
            if enable_reranking and len(results) > top_k:
                reranker = self._get_reranker(alpha=reranking_alpha)
                results = reranker.rerank(combined_embedding, results, top_k)
            else:
                results = results[:top_k]

            execution_time = int((time.time() - start_time) * 1000)

            # Log search query
            query_id = uuid.uuid4()
            SearchQuery.objects.create(
                id=query_id,
                tenant=self.tenant,
                user=self.user,
                query_type='hybrid',
                query_text=query_text,
                filters=filters or {},
                results_count=len(results),
                execution_time_ms=execution_time
            )

            return results, execution_time, str(query_id)

        finally:
            vector_db.disconnect()
    
    def search_similar(
        self,
        item_id: int,
        item_type: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None
    ) -> Tuple[List[VectorSearchResult], int, str]:
        """
        Find similar items to a given image or detection.
        
        Returns:
            Tuple of (results, execution_time_ms, query_id)
        """
        start_time = time.time()
        collection = self._get_active_collection()
        vector_db = self._get_vector_db_client(collection)
        
        try:
            # Get vector point ID
            if item_type == 'image':
                image = Image.objects.get(id=item_id, tenant=self.tenant)

                # Primary guard: fast, no network call
                if not image.has_embedding:
                    raise ValueError(
                        f"Image {item_id} has no embedding. "
                        "Run the embedding pipeline for this image first."
                    )


                vector_point_id = image.vector_point_id

                # Secondary guard: catches vector store / model flag inconsistency
                # (e.g. collection rebuilt, manual Qdrant deletion)
                points = vector_db.get([vector_point_id])
                if not points:
                    # Flag is stale — reset it so the next pipeline run re-embeds
                    Image.objects.filter(pk=image.pk).update(
                        embedding_generated=False,
                        vector_point_id=None,
                        embedding_model_version=None,
                    )
                    raise ValueError(
                        f"Image {item_id} embedding flag is set but the vector is missing "
                        "from the store. The flag has been reset — re-run the pipeline."
                    )
                
            elif item_type == 'detection':
                detection = Detection.objects.get(id=item_id, tenant=self.tenant)
              
                if not detection.has_embedding:
                    raise ValueError(
                        f"Detection {item_id} has no embedding. "
                        "Run the embedding pipeline for this detection first."
                    )

                vector_point_id = detection.vector_point_id

                points = vector_db.get([vector_point_id])
                if not points:
                    Detection.objects.filter(pk=detection.pk).update(
                        embedding_generated=False,
                        vector_point_id=None,
                        embedding_model_version=None,
                    )
                    raise ValueError(
                        f"Detection {item_id} embedding flag is set but the vector is missing "
                        "from the store. The flag has been reset — re-run the pipeline."
                )
            else:
                raise ValueError(f"Invalid item type: {item_type}")
            
            # Retrieve the vector
            points = vector_db.get([vector_point_id])
            if not points:
                raise ValueError(f"Vector not found for {item_type} {item_id}")
            
            query_vector = points[0].vector
            
            # Build filters
            vector_filters = self._build_vector_filters(filters)
            vector_filters['type'] = item_type  # Search same type
            
            # Search (exclude the query item itself)
            results = vector_db.search(
                query_vector=query_vector,
                limit=top_k + 1,  # Get one extra to exclude self
                filters=vector_filters,
                score_threshold=score_threshold,
                return_vectors=False
            )
            
            # Remove the query item from results
            results = [r for r in results if r.id != vector_point_id][:top_k]
            
            execution_time = int((time.time() - start_time) * 1000)
            
            # Log search query
            query_id = uuid.uuid4()
            SearchQuery.objects.create(
                id=query_id,
                tenant=self.tenant,
                user=self.user,
                query_type='similarity',
                filters=filters or {},
                results_count=len(results),
                execution_time_ms=execution_time
            )
            
            return results, execution_time, str(query_id)
            
        finally:
            vector_db.disconnect()