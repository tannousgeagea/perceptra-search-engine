# api_keys/auth.py

from typing import Optional, Tuple
from fastapi import HTTPException, status, Header, Request
from typing import Annotated
from tenants.models import Tenant
from api_keys.models import  APIKey
from tenants.context import RequestContext
from django.utils import timezone
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)


class APIKeyAuth:
    """API Key authentication handler."""
    
    @staticmethod
    async def verify_api_key(api_key: str) -> Tuple[APIKey, Tenant]:
        """
        Verify API key and return associated API key object and tenant.
        
        Args:
            api_key: Raw API key string
            
        Returns:
            Tuple of (APIKey instance, Tenant instance)
            
        Raises:
            HTTPException: If key is invalid
        """
        # Validate format
        if not api_key.startswith('ise_'):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key format"
            )
        
        # Extract prefix
        key_prefix = api_key[:12]
        
        # Check cache first (60 second TTL)
        cache_key = f"api_key:{key_prefix}"
        cached_data = cache.get(cache_key)
        
        if cached_data:
            api_key_obj, tenant = cached_data
            
            # Verify full key
            if not api_key_obj.verify_key(api_key):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid API key"
                )
            
            # Check if still valid
            if not api_key_obj.is_valid():
                cache.delete(cache_key)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="API key is inactive or expired"
                )
            
            return api_key_obj, tenant
        
        # Query database
        try:
            api_key_obj = await (
                APIKey.objects
                .select_related('tenant', 'created_by', 'owned_by')
                .aget(key_prefix=key_prefix)
            )
        except APIKey.DoesNotExist:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key"
            )
        
        # Verify full key
        if not api_key_obj.verify_key(api_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key"
            )
        
        # Check if valid
        if not api_key_obj.is_valid():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key is inactive or expired"
            )
        
        tenant = api_key_obj.tenant
        
        # Cache for 60 seconds
        cache.set(cache_key, (api_key_obj, tenant), 60)
        
        return api_key_obj, tenant
    
    @staticmethod
    def check_rate_limit(api_key: APIKey, cache_prefix: str = "rate_limit") -> bool:
        now = timezone.now()

        minute_key = f"{cache_prefix}:minute:{api_key.api_key_id}:{now.strftime('%Y%m%d%H%M')}"
        hour_key   = f"{cache_prefix}:hour:{api_key.api_key_id}:{now.strftime('%Y%m%d%H')}"

        # cache.add sets the key only if it doesn't exist (atomic).
        # cache.incr is atomic on Redis/Memcached — no read-modify-write race.
        cache.add(minute_key, 0, 60)
        minute_count = cache.incr(minute_key)

        if minute_count > api_key.rate_limit_per_minute:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: {api_key.rate_limit_per_minute} requests/min",
                headers={"Retry-After": "60"},
            )

        cache.add(hour_key, 0, 3600)
        hour_count = cache.incr(hour_key)

        if hour_count > api_key.rate_limit_per_hour:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: {api_key.rate_limit_per_hour} requests/hr",
                headers={"Retry-After": "3600"},
            )

        return True
    
    @staticmethod
    def check_ip_restriction(api_key: APIKey, ip_address: str) -> bool:
        """
        Check if request IP is allowed.
        
        Args:
            api_key: APIKey instance
            ip_address: Client IP address
            
        Returns:
            True if allowed, raises HTTPException if not
        """
        if not api_key.is_ip_allowed(ip_address):
            logger.warning(
                f"API key {api_key.key_prefix} used from unauthorized IP: {ip_address}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key not authorized from this IP address"
            )
        
        return True
    
    @staticmethod
    def check_scope(api_key: APIKey, required_scope: str) -> bool:
        """
        Check if API key has required scope.
        
        Args:
            api_key: APIKey instance
            required_scope: Required scope string
            
        Returns:
            True if has scope, raises HTTPException if not
        """
        if not api_key.has_scope(required_scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key does not have required scope: {required_scope}"
            )
        
        return True
    
    @staticmethod
    def check_permission(api_key: APIKey, required_permission: str) -> bool:
        """
        Check if API key has required permission level.
        
        Args:
            api_key: APIKey instance
            required_permission: Required permission ('read', 'write', 'admin')
            
        Returns:
            True if has permission, raises HTTPException if not
        """
        if not api_key.has_permission(required_permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key requires '{required_permission}' permission"
            )
        
        return True


async def get_api_key_from_header(
    x_api_key: Annotated[Optional[str], Header(alias="X-API-Key")] = None
) -> Optional[str]:
    """Extract API key from header."""
    return x_api_key


# =============================================================================
# api/auth/api_key.py
#
# Role resolution is done here, fully async, before RequestContext is built.
# One async function owns the full resolution chain:
#   verify_api_key → load owned_by membership → derive effective role → build ctx
# =============================================================================

async def _resolve_api_key_role(api_key, tenant) -> str:
    """
    Derive the effective role for an API key request.

    Rules:
      1. If the key has no owned_by, it acts as its creator — map the key's
         declared permission to a role directly.
      2. If the key has an owned_by, fetch that user's membership and take
         the lower of (key permission, membership role). This ensures an admin
         cannot create a key that exceeds the target user's actual privileges.
      3. If owned_by has lost their membership, drop to 'viewer' and log —
         the key is still valid but maximally restricted until reviewed.
    """
    from tenants.models import TenantMembership

    _permission_to_rank = {'read': 1, 'write': 2, 'admin': 3}
    _rank_to_role       = {1: 'viewer', 2: 'operator', 3: 'admin'}
    _role_to_rank       = {'viewer': 1, 'operator': 2, 'admin': 3}
    _permission_to_role = {'read': 'viewer', 'write': 'operator', 'admin': 'admin'}

    if api_key.owned_by is None:
        # No delegation — key acts as its creator at the declared permission level
        return _permission_to_role.get(api_key.permissions, 'viewer')

    # owned_by is already loaded (select_related in verify_api_key)
    # but the membership is not — fetch it now, properly async
    try:
        membership = await TenantMembership.objects.aget(
            user=api_key.owned_by,
            tenant=tenant,
            is_active=True,
        )
    except TenantMembership.DoesNotExist:
        # owned_by user lost their membership after the key was created
        logger.warning(
            f"API key {api_key.key_prefix}: owned_by user "
            f"{api_key.owned_by_id} has no active membership in "
            f"tenant {tenant.slug}. Restricting to viewer."
        )
        return 'viewer'

    key_rank    = _permission_to_rank.get(api_key.permissions, 1)
    member_rank = _role_to_rank.get(membership.role, 1)
    effective   = min(key_rank, member_rank)   # lower of the two wins

    return _rank_to_role[effective]


async def authenticate_with_api_key(
    request: Request,
    x_api_key: Annotated[Optional[str], Header(alias="X-API-Key")] = None
) -> RequestContext:
    """
    Authenticate request using API key.
    
    Returns:
        RequestContext with tenant and API key info
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Provide X-API-Key header."
        )
    
    # Verify API key
    api_key, tenant = await APIKeyAuth.verify_api_key(x_api_key)
    
    # Get client IP
    client_ip = request.client.host if request.client else "unknown"
    
    # Check IP restriction
    APIKeyAuth.check_ip_restriction(api_key, client_ip)
    
    # Check rate limits
    APIKeyAuth.check_rate_limit(api_key)
    
    # Record usage (async)
    from asgiref.sync import sync_to_async
    await sync_to_async(api_key.record_usage)(client_ip)
    
    # Resolve role fully async before touching RequestContext
    role = await _resolve_api_key_role(api_key, tenant)

    # Create request context
    # Note: No user for API key auth, just tenant
    context = RequestContext(
        user=None,  # No user for API key
        tenant=tenant,
        membership=None,  # type: ignore
        api_key=api_key,
        role=role,
        auth_method='api_key'
    )
    
    return context