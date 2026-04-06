"""
WasteVision alert engine — stateless rule engine that runs after each VLM inspection.

Rules:
  1. Contamination: any item with severity high or critical → immediate alert
  2. Blockage: line_blockage == True → critical alert
  3. Escalation: WASTEVISION_CONSECUTIVE_N consecutive high/critical frames → escalation alert
  4. Drift: any composition material jumps >WASTEVISION_DRIFT_PCT% vs 5-min window average

Deduplication: Redis TTL keys prevent re-alerting within WASTEVISION_DEDUP_WINDOW seconds.
"""

import logging
from datetime import datetime, timedelta, timezone

from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone as django_tz

from infrastructure.pubsub import publish
from wastevision.frame_capture import CapturedFrame

logger = logging.getLogger(__name__)

_REDIS_URL = None


def _get_redis_url() -> str:
    import os
    return os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')


async def _redis_set_ex(key: str, ttl: int) -> bool:
    """Set a Redis key with TTL if it doesn't already exist. Returns True if key was newly set."""
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(_get_redis_url())
        try:
            # SET key 1 EX ttl NX (set only if not exists)
            result = await r.set(key, 1, ex=ttl, nx=True)
            return result is True
        finally:
            await r.aclose()
    except Exception as e:
        logger.warning("WasteVision: Redis dedup check failed (%s) — allowing alert", e)
        return True  # Fail open: allow alert if Redis unavailable


class AlertEngine:
    """
    Processes one WasteInspection result and fires alerts based on rules.
    All state (dedup, consecutive count) is in Redis/DB, so this is stateless.
    """

    async def process(self, frame: CapturedFrame, inspection) -> None:
        from wastevision.models import WasteCamera
        camera = await sync_to_async(WasteCamera.objects.select_related('tenant').get)(id=frame.camera_id)

        # Rule 1 & 2: Contamination + blockage
        for item in (inspection.contamination_alerts or []):
            sev = item.get('severity', '').lower()
            if sev in ('high', 'critical'):
                await self._maybe_alert(camera, inspection, 'contamination', sev, item)

        if inspection.line_blockage:
            await self._maybe_alert(
                camera, inspection, 'blockage', 'critical',
                {'item': 'LINE_BLOCKAGE', 'action': 'Stop conveyor immediately'},
            )

        # Rule 3: Consecutive escalation
        if inspection.overall_risk in ('high', 'critical'):
            new_count = await sync_to_async(self._inc_consecutive)(camera)
            if new_count >= settings.WASTEVISION_CONSECUTIVE_N:
                await self._maybe_alert(
                    camera, inspection, 'escalation', 'critical',
                    {'consecutive_count': new_count, 'overall_risk': inspection.overall_risk},
                )
        else:
            await sync_to_async(self._reset_consecutive)(camera)

        # Rule 4: Composition drift
        drift = await self._check_drift(camera, inspection)
        if drift:
            await self._maybe_alert(camera, inspection, 'drift', 'high', drift)

    # ------------------------------------------------------------------ #
    # Rule helpers
    # ------------------------------------------------------------------ #

    def _inc_consecutive(self, camera) -> int:
        from wastevision.models import WasteCamera
        WasteCamera.objects.filter(id=camera.id).update(
            consecutive_high=camera.consecutive_high + 1
        )
        return camera.consecutive_high + 1

    def _reset_consecutive(self, camera) -> None:
        from wastevision.models import WasteCamera
        if camera.consecutive_high != 0:
            WasteCamera.objects.filter(id=camera.id).update(consecutive_high=0)

    async def _check_drift(self, camera, inspection) -> dict | None:
        """Return drift details if any material jumps by >WASTEVISION_DRIFT_PCT vs 5-min avg."""
        from wastevision.models import WasteInspection

        window_start = datetime.now(timezone.utc) - timedelta(seconds=300)

        def _get_recent():
            return list(
                WasteInspection.objects.filter(
                    camera=camera,
                    created_at__gte=window_start,
                ).values_list('waste_composition', flat=True)[:60]
            )

        recent = await sync_to_async(_get_recent)()
        if len(recent) < 3:
            return None

        comp_keys = ['plastic', 'paper', 'glass', 'metal', 'organic', 'e_waste', 'hazardous', 'other']
        current = inspection.waste_composition

        for key in comp_keys:
            values = [r.get(key, 0.0) for r in recent if isinstance(r, dict)]
            if not values:
                continue
            avg = sum(values) / len(values)
            current_val = current.get(key, 0.0)
            if abs(current_val - avg) > settings.WASTEVISION_DRIFT_PCT:
                return {
                    'material': key,
                    'current_pct': current_val,
                    'avg_pct': round(avg, 2),
                    'jump_pct': round(abs(current_val - avg), 2),
                }
        return None

    # ------------------------------------------------------------------ #
    # Deduplication + alert creation
    # ------------------------------------------------------------------ #

    async def _maybe_alert(self, camera, inspection, alert_type: str, severity: str, details: dict) -> None:
        """Create alert only if not within dedup window. Publish to Redis on success."""
        item_key = details.get('item', alert_type).replace(' ', '_').lower()
        dedup_key = f"wastevision:dedup:{camera.camera_uuid}:{alert_type}:{item_key}"

        was_set = await _redis_set_ex(dedup_key, settings.WASTEVISION_DEDUP_WINDOW)
        if not was_set:
            return  # Already alerted recently

        alert = await self._create_alert(camera, inspection, alert_type, severity, details)
        await self._publish_alert(camera, inspection, alert)

    async def _create_alert(self, camera, inspection, alert_type: str, severity: str, details: dict):
        from wastevision.models import WasteAlert
        from tenants.models import Tenant

        tenant = await sync_to_async(Tenant.objects.get)(id=camera.tenant_id)

        def _create():
            return WasteAlert.objects.create(
                tenant=tenant,
                camera=camera,
                inspection=inspection,
                alert_type=alert_type,
                severity=severity,
                details=details,
            )

        return await sync_to_async(_create)()

    async def _publish_alert(self, camera, inspection, alert) -> None:
        """Publish to the existing tenant alerts channel AND the WasteVision-specific channel."""
        msg = {
            "type": "new_alert",
            "alert": {
                "id": str(alert.alert_uuid),
                "source": "wastevision",
                "camera_id": str(camera.camera_uuid),
                "camera_name": camera.name,
                "camera_location": camera.location,
                "type": alert.alert_type,
                "severity": alert.severity,
                "timestamp": alert.created_at.isoformat(),
                "details": alert.details,
                "acknowledged": False,
                "plant_site": camera.plant_site,
                "inspector_note": inspection.inspector_note if inspection else "",
                # Backwards-compat fields expected by existing AlertContext
                "label": alert.details.get('item', alert.alert_type),
                "confidence": inspection.confidence if inspection else 0.0,
                "is_acknowledged": False,
            },
        }

        tenant_id = camera.tenant_id
        # 1. Existing alerts channel → existing frontend AlertContext picks this up
        await publish(f"alerts:{tenant_id}", msg)
        # 2. WasteVision-specific channel → /ws/wastevision/alerts/stream
        await publish(f"wastevision:alerts:{tenant_id}", msg)
