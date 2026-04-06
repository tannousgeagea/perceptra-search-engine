# =============================================================================
# 1. apps/media/ledger.py  —  single helper, called from the upload router
#    Kept separate from models.py so it can be imported without pulling in
#    the full model graph in tests.
# =============================================================================

from media.models import Media, MediaType, StatusChoices
from tenants.models import Tenant
from django.contrib.auth import get_user_model

User = get_user_model()


async def record_media(
    *,
    tenant: Tenant,
    media_type: str,          # MediaType choice value
    storage_backend: str,
    storage_key: str,
    filename: str,
    file_size_bytes: int,
    content_type: str,
    file_format: str,
    checksum: str | None = None,
    created_by: User = None,  # type: ignore
    created_by_api_key = None
) -> Media:
    """
    Write one Media ledger row after a file has been saved to storage.
    Called once per upload, regardless of media type.
    Does not link back to Video / Image / Detection — intentionally.
    """
    from asgiref.sync import sync_to_async

    return await sync_to_async(Media.objects.create)(
        tenant=tenant,
        media_type=media_type,
        storage_backend=storage_backend,
        storage_key=storage_key,
        filename=filename,
        file_size_bytes=file_size_bytes,
        content_type=content_type,
        file_format=file_format,
        checksum=checksum,
        status=StatusChoices.UPLOADED,
        created_by=created_by,
        updated_by=created_by,
        created_by_api_key=created_by_api_key,
    )