# api/dependencies.py

from fastapi import Header, HTTPException, Depends, Request
from typing import Optional, Annotated
from django.contrib.auth import get_user_model
from tenants.models import Tenant, TenantMembership
import logging

logger = logging.getLogger(__name__)

User = get_user_model()


async def get_tenant(
    x_tenant_id: Annotated[Optional[str], Header()] = None,
    request: Request = None
) -> Tenant:
    """
    Extract and validate tenant from request.
    Priority: Header > Subdomain
    """
    tenant = None
    
    # Method 1: X-Tenant-ID header
    if x_tenant_id:
        try:
            tenant = await Tenant.objects.aget(id=x_tenant_id, is_active=True)
        except Tenant.DoesNotExist:
            raise HTTPException(status_code=400, detail="Invalid tenant ID")
    
    # Method 2: Subdomain
    if not tenant and request:
        host = request.headers.get('host', '').split(':')[0]
        parts = host.split('.')
        if len(parts) > 2:
            subdomain = parts[0]
            try:
                tenant = await Tenant.objects.aget(slug=subdomain, is_active=True)
            except Tenant.DoesNotExist:
                pass
    
    if not tenant:
        raise HTTPException(
            status_code=400,
            detail="Tenant identification required. Provide X-Tenant-ID header or use subdomain."
        )
    
    return tenant


async def get_current_user(
    authorization: Annotated[Optional[str], Header()] = None
) -> User:
    """
    Extract user from JWT token.
    Placeholder - implement your JWT validation logic.
    """
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization token")
    
    token = authorization.split(' ')[1]
    
    # TODO: Implement JWT validation
    # user_id = decode_jwt(token)
    # user = await User.objects.aget(id=user_id)
    
    # Placeholder
    raise HTTPException(status_code=401, detail="JWT validation not implemented")


async def verify_tenant_access(
    user: Annotated[User, Depends(get_current_user)],
    tenant: Annotated[Tenant, Depends(get_tenant)]
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
        raise HTTPException(status_code=403, detail="Access denied to this tenant")


def require_role(*allowed_roles: str):
    """
    Dependency to check if user has required role.
    Usage: Depends(require_role('admin', 'operator'))
    """
    async def _check_role(
        membership: Annotated[TenantMembership, Depends(verify_tenant_access)]
    ):
        if membership.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Requires one of roles: {', '.join(allowed_roles)}"
            )
        return membership
    
    return _check_role