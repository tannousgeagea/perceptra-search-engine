# Sprint 2: Backend Hardening

## Context

The full feature pipeline is now built — auto-detection, embedding, search, annotation, bulk operations, and all frontend pages. However, the backend has production-readiness gaps that will cause issues at scale: no batch size limits (OOM on large batches), no model reload when switching active model (requires worker restart), no DB constraint preventing duplicate auto-detections (race conditions), high MAX_TASKS_PER_CHILD causing memory leaks, and no periodic validation of embedding consistency. This sprint hardens the pipeline for real workloads.

---

## Item 1: Batch Size Limits on Embedding Models

**Problem:** All embedding models (`encode_images_batch`) pass unbounded lists to `torch.stack()`. A batch of 500 images OOMs the GPU.

**Fix:** Add `MAX_BATCH_SIZE` class constant to each model and chunk inside `encode_images_batch`.

**Files:**
- `backend/infrastructure/embeddings/clip.py` — `encode_images_batch` (~line 196)
- `backend/infrastructure/embeddings/dinov2.py` — `encode_images_batch` (~line 213)
- `backend/infrastructure/embeddings/sam3_encoder.py` — `encode_images_batch` (~line 212), `encode_images_batch_with_rois` (~line 274)

**Pattern** (same for all models):
```python
MAX_BATCH_SIZE = 32  # CLIP/DINOv2: 32, SAM3: 8

def encode_images_batch(self, images):
    if len(images) <= self.MAX_BATCH_SIZE:
        return self._encode_images_batch_inner(images)
    # Chunk
    results = []
    for i in range(0, len(images), self.MAX_BATCH_SIZE):
        chunk = images[i:i + self.MAX_BATCH_SIZE]
        results.extend(self._encode_images_batch_inner(chunk))
    return results
```

---

## Item 2: Model Reload Mechanism

**Problem:** `EmbeddingTask._embedding_generator` is cached at task-class level, never refreshed. Switching the active `ModelVersion` in DB requires a worker restart.

**Fix:** On each task execution, compare cached model version ID against the current active version. If changed, reload.

**File:** `backend/embeddings/tasks/base.py` (~line 67-72)

```python
_embedding_generator = None
_cached_model_version_id = None

@property
def embedding_generator(self):
    current = get_active_model_version()
    if (self._embedding_generator is None or
        self._cached_model_version_id != current.id):
        if self._embedding_generator is not None:
            self._embedding_generator.clear_cache()
        self._embedding_generator = get_embedding_generator()
        self._cached_model_version_id = current.id
    return self._embedding_generator
```

Note: `get_active_model_version()` hits DB on every task. This is a single indexed query (~0.5ms) — acceptable since embedding inference is 50-5000ms.

---

## Item 3: Auto-Detection Dedup DB Constraint

**Problem:** `auto_detect_image_task` checks for duplicates at application level with tolerance-based bbox overlap. Two concurrent tasks for the same image both read the existing detections, both see none, both create duplicates.

**Fix:** Add a partial unique index on `Detection` for `(image, label, bbox_x, bbox_y)` rounded to 2 decimal places, or simpler — add `unique_together` on `(image, label, checksum)` since the crop checksum is deterministic for the same region.

**Better approach:** The crop `checksum` (SHA256 of the JPEG bytes) is already computed for each detection. Two detections of the same region on the same image will produce the same crop bytes → same checksum. Add:

**File:** `backend/media/models.py` — Detection Meta class (~line 610)

```python
class Meta:
    ...
    constraints = [
        models.UniqueConstraint(
            fields=['image', 'checksum'],
            name='unique_detection_per_image_checksum',
            condition=models.Q(checksum__isnull=False),
        )
    ]
```

**File:** `backend/embeddings/tasks/auto_detection.py` — wrap `detection.save()` with `IntegrityError` handling:
```python
try:
    detection.save()
    created_ids.append(detection.pk)
except IntegrityError:
    logger.debug(f"Skipping duplicate detection (checksum match)")
```

This makes dedup atomic at the DB level — no race conditions possible.

---

## Item 4: Lower MAX_TASKS_PER_CHILD

**Problem:** `CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000` in dev. PyTorch/numpy accumulate memory across tasks. After 1000 tasks, worker uses significantly more RAM.

**Fix:** Lower to 200 for embedding/detection workers.

**File:** `backend/embeddings/config/celery_config.py` (~line 48)

```python
CELERY_WORKER_MAX_TASKS_PER_CHILD = 200
```

---

## Item 5: Embedding Validation Periodic Task

**Problem:** `embedding_generated=True` in DB doesn't guarantee the vector exists in Qdrant. Network partitions, manual Qdrant edits, or collection rebuilds break this invariant. Stale flags cause search to miss items or return errors.

**Fix:** Add a Celery Beat periodic task that samples images/detections and validates their vectors exist.

**Files:**
- `backend/embeddings/tasks/validation.py` (new) — the validation task
- `backend/embeddings/config/celery_config.py` — add Beat schedule

**Task logic:**
```python
@shared_task(name='maintenance:validate_embeddings', queue='maintenance')
def validate_embeddings_task(sample_size=100):
    """Sample images with embedding_generated=True and verify vectors exist in Qdrant."""
    # 1. Get active model version and collection
    # 2. Sample N images where embedding_generated=True
    # 3. For each, check vector exists via vector_db.retrieve(vector_point_id)
    # 4. If missing: reset embedding_generated=False, vector_point_id=None
    # 5. Log count of stale flags found
    # 6. Same for detections
```

**Beat schedule** (add to celery_config.py):
```python
from celery.schedules import crontab

beat_schedule = {
    'validate-embeddings-hourly': {
        'task': 'maintenance:validate_embeddings',
        'schedule': crontab(minute=0),  # every hour
        'kwargs': {'sample_size': 100},
    },
}
```

**Supervisord:** Add a beat process:
```ini
[program:celery_beat]
command=celery -A celery_app.celery beat --loglevel=info
directory=/home/%(ENV_user)s/src/backend/embeddings
...
```

---

## File Summary

| Action | File | What |
|--------|------|------|
| MODIFY | `backend/infrastructure/embeddings/clip.py` | Add MAX_BATCH_SIZE + chunking |
| MODIFY | `backend/infrastructure/embeddings/dinov2.py` | Add MAX_BATCH_SIZE + chunking |
| MODIFY | `backend/infrastructure/embeddings/sam3_encoder.py` | Add MAX_BATCH_SIZE + chunking |
| MODIFY | `backend/embeddings/tasks/base.py` | Model version check + reload |
| MODIFY | `backend/media/models.py` | Add unique constraint on Detection(image, checksum) |
| MODIFY | `backend/embeddings/tasks/auto_detection.py` | Handle IntegrityError for dedup |
| MODIFY | `backend/embeddings/config/celery_config.py` | Lower MAX_TASKS_PER_CHILD, add Beat schedule |
| CREATE | `backend/embeddings/tasks/validation.py` | Periodic embedding validation task |
| MODIFY | `supervisord.conf` | Add celery_beat program |

---

## Implementation Order

1. **Item 4** (config change, zero risk)
2. **Item 1** (batch limits, isolated to model wrappers)
3. **Item 3** (dedup constraint, requires migration)
4. **Item 2** (model reload, touches task base class)
5. **Item 5** (validation task + Beat, new infrastructure)

---

## Verification

1. **Batch limits:** Call `encode_images_batch` with 100 images on CLIP — should process in chunks of 32 without OOM
2. **Model reload:** Change active ModelVersion via admin → next embedding task uses new model without worker restart
3. **Dedup constraint:** Run `auto_detect_image_task` twice for same image concurrently → second run skips duplicates via IntegrityError, no duplicate rows
4. **MAX_TASKS_PER_CHILD:** Monitor worker RSS memory — should restart child process after 200 tasks
5. **Validation task:** Manually delete a vector from Qdrant → run `validate_embeddings_task` → flag reset to `False`