# api/routers/api_keys.py

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from datetime import timedelta
from asgiref.sync import sync_to_async
from django.utils import timezone
from django.db.models import Count

from tenants.context import RequestContext
from tenants.models import TenantMembership
from api_keys.models import APIKey, APIKeyUsageLog
from api.dependencies import require_permission
from pydantic import BaseModel, Field
from datetime import datetime
import logging

router = APIRouter(prefix="/api-keys", tags=["API Keys"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class APIKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    permissions: str = Field(default='read', pattern='^(read|write|admin)$')
    # owned_by: the user this key acts on behalf of.
    # Null means the key acts as the admin who created it.
    owned_by_user_id: Optional[int] = Field(
        default=None,
        description=(
            "ID of the user this key acts on behalf of. "
            "Must be an active member of the tenant. "
            "Key permission cannot exceed the user's role."
        ),
    )
    scopes: Optional[List[str]] = None
    rate_limit_per_minute: int = Field(default=60, ge=1, le=1000)
    rate_limit_per_hour: int = Field(default=1000, ge=1, le=100000)
    expires_days: Optional[int] = Field(default=None, ge=1, le=365)
    allowed_ips: Optional[List[str]] = None


class OwnedByResponse(BaseModel):
    id: int
    email: str

    model_config = {"from_attributes": True}


class APIKeyResponse(BaseModel):
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
    owned_by: Optional[OwnedByResponse] = None

    model_config = {"from_attributes": True}


class APIKeyWithSecret(BaseModel):
    api_key: APIKeyResponse
    secret_key: str
    warning: str = "Save this key securely. It will not be shown again."


class APIKeyUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    is_active: Optional[bool] = None
    rate_limit_per_minute: Optional[int] = Field(default=None, ge=1, le=1000)
    rate_limit_per_hour: Optional[int] = Field(default=None, ge=1, le=100000)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ROLE_TO_PERMISSION_RANK = {'viewer': 1, 'operator': 2, 'admin': 3}
_PERMISSION_TO_RANK = {'read': 1, 'write': 2, 'admin': 3}
_RANK_TO_PERMISSION = {1: 'read', 2: 'write', 3: 'admin'}


async def _resolve_owned_by(owned_by_user_id: int, requested_permission: str, ctx: RequestContext):
    """
    Validate owned_by_user_id and enforce the permission ceiling.

    Rules:
      - owned_by must be an active member of the tenant
      - key permission cannot exceed the owned_by user's membership role
      - returns the User instance
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    try:
        owned_by_user = await User.objects.aget(id=owned_by_user_id)
    except User.DoesNotExist:
        raise HTTPException(status_code=404, detail=f"User {owned_by_user_id} not found")

    try:
        membership = await TenantMembership.objects.aget(
            user=owned_by_user,
            tenant=ctx.tenant,
            is_active=True,
        )
    except TenantMembership.DoesNotExist:
        raise HTTPException(
            status_code=400,
            detail=f"User {owned_by_user_id} is not an active member of this tenant",
        )

    key_rank = _PERMISSION_TO_RANK.get(requested_permission, 1)
    member_rank = _ROLE_TO_PERMISSION_RANK.get(membership.role, 1)

    if key_rank > member_rank:
        max_allowed = _RANK_TO_PERMISSION[member_rank]
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot grant '{requested_permission}' permission to a user "
                f"whose role only allows '{max_allowed}'"
            ),
        )

    return owned_by_user


def _build_response(api_key: APIKey) -> APIKeyResponse:
    """
    Build APIKeyResponse, safely handling owned_by which may or may not
    be loaded into fields_cache depending on the call path.
    """
    owned_by_data = None
    try:
        # Will raise if not in fields_cache and we're in sync context —
        # callers that need owned_by must use select_related beforehand.
        ob = api_key.owned_by
        if ob is not None:
            owned_by_data = OwnedByResponse(id=ob.id, email=ob.email)
    except Exception:
        # owned_by not loaded — omit rather than crash
        pass

    return APIKeyResponse(
        id=str(api_key.api_key_id),
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        permissions=api_key.permissions,
        scopes=api_key.scopes or [],
        rate_limit_per_minute=api_key.rate_limit_per_minute,
        rate_limit_per_hour=api_key.rate_limit_per_hour,
        is_active=api_key.is_active,
        expires_at=api_key.expires_at,
        last_used_at=api_key.last_used_at,
        total_requests=api_key.total_requests,
        created_at=api_key.created_at,
        owned_by=owned_by_data,
    )


async def _invalidate_cache(key_prefix: str):
    from django.core.cache import cache
    await sync_to_async(cache.delete)(f"api_key:{key_prefix}")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/", response_model=APIKeyWithSecret, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    request: APIKeyCreate,
    ctx: RequestContext = Depends(require_permission('admin')),
):
    """
    Create a new API key. Admin only.
    The secret key is returned once — save it securely.
    """
    expires_at = None
    if request.expires_days:
        expires_at = timezone.now() + timedelta(days=request.expires_days)

    # Resolve and validate owned_by if provided
    owned_by_user = None
    if request.owned_by_user_id is not None:
        owned_by_user = await _resolve_owned_by(
            request.owned_by_user_id, request.permissions, ctx
        )

    api_key, secret_key = await sync_to_async(APIKey.create_key)(
        tenant=ctx.tenant,
        name=request.name,
        permissions=request.permissions,
        created_by=ctx.effective_user,
        owned_by=owned_by_user,        # None = key acts as its creator
        expires_at=expires_at,
        scopes=request.scopes or [],
        rate_limit_per_minute=request.rate_limit_per_minute,
        rate_limit_per_hour=request.rate_limit_per_hour,
        allowed_ips=request.allowed_ips or [],
    )

    logger.info(
        f"API key created: prefix={api_key.key_prefix} "
        f"tenant={ctx.tenant.slug} "
        f"created_by={ctx.effective_user} "
        f"owned_by={owned_by_user}"
    )

    return APIKeyWithSecret(
        api_key=_build_response(api_key),
        secret_key=secret_key,
    )


@router.get("/", response_model=List[APIKeyResponse])
async def list_api_keys(
    is_active: Optional[bool] = None,
    ctx: RequestContext = Depends(require_permission('admin')),
):
    """List all API keys for the tenant. Admin only."""
    queryset = (
        APIKey.objects
        .filter(tenant=ctx.tenant)
        .select_related('owned_by')   # load owned_by in one query
        .order_by('-created_at')
    )
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)

    api_keys = await sync_to_async(list)(queryset)
    return [_build_response(k) for k in api_keys]


@router.get("/{key_id}", response_model=APIKeyResponse)
async def get_api_key(
    key_id: str,
    ctx: RequestContext = Depends(require_permission('admin')),
):
    """Get details of a specific API key. Admin only."""
    try:
        api_key = await (
            APIKey.objects
            .select_related('owned_by')
            .aget(api_key_id=key_id, tenant=ctx.tenant)
        )
    except APIKey.DoesNotExist:
        raise HTTPException(status_code=404, detail="API key not found")

    return _build_response(api_key)


@router.patch("/{key_id}", response_model=APIKeyResponse)
async def update_api_key(
    key_id: str,
    request: APIKeyUpdate,
    ctx: RequestContext = Depends(require_permission('admin')),
):
    """
    Update name, active status, or rate limits. Admin only.
    Permissions and scopes cannot be changed — create a new key instead.
    """
    try:
        api_key = await (
            APIKey.objects
            .select_related('owned_by')
            .aget(api_key_id=key_id, tenant=ctx.tenant)
        )
    except APIKey.DoesNotExist:
        raise HTTPException(status_code=404, detail="API key not found")

    update_fields = ['updated_at']

    if request.name is not None:
        api_key.name = request.name
        update_fields.append('name')
    if request.is_active is not None:
        api_key.is_active = request.is_active
        update_fields.append('is_active')
    if request.rate_limit_per_minute is not None:
        api_key.rate_limit_per_minute = request.rate_limit_per_minute
        update_fields.append('rate_limit_per_minute')
    if request.rate_limit_per_hour is not None:
        api_key.rate_limit_per_hour = request.rate_limit_per_hour
        update_fields.append('rate_limit_per_hour')

    await sync_to_async(api_key.save)(update_fields=update_fields)
    await _invalidate_cache(api_key.key_prefix)

    return _build_response(api_key)


@router.delete("/{key_id}", status_code=status.HTTP_200_OK)
async def delete_api_key(
    key_id: str,
    ctx: RequestContext = Depends(require_permission('admin')),
):
    """Permanently revoke an API key. Admin only."""
    try:
        api_key = await APIKey.objects.aget(api_key_id=key_id, tenant=ctx.tenant)
    except APIKey.DoesNotExist:
        raise HTTPException(status_code=404, detail="API key not found")

    await _invalidate_cache(api_key.key_prefix)
    await sync_to_async(api_key.delete)()

    logger.info(
        f"API key deleted: prefix={api_key.key_prefix} tenant={ctx.tenant.slug} "
        f"deleted_by={ctx.effective_user}"
    )
    return {"message": "API key deleted successfully"}


@router.get("/{key_id}/usage")
async def get_api_key_usage(
    key_id: str,
    days: int = Query(default=7, ge=1, le=90),
    ctx: RequestContext = Depends(require_permission('admin')),
):
    """Usage statistics for an API key. Admin only."""
    try:
        api_key = await APIKey.objects.aget(api_key_id=key_id, tenant=ctx.tenant)
    except APIKey.DoesNotExist:
        raise HTTPException(status_code=404, detail="API key not found")

    since = timezone.now() - timedelta(days=days)

    usage_by_endpoint = await sync_to_async(list)(
        APIKeyUsageLog.objects
        .filter(api_key=api_key, request_time__gte=since)
        .values('endpoint', 'method', 'status_code')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    return {
        'key_id': str(api_key.api_key_id),
        'key_name': api_key.name,
        'total_requests': api_key.total_requests,
        'last_used_at': api_key.last_used_at,
        'period_days': days,
        'usage_by_endpoint': usage_by_endpoint,
    }