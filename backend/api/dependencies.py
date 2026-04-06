# api/dependencies.py

from fastapi import Depends, HTTPException, status
from typing import Annotated
from tenants.models import Tenant, TenantMembership
from tenants.context import RequestContext
from tenants.resolution import resolve_tenant
from users.auth import get_current_user
from api_keys.auth import authenticate_with_api_key, get_api_key_from_header
from django.contrib.auth import get_user_model
from typing import Optional
from fastapi import Header, Request


User = get_user_model()


async def get_tenant_membership(
    user: Annotated[User, Depends(get_current_user)],   # type: ignore
    tenant: Annotated[Tenant, Depends(resolve_tenant)]
) -> TenantMembership:
    """
    Verify user has access to tenant and return membership.
    """
    try:
        membership = await TenantMembership.objects.select_related('tenant', 'user').aget(
            user=user,
            tenant=tenant,
            is_active=True
        )
        return membership
    except TenantMembership.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User does not have access to tenant '{tenant.name}'"
        )


async def get_request_context(
    request: Request,
    authorization: Annotated[Optional[str], Header()] = None,
    x_api_key: Annotated[Optional[str], Header(alias="X-API-Key")] = None,
    x_tenant_id: Annotated[Optional[str], Header(alias="X-Tenant-ID")] = None,
    x_tenant_domain: Annotated[Optional[str], Header(alias="X-Tenant-Domain")] = None
) -> RequestContext:
    """
    Get request context with either JWT or API key authentication.
    
    Priority:
    1. API Key (X-API-Key header)
    2. JWT Token (Authorization header)
    
    For JWT auth, tenant must be specified via X-Tenant-ID or X-Tenant-Domain.
    For API Key auth, tenant is automatically determined from the key.

    Usage:
        @router.get("/endpoint")
        async def my_endpoint(ctx: RequestContext = Depends(get_request_context)):
            # ctx.user, ctx.tenant, ctx.role are all available
            # ctx.has_role('admin')
            # ctx.require_role('admin', 'operator')
    """

    if x_api_key:
        return await authenticate_with_api_key(request, x_api_key)

    # Try JWT authentication
    if authorization:
        # Get user from JWT
        user = await get_current_user(authorization)
        tenant = await resolve_tenant(x_tenant_id=x_tenant_id, x_tenant_domain=x_tenant_domain)
        membership = await get_tenant_membership(user, tenant)
        
        # Create context
        return RequestContext(
            user=user, 
            tenant=tenant, 
            membership=membership,
            role=membership.role,
            auth_method='jwt'
        )
            
    # No authentication provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Provide either X-API-Key or Authorization header."
    )


def require_permission(permission: str):
    """
    Dependency to require specific permission level.
    Works with both JWT (role-based) and API Key (permission-based) auth.
    """
    async def _check_permission(ctx: RequestContext = Depends(get_request_context)):
        if hasattr(ctx, 'api_key') and ctx.api_key:
            # API Key authentication
            from api_keys.auth import APIKeyAuth
            APIKeyAuth.check_permission(ctx.api_key, permission)
        else:
            # JWT authentication (role-based)
            role_permission_map = {
                'read': ['admin', 'operator', 'viewer'],
                'write': ['admin', 'operator'],
                'admin': ['admin']
            }
            
            allowed_roles = role_permission_map.get(permission, [])
            if ctx.role not in allowed_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Requires '{permission}' permission"
                )
        
        return ctx
    
    return _check_permission

def require_scope(scope: str):
    """
    Dependency to require specific scope.
    Only applicable for API Key authentication.
    """
    async def _check_scope(ctx: RequestContext = Depends(get_request_context)):
        if hasattr(ctx, 'api_key') and ctx.api_key:
            from api_keys.auth import APIKeyAuth
            APIKeyAuth.check_scope(ctx.api_key, scope)
        # JWT auth doesn't use scopes, so we allow it
        
        return ctx
    
    return _check_scope