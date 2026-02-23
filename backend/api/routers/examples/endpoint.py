# api/routers/example.py

from fastapi import APIRouter, Depends, HTTPException
from tenants.context import RequestContext
from api.dependencies import get_request_context

router = APIRouter(prefix="/api", tags=["examples"])


@router.get("/profile")
async def get_profile(ctx: RequestContext = Depends(get_request_context)):
    """
    Get user profile - available to all authenticated users.
    """
    return {
        "user": {
            "id": ctx.user_id,
            "email": ctx.user.email,
            "name": ctx.user.name
        },
        "tenant": {
            "id": ctx.tenant_id,
            "name": ctx.tenant.name,
            "slug": ctx.tenant.slug
        },
        "role": ctx.role
    }


@router.get("/admin-only")
async def admin_endpoint(ctx: RequestContext = Depends(get_request_context)):
    """
    Admin-only endpoint.
    """
    ctx.require_role('admin')
    
    return {
        "message": "You are an admin!",
        "tenant": ctx.tenant.name
    }


@router.post("/upload")
async def upload_data(ctx: RequestContext = Depends(get_request_context)):
    """
    Upload endpoint - requires operator or admin role.
    """
    ctx.require_role('admin', 'operator')
    
    return {
        "message": "Upload successful",
        "user": ctx.user.email,
        "role": ctx.role
    }


@router.get("/view-data")
async def view_data(ctx: RequestContext = Depends(get_request_context)):
    """
    View data - any role can access.
    """
    # No role check needed, just being authenticated is enough
    
    can_edit = ctx.is_operator()  # True for admin or operator
    
    return {
        "data": "some data",
        "can_edit": can_edit,
        "role": ctx.role
    }


@router.delete("/delete/{item_id}")
async def delete_item(
    item_id: str,
    ctx: RequestContext = Depends(get_request_context)
):
    """
    Delete item - admin only with explicit check.
    """
    if not ctx.is_admin():
        raise HTTPException(
            status_code=403,
            detail="Only admins can delete items"
        )
    
    return {
        "message": f"Item {item_id} deleted",
        "deleted_by": ctx.user.email
    }