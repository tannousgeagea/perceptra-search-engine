"""
Management command to backfill tags into Qdrant payloads for existing image embeddings.

Usage:
    python manage.py backfill_tags
    python manage.py backfill_tags --tenant <tenant_id>
    python manage.py backfill_tags --dry-run
"""

import logging
from django.core.management.base import BaseCommand
from media.models import Image
from embeddings.models import TenantVectorCollection, ModelVersion
from infrastructure.vectordb.manager import VectorDBManager

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Backfill tags into Qdrant payloads for existing image embeddings"

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant",
            type=str,
            default=None,
            help="Only backfill for a specific tenant ID",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be updated without making changes",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Number of images to process per batch (default: 100)",
        )

    def handle(self, *args, **options):
        tenant_filter = options["tenant"]
        dry_run = options["dry_run"]
        batch_size = options["batch_size"]

        # Get active model version
        try:
            model_version = ModelVersion.objects.get(is_active=True)
        except ModelVersion.DoesNotExist:
            self.stderr.write(self.style.ERROR("No active model version found"))
            return

        # Build image queryset
        qs = (
            Image.objects
            .filter(embedding_generated=True, vector_point_id__isnull=False)
            .prefetch_related("tags")
            .select_related("tenant")
        )
        if tenant_filter:
            qs = qs.filter(tenant__tenant_id=tenant_filter)

        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.WARNING("No embedded images found to backfill"))
            return

        self.stdout.write(f"Backfilling tags for {total} images (dry_run={dry_run})")

        # Group by tenant collection
        updated = 0
        skipped = 0
        errors = 0

        # Process in batches
        for offset in range(0, total, batch_size):
            batch = list(qs[offset:offset + batch_size])

            # Group by tenant for collection lookup
            by_tenant = {}
            for image in batch:
                tid = image.tenant_id
                if tid not in by_tenant:
                    by_tenant[tid] = []
                by_tenant[tid].append(image)

            for tenant_id, images in by_tenant.items():
                # Get the collection for this tenant
                try:
                    collection = TenantVectorCollection.objects.get(
                        tenant_id=tenant_id,
                        model_version=model_version,
                        purpose='embeddings',
                        is_active=True,
                    )
                except TenantVectorCollection.DoesNotExist:
                    logger.warning(f"No active collection for tenant {tenant_id}, skipping {len(images)} images")
                    skipped += len(images)
                    continue

                if dry_run:
                    for image in images:
                        tag_names = list(image.tags.values_list("name", flat=True))
                        self.stdout.write(
                            f"  [DRY RUN] Image {image.vector_point_id}: tags={tag_names}"
                        )
                    updated += len(images)
                    continue

                # Get vector DB client
                try:
                    vector_db = VectorDBManager.create(
                        db_type=collection.db_type,
                        collection_name=collection.collection_name,
                        dimension=model_version.vector_dimension,
                    )
                    vector_db.connect()
                except Exception as e:
                    logger.error(f"Failed to connect to vector DB for {collection.collection_name}: {e}")
                    errors += len(images)
                    continue

                try:
                    for image in images:
                        tag_names = list(image.tags.values_list("name", flat=True))
                        try:
                            vector_db._client.set_payload(
                                collection_name=collection.collection_name,
                                payload={"tags": tag_names},
                                points=[image.vector_point_id],
                            )
                            updated += 1
                        except Exception as e:
                            logger.error(f"Failed to update {image.vector_point_id}: {e}")
                            errors += 1
                finally:
                    vector_db.disconnect()

            self.stdout.write(f"  Processed {min(offset + batch_size, total)}/{total}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {updated} updated, {skipped} skipped, {errors} errors"
            )
        )
