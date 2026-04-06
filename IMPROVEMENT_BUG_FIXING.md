# Pipeline Assessment & Improvement Plan

## Context

Full engineering assessment of the multi-modal search engine's CV pipeline — embedding generation, auto-detection, vector search, and supporting infrastructure. The system is functional but has critical bugs, production-readiness gaps, and architectural improvements needed before scaling. This plan documents findings and prioritises next steps.

---

## Assessment Summary

### What works well
- Clean abstractions: `BaseEmbeddingModel`, `BaseDetectionBackend`, `BaseVectorDB` — extensible
- Signal-driven pipeline: upload → embed → detect → embed detections — fully automated
- Multi-tenancy: isolated vector collections per tenant+model
- Retry logic: exponential backoff with jitter on all Celery tasks
- Storage abstraction: 4 backends (Azure, S3, MinIO, local) behind one interface
- Auto-detection pipeline (newly added): separate queue/worker, SAM3+perceptra-seg

### What needs fixing (by severity)

---

## P0: Critical Bugs (Break at Runtime)

### 1. SAM3 encoder normalization bug
**File:** `backend/infrastructure/embeddings/sam3_encoder.py:217,229`
```python
# CURRENT (wrong — adds epsilon AFTER division, destroying unit norm):
image_features = image_features / image_features.norm(dim=-1, keepdim=True) + 1e-10

# CORRECT:
image_features = image_features / (image_features.norm(dim=-1, keepdim=True) + 1e-10)
```
Affects lines 217 and 229 (both `encode_images_batch` and `encode_image`). Same bug in ROI methods (lines 257).

### 2. SAM3 encoder broken import
**File:** `backend/infrastructure/embeddings/sam3_encoder.py:11`
```python
# CURRENT:
from base import (BaseEmbeddingModel, ...)
# FIX:
from infrastructure.embeddings.base import (BaseEmbeddingModel, ...)
```

### 3. SAM3 weight download: `os.makedirs` without `exist_ok`
**File:** `backend/infrastructure/embeddings/sam3_encoder.py:85`
```python
os.makedirs(sam3_dir)  # Raises FileExistsError
# FIX:
os.makedirs(sam3_dir, exist_ok=True)
```

### 4. SAM3 error log typo
**File:** `backend/infrastructure/embeddings/sam3_encoder.py:210`
```python
raise EncodingError(f"Encountered error while encoding image: str{e}")
# FIX:                                                        ^^^
raise EncodingError(f"Encountered error while encoding image: {e}")
```

---

## P1: High-Priority Improvements (Incorrect Results / Data Consistency)

### 5. EmbeddingGenerator missing DINOv2 and SAM3
**File:** `backend/infrastructure/embeddings/generator.py`
- `_discover_models()` only registers CLIP and Perception
- DINOv2 and SAM3 are implemented but unreachable via the generator
- **Fix:** Import and register both in `_discover_models()`, add model construction cases in `get_model()`

### 6. DINOv2 missing RGB enforcement
**File:** `backend/infrastructure/embeddings/dinov2.py:170`
```python
# numpy → PIL without RGB conversion:
image = Image.fromarray(image)
# FIX:
image = Image.fromarray(image).convert('RGB')
```
Also add `.convert('RGB')` to the bytes path as a safety net.

### 7. No dimension verification on Perception and DINOv2
**Files:** `perception.py`, `dinov2.py`
- CLIP verifies `model.visual.output_dim` matches config after load
- Perception and DINOv2 trust config blindly
- **Fix:** Add post-load assertion: `assert actual_dim == self._embedding_dim`

### 8. Vector DB client not pooled — new connection per request
**File:** `backend/search/services.py:54-62`
- `_get_vector_db_client()` creates a fresh TCP connection every call
- Under load: connection exhaustion, slow search
- **Fix:** Singleton client per collection (cached on `SearchService` or module-level dict)

### 9. Embedding flag / vector store out of sync
- `embedding_generated=True` in DB does not guarantee vector exists in Qdrant
- Manual Qdrant edits, collection rebuild, or network partitions break this
- **Fix:** Add a periodic Celery beat task (`embedding:validate_vectors`) that samples N images/detections per tenant and verifies their `vector_point_id` exists in Qdrant. Mark stale ones for re-embedding.

### 10. Auto-detection dedup race condition
**File:** `backend/embeddings/tasks/auto_detection.py:157-161`
- Two parallel `auto_detect_image_task` calls for same image both read existing detections, both create new ones
- **Fix:** Add `select_for_update()` or a DB-level unique constraint on `(image, label, bbox_x, bbox_y)` with conflict handling.

---

## P2: Production Readiness

### 11. Signal dispatch unprotected
**File:** `backend/embeddings/signals.py`
- `process_image_task.delay()` inside `post_save` signal has no try-except
- If Redis is down, signal raises unhandled exception and the entire save fails
- **Fix:** Wrap `.delay()` calls in try-except, log warnings, don't block the save

### 12. No batch size limits on embedding models
- All models stack entire batch into GPU memory without limit
- 1000-image batch → OOM
- **Fix:** Add `MAX_BATCH_SIZE` constant per model (e.g. 32 for CLIP, 8 for SAM3), chunk inputs in `encode_images_batch()`

### 13. Celery worker config under-optimized
**File:** `backend/embeddings/config/celery_config.py`
- `CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000` — too high, PyTorch/numpy memory leaks accumulate
- **Fix:** Lower to 100-200 for embedding/detection workers

### 14. No model reload mechanism
- `EmbeddingTask._embedding_generator` cached at class level, never refreshed
- Switching active model in DB requires worker restart
- **Fix:** Check `ModelVersion.is_active` hash on each task, reload if changed (or use Celery worker signal to reload)

### 15. Video frame extraction: hardcoded 1 FPS, no keyframe detection
**File:** `backend/ml/video_processing.py`
- 1-hour video = 3600 frames at 1 FPS — excessive
- No scene-change detection, wastes compute on static frames
- **Fix:** Make FPS configurable per tenant (store in `TenantHazardConfig` or new `TenantMediaConfig`). Add optional keyframe-only mode using frame differencing.

### 16. Storage URL inconsistency
**File:** `backend/media/models.py:474-486`
- `Image.get_download_url()` returns `/media/{key}` for local storage
- But media router serves from `/api/v1/media/files/{key}`
- **Fix:** Use `_media_url()` helper from storage client consistently, or remove the model method in favor of the router

---

## P3: Search Quality & Observability

### 17. No search result diversity / re-ranking
**File:** `backend/search/services.py`
- Raw cosine scores returned, no post-processing
- Can return 10 near-identical detections from same image
- **Fix:** Add optional diversity parameter: max N results per parent image. Implement MMR (Maximal Marginal Relevance) for diversity.

### 18. No score normalization across model versions
- Score threshold 0.5 means different things for CLIP vs DINOv2
- Model swap silently changes search quality
- **Fix:** Store per-model score calibration (p50/p95 scores from a reference set), normalize to 0-1 range

### 19. Missing `tenant_id` in vector search filters
**File:** `backend/search/services.py:64-80`
- Relies on collection isolation for tenant scoping
- If collections are ever shared/merged, cross-tenant leakage
- **Fix:** Always include `tenant_id` in vector filters as defense-in-depth

### 20. No task execution metrics
- `inference_ms` logged but not persisted for aggregation
- No p50/p95/p99 tracking
- **Fix:** Store timing breakdown in `EmbeddingJob` or separate metrics table. Expose via `/api/v1/admin/metrics` endpoint.

### 21. No automated tests
- Zero test files found in codebase
- **Fix:** Add test suite covering:
  - Embedding dimension consistency (index same image, verify dimension matches config)
  - Vector upsert/search round-trip (upsert point, search by same vector, verify match)
  - Deduplication (upload same image twice, verify single vector)
  - Multi-tenant isolation (tenant A's images invisible to tenant B)
  - Auto-detection crop correctness (verify crop bbox matches original)

---

## Implementation Roadmap

### Sprint 1: Critical Fixes (P0 + core P1)
| # | Task | Files |
|---|------|-------|
| 1 | Fix SAM3 normalization (lines 217, 229, 257) | `sam3_encoder.py` |
| 2 | Fix SAM3 import, makedirs, typo | `sam3_encoder.py` |
| 3 | Register DINOv2 + SAM3 in generator | `generator.py` |
| 4 | Add RGB enforcement to DINOv2 | `dinov2.py` |
| 5 | Add dimension verification to Perception + DINOv2 | `perception.py`, `dinov2.py` |
| 6 | Protect signal dispatch with try-except | `signals.py` |
| 7 | Add vector DB client pooling in SearchService | `search/services.py` |

### Sprint 2: Production Hardening (P1 + P2)
| # | Task | Files |
|---|------|-------|
| 8 | Add batch size limits to all models | `clip.py`, `dinov2.py`, `perception.py`, `sam3_encoder.py` |
| 9 | Fix storage URL inconsistency | `media/models.py` |
| 10 | Add embedding validation Celery beat task | New: `embeddings/tasks/validation.py` |
| 11 | Add auto-detection dedup constraint | New migration on `Detection` |
| 12 | Lower `MAX_TASKS_PER_CHILD` | `celery_config.py` |
| 13 | Add model reload mechanism to workers | `embeddings/tasks/base.py` |

### Sprint 3: Search Quality + Tests (P2 + P3)
| # | Task | Files |
|---|------|-------|
| 14 | Add result diversity / per-image limit | `search/services.py` |
| 15 | Add `tenant_id` to vector filters | `search/services.py` |
| 16 | Add configurable video FPS per tenant | `ml/video_processing.py`, `TenantMediaConfig` model |
| 17 | Scaffold test suite | New: `backend/tests/` |
| 18 | Add task execution metrics | `embeddings/models.py`, new metrics endpoint |

---

## Verification

After each sprint:
1. **SAM3 fixes:** `python -c "from infrastructure.embeddings.sam3_encoder import SAM3Embedding"` should not raise ImportError. Generate embedding, assert L2 norm == 1.0 (±1e-6).
2. **Generator:** `EmbeddingGenerator().list_available_models()` should include `clip`, `perception`, `dinov2`, `sam3`.
3. **Signal safety:** Stop Redis, upload an image via API — should succeed (image saved) with warning log (task not dispatched).
4. **Client pooling:** Run 100 concurrent searches, verify Qdrant connection count stays ≤ 5 (not 100).
5. **Embedding validation:** Create an image with `embedding_generated=True` but delete its vector from Qdrant. Run validation task. Verify flag is reset.
6. **Tests:** `pytest backend/tests/ -v` passes all.