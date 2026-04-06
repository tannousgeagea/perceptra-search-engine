# Wire Dashboard to Real Data

## Context

The dashboard has 4 stat cards, 2 charts, and 2 panels. The stat cards and 2 charts partially use real API data (with fallbacks), but **2 sections are 100% hardcoded mock** and several real-data sections have issues:

| Section | Current State | Issue |
|---------|--------------|-------|
| Stat cards (4) | Real API | Trend indicators are hardcoded ("+12%", "24 this shift", "-8ms") |
| Search Volume chart | **100% mock** `MOCK_VOLUME` | No time-series endpoint exists |
| Defect Distribution chart | Real w/ fallback | Works if `top_labels` returned; color cycling from mock palette |
| Plant Breakdown chart | Real w/ fallback | `defects` column is faked as `count * 0.32` |
| Recent Activity feed | **100% mock** `MOCK_ACTIVITY` | No activity/audit endpoint exists |
| **Backend/Frontend field mismatch** | — | Backend returns `detections_by_label`, frontend expects `top_labels` / `plant_breakdown` — these fields don't exist in backend response |

---

## Plan

### 1. Backend: Enhance `/api/v1/media/stats` endpoint

**File:** `backend/media/services.py` — `get_media_stats()`

Add two new data sections to the response:

**a) `top_labels`** — already returned as `detections_by_label`, just needs renaming in the response and schema to match frontend type. Maps `[{label, count}]`.

**b) `plant_breakdown`** — new query, group images by `plant_site`:
```python
plant_breakdown = list(
    Image.objects.filter(tenant=self.tenant)
    .exclude(plant_site='')
    .values('plant_site')
    .annotate(
        total=Count('id'),
        detections=Count('id', filter=Q(detections__isnull=False)),
    )
    .order_by('-total')[:10]
)
```

This gives real detection counts per plant instead of the `count * 0.32` hack.

**File:** `backend/api/routers/media/schemas.py` — `MediaStatsResponse`

Add fields: `top_labels`, `plant_breakdown` (with proper typed sub-schemas).

**File:** `backend/api/routers/media/queries/media.py` — wire the new fields in the endpoint response.

### 2. Backend: New `/api/v1/search/stats/volume` endpoint

**File:** `backend/api/routers/search/queries/search.py`

New endpoint returning daily search counts for the last 7 days, queried from `SearchQuery` model (has `created_at` indexed on `[tenant, created_at]`):

```python
@router.get("/stats/volume")
async def get_search_volume(ctx, days: int = 7):
    # Group SearchQuery by date for last N days
    # Return: [{date: "2026-03-17", searches: 42, detections: 28}, ...]
```

`detections` count = searches where `results_count > 0` (or queries with `query_type` filtering — depends on preference).

**New schema:** `SearchVolumeDay` with `date`, `searches`, `detections` fields.

### 3. Backend: New `/api/v1/search/stats/activity` endpoint

**File:** `backend/api/routers/search/queries/search.py`

New endpoint returning recent activity (searches + uploads combined), queried from `SearchQuery` + `Image` + `Video` models:

```python
@router.get("/stats/activity")
async def get_recent_activity(ctx, limit: int = 10):
    # Fetch recent SearchQuery entries + recent Image/Video uploads
    # Merge, sort by created_at desc, return top N
    # Return: [{type: "search"|"upload"|"detect", msg: "...", time: "2m ago", tag: "TEXT"}]
```

Uses `SearchQuery.query_type` to derive the tag (TEXT, IMAGE, HYBRID), and `Image`/`Video` uploads for UPLOAD entries. `Detection` creation events for DETECT entries. The `time` field is a relative time string computed from `created_at`.

**New schema:** `ActivityItem` with `type`, `msg`, `time`, `tag` fields.

### 4. Backend: Compute real stat card trends

**File:** `backend/api/routers/search/queries/search.py` — enhance `/stats` response

Add computed trend fields:
- **searches_yesterday** — compare today vs yesterday for trend
- **media_7d_trend** — compare this week vs last week upload count

**File:** `backend/media/services.py` — add `previous_period_uploads` (7-14 days ago) to compute % change.

### 5. Frontend: Add new API calls

**File:** `frontend/src/api/client.ts`

```typescript
export const getSearchVolume = (days?: number) =>
  api.get<SearchVolumeDay[]>('/v1/search/stats/volume', { params: { days } })

export const getRecentActivity = (limit?: number) =>
  api.get<ActivityItem[]>('/v1/search/stats/activity', { params: { limit } })
```

**File:** `frontend/src/types/api.ts`

Add types:
```typescript
export interface SearchVolumeDay {
  date: string
  searches: number
  detections: number
}

export interface ActivityItem {
  type: 'search' | 'upload' | 'detect'
  msg: string
  time: string
  tag: string
}
```

Update `MediaStats` to match backend fields (add `top_labels`, `plant_breakdown` with proper typing).

Update `SearchStatsResponse` to include trend fields.

### 6. Frontend: Wire Dashboard to real data

**File:** `frontend/src/pages/Dashboard.tsx`

**a) Search Volume chart** — Replace `MOCK_VOLUME` with `getSearchVolume()` API call on mount. Format dates as day names (Mon, Tue...).

**b) Recent Activity** — Replace `MOCK_ACTIVITY` with `getRecentActivity()` API call on mount.

**c) Stat card trends** — Replace hardcoded "+12%", "24 this shift", "-8ms" with computed values from enhanced stats responses.

**d) Plant Breakdown** — Use real `detections` count from new `plant_breakdown` field instead of `count * 0.32`.

**e) Remove mock constants** — Delete `MOCK_VOLUME`, `MOCK_ACTIVITY`, `MOCK_PLANTS`, `MOCK_DEFECTS` (keep defect colors as a palette).

---

## Files to Modify

| File | Change |
|------|--------|
| `backend/media/services.py` | Add `top_labels`, `plant_breakdown` (with real detection counts) to `get_media_stats()` |
| `backend/api/routers/media/schemas.py` | Add `top_labels`, `plant_breakdown` fields to `MediaStatsResponse` |
| `backend/api/routers/media/queries/media.py` | Wire new fields in stats endpoint response |
| `backend/api/routers/search/queries/search.py` | Add `/stats/volume` and `/stats/activity` endpoints; enhance `/stats` with trend data |
| `backend/api/routers/search/schemas.py` | Add `SearchVolumeDay`, `ActivityItem` schemas; add trend fields to `SearchStatsResponse` |
| `frontend/src/types/api.ts` | Add `SearchVolumeDay`, `ActivityItem` types; update `MediaStats` and `SearchStatsResponse` |
| `frontend/src/api/client.ts` | Add `getSearchVolume()`, `getRecentActivity()` calls |
| `frontend/src/pages/Dashboard.tsx` | Wire all charts/panels to real API data, remove mock constants |

---

## Verification

1. **Stat cards:** Values match real DB counts; trends show computed deltas (not hardcoded)
2. **Search Volume chart:** Shows actual search counts per day for last 7 days from `SearchQuery` table
3. **Defect Distribution:** Shows real `detections_by_label` data with no fallback needed
4. **Plant Breakdown:** Shows real image + detection counts per plant_site (no `* 0.32` hack)
5. **Recent Activity:** Shows real recent searches and uploads with relative timestamps
6. **Empty state:** When no data exists (fresh install), charts show empty/zero gracefully — no mock data displayed
7. **Swagger:** New endpoints `/search/stats/volume` and `/search/stats/activity` visible at `/docs`