# search/delta_service.py
"""Temporal degradation search — find locations with similar change patterns."""

import logging
import time
import uuid
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
from django.conf import settings

from embeddings.models import ModelVersion, TenantVectorCollection
from infrastructure.vectordb.base import SearchResult
from infrastructure.vectordb.manager import VectorDBManager
from media.models import Image
from search.models import SearchQuery
from tenants.models import Tenant

logger = logging.getLogger(__name__)


class DeltaSearchService:
    """Search for similar degradation patterns across locations.

    Given a reference image, computes the delta against the most recent
    prior image at the same location, then searches the ``_deltas``
    collection for other locations with a similar change direction.
    """

    # Reuse the same client pool as SearchService
    _client_pool: Dict[str, Any] = {}

    def __init__(self, tenant: Tenant, user=None):
        self.tenant = tenant
        self.user = user

    def _get_client(self, collection_name: str, dimension: int):
        if collection_name in self._client_pool:
            return self._client_pool[collection_name]
        client = VectorDBManager.create(
            db_type='qdrant',
            collection_name=collection_name,
            dimension=dimension,
        )
        client.connect()
        self._client_pool[collection_name] = client
        return client

    def search_degradation_pattern(
        self,
        image_id: int,
        top_k: int = 10,
        min_magnitude: float = 0.0,
        plant_site: Optional[str] = None,
    ) -> Tuple[List[SearchResult], int, str]:
        """Find locations with similar deterioration patterns.

        Args:
            image_id: Reference image to compute delta from.
            top_k: Number of results.
            min_magnitude: Only return deltas where magnitude >= this value.
            plant_site: Optional filter to specific plant.

        Returns:
            (results, execution_time_ms, query_id)
        """
        start = time.time()

        model_version = ModelVersion.objects.get(is_active=True)

        from embeddings.models import CollectionPurpose

        # Find the base and delta collections
        base_collection = TenantVectorCollection.objects.get(
            tenant=self.tenant, model_version=model_version,
            purpose=CollectionPurpose.EMBEDDINGS, is_searchable=True,
        )
        try:
            delta_collection = TenantVectorCollection.objects.get(
                tenant=self.tenant, model_version=model_version,
                purpose=CollectionPurpose.DELTAS,
            )
        except TenantVectorCollection.DoesNotExist:
            raise ValueError("No delta collection exists yet. Upload more images to build temporal data.")

        dim = model_version.vector_dimension

        # Get the reference image and its predecessor
        image = Image.objects.get(id=image_id, tenant=self.tenant)
        if not image.embedding_generated or not image.vector_point_id:
            raise ValueError(f"Image {image_id} has no embedding.")

        # Find predecessor
        prev_qs = Image.objects.filter(
            tenant=self.tenant,
            plant_site=image.plant_site,
            embedding_generated=True,
            captured_at__lt=image.captured_at,
        )
        if image.inspection_line:
            prev_qs = prev_qs.filter(inspection_line=image.inspection_line)
        prev_image = prev_qs.order_by('-captured_at').first()

        if prev_image is None:
            raise ValueError("No previous image at this location to compute delta from.")

        # Retrieve both vectors from base collection
        base_client = self._get_client(base_collection.collection_name, dim)
        new_points = base_client.get([image.vector_point_id])
        old_points = base_client.get([prev_image.vector_point_id])

        if not new_points or not old_points:
            raise ValueError("Could not retrieve embedding vectors for delta computation.")

        new_vec = np.array(new_points[0].vector, dtype=np.float32)
        old_vec = np.array(old_points[0].vector, dtype=np.float32)

        # Compute query delta
        raw_delta = new_vec - old_vec
        magnitude = float(np.linalg.norm(raw_delta))
        if magnitude < 1e-6:
            raise ValueError("No meaningful change detected between the two images.")
        query_delta = raw_delta / magnitude

        # Search delta collection
        delta_client = self._get_client(delta_collection.collection_name, dim)
        filters: Dict[str, Any] = {}
        if min_magnitude > 0:
            filters['magnitude'] = {'$gte': min_magnitude}
        if plant_site:
            filters['plant_site'] = plant_site

        results = delta_client.search(
            query_vector=list(query_delta),
            limit=top_k + 1,
            filters=filters,
            return_vectors=False,
        )

        # Exclude the reference image's own delta if present
        ref_delta_id = f"{image.vector_point_id}"
        results = [r for r in results if r.id != ref_delta_id][:top_k]

        exec_ms = int((time.time() - start) * 1000)

        query_id = uuid.uuid4()
        SearchQuery.objects.create(
            id=query_id,
            tenant=self.tenant,
            user=self.user,
            query_type='degradation',
            filters={'image_id': image_id, 'min_magnitude': min_magnitude},
            results_count=len(results),
            execution_time_ms=exec_ms,
        )

        return results, exec_ms, str(query_id)
