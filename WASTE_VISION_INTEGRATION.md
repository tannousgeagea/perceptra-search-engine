# WasteVision Module — Implementation Plan

## Context

WasteVision is a real-time AI waste inspection system powered by VLM APIs, added as a **native module** — no new servers, no duplicate auth, no separate frontend. It ingests live camera streams (RTSP, MJPEG, or uploaded video), emits frames to a configurable-FPS asyncio queue, analyzes each frame through a VLM worker pool, runs a rule-based alert engine, and presents results on an industrial control-room dashboard inside the existing React app.

**Hard integration constraints:**
- No new auth — reuse `require_permission()` and `RequestContext` throughout
- Alerts broadcast on existing Redis `alerts:{tenant_id}` pub/sub + dedicated per-camera channels
- Django app + FastAPI APIRouter mounted inside existing processes
- Frontend is a new `/wastevision` route inside the existing React app

---

## Critical Files to Modify

| File | Change |
|------|--------|
| `backend/backend/settings.py` | Add `'wastevision'` to `INSTALLED_APPS`; add WASTEVISION_* env defaults |
| `backend/infrastructure/llm/base.py` | Add abstract `analyze_image()` |
| `backend/infrastructure/llm/anthropic_client.py` | Implement `analyze_image()` |
| `backend/infrastructure/llm/openai_client.py` | Implement `analyze_image()` |
| `backend/infrastructure/llm/ollama_client.py` | Implement `analyze_image()` |
| `frontend/src/App.tsx` | Add `/wastevision` route |
| `frontend/src/components/Layout/Sidebar.tsx` | Add WasteVision nav item (ScanLine icon) |
| `frontend/src/api/client.ts` | Add WasteVision API + WebSocket helpers |
| `frontend/src/types/api.ts` | Add all WasteVision TypeScript types |

---

## New Files to Create

```
backend/wastevision/
  __init__.py
  apps.py
  models.py
  admin.py
  service.py            ← VLM worker pool + analysis logic
  frame_capture.py      ← Stream ingestion (RTSP/MJPEG/file) → asyncio queue
  alert_engine.py       ← Rule engine subscribing to VLM results stream
  tasks.py              ← Celery task: start/stop camera ingestion
  migrations/__init__.py
  migrations/0001_initial.py   (generated via makemigrations)

backend/api/routers/wastevision/
  __init__.py
  endpoint.py
  schemas.py
  queries/
    __init__.py
    cameras.py
    inspections.py
    websockets.py       ← Two new WS endpoints

frontend/src/pages/WasteVision/
  index.tsx             ← Page entry, tab routing
  CameraGrid.tsx
  CompositionPanel.tsx
  AlertFeed.tsx
  InspectorLog.tsx
  CameraManager.tsx
  EmbedWidget.tsx       ← Standalone iframe-compatible minimal view
  hooks/
    useCameraStream.ts  ← WebSocket hook for per-camera live frames
    useWasteAlerts.ts   ← WebSocket hook for global alert feed
  wastevision.css       ← Control-room theme overrides
```

---

## Step 1 — Django App: `backend/wastevision/`

### `settings.py` additions
```python
INSTALLED_APPS = [..., 'wastevision']

# WasteVision
WASTEVISION_FRAME_FPS      = int(env('WASTEVISION_FRAME_FPS', '2'))         # frames/sec emitted to queue
WASTEVISION_MAX_CAMERAS    = int(env('WASTEVISION_MAX_CAMERAS', '16'))       # concurrent camera slots
WASTEVISION_VLM_WORKERS    = int(env('WASTEVISION_VLM_WORKERS', '3'))        # asyncio VLM concurrency
WASTEVISION_VLM_PROVIDER   = env('WASTEVISION_VLM_PROVIDER', '')             # override LLM_PROVIDER
WASTEVISION_VLM_MODEL      = env('WASTEVISION_VLM_MODEL', '')                # override LLM_MODEL
WASTEVISION_DEDUP_WINDOW   = int(env('WASTEVISION_DEDUP_WINDOW', '300'))     # seconds for alert dedup
WASTEVISION_CONSECUTIVE_N  = int(env('WASTEVISION_CONSECUTIVE_N', '3'))      # high alerts for escalation
WASTEVISION_DRIFT_PCT      = float(env('WASTEVISION_DRIFT_PCT', '30.0'))     # composition drift threshold
```

### `models.py`

**`WasteCamera(TenantScopedModel)`**
```
id:                  (Django default BigAutoField — primary key)
camera_uuid:         UUIDField(default=uuid.uuid4, unique=True, db_index=True)
name:                CharField(max_length=100)
location:            CharField(max_length=200)
plant_site:          CharField(max_length=100, blank=True)
stream_type:         CharField(max_length=20, choices=['rtsp','mjpeg','upload'])
stream_url:          CharField(max_length=500, blank=True)   # for rtsp/mjpeg
target_fps:          FloatField(default=2.0)
is_active:           BooleanField(default=True, db_index=True)
status:              CharField(max_length=20, choices=['idle','streaming','error'], default='idle')
last_frame_at:       DateTimeField(null=True, blank=True)
last_risk_level:     CharField(max_length=20, blank=True)    # last overall_risk seen
consecutive_high:    IntegerField(default=0)                 # tracks consecutive high/critical
created_at:          DateTimeField(auto_now_add=True)
updated_at:          DateTimeField(auto_now=True)

Meta: unique_together = [('tenant', 'name')]
```

**`WasteInspection(TenantScopedModel)`**
```
id:                  (Django default BigAutoField — primary key)
inspection_uuid:     UUIDField(default=uuid.uuid4, unique=True, db_index=True)
camera:              ForeignKey(WasteCamera, on_delete=CASCADE, related_name='inspections')
sequence_no:         BigIntegerField()                       # monotonic frame counter per camera
frame_timestamp:     DateTimeField()                         # when the frame was captured
waste_composition:   JSONField()                             # {plastic, paper, glass, metal, organic, e_waste, hazardous, other}
contamination_alerts: JSONField(default=list)                # [{item, severity, location_in_frame, action}]
line_blockage:       BooleanField(default=False)
overall_risk:        CharField(max_length=20, choices=['low','medium','high','critical'])
confidence:          FloatField()
inspector_note:      TextField()
vlm_provider:        CharField(max_length=50)
vlm_model:           CharField(max_length=100)
processing_time_ms:  IntegerField(null=True)
created_at:          DateTimeField(auto_now_add=True)

Meta: indexes on (camera_id, created_at), (tenant_id, created_at), (overall_risk,)
```

**`WasteAlert(TenantScopedModel)`**

WasteVision's own alert record (distinct from the generic `Alert` model — different schema, linked to inspections).
```
id:                  (Django default BigAutoField — primary key)
alert_uuid:          UUIDField(default=uuid.uuid4, unique=True, db_index=True)
camera:              ForeignKey(WasteCamera, on_delete=CASCADE)
inspection:          ForeignKey(WasteInspection, on_delete=SET_NULL, null=True)
alert_type:          CharField(max_length=50, choices=['contamination','blockage','escalation','drift'])
severity:            CharField(max_length=20, choices=['low','medium','high','critical'])
details:             JSONField(default=dict)                 # type-specific metadata
is_acknowledged:     BooleanField(default=False, db_index=True)
acknowledged_by:     ForeignKey(CustomUser, null=True, blank=True, on_delete=SET_NULL)
acknowledged_at:     DateTimeField(null=True, blank=True)
created_at:          DateTimeField(auto_now_add=True)

Meta: indexes on (camera_id, created_at), (tenant_id, is_acknowledged), (severity,)
```

**Why a separate `WasteAlert` model?** The generic `Alert` model requires `detection` FK and `alert_rule` FK which are not applicable here. WasteAlert carries alert_type, links to WasteInspection, and has its own acknowledgment flow. It still broadcasts to the shared Redis channel so existing frontend WebSocket receives it.

---

## Step 2 — VLM Vision Extension (existing `infrastructure/llm/`)

### `backend/infrastructure/llm/base.py`
Add abstract method to `BaseLLMClient`:
```python
@abstractmethod
async def analyze_image(
    self,
    image_b64: str,          # base64-encoded JPEG
    prompt: str,
    system_prompt: str = "",
    max_tokens: int = 1024,
) -> str:
    """Send a frame image + prompt to the VLM. Return raw text response."""
```

### `anthropic_client.py` — vision via messages API
```python
async def analyze_image(self, image_b64, prompt, system_prompt="", max_tokens=1024) -> str:
    response = await self._client.messages.create(
        model=self.model, max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
            {"type": "text", "text": prompt},
        ]}]
    )
    return response.content[0].text
```

### `openai_client.py` — vision via chat completions
```python
async def analyze_image(self, image_b64, prompt, system_prompt="", max_tokens=1024) -> str:
    msgs = []
    if system_prompt:
        msgs.append({"role": "system", "content": system_prompt})
    msgs.append({"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
        {"type": "text", "text": prompt},
    ]})
    r = await self._client.chat.completions.create(model=self.model, messages=msgs, max_tokens=max_tokens)
    return r.choices[0].message.content
```

### `ollama_client.py` — vision via /api/chat with images field
```python
async def analyze_image(self, image_b64, prompt, system_prompt="", max_tokens=1024) -> str:
    payload = {
        "model": self.model, "stream": False,
        "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
        "options": {"num_predict": max_tokens},
    }
    async with httpx.AsyncClient(base_url=self.base_url, timeout=60) as c:
        r = await c.post("/api/chat", json=payload)
        r.raise_for_status()
        return r.json()["message"]["content"]
```

---

## Step 3 — Frame Capture: `backend/wastevision/frame_capture.py`

Central asyncio-based stream manager. Not a Celery task — runs as a long-lived coroutine managed by FastAPI lifespan.

```python
@dataclass
class CapturedFrame:
    camera_id: int         # DB pk
    camera_uuid: str
    tenant_id: str
    timestamp: datetime
    frame_bytes: bytes     # JPEG bytes
    sequence_no: int

class CameraStreamManager:
    """
    Manages N concurrent camera streams. Each stream runs as an asyncio task
    that reads frames and puts CapturedFrame objects onto a shared asyncio.Queue.
    """
    def __init__(self, frame_queue: asyncio.Queue, max_cameras: int = 16, default_fps: float = 2.0):
        self._queue = frame_queue
        self._tasks: dict[int, asyncio.Task] = {}        # camera.id → asyncio.Task
        self._seq: dict[int, int] = {}                   # camera.id → sequence counter

    async def add_camera(self, camera: WasteCamera) -> None:
        """Start streaming a camera. Idempotent — skips if already running."""

    async def remove_camera(self, camera_id: int) -> None:
        """Cancel and remove camera stream task."""

    async def _stream_rtsp(self, camera: WasteCamera) -> None:
        """
        Reads RTSP via cv2.VideoCapture in a thread pool executor
        (cv2 is sync; use asyncio.get_event_loop().run_in_executor).
        Throttles to camera.target_fps using asyncio.sleep.
        Encodes frame to JPEG bytes. Puts CapturedFrame on queue.
        On error: updates camera.status='error' (sync_to_async), retries with backoff.
        """

    async def _stream_mjpeg(self, camera: WasteCamera) -> None:
        """
        Reads MJPEG HTTP stream via httpx.AsyncClient with streaming=True.
        Parses multipart/x-mixed-replace boundaries to extract JPEG frames.
        Throttles to target_fps.
        """

    async def _stream_upload(self, camera: WasteCamera) -> None:
        """
        For cameras of type 'upload': reads from a local file path (stream_url = file path).
        Used for testing / uploaded video files.
        Reads via cv2 in executor, same throttling logic.
        """
```

**FastAPI lifespan integration** — in `backend/api/main.py`, the lifespan context manager (or startup event) initializes a `CameraStreamManager` and a VLM worker pool, then starts all active cameras. On shutdown, cancels all tasks.

```python
# In api/main.py (modify lifespan or startup):
@asynccontextmanager
async def lifespan(app: FastAPI):
    frame_queue = asyncio.Queue(maxsize=200)
    app.state.frame_queue = frame_queue
    app.state.stream_manager = CameraStreamManager(frame_queue)
    app.state.vlm_service = WasteVisionService(frame_queue)
    
    # Load active cameras from DB
    cameras = await sync_to_async(list)(WasteCamera.objects.filter(is_active=True))
    for cam in cameras:
        await app.state.stream_manager.add_camera(cam)
    
    # Start VLM worker pool
    vlm_task = asyncio.create_task(app.state.vlm_service.run_workers())
    
    yield
    
    vlm_task.cancel()
    # stream_manager cancels all tasks on removal
```

---

## Step 4 — VLM Service: `backend/wastevision/service.py`

```python
WASTEVISION_SYSTEM_PROMPT = """
You are an automated waste inspection AI running 24/7 at a waste management facility.
Analyze each camera frame and return ONLY valid JSON — no markdown, no preamble.
[... exact schema from spec ...]
"""

class WasteVisionService:
    """
    Worker pool: pulls CapturedFrame from queue, calls VLM, saves result,
    runs alert checks, publishes to Redis.
    """
    def __init__(self, frame_queue: asyncio.Queue):
        self._queue = frame_queue
        self._semaphore = asyncio.Semaphore(settings.WASTEVISION_VLM_WORKERS)
        self._llm = self._build_llm_client()   # uses WASTEVISION_VLM_PROVIDER / WASTEVISION_VLM_MODEL
                                                # falling back to LLM_PROVIDER / LLM_MODEL

    def _build_llm_client(self) -> BaseLLMClient:
        """Instantiate VLM client. Prefers WASTEVISION_VLM_* env vars, falls back to get_llm_client()."""

    async def run_workers(self):
        """Infinite loop: pull from queue, dispatch _process_frame as concurrent tasks."""
        while True:
            frame = await self._queue.get()
            asyncio.create_task(self._process_frame(frame))

    async def _process_frame(self, frame: CapturedFrame):
        async with self._semaphore:
            await self._analyze_with_backoff(frame)

    async def _analyze_with_backoff(self, frame: CapturedFrame, max_retries=4):
        """
        Calls self._llm.analyze_image() with exponential backoff on API errors.
        Delays: 1s, 2s, 4s, 8s.
        On final failure: logs error, skips frame (no DB write).
        """
        image_b64 = base64.b64encode(frame.frame_bytes).decode()
        for attempt in range(max_retries):
            try:
                t0 = time.monotonic()
                raw = await self._llm.analyze_image(image_b64, "Return JSON only.", WASTEVISION_SYSTEM_PROMPT)
                ms = int((time.monotonic() - t0) * 1000)
                data = self._parse_vlm_response(raw)
                inspection = await self._save_inspection(frame, data, ms)
                await self._publish_frame_result(frame, inspection)
                await self._run_alert_engine(frame, inspection)
                return
            except (RateLimitError, APIError) as e:
                if attempt == max_retries - 1:
                    logger.error("VLM failed after %d retries: %s", max_retries, e)
                    return
                await asyncio.sleep(2 ** attempt)

    def _parse_vlm_response(self, raw: str) -> dict:
        """Strip any accidental markdown, JSON.parse, validate required keys. Raise ValueError on bad schema."""

    async def _save_inspection(self, frame: CapturedFrame, data: dict, ms: int) -> WasteInspection:
        """Create WasteInspection record via sync_to_async. Update camera.last_frame_at."""

    async def _publish_frame_result(self, frame: CapturedFrame, inspection: WasteInspection):
        """
        Publish to per-camera channel: wastevision:camera:{camera_uuid}
        Message: { type: 'frame_result', inspection: {...} }
        This is what WS /ws/camera/{camera_id} subscribes to.
        """

    async def _run_alert_engine(self, frame: CapturedFrame, inspection: WasteInspection):
        """Delegate to AlertEngine.process(inspection)."""
```

---

## Step 5 — Alert Engine: `backend/wastevision/alert_engine.py`

```python
class AlertEngine:
    """
    Stateless rule engine. Called per inspection result.
    Reads dedup state from Redis (key: wastevision:dedup:{camera_uuid}:{contaminant}).
    """

    async def process(self, frame: CapturedFrame, inspection: WasteInspection):
        camera = await sync_to_async(WasteCamera.objects.get)(id=frame.camera_id)

        # Rule 1: Critical severity contamination items → immediate alert
        for item in inspection.contamination_alerts:
            if item['severity'] == 'critical':
                await self._maybe_alert(camera, inspection, 'contamination', 'critical', item)

        # Rule 2: High severity contamination → alert
        for item in inspection.contamination_alerts:
            if item['severity'] == 'high':
                await self._maybe_alert(camera, inspection, 'contamination', 'high', item)

        # Rule 3: Line blockage
        if inspection.line_blockage:
            await self._maybe_alert(camera, inspection, 'blockage', 'critical',
                                    {'item': 'LINE_BLOCKAGE', 'action': 'Stop conveyor immediately'})

        # Rule 4: Consecutive high/critical escalation
        if inspection.overall_risk in ('high', 'critical'):
            new_count = await sync_to_async(self._inc_consecutive)(camera)
            if new_count >= settings.WASTEVISION_CONSECUTIVE_N:
                await self._maybe_alert(camera, inspection, 'escalation', 'critical',
                                        {'consecutive_count': new_count})
        else:
            await sync_to_async(self._reset_consecutive)(camera)

        # Rule 5: Composition drift (>WASTEVISION_DRIFT_PCT% jump in any material vs 5-min window avg)
        drift = await self._check_drift(camera, inspection)
        if drift:
            await self._maybe_alert(camera, inspection, 'drift', 'high', drift)

    async def _maybe_alert(self, camera, inspection, alert_type, severity, details):
        """
        Deduplication: check Redis key wastevision:dedup:{camera.camera_uuid}:{alert_type}:{item_key}
        TTL = WASTEVISION_DEDUP_WINDOW seconds.
        If key exists: skip (already alerted recently).
        If not: create WasteAlert record, publish to Redis, set dedup key.
        """

    async def _publish_alert(self, alert: WasteAlert):
        """
        Publish to TWO channels:
        1. alerts:{tenant_id}   ← existing channel, picked up by existing frontend AlertContext
        2. wastevision:alerts:{tenant_id}  ← WS /ws/alerts subscribes to this

        Message format (backwards-compatible with existing 'new_alert' format):
        {
            "type": "new_alert",
            "alert": {
                "id": alert.alert_uuid,
                "source": "wastevision",
                "camera_id": str(camera.camera_uuid),
                "camera_name": camera.name,
                "camera_location": camera.location,
                "type": alert.alert_type,
                "severity": alert.severity,
                "timestamp": alert.created_at.isoformat(),
                "details": alert.details,
                "acknowledged": False,
                "plant_site": camera.plant_site,
                "inspector_note": inspection.inspector_note,
            }
        }
        """

    async def _check_drift(self, camera, inspection) -> dict | None:
        """
        Query WasteInspection for this camera over last 5 minutes.
        Compute avg of each composition material.
        If any material in current inspection exceeds avg by WASTEVISION_DRIFT_PCT: return drift details.
        """
```

---

## Step 6 — FastAPI Router: `backend/api/routers/wastevision/`

### `schemas.py` — Pydantic models
```python
# Request models
class WasteCameraCreate(BaseModel):
    name: str; location: str; plant_site: str = ""
    stream_type: Literal['rtsp', 'mjpeg', 'upload']
    stream_url: str = ""      # required for rtsp/mjpeg
    target_fps: float = 2.0   # capped to WASTEVISION_FRAME_FPS

class InspectFrameRequest(BaseModel):
    camera_uuid: UUID
    image_b64: str            # base64 JPEG (for manual/upload inspection)

# Response models
class WasteCameraResponse(BaseModel):
    camera_uuid: UUID; name: str; location: str; plant_site: str
    stream_type: str; stream_url: str; target_fps: float
    is_active: bool; status: str; consecutive_high: int
    last_frame_at: Optional[datetime]; last_risk_level: str

class WasteComposition(BaseModel):
    plastic: float; paper: float; glass: float; metal: float
    organic: float; e_waste: float; hazardous: float; other: float

class ContaminationItem(BaseModel):
    item: str; severity: str; location_in_frame: str; action: str

class WasteInspectionResponse(BaseModel):
    inspection_uuid: UUID; camera_uuid: UUID
    sequence_no: int; frame_timestamp: datetime
    waste_composition: WasteComposition
    contamination_alerts: List[ContaminationItem]
    line_blockage: bool; overall_risk: str
    confidence: float; inspector_note: str
    vlm_provider: str; vlm_model: str
    processing_time_ms: Optional[int]; created_at: datetime

class WasteAlertResponse(BaseModel):
    alert_uuid: UUID; camera_uuid: UUID
    alert_type: str; severity: str
    details: dict; is_acknowledged: bool
    acknowledged_at: Optional[datetime]; created_at: datetime

class WasteStats(BaseModel):
    total_inspections: int
    risk_breakdown: dict        # {low, medium, high, critical: int}
    top_contamination_labels: List[dict]
    avg_confidence_by_camera: List[dict]
    active_cameras: int
    alerts_last_24h: int
```

### `queries/cameras.py` — REST endpoints
```
GET    /wastevision/cameras              → list (paginated, filter: is_active, plant_site)
POST   /wastevision/cameras              → create + start stream (write permission)
PUT    /wastevision/cameras/{uuid}       → update (write permission)
DELETE /wastevision/cameras/{uuid}       → delete + stop stream (admin permission)
POST   /wastevision/cameras/{uuid}/start → start stream for idle camera
POST   /wastevision/cameras/{uuid}/stop  → stop stream without deleting
```
Camera start/stop calls `request.app.state.stream_manager.add_camera()` or `.remove_camera()`.

### `queries/inspections.py` — REST endpoints
```
POST /wastevision/inspect                → manual frame submit (sync analysis, returns WasteInspectionResponse)
GET  /wastevision/inspections            → list (filter: camera_uuid, risk, date_from, date_to; paginated)
GET  /wastevision/inspections/{uuid}     → single inspection
GET  /wastevision/cameras/{uuid}/trend   → last N inspections (default 50) for trend chart
GET  /wastevision/stats                  → aggregate stats
GET  /wastevision/alerts                 → list WasteAlerts (filter: camera, severity, acknowledged)
POST /wastevision/alerts/{uuid}/acknowledge → acknowledge alert
GET  /wastevision/inspections/export     → CSV download (streaming response)
```

### `queries/websockets.py` — Two new WebSocket endpoints

**`WS /api/v1/wastevision/cameras/{camera_uuid}/stream`**
- Auth: same `_authenticate_ws()` pattern as existing alerts WS (token or api_key query param)
- Subscribes to Redis channel `wastevision:camera:{camera_uuid}`
- Forwards every `frame_result` message as JSON text to client
- Client receives: `{ type: "frame_result", inspection: WasteInspectionResponse }`

**`WS /api/v1/wastevision/alerts/stream`**
- Auth: same pattern
- Subscribes to Redis channel `wastevision:alerts:{tenant_id}`
- Forwards every `new_alert` message as JSON text to client
- (Separate from existing `/api/v1/alerts/ws` — WasteVision-specific feed only)

---

## Step 7 — Frontend: Industrial Control Room UI

### Design System Additions: `wastevision.css`
```css
/* Control room theme — extends existing CSS vars */
.wv-root {
  --wv-grid-bg: #040608;
  --wv-panel-bg: #0a0e18;
  --wv-border: #1a2235;
  --wv-amber: var(--amber);
  --wv-green: #00ff88;    /* OK signal */
  --wv-red: #ff2244;      /* CRITICAL signal */
  --wv-yellow: #ffcc00;   /* WARNING signal */
  --wv-mono: var(--font-mono);
  font-family: var(--wv-mono);
}
/* Scanline effect, grid overlays, pulsing CRITICAL badges, etc. */
```

### TypeScript Types in `src/types/api.ts`
```typescript
export interface WasteCamera { camera_uuid: string; name: string; location: string; plant_site: string; stream_type: 'rtsp'|'mjpeg'|'upload'; stream_url: string; target_fps: number; is_active: boolean; status: 'idle'|'streaming'|'error'; consecutive_high: number; last_frame_at: string|null; last_risk_level: string; }
export interface WasteComposition { plastic: number; paper: number; glass: number; metal: number; organic: number; e_waste: number; hazardous: number; other: number; }
export type RiskLevel = 'low'|'medium'|'high'|'critical';
export interface ContaminationItem { item: string; severity: RiskLevel; location_in_frame: string; action: string; }
export interface WasteInspection { inspection_uuid: string; camera_uuid: string; sequence_no: number; frame_timestamp: string; waste_composition: WasteComposition; contamination_alerts: ContaminationItem[]; line_blockage: boolean; overall_risk: RiskLevel; confidence: number; inspector_note: string; vlm_provider: string; vlm_model: string; processing_time_ms: number|null; created_at: string; }
export interface WasteAlert { alert_uuid: string; camera_uuid: string; alert_type: 'contamination'|'blockage'|'escalation'|'drift'; severity: RiskLevel; details: Record<string, unknown>; is_acknowledged: boolean; acknowledged_at: string|null; created_at: string; }
export interface WasteStats { total_inspections: number; risk_breakdown: Record<RiskLevel,number>; top_contamination_labels: {label:string;count:number}[]; avg_confidence_by_camera: {camera_uuid:string;camera_name:string;avg_confidence:number}[]; active_cameras: number; alerts_last_24h: number; }
```

### API Client additions in `src/api/client.ts`
```typescript
// Cameras
listWasteCameras: (p?) => api.get('/v1/wastevision/cameras', {params: p}),
createWasteCamera: (d) => api.post('/v1/wastevision/cameras', d),
updateWasteCamera: (uuid, d) => api.put(`/v1/wastevision/cameras/${uuid}`, d),
deleteWasteCamera: (uuid) => api.delete(`/v1/wastevision/cameras/${uuid}`),
startCamera: (uuid) => api.post(`/v1/wastevision/cameras/${uuid}/start`),
stopCamera: (uuid) => api.post(`/v1/wastevision/cameras/${uuid}/stop`),
// Inspections
inspectFrame: (d) => api.post('/v1/wastevision/inspect', d),
listInspections: (p) => api.get('/v1/wastevision/inspections', {params: p}),
getCameraTrend: (uuid, n=50) => api.get(`/v1/wastevision/cameras/${uuid}/trend`, {params:{n}}),
getWasteStats: () => api.get('/v1/wastevision/stats'),
exportInspections: (p) => api.get('/v1/wastevision/inspections/export', {params:p, responseType:'blob'}),
// Alerts
listWasteAlerts: (p) => api.get('/v1/wastevision/alerts', {params:p}),
acknowledgeWasteAlert: (uuid) => api.post(`/v1/wastevision/alerts/${uuid}/acknowledge`),
```

### WebSocket Hooks

**`hooks/useCameraStream.ts`**
```typescript
// Connects to WS /api/v1/wastevision/cameras/{camera_uuid}/stream
// Returns: { latestInspection: WasteInspection | null, connected: boolean }
// Auto-reconnects (same 5s retry pattern as AlertContext)
```

**`hooks/useWasteAlerts.ts`**
```typescript
// Connects to WS /api/v1/wastevision/alerts/stream
// Returns: { alerts: WasteAlert[], unreadCount: number, acknowledge(uuid): void }
// Prepends new alerts, keeps last 100
```

### Page Components

**`pages/WasteVision/index.tsx`** — main page, tab bar: `CAMERAS | COMPOSITION | ALERTS | LOG | MANAGE`

**`CameraGrid.tsx`**
- CSS grid layout (2×2, 3×3, or 4×4 configurable)
- Each cell: camera name header, live frame (polling `/trend?n=1` at configurable interval OR WebSocket JPEG delivery via `useCameraStream`)
- Risk badge overlay: `OK` (green), `WARNING` (amber), `CRITICAL` (red pulsing)
- Contamination bounding region: semi-transparent colored overlay box positioned via `location_in_frame` (5-zone grid: top-left/top-right/center/bottom-left/bottom-right)
- Click cell → focus/expand that camera

**`CompositionPanel.tsx`**
- Left: horizontal bar chart (each material = one bar, width = %, colored by threshold)
- Right: trend area chart for last 1h — data from `getCameraTrend()` + live updates via `useCameraStream`
- Camera selector to switch between feeds
- All numbers in `--font-mono`, labels uppercase

**`AlertFeed.tsx`**
- Scrolling list of WasteAlerts from `useWasteAlerts` hook
- Each row: timestamp (mono), severity badge, camera name, alert type, item name, acknowledge button
- Color coding: critical=`--wv-red`, high=amber, medium=yellow, low=muted
- Click row → opens inspection detail modal

**`InspectorLog.tsx`**
- Paginated data table of WasteInspections (filter: camera, risk_level, date range)
- Columns: timestamp, camera, sequence_no, overall_risk badge, confidence, top contamination item, line_blockage, processing_ms
- Export button → calls `exportInspections()` → downloads CSV
- All using existing `.data-table` CSS class

**`CameraManager.tsx`**
- Table of cameras with status indicator, start/stop toggle, FPS display
- "Add Camera" form: name, location, plant_site, stream_type selector, stream_url, target_fps
- Delete with confirmation
- Stream status updates every 10s via polling `listWasteCameras()`

**`EmbedWidget.tsx`**
- Minimal standalone view: single camera, last inspection, risk badge, top contamination item
- Designed for `<iframe>` embedding in parent dashboards
- URL pattern: `/wastevision?embed=1&camera={uuid}` — hides sidebar, renders `EmbedWidget` only
- No auth context needed if token passed as query param (handled by existing `/api/v1/wastevision/inspect` with API key)

### Sidebar + Router
```tsx
// Sidebar.tsx — add after HazardConfig:
{ path: '/wastevision', icon: ScanLine, label: 'WasteVision', labelSuffix: <LiveBadge /> }

// App.tsx — inside AuthGuard → AppLayout:
<Route path="/wastevision" element={<WasteVisionPage />} />

// Check for embed mode:
// In WasteVisionPage/index.tsx:
const isEmbed = new URLSearchParams(window.location.search).get('embed') === '1';
if (isEmbed) return <EmbedWidget />;
```

---

## Step 8 — Lifespan / Startup Integration

**File to modify:** `backend/api/main.py`

Add lifespan context manager (or extend existing if one exists):
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    from wastevision.frame_capture import CameraStreamManager
    from wastevision.service import WasteVisionService
    
    frame_queue = asyncio.Queue(maxsize=500)
    stream_manager = CameraStreamManager(frame_queue, max_cameras=settings.WASTEVISION_MAX_CAMERAS)
    vlm_service = WasteVisionService(frame_queue)
    
    app.state.wv_stream_manager = stream_manager
    app.state.wv_vlm_service = vlm_service
    
    # Boot all active cameras
    active_cams = await sync_to_async(list)(WasteCamera.objects.filter(is_active=True))
    for cam in active_cams:
        await stream_manager.add_camera(cam)
    
    worker_task = asyncio.create_task(vlm_service.run_workers())
    
    yield
    
    worker_task.cancel()
    await asyncio.gather(worker_task, return_exceptions=True)
```

---

## Step 9 — Migration & Deployment

```bash
docker compose exec search-engine python manage.py makemigrations wastevision
docker compose exec search-engine python manage.py migrate
docker compose up --build search-engine -d
docker compose up --build frontend -d
```

Add `opencv-python-headless` and `httpx` to `Dockerfile.backend` requirements if not already present (needed for frame capture).

---

## Verification Checklist

1. **Camera registration** — POST `/api/v1/wastevision/cameras` with RTSP URL → camera created, `status='streaming'`
2. **Frame analysis** — POST `/api/v1/wastevision/inspect` with test JPEG base64 → returns `WasteInspectionResponse` with all fields populated
3. **Redis publishing** — After analysis, confirm message on `wastevision:camera:{uuid}` channel via `redis-cli SUBSCRIBE`
4. **Alert engine** — Submit frame with `overall_risk=critical` contamination → confirm `WasteAlert` record created + message on `alerts:{tenant_id}` channel
5. **WebSocket per-camera** — Connect to `WS /api/v1/wastevision/cameras/{uuid}/stream`, start a camera, confirm JSON frames arrive
6. **WebSocket alerts** — Connect to `WS /api/v1/wastevision/alerts/stream`, trigger alert, confirm arrival
7. **Deduplication** — Submit identical critical contamination twice within dedup window → only one `WasteAlert` created
8. **Escalation** — Submit 3 consecutive `overall_risk=high` frames for same camera → escalation alert fires
9. **Frontend** — Navigate to `/wastevision`, camera grid renders, composition panel updates live, alert feed shows alerts
10. **CSV export** — GET `/api/v1/wastevision/inspections/export` → valid CSV download
11. **Embed widget** — `/wastevision?embed=1&camera={uuid}` renders minimal view without sidebar