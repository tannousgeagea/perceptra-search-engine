# api/routers/search/queries/degradation.py
"""Temporal degradation search — find similar deterioration patterns."""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from asgiref.sync import sync_to_async

from tenants.context import RequestContext
from api.dependencies import require_permission
from api.routers.search.schemas import (
    DegradationSearchRequest,
    DegradationSearchResponse,
    DegradationResult,
)

router = APIRouter(prefix="/search", tags=["Degradation Search"])
logger = logging.getLogger(__name__)


@router.post("/degradation", response_model=DegradationSearchResponse)
async def search_degradation(
    body: DegradationSearchRequest,
    ctx: RequestContext = Depends(require_permission('read')),
):
    """Find locations with similar degradation patterns over time.

    Given a reference image, computes the temporal delta against the
    most recent prior image at the same location, then searches for
    other location-pairs that changed in a similar direction in
    embedding space.

    Requires at least two images at the reference location captured
    at different times.
    """
    from search.delta_service import DeltaSearchService

    def _search():
        svc = DeltaSearchService(tenant=ctx.tenant, user=ctx.user)
        return svc.search_degradation_pattern(
            image_id=body.image_id,
            top_k=body.top_k,
            min_magnitude=body.min_magnitude,
            plant_site=body.plant_site,
        )

    try:
        results, exec_ms, query_id = await sync_to_async(_search)()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return DegradationSearchResponse(
        query_id=query_id,
        results=[
            DegradationResult(
                delta_id=r.id,
                similarity_score=r.score,
                plant_site=r.payload.get('plant_site') if r.payload else None,
                inspection_line=r.payload.get('inspection_line') if r.payload else None,
                from_image_id=r.payload.get('from_image_id') if r.payload else None,
                to_image_id=r.payload.get('to_image_id') if r.payload else None,
                from_captured_at=r.payload.get('from_captured_at') if r.payload else None,
                to_captured_at=r.payload.get('to_captured_at') if r.payload else None,
                time_span_days=r.payload.get('time_span_days') if r.payload else None,
                magnitude=r.payload.get('magnitude') if r.payload else None,
            )
            for r in results
        ],
        total_results=len(results),
        execution_time_ms=exec_ms,
        reference_image_id=body.image_id,
    )
