# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Running the Project

```bash
# Start all services (from repo root)
docker compose up -d

# Rebuild a specific service after code changes
docker compose up --build frontend -d
docker compose up --build search-engine -d

# View logs
docker compose logs -f search-engine
docker compose logs -f frontend

# Run Django migrations inside the container
docker compose exec search-engine python manage.py migrate
```

Services after startup:

| Service | URL | Purpose |
|---------|-----|---------|
| Frontend (React) | http://localhost:3000 | SPA served by nginx |
| FastAPI | http://localhost:8000 | REST API + Swagger at `/docs` |
| Django admin | http://localhost:8001/admin | ORM admin UI |
| Supervisor | http://localhost:9001 | Process monitor (admin/admin123) |

---

## Architecture Overview

Multi-modal search engine for industrial inspection data. Two Python web frameworks share one Docker container managed by **supervisord**:

- **Django 4.2** — ORM, models, admin interface (port 8001 via gunicorn)
- **FastAPI** — Async REST API for search/upload (port 8000 via uvicorn workers)
- **Celery + Redis** — Async worker for embedding generation
- **PostgreSQL** — Primary database
- **Qdrant** (or FAISS fallback) — Vector similarity search
- **React + TypeScript** — Frontend SPA (port 3000 via nginx)

### Request Flow

```
Upload:
  POST /api/v1/upload/image
    → FastAPI router
    → Django ORM (save Image record, storage backend)
    → Celery task dispatched to Redis
    → EmbeddingTask worker: model inference → vector upserted to Qdrant

Search:
  POST /api/v1/search/text (or /image, /hybrid, /similar)
    → FastAPI router
    → Embedding model (encode query)
    → Qdrant vector search (tenant-scoped collection)
    → ranked results returned

Auth:
  POST /api/v1/auth/token → JWT (access + refresh)
  X-API-Key header        → API key auth (auto-resolves tenant)
```

---

## Directory Structure

```
search-engine/
├── backend/                    # All Python code
│   ├── api/                    # FastAPI application
│   │   ├── main.py             # App factory, dynamic router loading, CORS
│   │   ├── dependencies.py     # Shared FastAPI deps (auth, tenant context)
│   │   └── routers/            # One subdirectory per feature
│   │       ├── auth/           # JWT + API key auth endpoints
│   │       ├── media/          # Image/Video/Detection CRUD
│   │       ├── search/         # Text/image/hybrid/similarity search
│   │       ├── upload/         # File upload + tag management
│   │       ├── api_keys/       # API key CRUD
│   │       └── detections/     # Detection crop endpoints
│   ├── users/                  # Django app: CustomUser, PasswordResetToken
│   ├── tenants/                # Django app: Tenant, multi-tenancy
│   ├── media/                  # Django app: Image, Video, Detection, Tag
│   ├── search/                 # Django app: SearchQuery history, stats
│   ├── embeddings/             # Django app: EmbeddingJob, ModelVersion, Celery tasks
│   ├── api_keys/               # Django app: ApiKey, rate limiting
│   ├── infrastructure/
│   │   ├── embeddings/         # Model wrappers (CLIP, DINOv2, SAM3, Perception)
│   │   ├── vectordb/           # Qdrant + FAISS clients behind BaseVectorDB
│   │   └── storage/            # Azure/S3/MinIO/local storage client
│   ├── ml/                     # Video frame extraction, image preprocessing
│   ├── backend/                # Django settings, urls, wsgi
│   └── celery_app.py           # Celery app instance
├── frontend/                   # React TypeScript SPA
│   ├── src/
│   │   ├── api/client.ts       # Axios instance, all API calls, auth interceptors
│   │   ├── context/AuthContext.tsx  # Auth state (JWT/API key), localStorage
│   │   ├── pages/              # Login, Dashboard, Search, MediaLibrary,
│   │   │                       # Upload, Analytics, Settings
│   │   ├── components/Layout/  # Sidebar, layout wrapper
│   │   └── types/api.ts        # TypeScript interfaces for all API models
│   ├── nginx.conf              # Nginx: proxies /api/ → backend, SPA fallback
│   ├── Dockerfile              # Multi-stage: node build → nginx serve
│   └── vite.config.ts          # Dev proxy /api → localhost:8000
├── examples/                   # Test scripts (curl, Python)
├── docker-compose.yml          # All services
├── Dockerfile.backend          # PyTorch + Django + FastAPI container
├── supervisord.conf            # Process manager (Django, FastAPI, Celery)
├── entrypoint.sh               # Container init (migrate, collectstatic, supervisord)
└── pull_weights.sh             # Download SAM3 weights from Hugging Face
```

---

## FastAPI Router Pattern

`api/main.py` auto-discovers routers by scanning `api/routers/*/endpoint.py`:

```python
# Each router directory needs:
api/routers/<feature>/
    __init__.py
    endpoint.py          # Defines router = APIRouter(prefix="/api/v1/...")
    queries/
        __init__.py
        <feature>.py     # Route handler functions
```

- Every endpoint has a custom `TimedRoute` that appends `X-Response-Time` to responses.
- Router prefix is always `/api/v1/...` (matches nginx proxy at `/api/`).
- New routers are picked up automatically on restart — no changes to `main.py` needed.

---

## Authentication

Two auth modes are supported simultaneously:

### JWT (email/password)
- `POST /api/v1/auth/token` → returns `{ access, refresh }`
- Access token: 60 minutes, payload has `user_id`, `email`, `token_type: "access"`
- Refresh token: 7 days, payload has `user_id`, `jti` (UUID), `token_type: "refresh"`
- Refresh revocation: `jti` stored in Django cache (`revoked_jti:{jti}`)
- Frontend sends: `Authorization: Bearer <access_token>`

### API Key
- Created via `POST /api/v1/api-keys/`
- Frontend sends: `X-API-Key: <key>`
- Automatically resolves the tenant from the key

### Multi-tenancy headers (JWT mode only)
- `X-Tenant-ID: <uuid>` — route to specific tenant
- `X-Tenant-Domain: <domain>` — alternative tenant lookup

### Full auth endpoint list
```
POST /api/v1/auth/register
POST /api/v1/auth/token
POST /api/v1/auth/token/refresh
POST /api/v1/auth/logout
GET  /api/v1/auth/me
POST /api/v1/auth/password/reset
POST /api/v1/auth/password/reset/confirm
POST /api/v1/auth/password/change
```

---

## Django Models

### `users` app
- **`CustomUser`** — extends `AbstractUser`. `email` is the `USERNAME_FIELD`. `username` field is kept (AbstractUser unique constraint) and set to `email` on creation.
- **`PasswordResetToken`** — `token` (64-char urlsafe), `expires_at` (1hr), `is_used`. Has `is_valid` property and `create_for_user()` classmethod.

### `media` app (core models)
- **`Image`** — `image_id` (UUID), `filename`, `storage_key`, `storage_backend`, `width/height`, `plant_site`, `shift`, `inspection_line`, `captured_at`, `status`, FKs to Tenant, optional Video.
- **`Video`** — `video_id` (UUID), `filename`, `duration_seconds`, `frame_count`, `status`, FK to Tenant.
- **`Detection`** — bounding box crop of an image. `label`, `confidence`, `bbox_x/y/width/height`, FK to Image and Tenant.
- **`Tag`** — name, color. M2M with Image, Video, Detection via `tags` relation. Has `usage_count` property (sync DB calls — **never call from async context**; use annotated querysets instead).

### `embeddings` app
- **`EmbeddingJob`** — tracks status of embedding task per media item.
- **`ModelVersion`** — name + version string for each embedding model.
- **`TenantVectorCollection`** — maps a Tenant to its Qdrant collection name.

### `api_keys` app
- **`ApiKey`** — `key` (hashed), `key_prefix`, `name`, `permissions` (read/write/admin), `is_active`, rate limits, `tenant` FK.

---

## Async/Sync Boundary Rules

Django ORM is synchronous. FastAPI handlers are async. **Never call Django ORM methods directly from async context.** Always wrap:

```python
# Correct
result = await sync_to_async(queryset.filter(...).first)()
items  = await sync_to_async(list)(queryset)
obj    = await sync_to_async(Model.objects.get)(id=pk)

# Also correct: prefetch related objects before entering async context
queryset = queryset.select_related('video').prefetch_related('tags')
images   = await sync_to_async(list)(queryset)
# Now safe to access image.video, image.tags (already cached)
```

Avoid `model_validate(django_orm_object)` if any schema field maps to a `@property` that fires DB queries (e.g., `Tag.usage_count`). Construct Pydantic models explicitly instead:

```python
# Bad — triggers Tag.usage_count property (sync DB query in async context)
TagResponse.model_validate(tag)

# Good
TagResponse(id=tag.id, name=tag.name, description=tag.description, color=tag.color)
```

---

## Storage Backends

Configured via `STORAGE_BACKEND` in `.env`:

| Backend | `STORAGE_BACKEND` | Notes |
|---------|-------------------|-------|
| Local filesystem | `local` | Stores under `STORAGE_PATH`. Served via `/api/v1/media/files/{key}` endpoint. |
| Azure Blob | `azure` | Requires `AZURE_STORAGE_*` vars. Returns presigned URLs. |
| AWS S3 | `s3` | Requires `AWS_S3_*` vars. Returns presigned URLs. |
| MinIO | `minio` | Requires `MINIO_*` vars. Returns presigned URLs. |

**Important:** Local storage's `generate_presigned_url()` returns `file://` URIs (not HTTP). The media router intercepts local storage keys and returns `/api/v1/media/files/{key}` HTTP URLs instead. Cloud backends use presigned URLs directly.

---

## API Response Shapes

### Paginated list endpoints
All list endpoints return:
```json
{
  "items": [...],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_items": 42,
    "total_pages": 3,
    "has_next": true,
    "has_previous": false
  },
  "filters_applied": {}
}
```

Frontend type: `PaginatedResponse<T>` in `src/types/api.ts`. Access total via `r.data.pagination.total_items`.

### Upload response
`POST /api/v1/upload/image` expects `multipart/form-data` with:
- `file` — the image file (field name must be `file`, not `image`)
- `plant_site`, `shift`, `inspection_line`, `captured_at` — metadata strings
- `tags` — JSON array string, e.g. `'[{"name":"defect"},{"name":"rust"}]'`

---

## Frontend Architecture

### Auth state (localStorage key: `auth`)
```typescript
// JWT mode
{ mode: 'jwt', token: '...', refreshToken: '...', email: '...', tenantId?: '...' }

// API key mode
{ mode: 'apikey', apiKey: '...', apiKeyLabel: '...' }
```

### Axios interceptors (`src/api/client.ts`)
1. **Request interceptor** — attaches `Authorization: Bearer` or `X-API-Key` from localStorage
2. **Response interceptor** — on 401, attempts silent token refresh via `/api/v1/auth/token/refresh`, retries original request once; on failure redirects to `/login`

### Pages and routes
```
/login          → Login.tsx (API key, sign in, register tabs)
/dashboard      → Dashboard.tsx (stats, charts)
/search         → Search.tsx (text/image/hybrid/similar tabs)
/media          → MediaLibrary.tsx (grid/list, filter by plant/shift)
/upload         → Upload.tsx (4-step wizard: type → file → metadata → progress)
/analytics      → Analytics.tsx (time-series, label distribution)
/settings       → Settings.tsx (profile, API keys, change password)
```

All routes except `/login` are wrapped in `AuthGuard` — redirects unauthenticated users to `/login`.

### Design tokens (CSS variables)
All colors/spacing use CSS custom properties defined in `src/index.css`. Key tokens:
- `--amber`, `--amber-700`, `--amber-glow` — primary accent
- `--cyan-400` — secondary accent
- `--bg-void`, `--bg-surface`, `--bg-elevated` — backgrounds
- `--font-display` (Rajdhani), `--font-mono` (JetBrains Mono), `--font-body` (DM Sans)

---

## Configuration Reference

All configuration is via `.env` in the project root.

| Variable | Purpose | Example |
|----------|---------|---------|
| `DATABASE_USER` / `DATABASE_PASSWORD` / `DATABASE_NAME` | PostgreSQL credentials | `postgres` / `secret` / `searchdb` |
| `DATABASE_HOST` / `DATABASE_PORT` | PostgreSQL connection | `search-engine-db` / `5432` |
| `SECRET_KEY` | Django + JWT signing key | 50-char random string |
| `ACCESS_TOKEN_LIFETIME_MINUTES` | JWT access token TTL | `60` |
| `REFRESH_TOKEN_LIFETIME_DAYS` | JWT refresh token TTL | `7` |
| `STORAGE_BACKEND` | Storage driver | `local` / `azure` / `s3` / `minio` |
| `STORAGE_PATH` | Local storage root | `/media/search-engine/` |
| `QDRANT_HOST` / `QDRANT_PORT` | Vector DB connection | `qdrant` / `6333` |
| `CELERY_BROKER_URL` | Redis broker URL | `redis://search-engine-redis:6379/0` |
| `CELERY_RESULT_BACKEND` | Redis result backend | `redis://search-engine-redis:6379/0` |
| `EMBEDDING_DEVICE` | Inference device | `cpu` / `cuda` |
| `HF_TOKEN` | Hugging Face token for SAM3 weights | `hf_...` |
| `HF_HUB_CACHE` | Model weight cache directory | `.models/` |
| `MEDIA_ROOT` | Host path for local storage volume | `/data/media/` |
| `FRONTEND_ENDPOINT` | Allowed CORS origin | `http://localhost:3000` |
| `DJANGO_SUPERUSER_USERNAME` / `_PASSWORD` / `_EMAIL` | Auto-created admin user | |

---

## Model Weights

SAM3 requires manual weight download before the embedding worker can use it:

```bash
export HF_TOKEN=hf_your_token_here
./pull_weights.sh
```

Weights land in the `model-weights` Docker volume, mounted at `/opt/checkpoints/` inside the container. HuggingFace cache (CLIP, DINOv2, etc.) is at `.models/` (mapped via `HF_HUB_CACHE`).

---

## Example Scripts

`examples/` contains ready-to-run scripts for manual API testing:

```bash
# Upload
python examples/test_image_upload.py
python examples/test_video_upload.py
python examples/test_detection_upload.py

# Search
python examples/search_examples.py

# cURL equivalents
bash examples/curl_examples.sh
```

---

## Common Pitfalls

| Problem | Cause | Fix |
|---------|-------|-----|
| `SynchronousOnlyOperation` in FastAPI handler | Django ORM called directly from async | Wrap with `sync_to_async` |
| `ValidationError: usage_count` on Tag | `model_validate(tag)` fires `@property` with DB queries | Construct `TagResponse(...)` explicitly |
| Upload returns `{"detail": [{"msg": "Field required", "loc": ["body", "file"]}]}` | Form field sent as `image` or `video` instead of `file` | Always use `fd.append('file', file)` |
| Tags not saved on upload | Tags sent as multiple form fields | Send as single JSON array: `fd.append('tags', JSON.stringify([{name},...]))` |
| 502 Bad Gateway on media list | Exception thrown after HTTP headers sent, corrupting response | Always wrap per-item build functions in try/except |
| `toLocaleString` crash on undefined | Frontend reads `r.data.total` but backend returns `r.data.pagination.total_items` | Use `PaginatedResponse<T>` type with `pagination.total_items` |
| Images show as broken / `file://` URLs | Local storage generates `file://` URIs, not HTTP | Media router returns `/api/v1/media/files/{key}` for local storage |
| Browser shows stale JS bundle | `index.html` cached by browser | `nginx.conf` sets `no-cache` on `index.html`; do hard refresh after rebuild |
