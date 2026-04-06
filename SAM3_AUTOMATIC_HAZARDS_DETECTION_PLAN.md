# Plan: SAM3-Based Automatic Hazard Detection Pipeline

## Context

Currently, detections (bounding boxes around hazardous objects) are only created via **manual upload**. The goal is to automatically detect hazards (metallic pipe, container, rust, etc.) in every uploaded image using SAM3 with text prompts via the `perceptra-seg` package. This creates a separate, GPU-intensive detection pipeline that runs after embedding, producing Detection records that flow into the existing embedding pipeline for searchability.

---

## Architecture Overview

```
Image Upload
  -> Image record created (status=uploaded)
  -> [embedding queue] process_image_task
       CLIP/Perception embedding -> Qdrant
       image status=completed
       triggers embedding for existing manual detections
       NEW: dispatches auto_detect_image_task to detection queue
  -> [detection queue] auto_detect_image_task (SEPARATE WORKER)
       loads tenant hazard config (text prompts)
       runs perceptra-seg SAM3 segmentation
       for each detected object:
         crops region -> saves to storage
         creates Detection record (source='auto')
         post_save signal -> process_detection_task (embedding queue)
```

Key decisions:
- **Separate `detection` Celery queue + worker** -- SAM3 is GPU-heavy (~1GB+ VRAM), must not block embedding
- **Detection worker runs on CPU** (single GPU deployment) -- embedding worker keeps the GPU
- **Lazy dispatch** (`.delay()`) not Celery chain -- embedding completion is not gated by detection success
- **Reuses existing `Detection` model** -- auto-detections are first-class, searchable like manual ones
- **Reuses existing `post_save` signal** -- auto-created Detection records automatically get embedded
- **All new models in `embeddings` app** -- TenantHazardConfig + DetectionJob both live in embeddings
- **Full API + admin** for TenantHazardConfig CRUD
- **perceptra-seg wrapper** will be finalized after user shares the exact API

---

## Phase 1: Detection Service Abstraction

Create `backend/infrastructure/detections/` following the existing `infrastructure/embeddings/` pattern.

### Create: `backend/infrastructure/detections/__init__.py`

Empty init.

### Create: `backend/infrastructure/detections/base.py`

```python
@dataclass
class DetectionResult:
    label: str
    confidence: float
    bbox_x: float       # normalized 0-1 (x, y, width, height)
    bbox_y: float
    bbox_width: float
    bbox_height: float
    mask: Optional[np.ndarray] = None

class BaseDetectionBackend(ABC):
    def __init__(self, device=None, **kwargs)
    @abstractmethod load()
    @abstractmethod detect(image, prompts, confidence_threshold) -> List[DetectionResult]
    @abstractmethod detect_batch(images, prompts, confidence_threshold) -> List[List[DetectionResult]]
    unload()
```

### Create: `backend/infrastructure/detections/sam3_perceptra.py`

Wraps `perceptra-seg` SAM3 with multi-text prompt support. This is the **only file** that imports from `perceptra-seg`, isolating API changes.

```python
class SAM3PerceptraBackend(BaseDetectionBackend):
    name = 'sam3_perceptra'
    # Loads perceptra-seg model, caches in memory
    # detect(): runs all prompts in single forward pass
    # Converts absolute bbox output to normalized DetectionResult
```

### Create: `backend/infrastructure/detections/registry.py`

```python
class DetectionBackendRegistry:  # Singleton
    # Caches loaded backend models per (backend_name, device) key
    # get_backend(name, device) -> BaseDetectionBackend
```

---

## Phase 2: Django Models (requires migration)

Both new models go in `backend/embeddings/models.py` alongside EmbeddingJob and ModelVersion.

### Modify: `backend/embeddings/models.py`

**Add `TenantHazardConfig` model** -- configurable detection prompts per tenant:

```python
class TenantHazardConfig(models.Model):
    tenant = FK(Tenant)
    name = CharField(max_length=100)          # e.g. "Default Inspection Profile"
    prompts = JSONField()                     # ["metallic pipe", "rust", "container"]
    detection_backend = CharField(default='sam3_perceptra')
    confidence_threshold = FloatField(default=0.3)
    is_active = BooleanField(default=True)
    is_default = BooleanField(default=False)
    config = JSONField(default=dict)          # backend-specific config
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)

    Meta:
        db_table = 'tenant_hazard_configs'
        unique_together = [('tenant', 'name')]
```

**Add `DetectionJob` model** -- tracks auto-detection status per image:

```python
class DetectionJob(models.Model):
    detection_job_id = UUIDField(default=uuid4)
    tenant = FK(Tenant)
    image = FK('media.Image')
    hazard_config = FK('embeddings.TenantHazardConfig', null=True)
    detection_backend = CharField(default='sam3_perceptra')
    total_detections = IntegerField(default=0)
    status = CharField(choices=[pending/running/completed/failed/skipped])
    started_at, completed_at = DateTimeFields
    error_message = TextField(null=True)
    inference_time_ms = FloatField(null=True)

    Meta: db_table = 'detection_jobs'
```

### Modify: `backend/media/models.py`

**Add fields to `Detection` model:**

```python
source = CharField(max_length=20, choices=[('manual','Manual'),('auto','Auto')], default='manual')
detection_job = FK('embeddings.DetectionJob', null=True, blank=True)
```

### Run migrations

```bash
docker compose exec search-engine python manage.py makemigrations embeddings media
docker compose exec search-engine python manage.py migrate
```

---

## Phase 3: Celery Task + Worker

### Modify: `backend/embeddings/config/celery_config.py`

Add detection queue:

```python
CELERY_TASK_QUEUES = (
    Queue("celery"),
    Queue("cleanup"),
    Queue("embedding"),
    Queue("detection"),       # NEW
    Queue("maintenance"),
)
```

### Modify: `backend/embeddings/tasks/base.py`

Add `DetectionTask` base class (parallel to `EmbeddingTask`):

```python
class DetectionTask(Task):
    _detection_registry = None
    autoretry_for = (Exception,)
    retry_kwargs = {'max_retries': 2, 'countdown': 120}

    @property
    def detection_registry(self):
        if self._detection_registry is None:
            from infrastructure.detections.registry import DetectionBackendRegistry
            self._detection_registry = DetectionBackendRegistry()
        return self._detection_registry
```

### Create: `backend/embeddings/tasks/auto_detection.py`

Core task: `auto_detect_image_task(image_id, hazard_config_id=None)`

Flow:
1. Load Image + tenant's active TenantHazardConfig (skip if none)
2. Create DetectionJob (status=running)
3. Download image from storage
4. Get detection backend from registry (model cached in worker)
5. Run `backend.detect(image, prompts, threshold)` -- all prompts in one pass
6. For each DetectionResult:
   - Crop region from image array
   - Save crop to storage (`org-{slug}/detections/{year}/{month}/autodet_{uuid}.jpg`)
   - Deduplicate: check existing detection with same image+bbox+label
   - Create Detection record (source='auto', detection_job=job)
   - `post_save` signal auto-fires `process_detection_task.delay()` on embedding queue
7. Update DetectionJob (status=completed, total_detections=N)
8. Atomically increment Image.detection_count (and Video.detection_count if applicable)

### Modify: `backend/embeddings/tasks/image.py`

At end of `process_image_task` (after line ~137), add auto-detection dispatch:

```python
# Trigger auto-detection if tenant has hazard config
try:
    from media.models import TenantHazardConfig
    has_config = TenantHazardConfig.objects.filter(
        tenant=image.tenant, is_active=True
    ).exists()
    if has_config:
        from embeddings.tasks.auto_detection import auto_detect_image_task
        auto_detect_image_task.delay(image_id)
        logger.info(f"Queued auto-detection for image {image_id}")
except Exception as e:
    logger.warning(f"Failed to queue auto-detection for image {image_id}: {e}")
```

### Modify: `backend/embeddings/tasks/__init__.py`

Export `auto_detect_image_task`.

### Modify: `supervisord.conf`

Add detection worker:

```ini
[program:detection_worker]
environment=PYTHONPATH=/home/%(ENV_user)s/src/backend
command=celery -A celery_app.celery worker --concurrency=1 --loglevel=info -Q detection -n detection@%%h
directory=/home/%(ENV_user)s/src/backend/embeddings
user=%(ENV_user)s
autostart=true
autorestart=true
stderr_logfile=/var/log/detection_worker.err.log
stdout_logfile=/var/log/detection_worker.out.log
```

### Modify: `Dockerfile.backend`

```dockerfile
RUN pip3 install git+https://github.com/tannousgeagea/perceptra-seg.git
```

---

## Phase 4: Admin + API

### Register admin classes in `backend/embeddings/admin.py`

- `TenantHazardConfig` admin -- configure prompts per tenant
- `DetectionJob` admin -- monitor auto-detection job status (read-only list)

### Create: FastAPI hazard config CRUD router

New router: `backend/api/routers/hazard_config/` following existing auto-discovery pattern.

```
backend/api/routers/hazard_config/
    __init__.py
    endpoint.py          # router = APIRouter(prefix="/api/v1/hazard-configs")
    queries/
        __init__.py
        hazard_config.py  # CRUD handler functions
```

**Endpoints:**

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/hazard-configs/` | List configs for tenant (paginated) |
| POST | `/api/v1/hazard-configs/` | Create new hazard config |
| GET | `/api/v1/hazard-configs/{id}` | Get single config |
| PUT | `/api/v1/hazard-configs/{id}` | Update config (prompts, threshold, active) |
| DELETE | `/api/v1/hazard-configs/{id}` | Delete config |
| GET | `/api/v1/hazard-configs/detection-jobs/` | List detection jobs (filterable by image, status) |
| POST | `/api/v1/hazard-configs/{id}/run` | Manually trigger detection on specific image(s) |

**Pydantic schemas** (in `endpoint.py` or separate `schemas.py`):

```python
class HazardConfigCreate(BaseModel):
    name: str
    prompts: List[str]
    detection_backend: str = 'sam3_perceptra'
    confidence_threshold: float = 0.3
    is_active: bool = True
    is_default: bool = False
    config: dict = {}

class HazardConfigResponse(BaseModel):
    id: int
    name: str
    prompts: List[str]
    detection_backend: str
    confidence_threshold: float
    is_active: bool
    is_default: bool
    config: dict
    created_at: datetime
    updated_at: datetime

class DetectionJobResponse(BaseModel):
    id: int
    detection_job_id: str
    image_id: int
    status: str
    total_detections: int
    inference_time_ms: Optional[float]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
```

---

## File Summary

| Action | File | What |
|--------|------|------|
| CREATE | `backend/infrastructure/detections/__init__.py` | Package init |
| CREATE | `backend/infrastructure/detections/base.py` | BaseDetectionBackend + DetectionResult |
| CREATE | `backend/infrastructure/detections/sam3_perceptra.py` | perceptra-seg SAM3 wrapper |
| CREATE | `backend/infrastructure/detections/registry.py` | DetectionBackendRegistry singleton |
| CREATE | `backend/embeddings/tasks/auto_detection.py` | auto_detect_image_task |
| CREATE | `backend/api/routers/hazard_config/__init__.py` | Package init |
| CREATE | `backend/api/routers/hazard_config/endpoint.py` | Router + Pydantic schemas |
| CREATE | `backend/api/routers/hazard_config/queries/__init__.py` | Package init |
| CREATE | `backend/api/routers/hazard_config/queries/hazard_config.py` | CRUD handler functions |
| MODIFY | `backend/media/models.py` | Add Detection.source, Detection.detection_job fields |
| MODIFY | `backend/embeddings/models.py` | Add TenantHazardConfig + DetectionJob models |
| MODIFY | `backend/embeddings/admin.py` | Register TenantHazardConfig + DetectionJob admin |
| MODIFY | `backend/embeddings/tasks/base.py` | Add DetectionTask base class |
| MODIFY | `backend/embeddings/tasks/image.py` | Chain auto_detect_image_task after embedding |
| MODIFY | `backend/embeddings/tasks/__init__.py` | Export new task |
| MODIFY | `backend/embeddings/config/celery_config.py` | Add Queue("detection") |
| MODIFY | `supervisord.conf` | Add detection_worker program |
| MODIFY | `Dockerfile.backend` | Install perceptra-seg |

---

## Key Design Considerations

### Why a separate worker (not just a separate queue on the same worker)?
- SAM3 loads ~1GB+ into GPU memory. Sharing a worker with CLIP/Perception risks OOM.
- Detection tasks take 1-5s+ vs embedding at ~50ms. Different concurrency profiles.
- Independent scaling: can add more detection workers without affecting embedding throughput.

### Why `post_save` signal for embedding auto-detections (not explicit dispatch)?
- Reuses existing infrastructure with zero code changes to the embedding pipeline.
- Auto-detections and manual detections follow identical embedding paths.
- The signal is already battle-tested and handles edge cases.

### Why lazy dispatch (`.delay()`) not Celery chain?
- Embedding completion should not be gated on detection success.
- Detection is optional -- if no TenantHazardConfig exists, nothing happens.
- Cleaner error isolation: detection failures don't affect embedding status.

### GPU memory management (Single GPU deployment)
- Detection worker defaults to **CPU** via `DETECTION_DEVICE=cpu` env var
- Embedding worker keeps the GPU for fast CLIP/Perception inference
- SAM3 on CPU is slower (~5-15s per image) but avoids GPU memory contention
- Detection is async and not user-blocking, so CPU latency is acceptable
- Can switch to GPU later with multi-GPU setup via `CUDA_VISIBLE_DEVICES`

### Deduplication
- `auto_detect_image_task` should check for existing Detection with matching (image, bbox, label) before creating, preventing duplicates on retry.

---

## Verification Plan

1. **Unit test** the detection service abstraction with a mock backend
2. **Integration test**: create TenantHazardConfig via admin, upload an image, verify:
   - Image gets embedded (embedding queue)
   - `auto_detect_image_task` dispatched (detection queue)
   - Detection records created with `source='auto'`
   - Crops saved to storage
   - Detection embeddings generated and upserted to Qdrant
   - Detections appear in search results
3. **Monitor**: check Celery Flower or `docker compose logs -f search-engine` for task flow
4. **Load test**: upload batch of images, verify detection queue processes without blocking embedding queue