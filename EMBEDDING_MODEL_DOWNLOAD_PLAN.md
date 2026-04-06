# Plan: Embedding Model Download Strategy

## Problems

1. Models download lazily on first Celery task — can take 30+ min and exceed task time limits
2. DINOv2 cache (`~/.cache/torch/hub/`) is container-local — lost on container removal
3. SAM3 requires manual `pull_weights.sh` before startup
4. Caches scattered: HF in `.models/` (bind mount), SAM3 in `/opt/checkpoints/` (volume), DINOv2 ephemeral

## Solution: `model-puller` Service + Unified Volume + DB-driven Variant Selection

### Core Design

A **separate one-shot Docker Compose service** (`model-puller`) that:
- Reads the active `ModelVersion` from the DB to know exactly which model type + variant to download
- Downloads models **in parallel** (each model has its own retry loop — one failure doesn't block others)
- Stores everything in the `model-weights` named Docker volume (persists across container removal)
- Uses Docker Compose `profiles: [setup]` — does NOT start with `docker compose up`
- The main service starts immediately; if models aren't ready, tasks retry with backoff

### Unified Volume Layout

All caches consolidated under `/opt/checkpoints/` (existing `model-weights` named volume):

```
/opt/checkpoints/
├── huggingface/        ← HF_HUB_CACHE (CLIP, Perception)
├── torch_hub/          ← TORCH_HOME (DINOv2)
├── sam3/               ← SAM3 weights (sam3.pt, config.json)
└── .ready              ← sentinel written after all downloads succeed
```

### DB-driven Variant Selection

The `ModelVersion` table stores:
- `model_type`: clip / dinov2 / perception / sam3
- `config` (JSON): `{"variant": "ViT-B-32"}` (or whatever the active variant is)

The `model-puller` script:
1. Sets up Django, connects to DB
2. Queries `ModelVersion.objects.filter(is_active=True)` to get the exact model type + variant
3. If no active model in DB (fresh deployment), falls back to `PREFETCH_MODELS` env var with default variants
4. Downloads only what's needed

### Parallel Downloads

Each model downloads in its own thread via `concurrent.futures.ThreadPoolExecutor`:
- CLIP failing 3x with backoff does NOT block DINOv2 from downloading
- Each thread has independent 3-retry logic
- Script exits 0 only if ALL models succeed; exit 1 if any fail

### Worker Resilience

When the worker picks up a task but models aren't cached yet:
- `ModelNotReadyError` raised before `model.load()`
- Task retries with 2-min backoff, up to 10 retries (~20 min window)
- Once model-puller finishes, next retry succeeds automatically

### User Workflow

```bash
# First-time or after model changes
docker compose run model-puller       # ~5GB, independent of main service

# Start services (does NOT wait for model-puller)
docker compose up -d

# Subsequent deploys — models persist in named volume
docker compose up -d                  # instant, no re-download
```

---

## Files to Create/Modify

### 1. CREATE: `scripts/pull_models.py`

```python
#!/usr/bin/env python3
"""Download embedding models into the model-weights volume."""

import os, sys, time, subprocess, logging
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CHECKPOINT_ROOT = Path("/opt/checkpoints")
HF_CACHE        = CHECKPOINT_ROOT / "huggingface"
TORCH_CACHE     = CHECKPOINT_ROOT / "torch_hub"
SAM3_DIR        = CHECKPOINT_ROOT / "sam3"
READY_FILE      = CHECKPOINT_ROOT / ".ready"

# --- Default variants (used when DB has no active model) ---
DEFAULT_VARIANTS = {
    "clip":       "ViT-B-32",
    "dinov2":     "dinov2_vitb14",
    "perception": "PE-Core-L-14-336",
    "sam3":       "SAM3",
}

def setup_env():
    os.environ["HF_HUB_CACHE"] = str(HF_CACHE)
    os.environ["TORCH_HOME"]   = str(TORCH_CACHE)
    for d in (HF_CACHE, TORCH_CACHE, SAM3_DIR):
        d.mkdir(parents=True, exist_ok=True)

def get_models_from_db():
    """Query active ModelVersion from DB. Returns list of (model_type, variant)."""
    try:
        import django
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
        sys.path.insert(0, "/home/appuser/src/backend")
        django.setup()
        from embeddings.models import ModelVersion
        models = []
        for mv in ModelVersion.objects.filter(is_active=True):
            variant = (mv.config or {}).get("variant", DEFAULT_VARIANTS.get(mv.model_type))
            models.append((mv.model_type, variant))
            logger.info(f"DB active model: {mv.model_type} variant={variant}")
        return models if models else None
    except Exception as e:
        logger.warning(f"Could not read models from DB: {e}")
        return None

def get_models_from_env():
    """Fallback: parse PREFETCH_MODELS env var."""
    raw = os.environ.get("PREFETCH_MODELS", "clip")
    models = []
    for entry in raw.split(","):
        entry = entry.strip()
        if ":" in entry:
            model_type, variant = entry.split(":", 1)
        else:
            model_type = entry
            variant = DEFAULT_VARIANTS.get(model_type, "")
        models.append((model_type, variant))
    return models

def retry(fn, label, max_retries=3, backoff_base=30):
    for attempt in range(1, max_retries + 1):
        try:
            fn()
            logger.info(f"{label}: OK")
            return True
        except Exception as e:
            wait = backoff_base * (2 ** (attempt - 1))
            logger.error(f"{label}: attempt {attempt}/{max_retries} failed: {e}")
            if attempt < max_retries:
                logger.info(f"{label}: retrying in {wait}s...")
                time.sleep(wait)
    logger.error(f"{label}: FAILED after {max_retries} attempts")
    return False

# --- Per-model download functions ---

def pull_clip(variant):
    import open_clip
    pretrained_map = {
        'ViT-B-32': 'openai', 'ViT-B-16': 'openai',
        'ViT-L-14': 'openai', 'ViT-L-14-336': 'openai',
        'ViT-H-14': 'laion2b_s32b_b79k', 'ViT-g-14': 'laion2b_s12b_b42k',
    }
    pretrained = pretrained_map.get(variant, 'openai')
    model, _, _ = open_clip.create_model_and_transforms(variant, pretrained=pretrained)
    del model

def pull_dinov2(variant):
    import torch
    torch.hub.load("facebookresearch/dinov2", variant)

def pull_perception(variant):
    import open_clip
    perception_models = {
        "PE-Core-L-14-336": "hf-hub:timm/PE-Core-L-14-336",
        "PE-Core-B-16": "hf-hub:timm/PE-Core-B-16",
        "PE-Core-bigG-14-448": "hf-hub:timm/PE-Core-bigG-14-448",
    }
    model_id = perception_models.get(variant, f"hf-hub:timm/{variant}")
    model, _, _ = open_clip.create_model_and_transforms(model_id)
    del model

def pull_sam3(variant):
    weight_file = SAM3_DIR / "sam3.pt"
    config_file = SAM3_DIR / "config.json"
    if weight_file.exists() and config_file.exists():
        logger.info("SAM3 weights already present.")
        return
    hf_token = os.environ.get("HF_TOKEN")
    if not hf_token:
        raise RuntimeError("HF_TOKEN not set, cannot download SAM3")
    subprocess.run([
        "hf", "download", "--token", hf_token,
        "facebook/sam3", "sam3.pt", "config.json",
        "--local-dir", str(SAM3_DIR),
    ], check=True)

PULLERS = {
    "clip": pull_clip,
    "dinov2": pull_dinov2,
    "perception": pull_perception,
    "sam3": pull_sam3,
}

def fix_permissions():
    subprocess.run(["chmod", "-R", "a+rX", str(CHECKPOINT_ROOT)], check=True)

def main():
    setup_env()

    # Try DB first, fall back to env
    models = get_models_from_db()
    if models is None:
        logger.info("No active models in DB, using PREFETCH_MODELS env var")
        models = get_models_from_env()

    logger.info(f"Models to download: {models}")

    # Download in parallel
    results = {}
    with ThreadPoolExecutor(max_workers=len(models)) as pool:
        futures = {}
        for model_type, variant in models:
            puller = PULLERS.get(model_type)
            if puller is None:
                logger.warning(f"Unknown model type: {model_type}, skipping")
                continue
            label = f"{model_type}:{variant}"
            future = pool.submit(retry, lambda p=puller, v=variant: p(v), label)
            futures[future] = label

        for future in as_completed(futures):
            label = futures[future]
            results[label] = future.result()

    fix_permissions()

    failed = [k for k, v in results.items() if not v]
    if failed:
        logger.error(f"Failed models: {failed}")
        sys.exit(1)

    READY_FILE.write_text(datetime.utcnow().isoformat())
    logger.info("All models downloaded successfully.")

if __name__ == "__main__":
    main()
```

### 2. EDIT: `docker-compose.yml`

Add `model-puller` service and env vars to `optivyn` service:

```yaml
  # Add to optivyn service environment:
      - HF_HUB_CACHE=/opt/checkpoints/huggingface
      - TORCH_HOME=/opt/checkpoints/torch_hub

  # New service:
  model-puller:
    image: tannousgeagea/optivyn:latest
    container_name: optivyn-model-puller
    env_file: .env
    environment:
      - HF_HUB_CACHE=/opt/checkpoints/huggingface
      - TORCH_HOME=/opt/checkpoints/torch_hub
      - PREFETCH_MODELS=${PREFETCH_MODELS:-clip}
    volumes:
      - .:/home/appuser/src
      - model-weights:/opt/checkpoints/
    entrypoint: ["python3", "/home/appuser/src/scripts/pull_models.py"]
    depends_on:
      - db
    profiles:
      - setup
```

### 3. EDIT: `.env`

```diff
-HF_HUB_CACHE=/home/appuser/src/.models
+HF_HUB_CACHE=/opt/checkpoints/huggingface
+TORCH_HOME=/opt/checkpoints/torch_hub
+PREFETCH_MODELS=clip
```

### 4. EDIT: `entrypoint.sh`

Add quick (non-blocking) permission fix before supervisord:

```bash
# Ensure appuser can read model weights from model-puller
if [ -d /opt/checkpoints ]; then
    sudo chmod -R a+rX /opt/checkpoints 2>/dev/null || true
fi
```

### 5. EDIT: `supervisord.conf`

Add `TORCH_HOME` and `HF_HUB_CACHE` to all program environments:

```ini
[program:core]
environment=PYTHONPATH=...,TORCH_HOME=/opt/checkpoints/torch_hub,HF_HUB_CACHE=/opt/checkpoints/huggingface

[program:api]
environment=PYTHONPATH=...,TORCH_HOME=/opt/checkpoints/torch_hub,HF_HUB_CACHE=/opt/checkpoints/huggingface

[program:embedding_worker]
environment=PYTHONPATH=...,TORCH_HOME=/opt/checkpoints/torch_hub,HF_HUB_CACHE=/opt/checkpoints/huggingface

[program:detection_worker]
environment=PYTHONPATH=...,TORCH_HOME=/opt/checkpoints/torch_hub,HF_HUB_CACHE=/opt/checkpoints/huggingface
```

### 6. EDIT: `backend/infrastructure/embeddings/base.py`

Add `ModelNotReadyError` after `EncodingError` (line ~211):

```python
class ModelNotReadyError(EmbeddingModelException):
    """Raised when model weights are not yet downloaded."""
    pass
```

### 7. EDIT: `backend/infrastructure/embeddings/generator.py`

Add readiness check in `get_model()` before `model.load()`:

```python
from pathlib import Path
from .base import ModelNotReadyError

# In get_model(), before model.load():
ready_file = Path("/opt/checkpoints/.ready")
if not ready_file.exists():
    raise ModelNotReadyError(
        "Model weights not yet available. Run: docker compose run model-puller"
    )
```

### 8. EDIT: `backend/embeddings/tasks/base.py`

Add `ModelNotReadyError` handling in `EmbeddingTask`:

```python
from infrastructure.embeddings.base import ModelNotReadyError

class EmbeddingTask(Task):
    # ... existing config ...

    def __call__(self, *args, **kwargs):
        try:
            return super().__call__(*args, **kwargs)
        except ModelNotReadyError as exc:
            # Models not downloaded yet — retry with longer backoff
            raise self.retry(exc=exc, max_retries=10, countdown=120)
```

### 9. EDIT: `backend/infrastructure/embeddings/dinov2.py`

Add debug log in `load()`:

```python
logger.info(f"DINOv2 torch.hub cache dir: {torch.hub.get_dir()}")
```

### 10. EDIT: `.gitignore`

Add `.torch_cache/`

---

## Summary of Changes

| File | Action | Purpose |
|------|--------|---------|
| `scripts/pull_models.py` | Create | Standalone model download script (parallel, DB-driven, retry) |
| `docker-compose.yml` | Edit | Add `model-puller` service + env vars |
| `.env` | Edit | Point caches to `/opt/checkpoints/` subdirs |
| `entrypoint.sh` | Edit | Quick `chmod` (no downloads) |
| `supervisord.conf` | Edit | Add cache env vars to all programs |
| `infrastructure/embeddings/base.py` | Edit | Add `ModelNotReadyError` |
| `infrastructure/embeddings/generator.py` | Edit | Readiness check before `model.load()` |
| `embeddings/tasks/base.py` | Edit | `ModelNotReadyError` retry with 2min backoff |
| `infrastructure/embeddings/dinov2.py` | Edit | Debug log for cache dir |
| `.gitignore` | Edit | Add `.torch_cache/` |