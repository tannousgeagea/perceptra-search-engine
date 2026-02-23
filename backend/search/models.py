# apps/search/models.py

from django.db import models
from django.contrib.auth import get_user_model
from media.models import TenantScopedModel, Detection
import uuid


User = get_user_model()

class SearchQuery(TenantScopedModel):
    """Log search queries for analytics"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    # Query info
    QUERY_TYPE_CHOICES = [
        ('image', 'Image'),
        ('text', 'Text'),
        ('video', 'Video'),
        ('hybrid', 'Hybrid'),
    ]
    query_type = models.CharField(max_length=20, choices=QUERY_TYPE_CHOICES)
    query_text = models.TextField(null=True, blank=True)
    query_image_path = models.CharField(max_length=512, null=True, blank=True)
    
    # Filters applied
    filters = models.JSONField(default=dict, blank=True)  # plant_site, date_range, labels, etc.
    
    # Results
    results_count = models.IntegerField()
    top_result_id = models.UUIDField(null=True, blank=True)
    
    # Performance
    execution_time_ms = models.IntegerField()
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        db_table = 'search_queries'
        indexes = [
            models.Index(fields=['tenant', 'created_at']),
            models.Index(fields=['tenant', 'query_type']),
            models.Index(fields=['user']),
        ]
        default_manager_name = 'objects'