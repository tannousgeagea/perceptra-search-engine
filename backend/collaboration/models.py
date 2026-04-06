from django.db import models
from django.contrib.auth import get_user_model
from tenants.managers import TenantManager
from media.models import TenantScopedModel, Detection

User = get_user_model()


class Comment(TenantScopedModel):
    """Comment on an image, detection, or video."""

    class ContentType(models.TextChoices):
        IMAGE = 'image', 'Image'
        DETECTION = 'detection', 'Detection'
        VIDEO = 'video', 'Video'

    content_type = models.CharField(max_length=20, choices=ContentType.choices)
    object_id = models.IntegerField()
    author = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='comments',
    )
    text = models.TextField()
    mentions = models.JSONField(default=list, blank=True, help_text='List of mentioned user IDs')

    objects = TenantManager()

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['tenant', 'content_type', 'object_id']),
        ]

    def __str__(self):
        return f'Comment by {self.author.email} on {self.content_type}:{self.object_id}'


class Assignment(TenantScopedModel):
    """Assignment of a detection to a team member."""

    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        IN_PROGRESS = 'in_progress', 'In Progress'
        RESOLVED = 'resolved', 'Resolved'
        WONT_FIX = 'wont_fix', "Won't Fix"

    class Priority(models.TextChoices):
        LOW = 'low', 'Low'
        MEDIUM = 'medium', 'Medium'
        HIGH = 'high', 'High'
        CRITICAL = 'critical', 'Critical'

    detection = models.ForeignKey(
        Detection, on_delete=models.CASCADE,
        related_name='assignments',
    )
    assigned_to = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='assignments_received',
    )
    assigned_by = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='assignments_given',
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM)
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    objects = TenantManager()

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'assigned_to', 'status']),
        ]

    def __str__(self):
        return f'Assignment: {self.detection.label} → {self.assigned_to.email}'


class ActivityEvent(TenantScopedModel):
    """Activity feed event for tracking team actions."""

    class Action(models.TextChoices):
        UPLOADED = 'uploaded', 'Uploaded'
        DETECTED = 'detected', 'Detected'
        COMMENTED = 'commented', 'Commented'
        ASSIGNED = 'assigned', 'Assigned'
        RESOLVED = 'resolved', 'Resolved'
        ACKNOWLEDGED = 'acknowledged', 'Acknowledged'

    user = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='activity_events',
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    target_type = models.CharField(max_length=20)
    target_id = models.IntegerField()
    metadata = models.JSONField(default=dict, blank=True)

    objects = TenantManager()

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'created_at']),
            models.Index(fields=['tenant', 'user']),
        ]

    def __str__(self):
        return f'{self.user.email} {self.action} {self.target_type}:{self.target_id}'
