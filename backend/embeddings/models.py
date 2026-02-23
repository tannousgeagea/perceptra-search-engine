# apps/embeddings/models.py

from django.db import models
from media.models import TenantScopedModel
import uuid


class ModelVersion(models.Model):
    """Track embedding model versions"""
    model_version_id = models.UUIDField(default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)  # e.g., 'clip-vit-b-32', 'dinov2-base'
    version = models.CharField(max_length=50)
    vector_dimension = models.IntegerField()
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'model_versions'


class EmbeddingJob(TenantScopedModel):
    """Track batch embedding generation jobs"""
    embedding_job_id = models.UUIDField(default=uuid.uuid4, editable=False)
    
    model_version = models.ForeignKey(ModelVersion, on_delete=models.PROTECT)
    
    # Job scope
    total_detections = models.IntegerField()
    processed_detections = models.IntegerField(default=0)
    failed_detections = models.IntegerField(default=0)
    
    # Status
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
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
            models.Index(fields=['created_at']),
        ]