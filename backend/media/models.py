# apps/media/models.py

from django.db import models
from backend.tenants.models import Tenant
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

User = get_user_model()
import uuid


class TenantScopedModel(models.Model):
    """Abstract base for tenant-scoped models"""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_index=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    # user
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_created",
        help_text="User who created this record"
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_updated",
        help_text="User who last updated this record"
    )


    class Meta:
        abstract = True


class Video(TenantScopedModel):
    """Video file from inspection"""
    video_id = models.UUIDField(default=uuid.uuid4, editable=False)
    
    # File info
    file_path = models.CharField(max_length=512)  # S3 key or filesystem path
    filename = models.CharField(max_length=255)
    file_size_bytes = models.BigIntegerField()
    duration_seconds = models.FloatField(null=True)
    
    # Metadata
    plant_site = models.CharField(max_length=100, db_index=True)
    shift = models.CharField(max_length=50, null=True, blank=True)
    inspection_line = models.CharField(max_length=100, null=True, blank=True)
    recorded_at = models.DateTimeField(db_index=True)
    
    # Processing status
    STATUS_CHOICES = [
        ('uploaded', 'Uploaded'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='uploaded', db_index=True)
    
    class Meta:
        db_table = 'videos'
        indexes = [
            models.Index(fields=['tenant', 'recorded_at']),
            models.Index(fields=['tenant', 'plant_site']),
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-recorded_at']


class Image(TenantScopedModel):
    """Still image or extracted video frame"""
    image_id = models.UUIDField(default=uuid.uuid4, editable=False)
    
    # Relationship
    video = models.ForeignKey(Video, on_delete=models.CASCADE, null=True, blank=True, related_name='frames')
    
    # File info
    file_path = models.CharField(max_length=512)
    filename = models.CharField(max_length=255)
    file_size_bytes = models.BigIntegerField()
    
    # Image properties
    width = models.IntegerField()
    height = models.IntegerField()
    
    # Video frame info (null if standalone image)
    frame_number = models.IntegerField(null=True, blank=True)
    timestamp_in_video = models.FloatField(null=True, blank=True)  # seconds
    
    # Metadata
    plant_site = models.CharField(max_length=100, db_index=True)
    shift = models.CharField(max_length=50, null=True, blank=True)
    inspection_line = models.CharField(max_length=100, null=True, blank=True)
    captured_at = models.DateTimeField(db_index=True)
    
    
    class Meta:
        db_table = 'images'
        indexes = [
            models.Index(fields=['tenant', 'captured_at']),
            models.Index(fields=['tenant', 'plant_site']),
            models.Index(fields=['video', 'frame_number']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-captured_at']


class Detection(TenantScopedModel):
    """Individual impurity detection (ROI)"""
    detection_id = models.UUIDField(default=uuid.uuid4, editable=False)
    
    # Relationship
    image = models.ForeignKey(Image, on_delete=models.CASCADE, related_name='detections')
    
    # Bounding box (normalized 0-1 or absolute pixels)
    bbox_x = models.FloatField()
    bbox_y = models.FloatField()
    bbox_width = models.FloatField()
    bbox_height = models.FloatField()
    bbox_format = models.CharField(max_length=20, default='normalized')  # 'normalized' or 'absolute'
    
    # Classification
    label = models.CharField(max_length=100, db_index=True)
    confidence = models.FloatField()
    
    # Cropped region (optional, for faster retrieval)
    crop_path = models.CharField(max_length=512, null=True, blank=True)
    
    # Vector DB reference
    vector_point_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    embedding_generated = models.BooleanField(default=False, db_index=True)
    embedding_model_version = models.CharField(max_length=50, null=True, blank=True)
    
    
    class Meta:
        db_table = 'detections'
        indexes = [
            models.Index(fields=['tenant', 'label']),
            models.Index(fields=['tenant', 'embedding_generated']),
            models.Index(fields=['image', 'confidence']),
            models.Index(fields=['qdrant_point_id']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']