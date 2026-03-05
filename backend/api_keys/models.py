# apps/tenants/models.py (add to existing file)

import secrets
import hashlib
from typing import Optional
from django.db import models
from django.utils import timezone
from tenants.models import Tenant
from django.utils.translation import gettext_lazy as _
import uuid


class APIKey(models.Model):
    """
    API Keys for programmatic access to the platform.
    Each key is associated with a tenant and has specific permissions.
    """
    
    api_key_id = models.UUIDField(default=uuid.uuid4, editable=False)
    
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='api_keys'
    )
    
    # Key identification
    name = models.CharField(
        max_length=100,
        help_text=_('Friendly name for the API key')
    )
    
    # The actual key (hashed for security)
    key_prefix = models.CharField(
        max_length=8,
        unique=True,
        db_index=True,
        help_text=_('First 8 characters of the key (for identification)')
    )
    key_hash = models.CharField(
        max_length=128,
        unique=True,
        help_text=_('SHA-256 hash of the full key')
    )
    
    # Permissions
    PERMISSION_CHOICES = [
        ('read', 'Read Only'),
        ('write', 'Read & Write'),
        ('admin', 'Admin (Full Access)'),
    ]

    permissions = models.CharField(
        max_length=20,
        choices=PERMISSION_CHOICES,
        default='read',
        help_text=_('Permission level for this API key')
    )
    
    # Scopes (specific API endpoints/resources the key can access)
    scopes = models.JSONField(
        default=list,
        blank=True,
        help_text=_('List of allowed scopes/endpoints')
    )
    
    # Rate limiting
    rate_limit_per_minute = models.IntegerField(
        default=60,
        help_text=_('Maximum requests per minute')
    )
    rate_limit_per_hour = models.IntegerField(
        default=1000,
        help_text=_('Maximum requests per hour')
    )
    
    # Usage tracking
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_('Last time this key was used')
    )
    total_requests = models.BigIntegerField(
        default=0,
        help_text=_('Total number of requests made with this key')
    )
    
    # Status
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text=_('Whether this key is active')
    )
    
    # Expiration
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_('When this key expires (null = never)')
    )
    
    # Metadata
    created_by = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_api_keys'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # IP restrictions (optional)
    allowed_ips = models.JSONField(
        default=list,
        blank=True,
        help_text=_('List of allowed IP addresses (empty = allow all)')
    )
    
    class Meta:
        db_table = 'api_keys'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'is_active']),
            models.Index(fields=['key_prefix']),
            models.Index(fields=['expires_at']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.key_prefix}...)"
    
    @classmethod
    def generate_key(cls) -> str:
        """
        Generate a secure random API key.
        Format: ise_<32 random characters>
        """
        random_part = secrets.token_urlsafe(32)
        return f"ise_{random_part}"
    
    @classmethod
    def hash_key(cls, key: str) -> str:
        """Hash an API key using SHA-256."""
        return hashlib.sha256(key.encode()).hexdigest()
    
    @classmethod
    def create_key(
        cls,
        tenant,
        name: str,
        permissions: str = 'read',
        created_by=None,
        expires_at=None,
        **kwargs
    ):
        """
        Create a new API key.
        Returns tuple of (api_key_instance, raw_key)
        """
        # Generate key
        raw_key = cls.generate_key()
        
        # Extract prefix (first 8 chars after 'ise_')
        key_prefix = raw_key[:12]  # 'ise_' + 8 chars
        
        # Hash the key
        key_hash = cls.hash_key(raw_key)
        
        # Create instance
        api_key = cls.objects.create(
            tenant=tenant,
            name=name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            permissions=permissions,
            created_by=created_by,
            expires_at=expires_at,
            **kwargs
        )
        
        return api_key, raw_key
    
    def verify_key(self, raw_key: str) -> bool:
        """Verify that a raw key matches this API key."""
        return self.key_hash == self.hash_key(raw_key)
    
    def is_valid(self) -> bool:
        """Check if the API key is valid (active and not expired)."""
        if not self.is_active:
            return False
        
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        
        return True
    
    def record_usage(self, ip_address: Optional[str] = None):
        """Record API key usage."""
        self.last_used_at = timezone.now()
        self.total_requests += 1
        self.save(update_fields=['last_used_at', 'total_requests', 'updated_at'])
    
    def has_permission(self, required_permission: str) -> bool:
        """Check if key has required permission level."""
        permission_hierarchy = {
            'read': 1,
            'write': 2,
            'admin': 3
        }
        
        current_level = permission_hierarchy.get(self.permissions, 0)
        required_level = permission_hierarchy.get(required_permission, 0)
        
        return current_level >= required_level
    
    def has_scope(self, scope: str) -> bool:
        """Check if key has access to a specific scope."""
        if not self.scopes:  # Empty scopes = access to all
            return True
        return scope in self.scopes
    
    def is_ip_allowed(self, ip_address: str) -> bool:
        """Check if IP address is allowed."""
        if not self.allowed_ips:  # Empty = allow all
            return True
        return ip_address in self.allowed_ips


class APIKeyUsageLog(models.Model):
    """
    Log of API key usage for analytics and security.
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    api_key = models.ForeignKey(
        APIKey,
        on_delete=models.CASCADE,
        related_name='usage_logs'
    )
    
    # Request details
    endpoint = models.CharField(max_length=255)
    method = models.CharField(max_length=10)
    status_code = models.IntegerField()
    
    # Client info
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    
    # Timing
    request_time = models.DateTimeField(auto_now_add=True, db_index=True)
    response_time_ms = models.IntegerField(help_text=_('Response time in milliseconds'))
    
    # Error tracking
    error_message = models.TextField(blank=True)
    
    class Meta:
        db_table = 'api_key_usage_logs'
        ordering = ['-request_time']
        indexes = [
            models.Index(fields=['api_key', 'request_time']),
            models.Index(fields=['request_time']),
            models.Index(fields=['ip_address']),
        ]