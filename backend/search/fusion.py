# search/fusion.py
"""Reciprocal Rank Fusion for multi-model search results.

When multiple embedding models (e.g. CLIP + DINOv2) each return a ranked
list of candidates, RRF combines them without needing score normalisation.
For each result, the fused score is:

    score(r) = Σ  1 / (k + rank_i)

where *k* is a constant (default 60) that dampens the influence of rank
position, and the sum runs across all model rankings that include *r*.
"""

import logging
from typing import Dict, List, Tuple

from infrastructure.vectordb.base import SearchResult

logger = logging.getLogger(__name__)

DEFAULT_K = 60


def reciprocal_rank_fusion(
    ranked_lists: Dict[str, List[SearchResult]],
    top_k: int,
    k: int = DEFAULT_K,
) -> List[SearchResult]:
    """Fuse multiple ranked result lists via Reciprocal Rank Fusion.

    Args:
        ranked_lists: Mapping of ``model_name → sorted results``.
        top_k: Number of final results to return.
        k: RRF constant (higher = less emphasis on top ranks).

    Returns:
        Fused and re-ranked list, truncated to ``top_k``.
    """
    # Accumulate RRF scores per result ID
    scores: Dict[str, float] = {}
    result_map: Dict[str, SearchResult] = {}

    for model_name, results in ranked_lists.items():
        for rank, r in enumerate(results, start=1):
            rrf_score = 1.0 / (k + rank)
            scores[r.id] = scores.get(r.id, 0.0) + rrf_score

            # Keep the result object with the highest original score
            if r.id not in result_map or r.score > result_map[r.id].score:
                result_map[r.id] = r

    # Sort by fused score descending
    sorted_ids = sorted(scores.keys(), key=lambda rid: scores[rid], reverse=True)

    fused: List[SearchResult] = []
    for rid in sorted_ids[:top_k]:
        r = result_map[rid]
        # Replace the original score with the RRF fused score
        fused.append(SearchResult(
            id=r.id,
            score=scores[rid],
            payload=r.payload,
            vector=r.vector,
        ))

    return fused


def fuse_image_search(
    embedding_models: Dict[str, 'BaseEmbeddingModel'],  # noqa: F821
    image_bytes: bytes,
    vector_db_client,
    top_k: int,
    filters: dict,
    score_threshold: float = None,
) -> List[SearchResult]:
    """Run image search across multiple models and fuse with RRF.

    Each model independently encodes the query image and searches the
    same collection (using its own named vector or the default vector).
    Results are fused via RRF.

    Args:
        embedding_models: ``{name: model}`` pairs to query.
        image_bytes: Query image bytes.
        vector_db_client: Connected vector DB client.
        top_k: Desired result count.
        filters: Payload filters to apply.
        score_threshold: Optional minimum score.

    Returns:
        RRF-fused results.
    """
    ranked_lists: Dict[str, List[SearchResult]] = {}
    fetch_limit = top_k * 2  # Over-fetch per model

    for name, model in embedding_models.items():
        try:
            import numpy as np
            embedding = np.array(model.encode_image(image_bytes), dtype=np.float32)
            results = vector_db_client.search(
                query_vector=embedding,
                limit=fetch_limit,
                filters=filters,
                score_threshold=score_threshold,
                return_vectors=False,
            )
            ranked_lists[name] = results
            logger.debug(f"RRF: {name} returned {len(results)} results")
        except Exception as e:
            logger.warning(f"RRF: {name} search failed: {e}")

    if not ranked_lists:
        return []

    # If only one model succeeded, just return its results
    if len(ranked_lists) == 1:
        return list(ranked_lists.values())[0][:top_k]

    return reciprocal_rank_fusion(ranked_lists, top_k)
