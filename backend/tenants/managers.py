from django.db import models
from django.db.models import QuerySet

class TenantQuerySet(QuerySet):
    """QuerySet that filters by tenant"""
    
    def for_tenant(self, tenant):
        """Filter queryset by tenant"""
        if tenant is None:
            raise ValueError("Tenant cannot be None")
        return self.filter(tenant=tenant)


class TenantManager(models.Manager):
    """Manager that automatically filters by tenant"""
    
    def get_queryset(self):
        return TenantQuerySet(self.model, using=self._db)
    
    def for_tenant(self, tenant):
        """Get queryset for specific tenant"""
        return self.get_queryset().for_tenant(tenant)


class TenantAwareManager(TenantManager):
    """
    Manager with tenant context from thread-local storage.
    Automatically filters all queries by current tenant.
    """
    
    def get_queryset(self):
        qs = super().get_queryset()
        tenant = get_current_tenant()
        if tenant:
            qs = qs.for_tenant(tenant)
        return qs


# Thread-local storage for tenant context
import threading

_thread_locals = threading.local()


def set_current_tenant(tenant):
    """Set tenant for current thread"""
    _thread_locals.tenant = tenant


def get_current_tenant():
    """Get tenant for current thread"""
    return getattr(_thread_locals, 'tenant', None)


def clear_current_tenant():
    """Clear tenant context"""
    if hasattr(_thread_locals, 'tenant'):
        delattr(_thread_locals, 'tenant')