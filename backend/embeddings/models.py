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

class TenantVectorCollection(models.Model):
    """
    Track vector collections per tenant and model.
    Each tenant has separate collections for each model version (privacy + history).
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
    
    # Collection naming: tenant_{tenant_id}_{model_suffix}
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
        unique_together = [('tenant', 'model_version')]
        indexes = [
            models.Index(fields=['tenant', 'is_active']),
            models.Index(fields=['tenant', 'is_searchable']),
            models.Index(fields=['collection_name']),
        ]
    
    def __str__(self):
        return f"{self.tenant.name} - {self.model_version.name} [{self.collection_name}]"
    
    def save(self, *args, **kwargs):
        if not self.collection_name:
            # Generate collection name: tenant_<short_uuid>_<model_suffix>
            tenant_short = str(self.tenant.tenant_id).replace('-', '')[:12]
            model_suffix = self.model_version.collection_suffix
            self.collection_name = f"tenant_{tenant_short}_{model_suffix}"
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