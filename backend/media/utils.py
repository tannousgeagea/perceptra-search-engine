# apps/media/utils.py

from typing import List, Optional
from media.models import Tag
from tenants.models import Tenant
from django.contrib.auth import get_user_model

User = get_user_model()


async def get_or_create_tags(
    tag_inputs: List[dict],
    tenant: Tenant,
    user: Optional[User] = None   # type: ignore
) -> List[Tag]:
    """
    Get existing tags or create new ones.
    
    Args:
        tag_inputs: List of tag dictionaries with 'name', 'description', 'color'
        tenant: Tenant instance
        user: User creating the tags (optional)
        
    Returns:
        List of Tag instances
    """
    tags = []
    
    for tag_input in tag_inputs:
        tag_name = tag_input.get('name', '').strip()
        
        if not tag_name:
            continue
        
        # Try to get existing tag
        tag = await Tag.objects.filter(
            tenant=tenant,
            name__iexact=tag_name
        ).afirst()
        
        # Create if doesn't exist
        if not tag:
            tag = await Tag.objects.acreate(
                tenant=tenant,
                name=tag_name,
                description=tag_input.get('description', ''),
                color=tag_input.get('color', '#3B82F6')
            )
        
        tags.append(tag)
    
    return tags