"""WasteVision Celery tasks — used for background processing when called from API."""

import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name='wastevision:analyze_frame',
    queue='default',
    soft_time_limit=90,
    time_limit=120,
)
def analyze_frame_task(camera_uuid: str, image_b64: str, tenant_id: int) -> None:
    """
    Analyze a single frame for a given camera asynchronously.
    Used by the REST /inspect endpoint when async_mode=True.
    """
    import asyncio
    from wastevision.service import WasteVisionService

    async def _run():
        svc = WasteVisionService(asyncio.Queue())
        await svc.analyze_frame_sync(camera_uuid, image_b64, tenant_id)

    try:
        asyncio.run(_run())
    except Exception as e:
        logger.error("wastevision:analyze_frame task failed for camera %s: %s", camera_uuid, e)
        raise
