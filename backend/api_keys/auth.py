# api/auth/api_key.py

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
            api_key_obj = await APIKey.objects.select_related('tenant').aget(
                key_prefix=key_prefix
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
        """
        Check if API key has exceeded rate limits.
        
        Args:
            api_key: APIKey instance
            cache_prefix: Cache key prefix
            
        Returns:
            True if within limits, raises HTTPException if exceeded
        """
        now = timezone.now()
        
        # Per-minute check
        minute_key = f"{cache_prefix}:minute:{api_key.api_key_id}:{now.strftime('%Y%m%d%H%M')}"
        minute_count = cache.get(minute_key, 0)
        
        if minute_count >= api_key.rate_limit_per_minute:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: {api_key.rate_limit_per_minute} requests per minute",
                headers={"Retry-After": "60"}
            )
        
        # Per-hour check
        hour_key = f"{cache_prefix}:hour:{api_key.api_key_id}:{now.strftime('%Y%m%d%H')}"
        hour_count = cache.get(hour_key, 0)
        
        if hour_count >= api_key.rate_limit_per_hour:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: {api_key.rate_limit_per_hour} requests per hour",
                headers={"Retry-After": "3600"}
            )
        
        # Increment counters
        cache.set(minute_key, minute_count + 1, 60)
        cache.set(hour_key, hour_count + 1, 3600)
        
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
    
    # Create request context
    # Note: No user for API key auth, just tenant
    context = RequestContext(
        user=None,  # No user for API key
        tenant=tenant,
        membership=None  # type: ignore
    )
    
    # Attach API key info to context
    context.api_key = api_key   # type: ignore
    context.auth_method = 'api_key'  # type: ignore
    
    return context