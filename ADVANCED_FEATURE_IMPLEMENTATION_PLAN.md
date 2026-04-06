# Advanced Features Implementation Plan

## Context

The platform has a complete core pipeline (upload → detect → embed → search) with 11 pages, annotation tools, bulk operations, and backend hardening. The next tier of features transforms it from an inspection database into a **safety intelligence system** — real-time alerts, shift reporting, trend analytics, visual comparison, compliance checklists, data export, and team collaboration. These 7 features are ordered by business impact and build on each other (alerts feed into reports, trends feed into anomaly detection, etc.).

---

## Feature 1: Real-Time Defect Alert System

### What it does
When auto-detection finds a defect above a configurable severity threshold, immediately push a notification to connected clients via WebSocket. Optionally fire a webhook (Slack, Teams, PagerDuty). Alerts are acknowledged by operators, creating an audit trail.

### Backend

**New Django app: `alerts`**

```
backend/alerts/
├── __init__.py
├── models.py        # Alert, AlertRule
├── admin.py
└── migrations/
```

**Models (`alerts/models.py`):**
```python
class AlertRule(TenantScopedModel):
    name              # str
    label_pattern     # str (regex or exact match, e.g. "rust", "crack|corrosion")
    min_confidence    # float (0.0-1.0)
    plant_site        # str (nullable — any plant if null)
    is_active         # bool
    webhook_url       # str (nullable — Slack/Teams/PagerDuty)
    notify_websocket  # bool (default True)
    cooldown_minutes  # int (default 5 — suppress repeat alerts for same label+plant)
    created_by        # FK(User)

class Alert(TenantScopedModel):
    alert_rule        # FK(AlertRule, nullable)
    detection         # FK(Detection)
    image             # FK(Image)
    severity          # str (critical/warning/info — derived from confidence)
    label             # str (denormalized from detection)
    confidence        # float (denormalized)
    plant_site        # str (denormalized)
    is_acknowledged   # bool
    acknowledged_by   # FK(User, nullable)
    acknowledged_at   # DateTime(nullable)
    webhook_sent      # bool
    webhook_response  # str (nullable)
    created_at        # DateTime
```

Add `'alerts'` to `INSTALLED_APPS` in `backend/backend/settings.py`.

**New FastAPI router: `backend/api/routers/alerts/`**

Follow hazard_config pattern:
```
backend/api/routers/alerts/
├── __init__.py
├── endpoint.py
└── queries/
    ├── __init__.py
    └── alerts.py
```

Endpoints:
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/alerts/` | read | List alerts (paginated, filterable by severity, acknowledged, plant_site, date range) |
| GET | `/alerts/unread-count` | read | Return `{ count: int }` for notification badge |
| POST | `/alerts/{id}/acknowledge` | write | Set is_acknowledged=True, acknowledged_by/at |
| POST | `/alerts/acknowledge-all` | write | Acknowledge all unread alerts |
| GET | `/alerts/rules/` | admin | List alert rules |
| POST | `/alerts/rules/` | admin | Create alert rule |
| PUT | `/alerts/rules/{id}` | admin | Update alert rule |
| DELETE | `/alerts/rules/{id}` | admin | Delete alert rule |

**Alert trigger — new Celery task:**

File: `backend/embeddings/tasks/alert_check.py`
```python
@shared_task(name='alerts:check_detection', queue='maintenance')
def check_detection_alert_task(detection_id: int):
    detection = Detection.objects.select_related('image', 'tenant').get(id=detection_id)
    rules = AlertRule.objects.filter(tenant=detection.tenant, is_active=True)
    for rule in rules:
        if not _matches_rule(detection, rule): continue
        if _in_cooldown(rule, detection): continue
        alert = Alert.objects.create(
            tenant=detection.tenant, alert_rule=rule, detection=detection,
            image=detection.image, severity=_compute_severity(detection.confidence),
            label=detection.label, confidence=detection.confidence,
            plant_site=detection.image.plant_site,
        )
        if rule.webhook_url:
            _send_webhook(rule.webhook_url, alert)
        if rule.notify_websocket:
            _publish_to_redis(detection.tenant.id, alert)
```

Hook into Detection post_save signal in `backend/embeddings/signals.py`:
```python
@receiver(post_save, sender=Detection)
def check_alert_on_detection(sender, instance, created, **kwargs):
    if created:
        check_detection_alert_task.delay(instance.id)
```

Add `'alerts'` queue to `celery_config.py` CELERY_TASK_QUEUES. The existing `maintenance_worker` can process it, or route to a dedicated worker.

**WebSocket endpoint:**

File: `backend/api/routers/alerts/queries/websocket.py`

Use FastAPI's native WebSocket support. Redis pub/sub for cross-worker broadcasting:
```python
@router.websocket("/alerts/ws")
async def alert_websocket(ws: WebSocket):
    await ws.accept()
    # Authenticate via query param token
    # Subscribe to Redis channel f"alerts:{tenant_id}"
    # Forward messages to client
```

Add Redis pub/sub utility: `backend/infrastructure/pubsub.py` — thin wrapper around `redis.asyncio` subscribe/publish.

### Frontend

**New context: `frontend/src/context/AlertContext.tsx`**
- Manages WebSocket connection to `/api/v1/alerts/ws`
- Holds `unreadCount` and `recentAlerts[]` state
- Provides `useAlerts()` hook
- Auto-reconnects on disconnect
- Wraps app in `App.tsx` (inside AuthProvider)

**TopBar notification bell (`frontend/src/components/Layout/AppLayout.tsx`):**
- Bell icon with unread count badge (red dot with number)
- Click opens sliding alert panel (right drawer)
- Panel shows recent alerts: crop thumbnail, label, confidence, plant, time
- "Acknowledge" button per alert, "Acknowledge All" at top
- Click alert → navigates to detection detail page

**New page: `frontend/src/pages/Alerts.tsx`** (route: `/alerts`)
- Full alert history table with filters (severity, plant, date range, acknowledged status)
- Alert rules management section (admin only): CRUD for rules with label pattern, min confidence, plant filter, webhook URL, cooldown

**Sidebar:** Add nav item: `{ icon: Bell, label: 'Alerts', path: '/alerts' }` after Dashboard.

**Dashboard widget:** "Active Alerts" stat card showing unread count + "Critical" count.

**Settings page extension:** New "Alert Rules" card in right column — quick link to `/alerts` rules section, or inline CRUD.

### Files to create/modify

| Action | File |
|--------|------|
| CREATE | `backend/alerts/models.py`, `admin.py`, `__init__.py`, `migrations/` |
| CREATE | `backend/api/routers/alerts/endpoint.py`, `queries/alerts.py`, `queries/websocket.py` |
| CREATE | `backend/embeddings/tasks/alert_check.py` |
| CREATE | `backend/infrastructure/pubsub.py` |
| MODIFY | `backend/embeddings/signals.py` — add alert signal |
| MODIFY | `backend/embeddings/config/celery_config.py` — add alerts queue |
| MODIFY | `backend/backend/settings.py` — add alerts to INSTALLED_APPS |
| CREATE | `frontend/src/context/AlertContext.tsx` |
| CREATE | `frontend/src/pages/Alerts.tsx` |
| CREATE | `frontend/src/components/AlertPanel.tsx` |
| MODIFY | `frontend/src/components/Layout/AppLayout.tsx` — bell icon + drawer |
| MODIFY | `frontend/src/components/Layout/Sidebar.tsx` — nav item |
| MODIFY | `frontend/src/App.tsx` — AlertProvider + route |
| MODIFY | `frontend/src/pages/Dashboard.tsx` — alerts widget |
| MODIFY | `frontend/src/api/client.ts` — alert API functions |
| MODIFY | `frontend/src/types/api.ts` — Alert, AlertRule types |

### Verification
1. Create alert rule: label="rust", min_confidence=0.5, webhook_url=null
2. Upload image → auto-detection finds "rust" at 0.8 confidence
3. Bell icon shows "1" badge within seconds (WebSocket push)
4. Click bell → alert panel shows crop + details
5. Click "Acknowledge" → badge clears
6. Alert history page shows the acknowledged alert

---

## Feature 2: Shift Handoff Report

### What it does
Auto-generated end-of-shift summary: uploads, detections, top defects, high-severity items, delta vs. previous shift. Viewable in-app and downloadable as PDF.

### Backend

**New FastAPI router: `backend/api/routers/reports/`**

```
backend/api/routers/reports/
├── __init__.py
├── endpoint.py
└── queries/
    ├── __init__.py
    └── reports.py
```

Endpoints:
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/reports/shift-summary` | read | JSON summary (params: shift, date, plant_site) |
| GET | `/reports/shift-summary/pdf` | read | PDF download (same params) |
| GET | `/reports/available-shifts` | read | List shifts with data for a date range |

**Shift summary logic (`queries/reports.py`):**
```python
async def get_shift_summary(shift, date, plant_site, tenant):
    # Define shift windows (configurable per tenant timezone):
    #   morning: 06:00-14:00, afternoon: 14:00-22:00, night: 22:00-06:00
    start, end = _shift_window(shift, date, tenant.timezone)

    images = Image.objects.filter(tenant=tenant, captured_at__range=(start, end))
    if plant_site: images = images.filter(plant_site=plant_site)

    detections = Detection.objects.filter(image__in=images)

    # Compute: upload_count, detection_count, by_label, by_severity,
    #          high_severity_items (confidence > 0.8), unacknowledged_alerts

    # Previous shift comparison (same shift, previous day)
    prev_start, prev_end = _shift_window(shift, date - 1day, tenant.timezone)
    # Compute deltas: detection_delta, upload_delta

    return ShiftSummaryResponse(...)
```

**PDF generation:**
- Use `reportlab` (add to requirements.txt)
- Template: header (logo, tenant, shift, date), KPI row, detection table with thumbnails, comparison section
- Return as `StreamingResponse(content_type='application/pdf')`

**Pydantic schemas:**
```python
class ShiftSummaryResponse(BaseModel):
    shift: str
    date: str
    plant_site: str | None
    period_start: datetime
    period_end: datetime
    uploads: ShiftUploads        # total, images, videos
    detections: ShiftDetections  # total, by_label (list), high_severity (list with crop_url)
    alerts: ShiftAlerts          # total, unacknowledged, critical
    comparison: ShiftComparison  # prev_uploads, prev_detections, upload_delta_pct, detection_delta_pct
```

### Frontend

**New page: `frontend/src/pages/Reports.tsx`** (route: `/reports`)

Layout:
- **Filter bar:** Shift selector (morning/afternoon/night), date picker, plant filter
- **KPI cards row:** Uploads, Detections, High-Severity, Alerts — each with delta arrow vs. previous shift
- **Detections by Label:** Horizontal bar chart (Recharts BarChart, same pattern as Analytics)
- **High-Severity Items:** Grid of detection cards (crop thumbnail, label, confidence, image link)
- **Comparison panel:** Side-by-side bars (this shift vs. previous) for uploads and detections
- **"Download PDF" button** in page header — calls `/reports/shift-summary/pdf`

**Sidebar:** Add nav item `{ icon: FileText, label: 'Reports', path: '/reports' }` between Analytics and Hazard Config.

**Dashboard quick action:** "Generate Shift Report" button card linking to `/reports`.

### Files to create/modify

| Action | File |
|--------|------|
| CREATE | `backend/api/routers/reports/endpoint.py`, `queries/reports.py` |
| CREATE | `frontend/src/pages/Reports.tsx` |
| MODIFY | `frontend/src/App.tsx` — route |
| MODIFY | `frontend/src/components/Layout/Sidebar.tsx` — nav item |
| MODIFY | `frontend/src/api/client.ts` — report API functions |
| MODIFY | `frontend/src/types/api.ts` — ShiftSummary types |
| MODIFY | `frontend/src/pages/Dashboard.tsx` — quick action card |
| MODIFY | `requirements.txt` or Dockerfile — add `reportlab` |

### Verification
1. Upload 5 images with `shift=morning`, `captured_at=today 08:00`
2. Run auto-detection on them → detections created
3. Open Reports page → select "Morning", today, any plant
4. See KPI cards with counts, detection chart, high-severity list
5. Click "Download PDF" → PDF opens with formatted report
6. Change shift to previous day → comparison shows deltas

---

## Feature 3: Defect Trend Analytics & Anomaly Detection

### What it does
Time-series charts showing defect frequency by label/plant/line over configurable windows. Automatic anomaly detection using Z-score: flags spikes in defect rates. Anomaly cards on dashboard and analytics page with "Investigate" click-through.

### Backend

**Extend search router: `backend/api/routers/search/queries/search.py`**

New endpoints:
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/search/stats/trends` | read | Time-series data (params: labels[], plant_site, granularity=day/week, days=90) |
| GET | `/search/stats/anomalies` | read | Active anomalies with context |
| GET | `/search/stats/heatmap` | read | Label x Plant matrix of detection counts |

**Trend logic:**
```python
async def get_detection_trends(labels, plant_site, granularity, days, tenant):
    qs = Detection.objects.filter(tenant=tenant, created_at__gte=cutoff)
    if labels: qs = qs.filter(label__in=labels)
    if plant_site: qs = qs.filter(image__plant_site=plant_site)

    # Group by date + label
    series = qs.values('label').annotate(
        date=TruncDate('created_at') if granularity == 'day' else TruncWeek('created_at'),
        count=Count('id')
    ).order_by('date')

    return TrendResponse(series=[...])
```

**Anomaly detection logic:**
```python
def detect_anomalies(series, window=30, threshold=2.0):
    # For each label's time series:
    #   rolling_mean = mean of last `window` periods
    #   rolling_std = std of last `window` periods
    #   z_score = (current - rolling_mean) / rolling_std
    #   if z_score > threshold: flag as anomaly
    # Return list of AnomalyItem(label, plant, current_count, avg_count, z_score, pct_change)
```

No ML models needed — simple statistical Z-score is robust for count data with weekly/daily patterns.

**Schemas:**
```python
class TrendSeries(BaseModel):
    label: str
    data: List[TrendPoint]  # [{date, count}]

class TrendResponse(BaseModel):
    series: List[TrendSeries]
    granularity: str
    days: int

class AnomalyItem(BaseModel):
    label: str
    plant_site: str | None
    current_count: int
    avg_count: float
    z_score: float
    pct_change: float
    severity: str  # 'critical' if z > 3, 'warning' if z > 2
    period: str

class AnomalyResponse(BaseModel):
    anomalies: List[AnomalyItem]
    checked_at: datetime
```

### Frontend

**Extend Analytics page: `frontend/src/pages/Analytics.tsx`**

Add new tab bar at top: "Overview" (current) | "Trends" | "Anomalies"

**Trends tab:**
- Multi-select label chips (fetched from `getTags()` or detection labels)
- Plant filter dropdown
- Granularity toggle (Day / Week)
- Days slider (30 / 60 / 90)
- Recharts `LineChart` with multiple colored series (one per selected label)
- Tooltip showing date + count per label

**Anomalies tab:**
- Auto-fetched anomaly cards
- Each card: label badge, plant badge, "↑ 340%" large text, sparkline (mini trend), "Investigate" button
- "Investigate" button → navigates to `/search` with pre-filled filters (label, plant, date range)

**Heatmap section** (in Trends or separate):
- HTML table grid: rows = labels, columns = plants
- Cell color intensity = count (white to amber to red gradient)
- Click cell → pre-fills search with that label + plant

**Dashboard widget:** "Anomalies" stat card showing count + top anomaly label. Links to Analytics anomalies tab.

### Files to create/modify

| Action | File |
|--------|------|
| MODIFY | `backend/api/routers/search/queries/search.py` — 3 new endpoints |
| MODIFY | `backend/api/routers/search/schemas.py` — trend/anomaly schemas |
| MODIFY | `frontend/src/pages/Analytics.tsx` — tabs, TrendsChart, AnomalyCards, Heatmap |
| MODIFY | `frontend/src/api/client.ts` — trend/anomaly API functions |
| MODIFY | `frontend/src/types/api.ts` — trend/anomaly types |
| MODIFY | `frontend/src/pages/Dashboard.tsx` — anomaly widget |

### Verification
1. Have 30+ days of detection data (or seed test data)
2. Open Analytics → Trends tab → select "rust" label → see 90-day line chart
3. If rust spiked last week: Anomalies tab shows card with % change
4. Click "Investigate" → Search page opens with `label=rust` filter pre-filled
5. Heatmap shows all labels x plants with color-coded counts

---

## Feature 4: Side-by-Side Comparison View

### What it does
Select 2-4 images/detections and compare them in a synchronized viewer with zoom, pan, overlay, and temporal mode.

### Backend
No new backend needed — uses existing `getImage()`, `getDetection()` endpoints. All logic is frontend-only.

### Frontend

**New context: `frontend/src/context/CompareContext.tsx`**
```typescript
interface CompareItem {
  id: number
  type: 'image' | 'detection'
  url: string
  label: string
  plant_site: string
  captured_at: string
}

interface CompareContextValue {
  items: CompareItem[]          // max 4
  addItem: (item: CompareItem) => void
  removeItem: (id: number) => void
  clearAll: () => void
  isInTray: (id: number) => boolean
}
```

Wrap in `App.tsx` inside `AuthProvider`. Persists in `sessionStorage` (cleared on logout).

**Floating comparison tray: `frontend/src/components/CompareTray.tsx`**

Fixed bottom bar (similar to BulkActionBar pattern) that appears when items.length > 0:
```
┌──────────────────────────────────────────────────────┐
│  [thumb1] [thumb2] [thumb3]  [Compare ▶]  [Clear ✕] │
└──────────────────────────────────────────────────────┘
```
- Thumbnails (40x30px) for each item with X to remove
- "Compare" button → navigates to `/compare`
- Shown on all pages except `/compare` itself

**New page: `frontend/src/pages/Compare.tsx`** (route: `/compare`)

Layout: full-width grid of 2-4 panels:
```
┌─────────────┬─────────────┐
│   Image 1   │   Image 2   │
│  [zoom/pan]  │  [zoom/pan]  │
│  metadata   │  metadata   │
└─────────────┴─────────────┘
```

Features:
- **Synchronized zoom/pan:** Mouse wheel on any panel zooms all panels equally. Drag to pan syncs across all.
- **Overlay mode:** Toggle button stacks first two images with opacity slider (0-100%). Useful for same-location progression.
- **Detection overlay toggle:** Show/hide bounding boxes on compared images.
- **Metadata row** per panel: label, confidence, plant, shift, date.
- **Temporal mode:** If all items are from the same plant_site+inspection_line, show timeline slider to scrub through capture dates.

**"Add to Compare" button locations:**
- Search result cards (small icon button, like the amber detail arrow)
- Media Library cards (in info area)
- ImageDetail page (action card)
- DetectionDetail page (action card)

Uses `lucide-react` icon: `GitCompare` or `Columns2`

### Files to create/modify

| Action | File |
|--------|------|
| CREATE | `frontend/src/context/CompareContext.tsx` |
| CREATE | `frontend/src/components/CompareTray.tsx` |
| CREATE | `frontend/src/pages/Compare.tsx` |
| MODIFY | `frontend/src/App.tsx` — CompareProvider + route |
| MODIFY | `frontend/src/pages/Search.tsx` — "Add to Compare" on result cards |
| MODIFY | `frontend/src/pages/MediaLibrary.tsx` — "Add to Compare" on cards |
| MODIFY | `frontend/src/pages/ImageDetail.tsx` — "Add to Compare" action |
| MODIFY | `frontend/src/pages/DetectionDetail.tsx` — "Add to Compare" action |
| MODIFY | `frontend/src/components/Layout/Sidebar.tsx` — nav item |

### Verification
1. Open Media Library → click "Add to Compare" on 2 images → tray shows 2 thumbnails
2. Navigate to Search → add 1 more result → tray shows 3
3. Click "Compare" → compare page opens with 3 synced panels
4. Zoom on panel 1 → all 3 zoom equally
5. Toggle overlay mode → panels 1+2 stack with opacity slider
6. Toggle detection overlay → bounding boxes appear/disappear

---

## Feature 5: Inspection Checklists & Compliance Tracking

### What it does
Define inspection checklists per plant/line. Operators upload photos against items. Auto-detect on submission. Track completion rates for compliance.

### Backend

**New Django app: `checklists`**
```
backend/checklists/
├── __init__.py
├── models.py
├── admin.py
└── migrations/
```

**Models:**
```python
class ChecklistTemplate(TenantScopedModel):
    name               # str
    plant_site         # str
    inspection_line    # str (nullable)
    shift              # str (nullable — any shift if null)
    items              # JSONField — [{description, required_photo: bool, auto_detect: bool}]
    is_active          # bool
    created_by         # FK(User)

class ChecklistInstance(TenantScopedModel):
    template           # FK(ChecklistTemplate)
    shift              # str (morning/afternoon/night)
    date               # DateField
    operator           # FK(User)
    status             # str (pending/in_progress/completed/overdue)
    started_at         # DateTime(nullable)
    completed_at       # DateTime(nullable)
    notes              # TextField(nullable)

class ChecklistItemResult(TenantScopedModel):
    instance           # FK(ChecklistInstance, related_name='results')
    item_index         # int (position in template.items array)
    image              # FK(Image, nullable)
    status             # str (pending/passed/failed/flagged)
    notes              # TextField(nullable)
    detection_count    # int (auto-populated if auto_detect enabled)
    completed_at       # DateTime(nullable)
```

Add `'checklists'` to `INSTALLED_APPS`.

**New FastAPI router: `backend/api/routers/checklists/`**

Endpoints:
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/checklists/templates/` | read | List templates (filterable) |
| POST | `/checklists/templates/` | admin | Create template |
| PUT | `/checklists/templates/{id}` | admin | Update template |
| DELETE | `/checklists/templates/{id}` | admin | Delete template |
| GET | `/checklists/` | read | List checklist instances (filterable by date, shift, status, operator) |
| POST | `/checklists/` | write | Start new checklist instance from template |
| GET | `/checklists/{id}` | read | Get instance with all item results |
| POST | `/checklists/{id}/items/{index}/submit` | write | Submit item result (image_id, status, notes) |
| POST | `/checklists/{id}/complete` | write | Mark checklist as completed |
| GET | `/checklists/compliance` | read | Compliance stats (completion rate by plant/shift over time) |

When an item with `auto_detect=true` is submitted with an image, trigger `auto_detect_image_task` and update `detection_count` on the item result.

### Frontend

**New page: `frontend/src/pages/Checklists.tsx`** (route: `/checklists`)

Three sub-views via tabs:

**"Active" tab (default — operator view):**
- Today's pending checklists for the current user
- Each card: template name, plant, shift, progress bar (X/Y items completed)
- Click → opens checklist execution view:
  - List of items with description, status indicator, photo slot
  - Click item → upload modal (reuse existing file input pattern) + notes field
  - Status selector per item: Passed / Failed / Flagged
  - "Complete Checklist" button when all required items done

**"Templates" tab (admin only):**
- CRUD table for templates
- Create/edit modal: name, plant, shift, items list (drag-to-reorder, add/remove, toggle required_photo and auto_detect per item)

**"Compliance" tab (manager view):**
- Date range selector
- Completion rate line chart (Recharts, same pattern as Analytics)
- Table: plant × shift matrix showing completion percentage (color-coded green/amber/red)
- Overdue list: checklists past their shift window without completion

**Sidebar:** Add nav item `{ icon: ClipboardCheck, label: 'Checklists', path: '/checklists' }` before Settings.

### Files to create/modify

| Action | File |
|--------|------|
| CREATE | `backend/checklists/models.py`, `admin.py`, `__init__.py` |
| CREATE | `backend/api/routers/checklists/endpoint.py`, `queries/checklists.py` |
| CREATE | `frontend/src/pages/Checklists.tsx` |
| MODIFY | `frontend/src/App.tsx` — route |
| MODIFY | `frontend/src/components/Layout/Sidebar.tsx` — nav item |
| MODIFY | `frontend/src/api/client.ts` — checklist API functions |
| MODIFY | `frontend/src/types/api.ts` — checklist types |
| MODIFY | `backend/backend/settings.py` — add checklists to INSTALLED_APPS |

### Verification
1. Admin creates template: "Conveyor Belt Inspection" with 3 items
2. Operator opens Checklists → sees today's pending checklist
3. Clicks through each item, uploads photo, marks pass/fail
4. Item with auto_detect enabled → detection runs, detection_count updates
5. Completes checklist → status changes, compliance stats update
6. Manager views compliance tab → sees completion rate chart

---

## Feature 6: Export & Reporting API

### What it does
Export media metadata, detections, search results, and analytics as CSV/JSON/PDF. Scheduled exports via Celery Beat + email.

### Backend

**New FastAPI router: `backend/api/routers/exports/`**

Endpoints:
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/exports/media` | read | Export media metadata (params: format=csv/json, filters) |
| POST | `/exports/detections` | read | Export detection data (params: format, filters) |
| POST | `/exports/search-results/{query_id}` | read | Export a search result set |
| POST | `/exports/analytics` | read | Export analytics summary as PDF |
| GET | `/exports/schedules/` | admin | List scheduled exports |
| POST | `/exports/schedules/` | admin | Create scheduled export |
| DELETE | `/exports/schedules/{id}` | admin | Delete scheduled export |

**Export logic:**
- CSV: Use Python `csv.writer` with `StreamingResponse`
- JSON: Direct serialization with `StreamingResponse`
- PDF: Reuse `reportlab` from Feature 2
- All exports are tenant-scoped and respect filters (plant, date range, label, tags)

**Scheduled exports:**

New model:
```python
class ExportSchedule(TenantScopedModel):
    name              # str
    export_type       # str (media/detections/analytics)
    format            # str (csv/json/pdf)
    filters           # JSONField
    schedule          # str (daily/weekly/monthly)
    email_recipients  # JSONField — list of email addresses
    is_active         # bool
    last_run_at       # DateTime(nullable)
```

Celery Beat task:
```python
@shared_task(name='exports:run_scheduled', queue='maintenance')
def run_scheduled_exports():
    # Query ExportSchedule where is_active=True and due
    # Generate export file
    # Send via email (SMTP)
```

Add to `celery_config.py` beat_schedule:
```python
'run-scheduled-exports': {
    'task': 'exports:run_scheduled',
    'schedule': crontab(minute=0, hour=6),  # daily at 6am
}
```

**Email utility:** `backend/infrastructure/email.py` — simple SMTP sender using `smtplib` + env vars (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`).

### Frontend

**Export buttons added to existing pages:**
- Media Library: "Export" button in toolbar → opens format selector (CSV/JSON) → downloads
- Search results: "Export Results" button → exports current results as CSV/JSON
- Analytics: "Export PDF" button → downloads analytics summary

**Settings page extension:** New "Scheduled Exports" card:
- List of scheduled exports with name, type, format, schedule, recipients, last run
- Create/delete scheduled exports
- Email recipients input (comma-separated)

### Files to create/modify

| Action | File |
|--------|------|
| CREATE | `backend/api/routers/exports/endpoint.py`, `queries/exports.py` |
| CREATE | `backend/infrastructure/email.py` |
| MODIFY | `backend/embeddings/config/celery_config.py` — beat schedule |
| MODIFY | `frontend/src/pages/MediaLibrary.tsx` — export button |
| MODIFY | `frontend/src/pages/Search.tsx` — export button |
| MODIFY | `frontend/src/pages/Analytics.tsx` — export button |
| MODIFY | `frontend/src/pages/Settings.tsx` — scheduled exports section |
| MODIFY | `frontend/src/api/client.ts` — export API functions |
| MODIFY | `frontend/src/types/api.ts` — export types |

### Verification
1. Open Media Library → click "Export" → select CSV → file downloads with all filtered images
2. Run a search → click "Export Results" → CSV downloads with result data
3. Admin creates scheduled export: detections, CSV, weekly, email to manager@plant.com
4. Celery Beat fires at 6am → email sent with CSV attachment

---

## Feature 7: Multi-User Collaboration & Activity Feed

### What it does
Comment on detections/images. Assign detections to team members. @mention users. Rich activity feed on dashboard. "My Assignments" tracker.

### Backend

**New Django app: `collaboration`**
```
backend/collaboration/
├── __init__.py
├── models.py
├── admin.py
└── migrations/
```

**Models:**
```python
class Comment(TenantScopedModel):
    content_type      # str ('image' | 'detection' | 'video')
    object_id         # int (FK to the referenced object)
    author            # FK(User)
    text              # TextField
    mentions          # JSONField — list of user IDs mentioned
    created_at        # DateTime
    updated_at        # DateTime

class Assignment(TenantScopedModel):
    detection         # FK(Detection)
    assigned_to       # FK(User, related_name='assignments')
    assigned_by       # FK(User)
    status            # str (open/in_progress/resolved/wont_fix)
    priority          # str (low/medium/high/critical)
    due_date          # DateField(nullable)
    notes             # TextField(nullable)
    resolved_at       # DateTime(nullable)
    created_at        # DateTime

class ActivityEvent(TenantScopedModel):
    user              # FK(User)
    action            # str (uploaded/detected/commented/assigned/resolved/acknowledged)
    target_type       # str (image/detection/video/checklist/alert)
    target_id         # int
    metadata          # JSONField — action-specific context
    created_at        # DateTime
```

Add `'collaboration'` to `INSTALLED_APPS`.

**New FastAPI router: `backend/api/routers/collaboration/`**

Endpoints:
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/collaboration/comments` | read | List comments for a target (params: content_type, object_id) |
| POST | `/collaboration/comments` | write | Create comment (triggers ActivityEvent) |
| DELETE | `/collaboration/comments/{id}` | write | Delete own comment |
| GET | `/collaboration/assignments/` | read | List assignments (filterable: assigned_to, status, priority) |
| GET | `/collaboration/assignments/mine` | read | Current user's assignments |
| POST | `/collaboration/assignments/` | write | Create assignment |
| PATCH | `/collaboration/assignments/{id}` | write | Update status/priority |
| GET | `/collaboration/activity/` | read | Activity feed (paginated, filterable by action type) |
| GET | `/collaboration/users/` | read | List tenant members (for @mention autocomplete) |

**ActivityEvent creation:** Hook into key actions:
- Image upload → `action='uploaded', target_type='image'`
- Detection created → `action='detected', target_type='detection'`
- Comment posted → `action='commented', target_type=content_type`
- Assignment created → `action='assigned', target_type='detection'`
- Assignment resolved → `action='resolved', target_type='detection'`
- Alert acknowledged → `action='acknowledged', target_type='alert'`

Use signals or explicit calls in existing endpoints.

### Frontend

**Dashboard overhaul: `frontend/src/pages/Dashboard.tsx`**

Replace basic activity feed with rich activity feed:
- Each event: avatar, "User X [action] [target]", relative time
- Clickable targets (link to detail pages)
- Filter by action type

Add "My Assignments" widget:
- List of assigned detections with: crop thumbnail, label, priority badge, due date
- Click → detection detail page
- "Resolve" quick action button

**Comments on detail pages:**

Add comments section to `ImageDetail.tsx` and `DetectionDetail.tsx`:
- Thread of comments with author avatar, name, text, timestamp
- Input area with @mention autocomplete (dropdown of tenant users)
- Delete button on own comments

**"Assign" button on detection cards:**

Add to `DetectionDetail.tsx` actions:
- Opens modal: user picker (dropdown of tenant members), priority selector, optional due date, notes
- Creates assignment

### Files to create/modify

| Action | File |
|--------|------|
| CREATE | `backend/collaboration/models.py`, `admin.py`, `__init__.py` |
| CREATE | `backend/api/routers/collaboration/endpoint.py`, `queries/collaboration.py` |
| CREATE | `frontend/src/components/CommentThread.tsx` |
| CREATE | `frontend/src/components/AssignModal.tsx` |
| MODIFY | `frontend/src/pages/Dashboard.tsx` — rich activity feed, assignments widget |
| MODIFY | `frontend/src/pages/ImageDetail.tsx` — comments section |
| MODIFY | `frontend/src/pages/DetectionDetail.tsx` — comments + assign button |
| MODIFY | `frontend/src/App.tsx` — (no new route needed, embedded in existing pages) |
| MODIFY | `frontend/src/api/client.ts` — collaboration API functions |
| MODIFY | `frontend/src/types/api.ts` — Comment, Assignment, ActivityEvent types |
| MODIFY | `backend/backend/settings.py` — add collaboration to INSTALLED_APPS |

### Verification
1. Open detection detail → write comment "Check this @john" → comment appears, @john highlighted
2. Click "Assign" → select user, set priority high → assignment created
3. Assigned user opens Dashboard → "My Assignments" shows the detection
4. User clicks "Resolve" → status updates, activity event logged
5. Activity feed shows: "Jane assigned 'rust' detection to John"

---

## Implementation Order (Sequential Phases)

| Phase | Feature | Est. Effort | Dependencies |
|-------|---------|-------------|--------------|
| A | 1. Real-Time Alerts | Large | New Django app, WebSocket, Redis pub/sub |
| B | 2. Shift Handoff Report | Medium | Alert data (from Phase A) enriches reports |
| C | 3. Defect Trends & Anomalies | Medium | Detection data only, extends existing analytics |
| D | 4. Side-by-Side Comparison | Small-Medium | Frontend only, no backend changes |
| E | 5. Inspection Checklists | Large | New Django app, new page, upload integration |
| F | 6. Export & Reporting API | Medium | Reuses reportlab from Phase B, adds email infra |
| G | 7. Multi-User Collaboration | Large | New Django app, touches many existing pages |

**Phases A-C** are the highest-impact trio — they create the "safety intelligence" layer.
**Phase D** is a quick win between the larger phases.
**Phases E-G** are enterprise features that drive adoption at scale.

---

## Global Verification

After all 7 features, the full workflow:
1. Operator starts morning shift → opens **Checklists** → completes inspection items with photos
2. Auto-detection runs on uploaded photos → finds "crack" at 92% confidence
3. **Alert** fires → WebSocket pushes notification to supervisor's browser in real-time
4. Supervisor opens alert → clicks detection → adds **comment** "Maintenance needed" → **assigns** to maintenance team
5. Maintenance opens **Dashboard** → sees assignment → clicks through to detection → uses **Compare** to compare with last month's photo of same location
6. Shift ends → supervisor opens **Reports** → reviews shift summary → downloads PDF for plant manager
7. Plant manager opens **Analytics** → Trends tab shows "crack" detections trending up at this plant → **Anomaly** card confirms it's statistically significant
8. Weekly **scheduled export** emails CSV of all detections to compliance team
