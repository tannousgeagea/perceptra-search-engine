# Phase 3.2: Bulk Operations for Media Library

## Context

The Media Library currently supports only single-item operations (delete one image, delete one video). Managing large inspection datasets one item at a time is impractical. This plan adds multi-select with bulk delete, bulk tag, and bulk run-detection. The hazard detection endpoint (`POST /hazard-configs/{config_id}/run`) already exists and accepts `image_ids[]`.

---

## Architecture

```
User selects items (checkboxes on cards/rows)
  -> BulkActionBar appears at bottom of viewport
  -> User clicks action (Delete / Tag / Run Detection)
  -> ConfirmModal with summary + confirmation
  -> Frontend calls bulk API endpoint
  -> Backend processes in transaction, returns count
  -> Frontend clears selection, refreshes list
```

---

## Step 1: Backend — Bulk Endpoints

### Modify: `backend/api/routers/media/schemas.py`

Add request/response schemas:

```python
class BulkDeleteRequest(BaseModel):
    ids: List[int] = Field(..., min_length=1, max_length=500)

class BulkDeleteResponse(BaseModel):
    deleted: int
    failed: int = 0

class BulkTagRequest(BaseModel):
    ids: List[int] = Field(..., min_length=1, max_length=500)
    tag_names: List[str] = Field(..., min_length=1)
    action: str = Field(..., pattern='^(add|remove)$')

class BulkTagResponse(BaseModel):
    updated: int
    tags: List[str]
```

### Create: `backend/api/routers/media/queries/bulk.py`

Auto-discovered by existing `endpoint.py` router scanner. 6 endpoints:

| Method | Path | Action |
|--------|------|--------|
| POST | `/media/images/bulk-delete` | Delete multiple images (cascades to detections) |
| POST | `/media/videos/bulk-delete` | Delete multiple videos (cascades to frames+detections) |
| POST | `/media/detections/bulk-delete` | Delete multiple detections |
| POST | `/media/images/bulk-tag` | Add/remove tags on multiple images |
| POST | `/media/videos/bulk-tag` | Add/remove tags on multiple videos |
| POST | `/media/detections/bulk-tag` | Add/remove tags on multiple detections |

Implementation pattern (follows existing `delete_video` at line 497 of `media.py`):
- Require `write` permission (via `require_permission('write')`)
- Scope to tenant: `Model.objects.filter(id__in=ids, tenant=ctx.tenant)`
- Delete storage files first (collect failures, don't rollback DB)
- Delete ORM objects in transaction via `sync_to_async`
- Return count of deleted/updated items
- Handle `DoesNotExist` gracefully (skip, don't error)

For bulk tag:
- `action="add"`: get-or-create `Tag` per name (scoped to tenant), then bulk-create through-table rows ignoring conflicts
- `action="remove"`: delete matching through-table rows

---

## Step 2: Frontend — API Client

### Modify: `frontend/src/api/client.ts`

Add 6 functions after existing `deleteImage`/`deleteVideo`:

```typescript
export const bulkDeleteImages = (ids: number[]) =>
  api.post<{ deleted: number }>('/v1/media/images/bulk-delete', { ids })
export const bulkDeleteVideos = (ids: number[]) =>
  api.post<{ deleted: number }>('/v1/media/videos/bulk-delete', { ids })
export const bulkDeleteDetections = (ids: number[]) =>
  api.post<{ deleted: number }>('/v1/media/detections/bulk-delete', { ids })
export const bulkTagImages = (ids: number[], tag_names: string[], action: 'add' | 'remove') =>
  api.post('/v1/media/images/bulk-tag', { ids, tag_names, action })
export const bulkTagVideos = (ids: number[], tag_names: string[], action: 'add' | 'remove') =>
  api.post('/v1/media/videos/bulk-tag', { ids, tag_names, action })
export const bulkTagDetections = (ids: number[], tag_names: string[], action: 'add' | 'remove') =>
  api.post('/v1/media/detections/bulk-tag', { ids, tag_names, action })
```

---

## Step 3: Frontend — Selection Hook

### Create: `frontend/src/hooks/useSelection.ts`

```typescript
export function useSelection() {
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  return {
    selectedIds,
    count: selectedIds.size,
    toggle(id: number) { ... },
    selectAll(items: { id: number }[]) { ... },
    deselectAll() { ... },
    isSelected(id: number): boolean { ... },
    isAllSelected(items: { id: number }[]): boolean { ... },
  }
}
```

Page-scoped: selection covers the current visible page only. Clears on tab/page change.

---

## Step 4: Frontend — UI Components

### Create: `frontend/src/components/BulkActionBar.tsx`

Fixed-position bar at bottom of viewport. Appears when `selection.count > 0`.

```
┌─────────────────────────────────────────────────────────────┐
│  ✓ 5 selected     [🗑 Delete]  [🏷 Tag]  [⚡ Detect]  [✕] │
└─────────────────────────────────────────────────────────────┘
```

Props: `count`, `tab`, `onDelete`, `onTag`, `onRunDetection?`, `onDeselectAll`

- "Run Detection" only shown when `tab === 'images'`
- Buttons use existing `btn btn-danger btn-sm`, `btn btn-secondary btn-sm` classes
- Count uses amber badge
- Animate in with `fadeUp`

### Create: `frontend/src/components/ConfirmModal.tsx`

Reusable confirmation modal (danger or primary variant). Follows existing modal patterns (overlay + panel).

Props: `open`, `title`, `description`, `confirmLabel`, `confirmVariant`, `loading`, `onConfirm`, `onCancel`

### Bulk Tag Modal (inline in MediaLibrary or separate component)

When "Tag" is clicked:
- Fetch available tags via `getTags()`
- Show tag chips to toggle (same pattern as Search page tag filter)
- Text input to type new tag name
- "Add Tags" / "Remove Tags" toggle
- Confirm button calls `bulkTag*(ids, tagNames, action)`

### Bulk Detect Modal (inline in MediaLibrary)

When "Run Detection" is clicked (images tab only):
- Fetch hazard configs via `getHazardConfigs()`
- Show config picker (name + prompt count)
- Confirm calls `runDetection(configId, { image_ids })`
- Already exists in backend — just needs frontend modal

---

## Step 5: Frontend — Wire into MediaLibrary.tsx

### Modify: `frontend/src/pages/MediaLibrary.tsx`

1. **Imports**: Add `useSelection`, `BulkActionBar`, `ConfirmModal`, bulk API functions, `CheckSquare`/`Square` icons

2. **State**: Add `selection = useSelection()`, `confirmAction` state, `bulkLoading` state

3. **Clear on tab/page change**: Call `selection.deselectAll()` in tab switch and pagination handlers

4. **Select All checkbox**: Add in the toolbar area (above grid/table), toggles `selectAll`/`deselectAll`

5. **Checkboxes on grid cards**:
   - Top-left corner overlay on `.media-thumbnail` for all three tabs
   - `onClick stopPropagation` so it doesn't trigger modal/navigation
   - Visual: `CheckSquare` (amber) when selected, `Square` (muted) when not
   - Card gets amber outline when selected

6. **Checkboxes on list rows**:
   - New first `<th>/<td>` column with checkbox
   - Row highlight (amber border-left or background tint) when selected

7. **Render BulkActionBar**: At component bottom, conditional on `selection.count > 0`

8. **Render modals**: ConfirmModal for delete, TagModal for tagging, DetectModal for hazard detection

9. **Bottom padding**: Add `paddingBottom: 80px` when bar is visible so pagination isn't hidden

---

## File Summary

| Action | File | What |
|--------|------|------|
| MODIFY | `backend/api/routers/media/schemas.py` | Add BulkDeleteRequest/Response, BulkTagRequest/Response |
| CREATE | `backend/api/routers/media/queries/bulk.py` | 6 bulk endpoints (auto-discovered) |
| MODIFY | `frontend/src/api/client.ts` | Add 6 bulk API functions |
| CREATE | `frontend/src/hooks/useSelection.ts` | Selection state hook |
| CREATE | `frontend/src/components/BulkActionBar.tsx` | Floating action bar |
| CREATE | `frontend/src/components/ConfirmModal.tsx` | Reusable confirmation modal |
| MODIFY | `frontend/src/pages/MediaLibrary.tsx` | Wire selection, checkboxes, bar, modals |

---

## Implementation Order

1. Backend schemas + bulk endpoints (independent, can be tested with curl)
2. Frontend API client functions
3. `useSelection` hook + `ConfirmModal` + `BulkActionBar` (independent components)
4. MediaLibrary integration (depends on all above)

---

## Verification

1. **Bulk delete**: Select 3 images in grid view → click Delete → confirm → images gone, count updated
2. **Bulk tag**: Select 2 videos in list view → click Tag → add "defect" tag → confirm → tags visible on items
3. **Bulk detect**: Select 5 images → click "Run Detection" → pick hazard config → confirm → jobs appear in Hazard Config page
4. **Select all**: Click select-all checkbox → all 20 items on page selected → action bar shows "20 selected"
5. **Tab switch clears**: Select items on images tab → switch to videos tab → selection cleared
6. **Grid + list**: Checkboxes work in both view modes
7. **Permission**: Non-admin user attempting bulk delete → 403