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
        membership: Optional[TenantMembership],
        role: str,
        api_key: Optional[Any] = None,
        auth_method:Optional[str] = 'jwt'
    ):
        self.user = user
        self.tenant = tenant
        self.membership = membership
        self.api_key = api_key
        self.auth_method = auth_method
        self.role = role

    @property
    def effective_user(self):
        """
        Always returns a user instance safe to assign to created_by / updated_by.

        Resolution order:
          1. JWT-authenticated user (ctx.user)
          2. The user who created the API key (api_key.created_by)
          3. None — field is nullable, record is still created
        """
        if self.user is not None:
            return self.user
        if self.api_key is not None:
            return self.api_key.owned_by or self.api_key.created_by
        return None

    @property
    def effective_api_key(self):
        return self.api_key if self.auth_method == 'api_key' else None


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
    def user_id(self) -> Optional[str]:
        u = self.effective_user
        return str(u.id) if u else None

    def __repr__(self):
        user_label = self.effective_user.email if self.effective_user else 'anonymous'
        return f"RequestContext(user={user_label}, tenant={self.tenant.slug}, role={self.role})"
