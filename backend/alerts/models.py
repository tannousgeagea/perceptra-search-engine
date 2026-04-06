from django.db import models
from django.contrib.auth import get_user_model
from tenants.models import Tenant
from tenants.managers import TenantManager
from media.models import TenantScopedModel, Detection, Image

User = get_user_model()


class AlertRule(TenantScopedModel):
    """Configurable rule that triggers alerts when detections match criteria."""
    name = models.CharField(max_length=100)
    label_pattern = models.CharField(
        max_length=200,
        help_text='Regex or exact match pattern for detection labels (e.g. "rust", "crack|corrosion")',
    )
    min_confidence = models.FloatField(
        default=0.5,
        help_text='Minimum detection confidence to trigger alert (0.0-1.0)',
    )
    plant_site = models.CharField(
        max_length=200, blank=True, null=True,
        help_text='If set, only trigger for this plant site. Null means any plant.',
    )
    is_active = models.BooleanField(default=True)
    webhook_url = models.URLField(
        blank=True, null=True,
        help_text='Optional webhook URL for Slack/Teams/PagerDuty notifications',
    )
    notify_websocket = models.BooleanField(
        default=True,
        help_text='Push alert via WebSocket to connected clients',
    )
    cooldown_minutes = models.IntegerField(
        default=5,
        help_text='Suppress repeat alerts for same label+plant within this window',
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='alert_rules_created',
    )

    objects = TenantManager()

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'is_active']),
        ]
        unique_together = [('tenant', 'name')]

    def __str__(self):
        return f'{self.name} ({self.tenant.name})'


class Alert(TenantScopedModel):
    """An alert triggered by a detection matching an alert rule."""

    class Severity(models.TextChoices):
        CRITICAL = 'critical', 'Critical'
        WARNING = 'warning', 'Warning'
        INFO = 'info', 'Info'

    alert_rule = models.ForeignKey(
        AlertRule, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='alerts',
    )
    detection = models.ForeignKey(
        Detection, on_delete=models.CASCADE,
        related_name='alerts',
    )
    image = models.ForeignKey(
        Image, on_delete=models.CASCADE,
        related_name='alerts',
    )
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.WARNING)
    label = models.CharField(max_length=200)
    confidence = models.FloatField()
    plant_site = models.CharField(max_length=200, blank=True, null=True)
    is_acknowledged = models.BooleanField(default=False)
    acknowledged_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='acknowledged_alerts',
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    webhook_sent = models.BooleanField(default=False)
    webhook_response = models.TextField(blank=True, null=True)

    objects = TenantManager()

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'is_acknowledged']),
            models.Index(fields=['tenant', 'severity']),
            models.Index(fields=['tenant', 'created_at']),
        ]

    def __str__(self):
        return f'Alert: {self.label} ({self.severity}) @ {self.plant_site}'
