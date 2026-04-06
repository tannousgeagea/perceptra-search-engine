from django.db import models
from django.contrib.auth import get_user_model
from tenants.managers import TenantManager
from media.models import TenantScopedModel, Image

User = get_user_model()


class ChecklistTemplate(TenantScopedModel):
    """Reusable inspection checklist template for a plant/line."""
    name = models.CharField(max_length=200)
    plant_site = models.CharField(max_length=200)
    inspection_line = models.CharField(max_length=200, blank=True, null=True)
    shift = models.CharField(
        max_length=20, blank=True, null=True,
        help_text='If set, only for this shift. Null means any shift.',
    )
    items = models.JSONField(
        default=list,
        help_text='List of {description, required_photo, auto_detect}',
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='checklist_templates_created',
    )

    objects = TenantManager()

    class Meta:
        ordering = ['-created_at']
        unique_together = [('tenant', 'name')]

    def __str__(self):
        return f'{self.name} ({self.plant_site})'


class ChecklistInstance(TenantScopedModel):
    """A single execution of a checklist template."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        IN_PROGRESS = 'in_progress', 'In Progress'
        COMPLETED = 'completed', 'Completed'
        OVERDUE = 'overdue', 'Overdue'

    template = models.ForeignKey(
        ChecklistTemplate, on_delete=models.CASCADE,
        related_name='instances',
    )
    shift = models.CharField(max_length=20)
    date = models.DateField()
    operator = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='checklist_instances',
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)

    objects = TenantManager()

    class Meta:
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['tenant', 'date', 'status']),
        ]

    def __str__(self):
        return f'{self.template.name} — {self.date} {self.shift}'


class ChecklistItemResult(TenantScopedModel):
    """Result for a single item in a checklist instance."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PASSED = 'passed', 'Passed'
        FAILED = 'failed', 'Failed'
        FLAGGED = 'flagged', 'Flagged'

    instance = models.ForeignKey(
        ChecklistInstance, on_delete=models.CASCADE,
        related_name='results',
    )
    item_index = models.IntegerField()
    image = models.ForeignKey(
        Image, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='checklist_results',
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    notes = models.TextField(blank=True, null=True)
    detection_count = models.IntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)

    objects = TenantManager()

    class Meta:
        ordering = ['item_index']
        unique_together = [('instance', 'item_index')]

    def __str__(self):
        return f'Item {self.item_index} — {self.status}'
