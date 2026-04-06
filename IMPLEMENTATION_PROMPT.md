# Implementation Prompt for Advanced Features

Copy everything below this line and paste it as the first message to a new Claude Code session in this project directory.

---

You are implementing 7 advanced features for an industrial inspection search engine platform. The full implementation plan is in `ADVANCED_FEATURE_IMPLEMENTATION_PLAN.md` at the project root. Read it fully before starting.

## Your Role

You are a senior full-stack engineer implementing these features. You must:
- Follow existing codebase patterns exactly (read CLAUDE.md first)
- Write production-quality code — no placeholders, no TODOs, no stubs
- Implement both backend AND frontend for each feature
- Test that the TypeScript compiles (`tsc -b`) before moving to the next feature
- Commit after each feature is fully working

## What Already Exists

This platform has a complete core pipeline. Before writing ANY code, read these files to understand the patterns:

**Backend patterns (read these first):**
- `CLAUDE.md` — Architecture overview, async/sync rules, router patterns, all conventions
- `backend/api/routers/hazard_config/queries/hazard_config.py` — The most recently built CRUD router. Follow this exact pattern for new routers (schemas inline or in schemas.py, async endpoints, sync_to_async for ORM, permission checks, response builders)
- `backend/api/routers/media/queries/bulk.py` — Bulk operations pattern (recently built)
- `backend/embeddings/signals.py` — Post-save signal pattern for triggering tasks
- `backend/embeddings/tasks/auto_detection.py` — Celery task pattern
- `backend/embeddings/config/celery_config.py` — Queue configuration and Beat schedule
- `backend/media/models.py` — All media models (Image, Video, Detection, Tag)
- `supervisord.conf` — Running processes

**Frontend patterns (read these):**
- `frontend/src/pages/Analytics.tsx` — Charts with Recharts, KPI cards, data fetching pattern
- `frontend/src/pages/HazardConfig.tsx` — Full CRUD page with modals, recently built
- `frontend/src/pages/MediaLibrary.tsx` — Complex page with tabs, grid/list views, bulk selection, modals
- `frontend/src/components/ConfirmModal.tsx` — Reusable modal pattern
- `frontend/src/components/BulkActionBar.tsx` — Fixed-position floating bar pattern
- `frontend/src/components/Layout/Sidebar.tsx` — Navigation items (add new nav items here)
- `frontend/src/components/Layout/AppLayout.tsx` — Top bar layout (add notification bell here)
- `frontend/src/context/AuthContext.tsx` — Global context pattern (follow for AlertContext, CompareContext)
- `frontend/src/hooks/useSelection.ts` — Custom hook pattern
- `frontend/src/api/client.ts` — All API functions (add new ones here)
- `frontend/src/types/api.ts` — All TypeScript types (add new ones here)
- `frontend/src/App.tsx` — Route registration
- `frontend/src/index.css` — Design tokens (CSS variables for colors, fonts, spacing)

## Implementation Order

Implement features in this exact order. Each phase builds on the previous:

### Phase A: Real-Time Defect Alert System (Feature 1)
**Backend:**
1. Create `backend/alerts/` Django app with `Alert` and `AlertRule` models
2. Add `'alerts'` to INSTALLED_APPS, run makemigrations + migrate
3. Create `backend/api/routers/alerts/` router (follow hazard_config pattern) with 8 endpoints
4. Create `backend/embeddings/tasks/alert_check.py` — Celery task that checks detection against alert rules
5. Add Detection post_save signal in `signals.py` to trigger alert check
6. Create `backend/infrastructure/pubsub.py` — Redis pub/sub wrapper
7. Create WebSocket endpoint at `backend/api/routers/alerts/queries/websocket.py`
8. Add `alerts` queue to celery_config.py

**Frontend:**
1. Add Alert, AlertRule types to `types/api.ts`
2. Add alert API functions to `client.ts` (getAlerts, getUnreadCount, acknowledgeAlert, etc.)
3. Create `context/AlertContext.tsx` — WebSocket connection, unread count, recent alerts
4. Create `components/AlertPanel.tsx` — Sliding drawer with alert list and acknowledge buttons
5. Modify `components/Layout/AppLayout.tsx` — Add bell icon with badge in top bar
6. Create `pages/Alerts.tsx` — Full alert history + alert rule management
7. Modify `App.tsx` — Add AlertProvider wrapper + `/alerts` route
8. Modify `components/Layout/Sidebar.tsx` — Add Alerts nav item
9. Modify `pages/Dashboard.tsx` — Add "Active Alerts" stat card

### Phase B: Shift Handoff Report (Feature 2)
**Backend:**
1. Create `backend/api/routers/reports/` router with 3 endpoints
2. Add `reportlab` to Dockerfile/requirements
3. Implement shift summary query logic (filter by shift time window + plant)
4. Implement PDF generation with reportlab

**Frontend:**
1. Add ShiftSummary types to `types/api.ts`
2. Add report API functions to `client.ts`
3. Create `pages/Reports.tsx` — Shift selector + date + plant filter, KPI cards with deltas, detection chart, high-severity grid, PDF download button
4. Modify `App.tsx` — Add `/reports` route
5. Modify Sidebar — Add Reports nav item
6. Modify Dashboard — Add "Generate Shift Report" quick action

### Phase C: Defect Trend Analytics & Anomaly Detection (Feature 3)
**Backend:**
1. Add 3 new endpoints to `backend/api/routers/search/queries/search.py`: trends, anomalies, heatmap
2. Add trend/anomaly schemas to `search/schemas.py`
3. Implement Z-score anomaly detection (no ML, pure statistics)

**Frontend:**
1. Add trend/anomaly types to `types/api.ts`
2. Add API functions to `client.ts`
3. Modify `pages/Analytics.tsx` — Add tab bar (Overview/Trends/Anomalies), multi-series LineChart, anomaly cards with sparklines, label×plant heatmap
4. Modify `pages/Dashboard.tsx` — Add anomaly summary widget

### Phase D: Side-by-Side Comparison (Feature 4)
**Frontend only (no backend changes):**
1. Create `context/CompareContext.tsx` — Comparison tray state (max 4 items), sessionStorage persistence
2. Create `components/CompareTray.tsx` — Fixed bottom bar with thumbnails + "Compare" button
3. Create `pages/Compare.tsx` — Synchronized zoom/pan grid, overlay mode with opacity slider, detection overlay toggle
4. Modify `App.tsx` — Add CompareProvider + `/compare` route
5. Add "Add to Compare" button to: Search result cards, MediaLibrary cards, ImageDetail, DetectionDetail
6. Modify Sidebar — Add Compare nav item

### Phase E: Inspection Checklists (Feature 5)
**Backend:**
1. Create `backend/checklists/` Django app with ChecklistTemplate, ChecklistInstance, ChecklistItemResult models
2. Add to INSTALLED_APPS, run migrations
3. Create `backend/api/routers/checklists/` router with 10 endpoints
4. Wire auto-detect trigger on item submission

**Frontend:**
1. Add checklist types to `types/api.ts`
2. Add API functions to `client.ts`
3. Create `pages/Checklists.tsx` — 3 tabs (Active/Templates/Compliance), checklist execution view with photo upload, template CRUD, compliance charts
4. Modify `App.tsx` + Sidebar

### Phase F: Export & Reporting API (Feature 6)
**Backend:**
1. Create `backend/api/routers/exports/` router with 7 endpoints
2. Create `backend/infrastructure/email.py` — SMTP sender
3. Add ExportSchedule model + Celery Beat task for scheduled exports
4. Implement CSV/JSON/PDF streaming exports

**Frontend:**
1. Add "Export" buttons to MediaLibrary, Search, Analytics pages
2. Add "Scheduled Exports" section to Settings page

### Phase G: Multi-User Collaboration (Feature 7)
**Backend:**
1. Create `backend/collaboration/` Django app with Comment, Assignment, ActivityEvent models
2. Add to INSTALLED_APPS, run migrations
3. Create `backend/api/routers/collaboration/` router with 9 endpoints
4. Hook ActivityEvent creation into existing upload/detection/alert signals

**Frontend:**
1. Create `components/CommentThread.tsx` — Threaded comments with @mention
2. Create `components/AssignModal.tsx` — User picker + priority + due date
3. Modify `pages/Dashboard.tsx` — Rich activity feed, "My Assignments" widget
4. Modify `pages/ImageDetail.tsx` + `pages/DetectionDetail.tsx` — Comments section + Assign button

## Critical Rules

1. **Never break existing functionality.** Read before modifying.
2. **Follow the async/sync boundary rules** from CLAUDE.md — always use `sync_to_async` for Django ORM in FastAPI handlers.
3. **Router auto-discovery** — new routers in `backend/api/routers/{name}/` with `endpoint.py` are auto-discovered. No changes to `main.py` needed.
4. **Celery task naming** — use `{queue}:{task_name}` format (e.g., `alerts:check_detection`). The router in celery_config.py auto-routes by queue prefix.
5. **Frontend styling** — use inline styles with CSS variables from `index.css`. Follow existing patterns (card classes, badge classes, btn classes). No new CSS files.
6. **TypeScript strict mode** — all types must be defined. Run `tsc -b` to verify before committing.
7. **Permissions** — use `require_permission('read')`, `require_permission('write')`, or `require_permission('admin')` on every endpoint.
8. **Tenant scoping** — every DB query must filter by `tenant=ctx.tenant`. Never return data from other tenants.
9. **After creating Django models** — run `docker compose exec search-engine python manage.py makemigrations {app}` then `docker compose exec search-engine python manage.py migrate`.
10. **After frontend changes** — rebuild with `docker compose up --build frontend -d` and verify no TypeScript errors.

## How to Verify Each Feature

After implementing each phase, verify it works end-to-end:
- Backend: Check the endpoint returns correct data (use Swagger at localhost:8000/docs)
- Frontend: Check the page renders, interactions work, and data flows correctly
- Integration: Check the full workflow (e.g., detection → alert → bell notification → acknowledge)

Start by reading `CLAUDE.md` and `ADVANCED_FEATURE_IMPLEMENTATION_PLAN.md`, then begin Phase A.
