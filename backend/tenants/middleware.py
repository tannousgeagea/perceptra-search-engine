# apps/tenants/middleware.py

from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from .models import Tenant, TenantMembership
import logging
from .managers import set_current_tenant, clear_current_tenant

logger = logging.getLogger(__name__)


class TenantMiddleware(MiddlewareMixin):
    """
    Resolves tenant from request and attaches to request object.
    Supports: subdomain, X-Tenant-ID header, or JWT claim
    """
    
    def process_request(self, request):
        tenant = None
        
        # Method 1: From header (primary for API)
        tenant_id = request.headers.get('X-Tenant-ID')
        if tenant_id:
            try:
                tenant = Tenant.objects.get(id=tenant_id, is_active=True)
            except Tenant.DoesNotExist:
                return JsonResponse({'error': 'Invalid tenant'}, status=400)
        
        # Method 2: From subdomain
        if not tenant:
            host = request.get_host().split(':')[0]  # Remove port
            parts = host.split('.')
            if len(parts) > 2:  # tenant.domain.com
                subdomain = parts[0]
                try:
                    tenant = Tenant.objects.get(slug=subdomain, is_active=True)
                except Tenant.DoesNotExist:
                    pass
        
        # Method 3: From JWT (if using token auth)
        if not tenant and hasattr(request, 'user') and request.user.is_authenticated:
            # Get from token claims or user's first active membership
            memberships = TenantMembership.objects.filter(
                user=request.user,
                is_active=True
            ).select_related('tenant').first()
            
            if memberships:
                tenant = memberships.tenant
        
        # Attach tenant to request
        request.tenant = tenant
        
        # Verify user has access to this tenant
        if tenant and hasattr(request, 'user') and request.user.is_authenticated:
            try:
                membership = TenantMembership.objects.get(
                    user=request.user,
                    tenant=tenant,
                    is_active=True
                )
                request.tenant_membership = membership
                request.tenant_role = membership.role
            except TenantMembership.DoesNotExist:
                return JsonResponse({'error': 'Access denied to tenant'}, status=403)
        
        # Set thread-local tenant
        if tenant:
            set_current_tenant(tenant)

        return None

    def process_response(self, request, response):
        """Clear tenant context after request"""
        clear_current_tenant()
        return response
    
    def process_exception(self, request, exception):
        """Clear tenant context on exception"""
        clear_current_tenant()
        return None


class TenantRequiredMiddleware(MiddlewareMixin):
    """
    Ensures tenant is present for API endpoints.
    Place after TenantMiddleware.
    """
    
    EXCLUDED_PATHS = [
        '/admin/',
        '/auth/',
        '/health/',
        '/docs/',
    ]
    
    def process_request(self, request):
        # Skip for excluded paths
        if any(request.path.startswith(path) for path in self.EXCLUDED_PATHS):
            return None
        
        # Check if tenant is required
        if not hasattr(request, 'tenant') or request.tenant is None:
            return JsonResponse({
                'error': 'Tenant identification required',
                'hint': 'Provide X-Tenant-ID header or use subdomain'
            }, status=400)
        
        return None