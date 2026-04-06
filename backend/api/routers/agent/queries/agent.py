"""Agent search endpoint — LLM-orchestrated natural language search."""

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from asgiref.sync import sync_to_async

from tenants.context import RequestContext
from api.dependencies import get_request_context, require_scope
from api.routers.agent.schemas import (
    AgentSearchRequest,
    AgentSearchResponse,
    SearchPlan,
)
from api.routers.agent.tools import (
    AGENT_TOOLS,
    execute_search_text,
    execute_search_similar,
    execute_get_metadata,
    extract_filters,
)
from api.routers.search.schemas import SearchFilterParams
from api.routers.search.queries.search import (
    _build_image_result,
    _build_detection_result,
)
from infrastructure.llm.factory import get_llm_client
from infrastructure.llm.prompts import AGENT_SYSTEM_PROMPT
from infrastructure.llm.base import LLMResponse
from embeddings.models import ModelVersion

router = APIRouter(prefix="/agent", tags=["agent"])
logger = logging.getLogger(__name__)

MAX_LLM_TURNS = int(os.environ.get("AGENT_MAX_TURNS", "3"))
AGENT_TIMEOUT = int(os.environ.get("AGENT_TIMEOUT_SECONDS", "10"))


@router.post("/search", response_model=AgentSearchResponse)
async def agent_search(
    request: AgentSearchRequest,
    ctx: RequestContext = Depends(require_scope("search")),
):
    """Search using natural language, powered by an LLM agent.

    The agent interprets the query, extracts filters, selects the
    appropriate search method, and executes it against the existing
    search infrastructure. Falls back to plain text search on LLM failure.
    """
    agent_enabled = os.environ.get("AGENT_ENABLED", "true").lower() == "true"
    if not agent_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent search is currently disabled.",
        )

    llm_start = time.time()
    fallback = False
    llm_provider = os.environ.get("LLM_PROVIDER", "anthropic")

    try:
        plan, llm_time = await asyncio.wait_for(
            _run_llm_planning(request, ctx),
            timeout=AGENT_TIMEOUT,
        )
    except Exception as e:
        logger.warning(f"LLM planning failed ({type(e).__name__}: {e}), using fallback")
        plan = SearchPlan(
            search_method="text",
            query_text=request.query,
            filters=request.filters,
            top_k=request.top_k,
            reasoning="Fallback: LLM planning failed, using raw query as text search.",
        )
        llm_time = int((time.time() - llm_start) * 1000)
        fallback = True

    # Build effective filters: user-explicit filters override LLM-extracted ones
    effective_filters = _merge_filters(plan.filters, request.filters)

    # Build tool params for execution
    search_params = _build_search_params(plan, request, effective_filters)

    # Execute the search
    try:
        if plan.search_method == "text":
            results, exec_time, query_id = await execute_search_text(
                ctx.tenant, ctx.user, search_params,
            )
        elif plan.search_method == "similar":
            results, exec_time, query_id = await execute_search_similar(
                ctx.tenant, ctx.user, search_params,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown search method: {plan.search_method}",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Agent search execution failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search execution failed. Please try again.",
        )

    # Build response objects (reuse existing helpers)
    image_results = []
    detection_results = []
    for r in results:
        try:
            if r.payload.get("type") == "image":
                image_results.append(await _build_image_result(r.payload, r.score))
            elif r.payload.get("type") == "detection":
                detection_results.append(await _build_detection_result(r.payload, r.score))
        except Exception as e:
            logger.warning(f"Failed to build result for {r.payload.get('type')}: {e}")
            continue

    model_version = await sync_to_async(ModelVersion.objects.get)(is_active=True)

    return AgentSearchResponse(
        query_id=uuid.UUID(query_id),
        original_query=request.query,
        search_plan=plan,
        image_results=image_results if image_results else None,
        detection_results=detection_results if detection_results else None,
        total_results=len(results),
        execution_time_ms=exec_time,
        llm_time_ms=llm_time,
        llm_provider=llm_provider,
        model_version=model_version.name,
        fallback_used=fallback,
    )


async def _run_llm_planning(
    request: AgentSearchRequest,
    ctx: RequestContext,
) -> tuple:
    """Run the LLM planning loop. Returns (SearchPlan, llm_time_ms)."""
    client = get_llm_client()
    system = AGENT_SYSTEM_PROMPT.format(today=date.today().isoformat())
    messages = [{"role": "user", "content": request.query}]

    start = time.time()

    for turn in range(MAX_LLM_TURNS):
        response = await client.chat_with_tools(
            messages=messages,
            tools=AGENT_TOOLS,
            system_prompt=system,
            max_tokens=1024,
        )

        if not response.tool_calls:
            # LLM gave text without a tool call — use raw query
            break

        tool_call = response.tool_calls[0]

        # Handle metadata lookup (intermediate step)
        if tool_call.name == "get_available_metadata":
            metadata = await execute_get_metadata(ctx.tenant)
            messages.append(client.format_assistant_message(response))
            messages.append(
                client.format_tool_result(tool_call.id, json.dumps(metadata))
            )
            continue

        # Handle search tool calls — convert to SearchPlan
        llm_time = int((time.time() - start) * 1000)
        params = tool_call.arguments

        if tool_call.name == "search_text":
            filter_dict = extract_filters(params)
            return SearchPlan(
                search_method="text",
                query_text=params.get("query_text", request.query),
                filters=SearchFilterParams(**filter_dict) if filter_dict else None,
                top_k=params.get("top_k", request.top_k),
                reasoning=f"LLM selected text search: '{params.get('query_text', '')}'",
            ), llm_time

        elif tool_call.name == "search_similar":
            return SearchPlan(
                search_method="similar",
                item_id=params.get("item_id"),
                item_type=params.get("item_type", "detection"),
                top_k=params.get("top_k", request.top_k),
                reasoning=f"LLM selected similarity search for {params.get('item_type', 'detection')} #{params.get('item_id')}",
            ), llm_time

        else:
            logger.warning(f"LLM called unknown tool: {tool_call.name}")
            break

    # No valid tool call after all turns — fallback
    llm_time = int((time.time() - start) * 1000)
    return SearchPlan(
        search_method="text",
        query_text=request.query,
        top_k=request.top_k,
        reasoning="LLM did not produce a search tool call, using raw query.",
    ), llm_time


def _merge_filters(
    llm_filters: SearchFilterParams | None,
    user_filters: SearchFilterParams | None,
) -> dict | None:
    """Merge filters: user-explicit filters take precedence over LLM-extracted."""
    merged = {}
    if llm_filters:
        merged.update(llm_filters.dict(exclude_none=True))
    if user_filters:
        merged.update(user_filters.dict(exclude_none=True))
    return merged if merged else None


def _build_search_params(
    plan: SearchPlan,
    request: AgentSearchRequest,
    effective_filters: dict | None,
) -> dict:
    """Build the parameter dict for tool execution functions."""
    params = {"top_k": plan.top_k, "search_type": request.search_type}

    if plan.search_method == "text":
        params["query_text"] = plan.query_text or request.query
    elif plan.search_method == "similar":
        params["item_id"] = plan.item_id
        params["item_type"] = plan.item_type or "detection"

    if effective_filters:
        params.update(effective_filters)

    return params
