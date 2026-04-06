"""Provider-neutral tool definitions and execution functions for the agent.

Tool schemas are stored in Anthropic format (name, description, input_schema).
Each LLM provider client adapts these to its own format internally.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from asgiref.sync import sync_to_async
from media.models import Image, Detection
from search.services import SearchService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool schemas (provider-neutral, Anthropic-style)
# ---------------------------------------------------------------------------

AGENT_TOOLS = [
    {
        "name": "search_text",
        "description": (
            "Search for images or detections using a text description. "
            "Use this for any query that describes what the user wants to find visually. "
            "The text is encoded by CLIP into a vector and matched against stored embeddings."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query_text": {
                    "type": "string",
                    "description": "Visual description to search for (e.g., 'metal pipe', 'rust contamination')",
                },
                "plant_site": {
                    "type": "string",
                    "description": "Filter by plant site name",
                },
                "shift": {
                    "type": "string",
                    "description": "Filter by shift",
                },
                "inspection_line": {
                    "type": "string",
                    "description": "Filter by inspection line",
                },
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by detection labels",
                },
                "date_from": {
                    "type": "string",
                    "description": "ISO datetime string, start of date range",
                },
                "date_to": {
                    "type": "string",
                    "description": "ISO datetime string, end of date range",
                },
                "min_confidence": {
                    "type": "number",
                    "description": "Minimum detection confidence (0.0 to 1.0)",
                },
                "max_confidence": {
                    "type": "number",
                    "description": "Maximum detection confidence (0.0 to 1.0)",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return (default 10, max 50)",
                },
                "search_type": {
                    "type": "string",
                    "enum": ["images", "detections", "both"],
                    "description": "What to search: images, detections, or both",
                },
            },
            "required": ["query_text"],
        },
    },
    {
        "name": "search_similar",
        "description": (
            "Find items visually similar to an existing image or detection by its ID. "
            "Use this when the user references a specific item and wants 'more like this'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "integer",
                    "description": "ID of the image or detection to find similar items for",
                },
                "item_type": {
                    "type": "string",
                    "enum": ["image", "detection"],
                    "description": "Whether the ID refers to an image or detection",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return (default 10, max 50)",
                },
                "plant_site": {
                    "type": "string",
                    "description": "Filter by plant site name",
                },
                "date_from": {
                    "type": "string",
                    "description": "ISO datetime, start of date range",
                },
                "date_to": {
                    "type": "string",
                    "description": "ISO datetime, end of date range",
                },
            },
            "required": ["item_id", "item_type"],
        },
    },
    {
        "name": "get_available_metadata",
        "description": (
            "Get the list of available plant sites, shifts, inspection lines, and labels "
            "in the system. Use this when you need to map a user's informal terms to the "
            "actual filter values. Call this BEFORE search_text if the user mentions a "
            "location, shift, or label that might need normalization."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


# ---------------------------------------------------------------------------
# Filter extraction helper
# ---------------------------------------------------------------------------

FILTER_KEYS = {
    "plant_site", "shift", "inspection_line", "labels",
    "date_from", "date_to", "min_confidence", "max_confidence",
    "video_id",
}


def extract_filters(params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract SearchFilterParams-compatible dict from LLM tool call params."""
    filters = {}
    for key in FILTER_KEYS:
        value = params.get(key)
        if value is not None:
            filters[key] = value

    # Parse ISO date strings to datetime objects
    for dt_key in ("date_from", "date_to"):
        if dt_key in filters and isinstance(filters[dt_key], str):
            try:
                filters[dt_key] = datetime.fromisoformat(filters[dt_key])
            except ValueError:
                logger.warning(f"Invalid date format from LLM: {filters[dt_key]}")
                del filters[dt_key]

    return filters if filters else None


# ---------------------------------------------------------------------------
# Tool execution functions
# ---------------------------------------------------------------------------

async def execute_search_text(
    tenant,
    user,
    params: Dict[str, Any],
) -> Tuple[list, int, str]:
    """Execute text search tool call against SearchService."""
    service = SearchService(tenant=tenant, user=user)
    filters = extract_filters(params)

    results, time_ms, query_id = await sync_to_async(service.search_by_text)(
        query_text=params["query_text"],
        top_k=min(params.get("top_k", 10), 50),
        search_type=params.get("search_type", "detections"),
        filters=filters,
        score_threshold=params.get("score_threshold"),
    )
    return results, time_ms, query_id


async def execute_search_similar(
    tenant,
    user,
    params: Dict[str, Any],
) -> Tuple[list, int, str]:
    """Execute similarity search tool call against SearchService."""
    service = SearchService(tenant=tenant, user=user)
    filters = extract_filters(params)

    results, time_ms, query_id = await sync_to_async(service.search_similar)(
        item_id=params["item_id"],
        item_type=params.get("item_type", "detection"),
        top_k=min(params.get("top_k", 10), 50),
        filters=filters,
    )
    return results, time_ms, query_id


async def execute_get_metadata(tenant) -> Dict[str, Any]:
    """Return distinct filterable values for the tenant."""
    plant_sites = await sync_to_async(list)(
        Image.objects.filter(tenant=tenant)
        .values_list("plant_site", flat=True)
        .distinct()
    )
    labels = await sync_to_async(list)(
        Detection.objects.filter(tenant=tenant)
        .values_list("label", flat=True)
        .distinct()
    )
    shifts = await sync_to_async(list)(
        Image.objects.filter(tenant=tenant)
        .values_list("shift", flat=True)
        .distinct()
    )
    inspection_lines = await sync_to_async(list)(
        Image.objects.filter(tenant=tenant)
        .values_list("inspection_line", flat=True)
        .distinct()
    )

    return {
        "plant_sites": [s for s in plant_sites if s],
        "labels": [l for l in labels if l],
        "shifts": [s for s in shifts if s],
        "inspection_lines": [il for il in inspection_lines if il],
    }
