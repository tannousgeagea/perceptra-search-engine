# api/dependencies.py

from fastapi import Depends, HTTPException, status
from typing import Annotated
from tenants.models import Tenant, TenantMembership
from tenants.context import RequestContext
from tenants.resolution import resolve_tenant
from users.auth import get_current_user
from django.contrib.auth import get_user_model

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
    user: Annotated[User, Depends(get_current_user)],   # type: ignore
    tenant: Annotated[Tenant, Depends(resolve_tenant)],
    membership: Annotated[TenantMembership, Depends(get_tenant_membership)]
) -> RequestContext:
    """
    Get complete request context with user, tenant, and role.
    
    Usage:
        @router.get("/endpoint")
        async def my_endpoint(ctx: RequestContext = Depends(get_request_context)):
            # ctx.user, ctx.tenant, ctx.role are all available
            # ctx.has_role('admin')
            # ctx.require_role('admin', 'operator')
    """
    return RequestContext(user, tenant, membership)