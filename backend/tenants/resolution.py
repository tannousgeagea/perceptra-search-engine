# apps/tenants/resolution.py

from typing import Optional
from tenants.models import Tenant
from fastapi import Header, Query, HTTPException
from typing import Annotated


async def resolve_tenant(
    x_tenant_id: Annotated[Optional[str], Header(alias="X-Tenant-ID")] = None,
    x_tenant_domain: Annotated[Optional[str], Header(alias="X-Tenant-Domain")] = None,
    tenant_id: Annotated[Optional[str], Query()] = None,
    tenant_domain: Annotated[Optional[str], Query()] = None,
) -> Tenant:
    """
    Resolve tenant from headers or query parameters.
    Priority: Header > Query Parameter
    Priority: ID > Domain
    """
    
    # Try X-Tenant-ID header first
    if x_tenant_id:
        return await _get_tenant_by_id(x_tenant_id)
    
    # Try tenant_id query param
    if tenant_id:
        return await _get_tenant_by_id(tenant_id)
    
    # Try X-Tenant-Domain header
    if x_tenant_domain:
        return await _get_tenant_by_domain(x_tenant_domain)
    
    # Try tenant_domain query param
    if tenant_domain:
        return await _get_tenant_by_domain(tenant_domain)
    
    # No tenant identifier found
    raise HTTPException(
        status_code=400,
        detail={
            "error": "Tenant identification required",
            "options": [
                "Provide X-Tenant-ID header",
                "Provide X-Tenant-Domain header",
                "Provide tenant_id query parameter",
                "Provide tenant_domain query parameter"
            ]
        }
    )


async def _get_tenant_by_id(tenant_id: str) -> Tenant:
    """Get tenant by UUID"""
    try:
        tenant = await Tenant.objects.aget(tenant_id=tenant_id, is_active=True)
        return tenant
    except Tenant.DoesNotExist:
        raise HTTPException(
            status_code=404,
            detail=f"Tenant with ID '{tenant_id}' not found or inactive"
        )
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tenant ID format: '{tenant_id}'"
        )


async def _get_tenant_by_domain(domain: str) -> Tenant:
    """Get tenant by domain or slug."""
    # Try domain field first, then fall back to slug
    try:
        tenant = await Tenant.objects.aget(domain=domain, is_active=True)
        return tenant
    except Tenant.DoesNotExist:
        pass

    try:
        tenant = await Tenant.objects.aget(slug=domain, is_active=True)
        return tenant
    except Tenant.DoesNotExist:
        raise HTTPException(
            status_code=404,
            detail=f"Tenant with domain '{domain}' not found or inactive"
        )