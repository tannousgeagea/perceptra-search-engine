# embeddings/tasks/delta.py
"""Compute temporal delta embeddings for degradation tracking.

After an image is embedded, this task finds the most recent *previous*
image at the same (plant_site, inspection_line) location.  If one exists,
the normalised difference between the two embedding vectors is stored in
a dedicated ``_deltas`` collection.  Searching that collection answers
"which locations are degrading in a similar pattern?"
"""

import logging
import time

import numpy as np
from celery import shared_task
from django.conf import settings
from django.db.models import F

from embeddings.tasks.base import (
    EmbeddingTask,
    get_active_model_version,
    get_or_create_collection,
)
from embeddings.models import TenantVectorCollection
from infrastructure.vectordb.base import VectorPoint
from infrastructure.vectordb.manager import VectorDBManager
from media.models import Image

logger = logging.getLogger(__name__)


def _get_or_create_delta_collection(tenant, model_version):
    """Get or create the *deltas* collection for a tenant + model.

    Uses the ``purpose`` field on ``TenantVectorCollection`` so that the
    ``(tenant, model_version, purpose)`` unique constraint is satisfied
    separately from the primary embeddings collection.
    """
    from embeddings.models import CollectionPurpose

    base = get_or_create_collection(tenant, model_version)

    collection, created = TenantVectorCollection.objects.get_or_create(
        tenant=tenant,
        model_version=model_version,
        purpose=CollectionPurpose.DELTAS,
        defaults={
            'db_type': base.db_type,
            'is_active': True,
            'is_searchable': True,
        },
    )
    if created:
        logger.info(f"Created delta collection: {collection.collection_name}")
    return collection


@shared_task(
    base=EmbeddingTask,
    name='embedding:compute_delta',
    queue='embedding',
    soft_time_limit=120,
    time_limit=300,
)
def compute_delta_embedding_task(image_id: int):
    """Compute a delta embedding between this image and the previous
    image at the same location.

    The delta vector captures *how the scene changed* in embedding space.
    Searching the delta collection finds locations with similar
    deterioration patterns.
    """
    try:
        image = Image.objects.select_related('tenant').get(id=image_id)

        # Must have an embedding already
        if not image.embedding_generated or not image.vector_point_id:
            logger.debug(f"Image {image_id} not yet embedded, skipping delta")
            return {'status': 'skipped', 'reason': 'no_embedding'}

        # Location key — skip if no location metadata
        if not image.plant_site:
            return {'status': 'skipped', 'reason': 'no_location'}

        # Find the most recent *previous* image at the same location
        location_qs = Image.objects.filter(
            tenant=image.tenant,
            plant_site=image.plant_site,
            embedding_generated=True,
            captured_at__lt=image.captured_at,
        )
        if image.inspection_line:
            location_qs = location_qs.filter(inspection_line=image.inspection_line)

        prev_image = location_qs.order_by('-captured_at').first()
        if prev_image is None:
            logger.debug(f"No previous image at location for image {image_id}")
            return {'status': 'skipped', 'reason': 'no_previous'}

        # ── Retrieve both vectors ────────────────────────────
        model_version = get_active_model_version()
        if model_version is None:
            return {'status': 'skipped', 'reason': 'no_model'}

        base_collection = get_or_create_collection(image.tenant, model_version)
        vector_db = compute_delta_embedding_task.get_vector_db_client(  # type: ignore
            collection_name=base_collection.collection_name,
            dimension=model_version.vector_dimension,
        )

        new_points = vector_db.get([image.vector_point_id])
        old_points = vector_db.get([prev_image.vector_point_id])

        if not new_points or not old_points:
            logger.warning(f"Could not retrieve vectors for delta: new={image.vector_point_id}, old={prev_image.vector_point_id}")
            return {'status': 'skipped', 'reason': 'missing_vectors'}

        new_vec = np.array(new_points[0].vector, dtype=np.float32)
        old_vec = np.array(old_points[0].vector, dtype=np.float32)

        # ── Compute delta ────────────────────────────────────
        raw_delta = new_vec - old_vec
        magnitude = float(np.linalg.norm(raw_delta))

        # Skip trivially small changes (noise)
        if magnitude < 0.01:
            return {'status': 'skipped', 'reason': 'negligible_change', 'magnitude': magnitude}

        # Normalise the delta direction
        delta_vec = raw_delta / magnitude

        # ── Time span ────────────────────────────────────────
        time_span = (image.captured_at - prev_image.captured_at).total_seconds() / 86400.0  # days

        # ── Store in deltas collection ───────────────────────
        delta_collection = _get_or_create_delta_collection(image.tenant, model_version)
        delta_db = compute_delta_embedding_task.get_vector_db_client(  # type: ignore
            collection_name=delta_collection.collection_name,
            dimension=model_version.vector_dimension,
        )

        delta_point_id = f"{image.vector_point_id}"
        payload = {
            'type': 'delta',
            'tenant_id': str(image.tenant_id),
            'plant_site': image.plant_site,
            'inspection_line': image.inspection_line,

            # Temporal context
            'from_image_id': prev_image.id,
            'from_image_uuid': str(prev_image.image_id),
            'from_captured_at': prev_image.captured_at.isoformat(),
            'to_image_id': image.id,
            'to_image_uuid': str(image.image_id),
            'to_captured_at': image.captured_at.isoformat(),
            'time_span_days': round(time_span, 2),

            # Change magnitude (how much change occurred)
            'magnitude': round(magnitude, 6),
            'model_version': model_version.name,
        }

        delta_db.upsert([VectorPoint(id=delta_point_id, vector=list(delta_vec), payload=payload)])

        TenantVectorCollection.objects.filter(pk=delta_collection.pk).update(
            total_vectors=F('total_vectors') + 1,
        )

        logger.info(
            f"Delta embedding stored for image {image_id}: "
            f"magnitude={magnitude:.4f}, span={time_span:.1f}d, "
            f"location={image.plant_site}/{image.inspection_line}"
        )

        return {
            'status': 'success',
            'image_id': image_id,
            'prev_image_id': prev_image.id,
            'delta_point_id': delta_point_id,
            'magnitude': magnitude,
            'time_span_days': round(time_span, 2),
        }

    except Image.DoesNotExist:
        logger.error(f"Image {image_id} not found for delta computation")
        raise
    except Exception as e:
        logger.error(f"Delta computation failed for image {image_id}: {e}")
        raise
