from pydantic import BaseModel, Field, UUID4
from typing import Optional, List, Literal
from datetime import datetime
from api.routers.search.schemas import (
    SearchFilterParams,
    ImageSearchResult,
    DetectionSearchResult,
)


class AgentSearchRequest(BaseModel):
    """Natural language search request processed by the LLM agent."""
    query: str = Field(..., min_length=1, max_length=1000,
                       description="Natural language search query")
    top_k: int = Field(default=10, ge=1, le=50)
    search_type: Literal['images', 'detections', 'both'] = 'detections'
    filters: Optional[SearchFilterParams] = Field(
        default=None,
        description="Explicit filters that override LLM-extracted filters",
    )
    enable_reasoning: bool = Field(
        default=False,
        description="Enable post-retrieval LLM reasoning/summary (Phase 3)",
    )


class SearchPlan(BaseModel):
    """Structured search plan produced by the LLM, returned for transparency."""
    search_method: Literal['text', 'similar']
    query_text: Optional[str] = None
    item_id: Optional[int] = None
    item_type: Optional[Literal['image', 'detection']] = None
    filters: Optional[SearchFilterParams] = None
    top_k: int = 10
    reasoning: str = ""


class AgentSearchResponse(BaseModel):
    """Response from the agent search endpoint."""
    query_id: UUID4
    original_query: str
    search_plan: SearchPlan
    image_results: Optional[List[ImageSearchResult]] = None
    detection_results: Optional[List[DetectionSearchResult]] = None
    total_results: int
    execution_time_ms: int
    llm_time_ms: int
    llm_provider: str
    model_version: str
    agent_summary: Optional[str] = None
    fallback_used: bool = False
