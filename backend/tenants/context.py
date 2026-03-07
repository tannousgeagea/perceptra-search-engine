# apps/tenants/context.py

from typing import Optional, Any
from fastapi import HTTPException, status
from tenants.models import Tenant, TenantMembership
from django.contrib.auth import get_user_model

User = get_user_model()


class RequestContext:
    """Request context with user, tenant, and role."""
    
    def __init__(
        self,
        user: User,    #type: ignore
        tenant: Tenant,
        membership: TenantMembership,
        api_key: Optional[Any] = None,
        auth_method:Optional[str] = 'jwt'
    ):
        self.user = user
        self.tenant = tenant
        self.membership = membership
        if self.membership:
            self.role = membership.role
        self.api_key = api_key
        self.auth_method = auth_method
    
    def has_role(self, *role_names: str) -> bool:
        """Check if user has any of the specified roles."""
        return self.role in role_names
    
    def require_role(self, *role_names: str):
        """Raise exception if user doesn't have required role."""
        if not self.has_role(*role_names):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required roles: {', '.join(role_names)}. Your role: {self.role}"
            )
    
    def is_admin(self) -> bool:
        """Check if user is admin."""
        return self.role == 'admin'
    
    def is_operator(self) -> bool:
        """Check if user is operator or admin."""
        return self.role in ['admin', 'operator']
    
    def is_viewer(self) -> bool:
        """Check if user has at least viewer access."""
        return self.role in ['admin', 'operator', 'viewer']
    
    @property
    def tenant_id(self) -> str:
        """Get tenant ID as string."""
        return str(self.tenant.id)   # type: ignore
    
    @property
    def user_id(self) -> str:
        """Get user ID as string."""
        return str(self.user.id)
    
    def __repr__(self):
        return f"RequestContext(user={self.user.email}, tenant={self.tenant.slug}, role={self.role})"