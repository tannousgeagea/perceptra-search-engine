# embeddings/tasks/alert_check.py
"""Celery task to check new detections against alert rules."""

import re
import logging
from datetime import timedelta
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


def _matches_rule(detection, rule) -> bool:
    """Check if a detection matches a rule's label pattern and confidence."""
    if detection.confidence < rule.min_confidence:
        return False

    if rule.plant_site and detection.image.plant_site != rule.plant_site:
        return False

    try:
        if not re.search(rule.label_pattern, detection.label, re.IGNORECASE):
            return False
    except re.error:
        # Fallback to exact match if regex is invalid
        if rule.label_pattern.lower() != detection.label.lower():
            return False

    return True


def _in_cooldown(rule, detection) -> bool:
    """Check if an alert was recently created for the same rule+label+plant."""
    if rule.cooldown_minutes <= 0:
        return False

    from alerts.models import Alert
    cutoff = timezone.now() - timedelta(minutes=rule.cooldown_minutes)
    return Alert.objects.filter(
        alert_rule=rule,
        label=detection.label,
        plant_site=detection.image.plant_site,
        created_at__gte=cutoff,
    ).exists()


def _compute_severity(confidence: float) -> str:
    """Derive severity from confidence level."""
    if confidence >= 0.85:
        return 'critical'
    elif confidence >= 0.6:
        return 'warning'
    return 'info'


def _send_webhook(webhook_url: str, alert) -> tuple[bool, str]:
    """Send webhook notification for an alert."""
    import requests
    try:
        payload = {
            'alert_id': alert.pk,
            'severity': alert.severity,
            'label': alert.label,
            'confidence': alert.confidence,
            'plant_site': alert.plant_site,
            'detection_id': alert.detection_id,
            'image_id': alert.image_id,
            'created_at': str(alert.created_at),
        }
        resp = requests.post(webhook_url, json=payload, timeout=10)
        return True, f'{resp.status_code}: {resp.text[:200]}'
    except Exception as e:
        logger.warning(f"Webhook failed for alert {alert.pk}: {e}")
        return False, str(e)


@shared_task(
    name='alerts:check_detection',
    queue='alerts',
    soft_time_limit=30,
    time_limit=60,
)
def check_detection_alert_task(detection_id: int):
    """Check a new detection against all active alert rules and create alerts."""
    from media.models import Detection
    from alerts.models import Alert, AlertRule

    try:
        detection = Detection.objects.select_related('image', 'tenant').get(id=detection_id)
    except Detection.DoesNotExist:
        logger.warning(f"Detection {detection_id} not found for alert check")
        return

    rules = AlertRule.objects.filter(tenant=detection.tenant, is_active=True)
    alerts_created = 0

    for rule in rules:
        if not _matches_rule(detection, rule):
            continue
        if _in_cooldown(rule, detection):
            continue

        alert = Alert.objects.create(
            tenant=detection.tenant,
            alert_rule=rule,
            detection=detection,
            image=detection.image,
            severity=_compute_severity(detection.confidence),
            label=detection.label,
            confidence=detection.confidence,
            plant_site=detection.image.plant_site,
        )
        alerts_created += 1

        # Send webhook if configured
        if rule.webhook_url:
            sent, response = _send_webhook(rule.webhook_url, alert)
            alert.webhook_sent = sent
            alert.webhook_response = response
            alert.save(update_fields=['webhook_sent', 'webhook_response'])

        # Publish to Redis for WebSocket clients
        if rule.notify_websocket:
            try:
                from infrastructure.pubsub import publish_sync
                crop_url = None
                if detection.storage_key:
                    crop_url = f'/api/v1/media/files/{detection.storage_key}'

                publish_sync(f"alerts:{detection.tenant_id}", {
                    'type': 'new_alert',
                    'alert': {
                        'id': alert.pk,
                        'severity': alert.severity,
                        'label': alert.label,
                        'confidence': alert.confidence,
                        'plant_site': alert.plant_site,
                        'detection_id': alert.detection_id,
                        'image_id': alert.image_id,
                        'crop_url': crop_url,
                        'created_at': str(alert.created_at),
                    },
                })
            except Exception as e:
                logger.warning(f"Failed to publish WebSocket alert: {e}")

    if alerts_created:
        logger.info(f"Created {alerts_created} alert(s) for detection {detection_id}")
