import uuid
from django.db import models
from django.contrib.auth import get_user_model
from media.models import TenantScopedModel

User = get_user_model()


class StreamType(models.TextChoices):
    RTSP = 'rtsp', 'RTSP Stream'
    MJPEG = 'mjpeg', 'MJPEG HTTP Stream'
    UPLOAD = 'upload', 'Uploaded Video File'


class CameraStatus(models.TextChoices):
    IDLE = 'idle', 'Idle'
    STREAMING = 'streaming', 'Streaming'
    ERROR = 'error', 'Error'


class RiskLevel(models.TextChoices):
    LOW = 'low', 'Low'
    MEDIUM = 'medium', 'Medium'
    HIGH = 'high', 'High'
    CRITICAL = 'critical', 'Critical'


class AlertType(models.TextChoices):
    CONTAMINATION = 'contamination', 'Contamination'
    BLOCKAGE = 'blockage', 'Line Blockage'
    ESCALATION = 'escalation', 'Escalation'
    DRIFT = 'drift', 'Composition Drift'


class WasteCamera(TenantScopedModel):
    """A registered camera in the WasteVision inspection system."""

    camera_uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True, editable=False)
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=200)
    plant_site = models.CharField(max_length=100, blank=True)
    stream_type = models.CharField(max_length=20, choices=StreamType.choices, default=StreamType.RTSP)
    stream_url = models.CharField(max_length=500, blank=True, help_text='RTSP URL, MJPEG HTTP URL, or local file path')
    target_fps = models.FloatField(default=2.0, help_text='Frames per second to emit for VLM analysis')
    is_active = models.BooleanField(default=True, db_index=True)
    status = models.CharField(max_length=20, choices=CameraStatus.choices, default=CameraStatus.IDLE, db_index=True)
    last_frame_at = models.DateTimeField(null=True, blank=True)
    last_risk_level = models.CharField(max_length=20, blank=True)
    consecutive_high = models.IntegerField(default=0, help_text='Consecutive high/critical risk frames')

    class Meta:
        unique_together = [('tenant', 'name')]
        indexes = [
            models.Index(fields=['tenant', 'is_active']),
            models.Index(fields=['tenant', 'status']),
        ]
        ordering = ['name']

    def __str__(self):
        return f'{self.name} @ {self.location} ({self.tenant.name})'


class WasteInspection(TenantScopedModel):
    """A single VLM analysis result for one camera frame."""

    inspection_uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True, editable=False)
    camera = models.ForeignKey(WasteCamera, on_delete=models.CASCADE, related_name='inspections')
    sequence_no = models.BigIntegerField(help_text='Monotonic frame counter per camera')
    frame_timestamp = models.DateTimeField(help_text='When the frame was captured')
    waste_composition = models.JSONField(
        help_text='Waste material percentages: {plastic, paper, glass, metal, organic, e_waste, hazardous, other}'
    )
    contamination_alerts = models.JSONField(
        default=list,
        help_text='List of detected contaminants: [{item, severity, location_in_frame, action}]'
    )
    line_blockage = models.BooleanField(default=False)
    overall_risk = models.CharField(max_length=20, choices=RiskLevel.choices, db_index=True)
    confidence = models.FloatField()
    inspector_note = models.TextField()
    vlm_provider = models.CharField(max_length=50)
    vlm_model = models.CharField(max_length=100)
    processing_time_ms = models.IntegerField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['camera', 'created_at']),
            models.Index(fields=['tenant', 'created_at']),
            models.Index(fields=['overall_risk']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'Inspection {self.inspection_uuid} — {self.overall_risk} @ {self.camera.name}'


class WasteAlert(TenantScopedModel):
    """An alert triggered by the WasteVision rule engine."""

    alert_uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True, editable=False)
    camera = models.ForeignKey(WasteCamera, on_delete=models.CASCADE, related_name='waste_alerts')
    inspection = models.ForeignKey(
        WasteInspection, on_delete=models.SET_NULL, null=True, blank=True, related_name='alerts'
    )
    alert_type = models.CharField(max_length=50, choices=AlertType.choices)
    severity = models.CharField(max_length=20, choices=RiskLevel.choices, db_index=True)
    details = models.JSONField(default=dict, help_text='Type-specific alert metadata')
    is_acknowledged = models.BooleanField(default=False, db_index=True)
    acknowledged_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='acknowledged_waste_alerts'
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['camera', 'created_at']),
            models.Index(fields=['tenant', 'is_acknowledged']),
            models.Index(fields=['severity']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'WasteAlert {self.alert_type}/{self.severity} — {self.camera.name}'
