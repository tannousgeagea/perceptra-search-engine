# apps/tenants/models.py

from django.db import models

from django.contrib.auth import get_user_model
import uuid

User = get_user_model()

class Tenant(models.Model):
    """Organization/Company using the system"""
    tenant_id = models.UUIDField(default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, db_index=True)
    
    # Limits and quotas
    max_storage_gb = models.IntegerField(default=100)
    max_api_calls_per_day = models.IntegerField(default=10000)
    
    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Qdrant collection name
    vector_collection_name = models.CharField(max_length=255, unique=True)
    
    class Meta:
        db_table = 'tenants'
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['is_active']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.qdrant_collection_name:
            self.qdrant_collection_name = f"detections_{self.tenant_id.hex[:12]}"
        super().save(*args, **kwargs)



class TenantMembership(models.Model):
    """Links CustomUser to Tenant with role"""
    tenant_membership_id = models.UUIDField(default=uuid.uuid4, editable=False)
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='tenant_memberships'
    )
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='memberships'
    )
    
    # Role-based access
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('operator', 'Operator'),
        ('viewer', 'Viewer'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='viewer')
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tenant_memberships'
        unique_together = [['user', 'tenant']]
        indexes = [
            models.Index(fields=['user', 'tenant']),
            models.Index(fields=['tenant', 'is_active']),
            models.Index(fields=['user', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.tenant.name} ({self.role})"