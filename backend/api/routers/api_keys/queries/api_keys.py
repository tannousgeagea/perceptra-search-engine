# api/routers/api_keys.py

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Annotated, List, Optional
from tenants.context import RequestContext
from api_keys.models import APIKey
from api.dependencies import get_request_context
from pydantic import BaseModel, Field
from datetime import datetime
from asgiref.sync import sync_to_async

router = APIRouter(prefix="/api-keys", tags=["API Keys"])


class APIKeyCreate(BaseModel):
    """Request to create an API key."""
    name: str = Field(..., min_length=1, max_length=100)
    permissions: str = Field(default='read', pattern='^(read|write|admin)$')
    scopes: Optional[List[str]] = None
    rate_limit_per_minute: int = Field(default=60, ge=1, le=1000)
    rate_limit_per_hour: int = Field(default=1000, ge=1, le=100000)
    expires_days: Optional[int] = Field(default=None, ge=1, le=365)
    allowed_ips: Optional[List[str]] = None


class APIKeyResponse(BaseModel):
    """API key response (without the actual key)."""
    id: str
    name: str
    key_prefix: str
    permissions: str
    scopes: List[str]
    rate_limit_per_minute: int
    rate_limit_per_hour: int
    is_active: bool
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    total_requests: int
    created_at: datetime
    
    model_config = {
        "from_attributes": True
    }


class APIKeyWithSecret(BaseModel):
    """API key response with the actual key (only returned once on creation)."""
    api_key: APIKeyResponse
    secret_key: str
    warning: str = "Save this key securely. It will not be shown again."


@router.post("/", response_model=APIKeyWithSecret)
async def create_api_key(
    request: APIKeyCreate,
    ctx: RequestContext = Depends(get_request_context)
):
    """
    Create a new API key.
    
    Requires admin role or API key with 'admin' permission.
    The secret key is only returned once - save it securely!
    """
    # Check permission (admin only)
    if hasattr(ctx, 'api_key') and ctx.api_key:
        # API key auth
        if not ctx.api_key.has_permission('admin'):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Requires admin permission to create API keys"
            )
        created_by = None
    else:
        # JWT auth
        ctx.require_role('admin')
        created_by = ctx.user
    
    # Calculate expiration
    expires_at = None
    if request.expires_days:
        from django.utils import timezone
        from datetime import timedelta
        expires_at = timezone.now() + timedelta(days=request.expires_days)
    
    # Create API key
    api_key, secret_key = await sync_to_async(APIKey.create_key)(
        tenant=ctx.tenant,
        name=request.name,
        permissions=request.permissions,
        created_by=created_by,
        expires_at=expires_at,
        scopes=request.scopes or [],
        rate_limit_per_minute=request.rate_limit_per_minute,
        rate_limit_per_hour=request.rate_limit_per_hour,
        allowed_ips=request.allowed_ips or []
    )
    
    return APIKeyWithSecret(
        api_key=APIKeyResponse.model_validate(api_key),
        secret_key=secret_key
    )


@router.get("/", response_model=List[APIKeyResponse])
async def list_api_keys(
    is_active: Optional[bool] = None,
    ctx: RequestContext = Depends(get_request_context)
):
    """
    List all API keys for the tenant.
    
    Requires admin role or API key with 'admin' permission.
    """
    # Check permission
    if hasattr(ctx, 'api_key') and ctx.api_key:
        if not ctx.api_key.has_permission('admin'):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Requires admin permission"
            )
    else:
        ctx.require_role('admin')
    
    # Query API keys
    queryset = APIKey.objects.filter(tenant=ctx.tenant)
    
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    
    api_keys = await sync_to_async(list)(queryset.order_by('-created_at'))
    
    return [APIKeyResponse.model_validate(key) for key in api_keys]


@router.get("/{key_id}", response_model=APIKeyResponse)
async def get_api_key(
    key_id: str,
    ctx: RequestContext = Depends(get_request_context)
):
    """Get details of a specific API key."""
    # Check permission
    if hasattr(ctx, 'api_key') and ctx.api_key:
        if not ctx.api_key.has_permission('admin'):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Requires admin permission"
            )
    else:
        ctx.require_role('admin')
    
    try:
        api_key = await APIKey.objects.aget(id=key_id, tenant=ctx.tenant)
    except APIKey.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    return APIKeyResponse.model_validate(api_key)


@router.patch("/{key_id}", response_model=APIKeyResponse)
async def update_api_key(
    key_id: str,
    name: Optional[str] = None,
    is_active: Optional[bool] = None,
    rate_limit_per_minute: Optional[int] = None,
    rate_limit_per_hour: Optional[int] = None,
    ctx: RequestContext = Depends(get_request_context)
):
    """
    Update an API key.
    
    Can update name, active status, and rate limits.
    Cannot update permissions or scopes (create a new key instead).
    """
    # Check permission
    if hasattr(ctx, 'api_key') and ctx.api_key:
        if not ctx.api_key.has_permission('admin'):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Requires admin permission"
            )
    else:
        ctx.require_role('admin')
    
    try:
        api_key = await APIKey.objects.aget(id=key_id, tenant=ctx.tenant)
    except APIKey.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    # Update fields
    if name is not None:
        api_key.name = name
    if is_active is not None:
        api_key.is_active = is_active
    if rate_limit_per_minute is not None:
        api_key.rate_limit_per_minute = rate_limit_per_minute
    if rate_limit_per_hour is not None:
        api_key.rate_limit_per_hour = rate_limit_per_hour
    
    await sync_to_async(api_key.save)()
    
    # Invalidate cache
    from django.core.cache import cache
    cache.delete(f"api_key:{api_key.key_prefix}")
    
    return APIKeyResponse.model_validate(api_key)


@router.delete("/{key_id}")
async def delete_api_key(
    key_id: str,
    ctx: RequestContext = Depends(get_request_context)
):
    """
    Delete (revoke) an API key.
    
    This is permanent and cannot be undone.
    """
    # Check permission
    if hasattr(ctx, 'api_key') and ctx.api_key:
        if not ctx.api_key.has_permission('admin'):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Requires admin permission"
            )
    else:
        ctx.require_role('admin')
    
    try:
        api_key = await APIKey.objects.aget(id=key_id, tenant=ctx.tenant)
    except APIKey.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    # Delete from cache
    from django.core.cache import cache
    cache.delete(f"api_key:{api_key.key_prefix}")
    
    # Delete from database
    await sync_to_async(api_key.delete)()
    
    return {"message": "API key deleted successfully"}


@router.get("/{key_id}/usage", response_model=dict)
async def get_api_key_usage(
    key_id: str,
    days: int = 7,
    ctx: RequestContext = Depends(get_request_context)
):
    """Get usage statistics for an API key."""
    # Check permission
    if hasattr(ctx, 'api_key') and ctx.api_key:
        if not ctx.api_key.has_permission('admin'):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Requires admin permission"
            )
    else:
        ctx.require_role('admin')
    
    try:
        api_key = await APIKey.objects.aget(id=key_id, tenant=ctx.tenant)
    except APIKey.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    # Get usage logs
    from django.utils import timezone
    from datetime import timedelta
    from django.db import models
    from api_keys.models import APIKeyUsageLog
    
    since = timezone.now() - timedelta(days=days)
    
    logs = await sync_to_async(list)(
        APIKeyUsageLog.objects.filter(
            api_key=api_key,
            request_time__gte=since
        ).values('endpoint', 'method', 'status_code').annotate(
            count=models.Count('id')
        )
    )
    
    return {
        'key_id': str(api_key.api_key_id),
        'key_name': api_key.name,
        'total_requests': api_key.total_requests,
        'last_used_at': api_key.last_used_at,
        'usage_by_endpoint': logs
    }