# apps/embeddings/models.py

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from tenants.models import Tenant
from media.models import TenantScopedModel
import uuid


class EmbeddingModelType(models.TextChoices):
    """Supported embedding model types."""
    CLIP = 'clip', _('CLIP (OpenAI)')
    DINOV2 = 'dinov2', _('DINOv2 (Meta)')
    PERCEPTION = 'perception', _('Perception Encoder')
    SAM3 = 'sam3', _('SAM3')

class ModelVersion(models.Model):
    """Track embedding model versions"""
    model_version_id = models.UUIDField(default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text=_('Model identifier (e.g., clip-vit-b-32, dinov2-base)')
    )
    model_type = models.CharField(
        max_length=50,
        choices=EmbeddingModelType.choices,
        default=EmbeddingModelType.CLIP,
        help_text=_('Type of embedding model')
    )
    version = models.CharField(
        max_length=50,
        help_text=_('Model version string')
    )
    vector_dimension = models.IntegerField(
        help_text=_('Dimension of embedding vectors')
    )
    # Model configuration (JSON)
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text=_('Model-specific configuration parameters')
    )
    
    # Performance metadata
    avg_inference_time_ms = models.FloatField(
        null=True,
        blank=True,
        help_text=_('Average inference time in milliseconds')
    )
    
    # Status
    is_active = models.BooleanField(
        default=False,
        db_index=True,
        help_text=_('Currently active model (only one can be active)')
    )
    
    # Lifecycle
    activated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_('When this model was activated')
    )
    deactivated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_('When this model was deactivated')
    )

    description = models.TextField(
        blank=True,
        help_text=_('Optional description of the model version')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'model_versions'
        indexes = [
            models.Index(fields=['model_type', 'is_active']),
            models.Index(fields=['is_active', 'activated_at']),
        ]
        ordering = ['-activated_at', '-created_at']
    
    def __str__(self):
        active_status = "ACTIVE" if self.is_active else "inactive"
        return f"{self.name} ({self.model_type}) [{active_status}]"

    @property
    def collection_suffix(self):
        """Get collection name suffix for this model."""
        return self.name.replace('-', '_').replace('.', '_').lower()
    
    def clean(self):
        """Validate that only one model is active."""
        if self.is_active:
            active_models = ModelVersion.objects.filter(is_active=True).exclude(pk=self.pk).first()
            if active_models:
                raise ValidationError(
                    _('Only one model can be active at a time. Current active: %(model)s'),
                    params={'model': active_models.name}
                )
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
    
    @classmethod
    def get_active_model(cls):
        """Get the currently active model."""
        try:
            return cls.objects.get(is_active=True)
        except cls.DoesNotExist:
            raise ValueError("No active embedding model configured")
        except cls.MultipleObjectsReturned:
            # Safety fallback: return most recently activated
            return cls.objects.filter(is_active=True).order_by('-activated_at').first()

class VectorDBType(models.TextChoices):
    """Supported vector database types."""
    QDRANT = 'qdrant', _('Qdrant')
    FAISS = 'faiss', _('FAISS')


class CollectionPurpose(models.TextChoices):
    """Purpose of a vector collection — extensible as new embedding
    strategies are added (delta tracking, fusion, clustering, etc.)."""
    EMBEDDINGS = 'embeddings', _('Primary embeddings')
    DELTAS = 'deltas', _('Temporal delta vectors')
    FUSION = 'fusion', _('Multi-model fusion vectors')


class TenantVectorCollection(models.Model):
    """
    Track vector collections per tenant, model, and purpose.
    Each tenant can have multiple collections for the same model version
    when they serve different purposes (primary embeddings, temporal
    deltas, multi-model fusion, etc.).
    """
    tenant_vector_collection_id = models.UUIDField(default=uuid.uuid4, editable=False)

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='vector_collections'
    )

    model_version = models.ForeignKey(
        ModelVersion,
        on_delete=models.PROTECT,
        related_name='tenant_collections'
    )

    purpose = models.CharField(
        max_length=30,
        choices=CollectionPurpose.choices,
        default=CollectionPurpose.EMBEDDINGS,
        help_text=_('What kind of vectors this collection stores'),
    )

    # Collection naming: tenant_{tenant_id}_{model_suffix}[_{purpose}]
    collection_name = models.CharField(
        max_length=255,
        unique=True,
        help_text=_('Unique collection name in vector DB')
    )

    db_type = models.CharField(
        max_length=50,
        choices=VectorDBType.choices,
        help_text=_('Vector database type')
    )

    # Collection stats
    total_vectors = models.IntegerField(
        default=0,
        help_text=_('Total number of vectors in collection')
    )

    # Status
    is_active = models.BooleanField(
        default=True,
        help_text=_('Whether this collection is actively used for new embeddings')
    )
    is_searchable = models.BooleanField(
        default=True,
        help_text=_('Whether this collection is included in searches')
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tenant_vector_collections'
        unique_together = [('tenant', 'model_version', 'purpose')]
        indexes = [
            models.Index(fields=['tenant', 'is_active']),
            models.Index(fields=['tenant', 'is_searchable']),
            models.Index(fields=['collection_name']),
            models.Index(fields=['tenant', 'purpose']),
        ]

    def __str__(self):
        return f"{self.tenant.name} - {self.model_version.name} ({self.purpose}) [{self.collection_name}]"

    def save(self, *args, **kwargs):
        if not self.collection_name:
            # Generate collection name: tenant_<short_uuid>_<model_suffix>[_<purpose>]
            tenant_short = str(self.tenant.tenant_id).replace('-', '')[:12]
            model_suffix = self.model_version.collection_suffix
            if self.purpose == CollectionPurpose.EMBEDDINGS:
                self.collection_name = f"tenant_{tenant_short}_{model_suffix}"
            else:
                self.collection_name = f"tenant_{tenant_short}_{model_suffix}_{self.purpose}"
        super().save(*args, **kwargs)


class EmbeddingJob(models.Model):
    """Track batch embedding generation jobs"""
    embedding_job_id = models.UUIDField(default=uuid.uuid4, editable=False)
    
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='embedding_jobs'
    )

    model_version = models.ForeignKey(
        ModelVersion, 
        on_delete=models.PROTECT
    )
    
    collection = models.ForeignKey(
        TenantVectorCollection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    # Job scope
    job_type = models.CharField(
        max_length=50,
        choices=[
            ('images', 'Images'),
            ('detections', 'Detections'),
            ('migration', 'Model Migration')
        ],
        default='detections'
    )
    
    total_items = models.IntegerField(default=0)
    processed_items = models.IntegerField(default=0)
    failed_items = models.IntegerField(default=0)
    
    # Status
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Timing
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Error tracking
    error_message = models.TextField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'embedding_jobs'
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['model_version', 'status']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Job {self.embedding_job_id} - {self.tenant.name} - {self.status}"
    
    @property
    def progress_percent(self):
        """Calculate job progress percentage."""
        if self.total_items == 0:
            return 0
        return round((self.processed_items / self.total_items) * 100, 2)


# ─────────────────────────────────────────────────────────────
# Auto-Detection Configuration & Tracking
# ─────────────────────────────────────────────────────────────

class DetectionBackendType(models.TextChoices):
    """Supported detection backends."""
    SAM3_PERCEPTRA = 'sam3_perceptra', _('SAM3 (perceptra-seg)')


class TenantHazardConfig(models.Model):
    """Per-tenant configuration for automatic hazard detection.

    Each tenant can have multiple configs (e.g. different inspection
    profiles), but only ``is_active=True`` configs are used when new
    images are uploaded.  Exactly one config per tenant should be
    ``is_default=True`` — this is the one used when no specific config
    ID is passed to the detection task.
    """
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='hazard_configs',
    )
    name = models.CharField(
        max_length=100,
        help_text=_('Profile name (e.g. "Default Inspection Profile")'),
    )
    prompts = models.JSONField(
        help_text=_('List of text prompts for detection, e.g. ["metallic pipe", "rust", "container"]'),
    )
    detection_backend = models.CharField(
        max_length=50,
        choices=DetectionBackendType.choices,
        default=DetectionBackendType.SAM3_PERCEPTRA,
        help_text=_('Detection backend to use'),
    )
    confidence_threshold = models.FloatField(
        default=0.3,
        help_text=_('Minimum confidence score to keep a detection (0-1)'),
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text=_('Active configs are evaluated on every new image upload'),
    )
    is_default = models.BooleanField(
        default=False,
        help_text=_('Default config used when no specific config ID is provided'),
    )
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text=_('Backend-specific extra configuration'),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tenant_hazard_configs'
        unique_together = [('tenant', 'name')]
        indexes = [
            models.Index(fields=['tenant', 'is_active']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        status = 'ACTIVE' if self.is_active else 'inactive'
        default = ' (default)' if self.is_default else ''
        return f"{self.tenant.name} — {self.name} [{status}]{default}"

    def clean(self):
        if not isinstance(self.prompts, list) or not self.prompts:
            raise ValidationError({'prompts': _('Prompts must be a non-empty list of strings.')})
        if not all(isinstance(p, str) and p.strip() for p in self.prompts):
            raise ValidationError({'prompts': _('Each prompt must be a non-empty string.')})
        if not 0 <= self.confidence_threshold <= 1:
            raise ValidationError({'confidence_threshold': _('Must be between 0 and 1.')})


class DetectionJobStatus(models.TextChoices):
    PENDING = 'pending', _('Pending')
    RUNNING = 'running', _('Running')
    COMPLETED = 'completed', _('Completed')
    FAILED = 'failed', _('Failed')
    SKIPPED = 'skipped', _('Skipped')


class DetectionJob(models.Model):
    """Tracks the status of an automatic detection run for a single image.

    One ``DetectionJob`` is created per ``(image, hazard_config)`` pair
    when ``auto_detect_image_task`` is dispatched.
    """
    detection_job_id = models.UUIDField(default=uuid.uuid4, editable=False)

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='detection_jobs',
    )
    image = models.ForeignKey(
        'media.Image',
        on_delete=models.CASCADE,
        related_name='detection_jobs',
    )
    hazard_config = models.ForeignKey(
        TenantHazardConfig,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='detection_jobs',
    )
    detection_backend = models.CharField(
        max_length=50,
        choices=DetectionBackendType.choices,
        default=DetectionBackendType.SAM3_PERCEPTRA,
    )

    total_detections = models.IntegerField(default=0)

    status = models.CharField(
        max_length=20,
        choices=DetectionJobStatus.choices,
        default=DetectionJobStatus.PENDING,
        db_index=True,
    )

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    inference_time_ms = models.FloatField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'detection_jobs'
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['image', 'status']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"DetectionJob {str(self.detection_job_id)[:8]} — {self.status}"