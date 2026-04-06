# apps/embeddings/tasks/validation.py

"""
Periodic task that validates embedding consistency between the Django DB
and the Qdrant vector store.

Runs hourly via Celery Beat. Samples images and detections with
``embedding_generated=True`` and verifies their vectors exist in Qdrant.
Stale flags are reset so the items are re-embedded on the next batch run.
"""

import logging
from celery import shared_task
from django.conf import settings

from embeddings.models import ModelVersion, TenantVectorCollection
from infrastructure.vectordb.manager import VectorDBManager
from media.models import Image, Detection

logger = logging.getLogger(__name__)


@shared_task(name='maintenance:validate_embeddings', queue='maintenance')
def validate_embeddings_task(sample_size: int = 100):
    """Sample embedded items and verify their vectors exist in Qdrant.

    Resets ``embedding_generated`` to ``False`` for any items whose
    vector is missing, so they are picked up by the next batch re-embed.
    """
    try:
        model_version = ModelVersion.objects.filter(is_active=True).first()
        if not model_version:
            logger.info("No active model version — skipping validation")
            return {'status': 'skipped', 'reason': 'no_active_model'}

        collections = TenantVectorCollection.objects.filter(
            model_version=model_version,
            purpose='embeddings',
            is_active=True,
        ).select_related('tenant')

        total_checked = 0
        total_stale = 0

        for collection in collections:
            tenant = collection.tenant
            db_type = collection.db_type or getattr(settings, 'DEFAULT_VECTOR_DB', 'qdrant')

            try:
                client = VectorDBManager.create(
                    db_type=db_type,
                    collection_name=collection.collection_name,
                    dimension=model_version.vector_dimension,
                )
                client.connect()
            except Exception as e:
                logger.warning(f"Could not connect to vector DB for {collection.collection_name}: {e}")
                continue

            try:
                # ── Validate images ──
                images = list(
                    Image.objects.filter(
                        tenant=tenant,
                        embedding_generated=True,
                        vector_point_id__isnull=False,
                    ).order_by('?')[:sample_size]
                )

                stale_image_ids = []
                for img in images:
                    total_checked += 1
                    try:
                        results = client.retrieve([img.vector_point_id])
                        if not results:
                            stale_image_ids.append(img.id)
                    except Exception:
                        stale_image_ids.append(img.id)

                if stale_image_ids:
                    updated = Image.objects.filter(id__in=stale_image_ids).update(
                        embedding_generated=False,
                        vector_point_id=None,
                        embedding_model_version=None,
                    )
                    total_stale += updated
                    logger.warning(
                        f"Reset {updated} stale image embeddings "
                        f"for tenant {tenant.name} / {collection.collection_name}"
                    )

                # ── Validate detections ──
                detections = list(
                    Detection.objects.filter(
                        tenant=tenant,
                        embedding_generated=True,
                        vector_point_id__isnull=False,
                    ).order_by('?')[:sample_size]
                )

                stale_det_ids = []
                for det in detections:
                    total_checked += 1
                    try:
                        results = client.retrieve([det.vector_point_id])
                        if not results:
                            stale_det_ids.append(det.id)
                    except Exception:
                        stale_det_ids.append(det.id)

                if stale_det_ids:
                    updated = Detection.objects.filter(id__in=stale_det_ids).update(
                        embedding_generated=False,
                        vector_point_id=None,
                        embedding_model_version=None,
                    )
                    total_stale += updated
                    logger.warning(
                        f"Reset {updated} stale detection embeddings "
                        f"for tenant {tenant.name} / {collection.collection_name}"
                    )

            finally:
                try:
                    client.disconnect()
                except Exception:
                    pass

        logger.info(
            f"Embedding validation complete: checked {total_checked}, "
            f"found {total_stale} stale"
        )
        return {
            'status': 'completed',
            'checked': total_checked,
            'stale_reset': total_stale,
        }

    except Exception as e:
        logger.error(f"Embedding validation task failed: {e}")
        raise
