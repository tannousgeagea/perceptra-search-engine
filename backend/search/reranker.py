# search/reranker.py
"""Label-semantic re-ranking for search results.

Uses CLIP's text encoder to compute semantic similarity between the query
embedding and the text embeddings of each result's labels and tags.
Over-fetches candidates from vector search, blends visual similarity with
metadata relevance, and re-ranks.
"""

import logging
from functools import lru_cache
from typing import List, Optional, Tuple

import numpy as np

from infrastructure.embeddings.base import BaseEmbeddingModel
from infrastructure.vectordb.base import SearchResult

logger = logging.getLogger(__name__)

# Module-level LRU cache for label text embeddings.
# Key: (label_text, model_key) → embedding vector.
# Survives across requests within the same worker process.
_label_embedding_cache: dict[Tuple[str, str], np.ndarray] = {}
_CACHE_MAX_SIZE = 500


class MetadataReranker:
    """Re-ranks vector search results by blending visual similarity
    with semantic similarity between the query and each result's
    labels/tags.

    Falls back to original ranking if no text-capable model is available.
    """

    def __init__(
        self,
        model: Optional[BaseEmbeddingModel] = None,
        alpha: float = 0.8,
    ):
        """
        Args:
            model: A text-capable embedding model (typically CLIP).
                   If None or not text-capable, re-ranking is skipped.
            alpha: Blend weight.  final = alpha * vector_sim + (1-alpha) * metadata_sim.
                   Default 0.8 means visual similarity dominates, metadata
                   provides a 20% boost for semantically-matched labels.
        """
        self.model = model
        self.alpha = alpha
        self._can_rerank = model is not None and model.supports_text()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rerank(
        self,
        query_embedding: np.ndarray,
        results: List[SearchResult],
        top_k: int,
    ) -> List[SearchResult]:
        """Re-rank results with metadata semantic boost.

        Args:
            query_embedding: The original query vector (L2-normalised).
            results: Over-fetched candidates from vector search.
            top_k: Desired number of final results.

        Returns:
            Re-ranked list truncated to ``top_k``.
        """
        if not self._can_rerank or not results:
            return results[:top_k]

        try:
            scored = self._score_results(query_embedding, results)
            scored.sort(key=lambda pair: pair[1], reverse=True)
            return [r for r, _ in scored[:top_k]]
        except Exception as e:
            logger.warning(f"Re-ranking failed, returning original order: {e}")
            return results[:top_k]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _score_results(
        self,
        query_embedding: np.ndarray,
        results: List[SearchResult],
    ) -> List[Tuple[SearchResult, float]]:
        """Compute blended score for each result."""

        # Collect all unique label/tag strings across results
        unique_texts: set[str] = set()
        for r in results:
            payload = r.payload or {}
            label = payload.get('label')
            if label:
                unique_texts.add(str(label))
            tags = payload.get('tags')
            if isinstance(tags, list):
                for t in tags:
                    if isinstance(t, str) and t:
                        unique_texts.add(t)

        if not unique_texts:
            # Nothing to re-rank on — return with original scores
            return [(r, r.score) for r in results]

        # Encode all unique label/tag texts (cached)
        label_embeddings = self._get_label_embeddings(unique_texts)

        query_norm = np.array(query_embedding, dtype=np.float32)
        q_norm = np.linalg.norm(query_norm)
        if q_norm > 0:
            query_norm = query_norm / q_norm

        scored: List[Tuple[SearchResult, float]] = []
        for r in results:
            payload = r.payload or {}
            # Gather this result's label + tag texts
            texts: list[str] = []
            label = payload.get('label')
            if label:
                texts.append(str(label))
            tags = payload.get('tags')
            if isinstance(tags, list):
                texts.extend(t for t in tags if isinstance(t, str) and t)

            if not texts:
                scored.append((r, r.score))
                continue

            # Max cosine similarity between query and this result's labels/tags
            max_sim = 0.0
            for text in texts:
                emb = label_embeddings.get(text)
                if emb is not None:
                    sim = float(np.dot(query_norm, emb))
                    if sim > max_sim:
                        max_sim = sim

            blended = self.alpha * r.score + (1.0 - self.alpha) * max_sim
            scored.append((r, blended))

        return scored

    def _get_label_embeddings(self, texts: set[str]) -> dict[str, np.ndarray]:
        """Encode label/tag texts, using the module-level cache."""
        global _label_embedding_cache

        model_key = getattr(self.model, '_model_name', 'unknown')
        result: dict[str, np.ndarray] = {}
        to_encode: list[str] = []

        for text in texts:
            cache_key = (text, model_key)
            if cache_key in _label_embedding_cache:
                result[text] = _label_embedding_cache[cache_key]
            else:
                to_encode.append(text)

        # Batch-encode missing labels
        if to_encode and self.model is not None:
            for text in to_encode:
                try:
                    emb = np.array(self.model.encode_text(text), dtype=np.float32)
                    norm = np.linalg.norm(emb)
                    if norm > 0:
                        emb = emb / norm
                    cache_key = (text, model_key)
                    _label_embedding_cache[cache_key] = emb
                    result[text] = emb

                    # Evict oldest entries if cache too large
                    if len(_label_embedding_cache) > _CACHE_MAX_SIZE:
                        oldest = next(iter(_label_embedding_cache))
                        del _label_embedding_cache[oldest]
                except Exception as e:
                    logger.debug(f"Failed to encode label '{text}': {e}")

        return result
