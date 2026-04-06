# Auth Session Info — Dedicated Validation Endpoint + Frontend Display

## Context

**Problem:** After login (both API key and JWT), the frontend has almost no useful session info. Roles are hardcoded as "INSPECTOR" / "PLANT INSPECTOR", tenant name is not shown (only truncated UUID), and API key validation is done by hitting `/search/stats` as a proxy — which is fragile and returns no session context.

**Goal:**
1. Add a dedicated `GET /api/v1/auth/session` endpoint that works for **both** auth modes (JWT and API key) and returns user, tenant, role, and permissions info
2. Call this endpoint after login (both modes) and on app init
3. Display the real tenant name, user role, permissions in the Sidebar, Settings, and anywhere else relevant

---

## What's Wrong Today

| Issue | Where | Current | Should Be |
|-------|-------|---------|-----------|
| API key validation | `Login.tsx:47` | Calls `GET /search/stats` as proxy | Call `GET /auth/session` |
| JWT login — no session fetch | `Login.tsx:66-75` | Stores token + email, nothing else | Fetch session info after login |
| Role display in Sidebar | `Sidebar.tsx:221` | Hardcoded `INSPECTOR` | Real role from backend |
| Role display in Settings | `Settings.tsx:385` | Hardcoded `PLANT INSPECTOR` | Real role from backend |
| Tenant name | `Settings.tsx:416` | Only truncated UUID | Show tenant name |
| displayName | `AuthContext.tsx:52` | `email ?? apiKeyLabel ?? 'Inspector'` | User's actual name if available |
| No permissions shown | Settings profile card | Not shown | Show role + permissions |

---

## Current Flow (Before)

```
┌──────────────────────────────────────────────────────────────────────┐
│                     CURRENT API KEY LOGIN FLOW                       │
│                                                                      │
│  User enters API key                                                 │
│       │                                                              │
│       ▼                                                              │
│  localStorage.setItem('auth', {mode:'apikey', apiKey:'ise_...'})    │
│       │                                                              │
│       ▼                                                              │
│  validateAuth() → GET /api/v1/search/stats  ← WRONG ENDPOINT       │
│       │                                                              │
│       ├── 200 OK? → login(authData) → navigate('/dashboard')       │
│       │   (no tenant/role/permissions info returned)                 │
│       │                                                              │
│       └── 401? → "Invalid API key" error                            │
│                                                                      │
│  Result: Sidebar shows "INSPECTOR" (hardcoded), no tenant name       │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                     CURRENT JWT LOGIN FLOW                           │
│                                                                      │
│  User enters email + password                                        │
│       │                                                              │
│       ▼                                                              │
│  POST /api/v1/auth/token → {access, refresh}                        │
│       │                                                              │
│       ▼                                                              │
│  login({mode:'jwt', token, refreshToken, email})                    │
│       │                                                              │
│       ▼                                                              │
│  navigate('/dashboard')                                              │
│  (no session fetch — only email stored, no tenant/role info)        │
│                                                                      │
│  Result: Sidebar shows email, "INSPECTOR" (hardcoded)                │
└──────────────────────────────────────────────────────────────────────┘
```

---

## New Flow (After)

```
┌──────────────────────────────────────────────────────────────────────┐
│                     NEW API KEY LOGIN FLOW                           │
│                                                                      │
│  User enters API key                                                 │
│       │                                                              │
│       ▼                                                              │
│  localStorage.setItem('auth', {mode:'apikey', apiKey:'ise_...'})    │
│       │                                                              │
│       ▼                                                              │
│  GET /api/v1/auth/session  ← DEDICATED ENDPOINT                    │
│       │                                                              │
│       ├── 200 OK? → Returns:                                        │
│       │   {                                                          │
│       │     auth_method: "api_key",                                  │
│       │     role: "operator",                                        │
│       │     tenant: {name: "AGR Plant", slug: "agr", ...},          │
│       │     api_key: {name: "CI Key", permissions: "write", ...},   │
│       │     user: null                                               │
│       │   }                                                          │
│       │       │                                                      │
│       │       ▼                                                      │
│       │   Store session in AuthState                                 │
│       │   login(authData) → navigate('/dashboard')                  │
│       │                                                              │
│       └── 401? → "Invalid API key" error                            │
│                                                                      │
│  Result: Sidebar shows "OPERATOR", tenant "AGR Plant"                │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                     NEW JWT LOGIN FLOW                                │
│                                                                      │
│  User enters email + password                                        │
│       │                                                              │
│       ▼                                                              │
│  POST /api/v1/auth/token → {access, refresh}                        │
│       │                                                              │
│       ▼                                                              │
│  login({mode:'jwt', token, refreshToken, email})                    │
│       │                                                              │
│       ▼                                                              │
│  GET /api/v1/auth/session  ← FETCH SESSION INFO                    │
│       │                                                              │
│       ▼                                                              │
│  Returns:                                                            │
│  {                                                                   │
│    auth_method: "jwt",                                               │
│    role: "admin",                                                    │
│    tenant: {name: "AGR Plant", slug: "agr", ...},                   │
│    user: {id: 1, email: "admin@agr.com", name: "John Doe"},        │
│    api_key: null                                                     │
│  }                                                                   │
│       │                                                              │
│       ▼                                                              │
│  Store session in AuthState → navigate('/dashboard')                │
│                                                                      │
│  Result: Sidebar shows "John Doe", "ADMIN", tenant "AGR Plant"      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Session Endpoint Request/Response

```
GET /api/v1/auth/session
Headers:
  Authorization: Bearer <jwt>     ← JWT mode
  X-Tenant-ID: <uuid>            ← JWT mode (required)
  --- OR ---
  X-API-Key: ise_...              ← API key mode (tenant auto-resolved)

Response (JWT mode):
{
    "auth_method": "jwt",
    "role": "admin",
    "user": {
        "id": 1,
        "email": "admin@agr.com",
        "name": "John Doe",
        "is_active": true,
        "is_staff": false,
        "date_joined": "2026-01-15T10:00:00Z"
    },
    "tenant": {
        "id": "a1b2c3d4-...",
        "name": "AGR Plant",
        "slug": "agr-plant",
        "domain": "agr.example.com",
        "location": "Munich, Germany",
        "timezone": "Europe/Berlin"
    },
    "api_key": null
}

Response (API key mode):
{
    "auth_method": "api_key",
    "role": "operator",
    "user": null,
    "tenant": {
        "id": "a1b2c3d4-...",
        "name": "AGR Plant",
        "slug": "agr-plant",
        "domain": "agr.example.com",
        "location": "Munich, Germany",
        "timezone": "Europe/Berlin"
    },
    "api_key": {
        "name": "CI Pipeline Key",
        "key_prefix": "ise_abc12345",
        "permissions": "write",
        "expires_at": "2026-12-31T23:59:59Z"
    }
}
```

---

## Frontend UI Changes

### Sidebar (before vs after)

```
BEFORE:                              AFTER:
┌─────────────────────┐              ┌─────────────────────┐
│  ┌──┐                │              │  ┌──┐                │
│  │JD│ admin@agr.com  │              │  │JD│ John Doe       │
│  └──┘ INSPECTOR      │              │  └──┘ ADMIN          │
│                       │              │                       │
│  [Sign Out]           │              │  [Sign Out]           │
└─────────────────────┘              └─────────────────────┘
```

### Settings Profile Card (before vs after)

```
BEFORE:                              AFTER:
┌─────────────────────┐              ┌─────────────────────┐
│       ┌────┐         │              │       ┌────┐         │
│       │ JD │         │              │       │ JD │         │
│       └────┘         │              │       └────┘         │
│   admin@agr.com      │              │     John Doe         │
│   PLANT INSPECTOR    │              │     ADMIN            │
│                       │              │                       │
│  Auth Mode  [JWT]     │              │  Auth Mode   [JWT]   │
│  Tenant ID  a1b2c3.. │              │  Tenant      AGR Plnt│
│  Status     ONLINE    │              │  Role       [ADMIN]  │
│                       │              │  Location    Munich   │
└─────────────────────┘              │  Status      ONLINE   │
                                      │                       │
                                      │  (API key mode also   │
                                      │   shows: Permissions, │
                                      │   Key Name, Expires)  │
                                      └─────────────────────┘
```

---

## Implementation Plan

### Step 1: Backend — New `GET /api/v1/auth/session` endpoint

**File:** `backend/api/routers/auth/queries/auth.py`

Add three new Pydantic schemas and one new endpoint:

```python
class TenantInfo(BaseModel):
    id: str
    name: str
    slug: str
    domain: str
    location: str
    timezone: str

class ApiKeyInfo(BaseModel):
    name: str
    key_prefix: str
    permissions: str          # 'read', 'write', 'admin'
    expires_at: Optional[datetime]

class SessionResponse(BaseModel):
    auth_method: str          # 'jwt' or 'api_key'
    role: str                 # 'admin', 'operator', 'viewer'
    user: Optional[UserProfileResponse]
    tenant: TenantInfo
    api_key: Optional[ApiKeyInfo]
```

```python
@router.get("/session", response_model=SessionResponse)
async def get_session(ctx: RequestContext = Depends(get_request_context)):
    """Return current session info. Works with both JWT and API key auth."""
    tenant = ctx.tenant
    tenant_info = TenantInfo(
        id=str(tenant.tenant_id),
        name=tenant.name,
        slug=tenant.slug,
        domain=tenant.domain or "",
        location=tenant.location or "",
        timezone=tenant.timezone or "UTC",
    )

    user_info = None
    if ctx.user:
        user_info = UserProfileResponse.model_validate(ctx.user)

    api_key_info = None
    if ctx.api_key:
        api_key_info = ApiKeyInfo(
            name=ctx.api_key.name,
            key_prefix=ctx.api_key.key_prefix,
            permissions=ctx.api_key.permissions,
            expires_at=ctx.api_key.expires_at,
        )

    return SessionResponse(
        auth_method=ctx.auth_method,
        role=ctx.role,
        user=user_info,
        tenant=tenant_info,
        api_key=api_key_info,
    )
```

**Import additions:** `get_request_context` from `api.dependencies`, `RequestContext` from `tenants.context`.

### Step 2: Frontend — Add TypeScript types

**File:** `frontend/src/types/api.ts`

```typescript
export interface TenantInfo {
  id: string
  name: string
  slug: string
  domain: string
  location: string
  timezone: string
}

export interface ApiKeySessionInfo {
  name: string
  key_prefix: string
  permissions: string
  expires_at: string | null
}

export interface SessionInfo {
  auth_method: 'jwt' | 'api_key'
  role: string
  user: {
    id: number
    email: string
    name: string | null
    is_active: boolean
    is_staff: boolean
    date_joined: string
  } | null
  tenant: TenantInfo
  api_key: ApiKeySessionInfo | null
}
```

Add `session?: SessionInfo` field to existing `AuthState` interface.

### Step 3: Frontend — Add `getSession` API call

**File:** `frontend/src/api/client.ts`

```typescript
export const getSession = () =>
  api.get<SessionInfo>('/v1/auth/session')

// Update validateAuth to use the new endpoint
export const validateAuth = () => getSession()
```

### Step 4: Frontend — Update `AuthContext`

**File:** `frontend/src/context/AuthContext.tsx`

- Add `session: SessionInfo | null` to state
- Add `fetchSession()` async function that calls `getSession()` and updates state + localStorage
- Update `displayName` derivation:
  ```
  session?.user?.name ?? session?.user?.email ?? auth?.email ?? auth?.apiKeyLabel ?? 'Inspector'
  ```
- On mount, if `auth` exists in localStorage, call `fetchSession()` to refresh

### Step 5: Frontend — Update `Login.tsx`

**File:** `frontend/src/pages/Login.tsx`

**API key login** (`handleApiKeyLogin`):
1. Store auth in localStorage (same as now)
2. Call `getSession()` instead of `validateAuth()` — validates key AND gets session info
3. Store session in `authData.session`
4. Call `login(authData)`

**JWT login** (`handleCredentialsLogin`):
1. Call `loginWithCredentials()` (same as now)
2. Store token + email in auth (same as now)
3. Call `login(authData)` to persist tokens
4. Call `fetchSession()` from context to load tenant/role/name

### Step 6: Frontend — Update Sidebar

**File:** `frontend/src/components/Layout/Sidebar.tsx`

| Line | Current | New |
|------|---------|-----|
| 221 | `INSPECTOR` | `{session?.role?.toUpperCase() ?? 'INSPECTOR'}` |

Access `session` via `useAuth()` context.

### Step 7: Frontend — Update Settings profile card

**File:** `frontend/src/pages/Settings.tsx`

| Line | Current | New |
|------|---------|-----|
| 385 | `PLANT INSPECTOR` | `{session?.role?.toUpperCase() ?? 'INSPECTOR'}` |
| 416 | `{auth.tenantId.slice(0, 8)}…` | `{session?.tenant?.name ?? auth?.tenantId?.slice(0,8) ?? '—'}` |

Add new info rows to the profile card:
- **Tenant** — `session.tenant.name`
- **Role** — `session.role` with badge color (admin=amber, operator=cyan, viewer=muted)
- **Permissions** — for API key auth: `session.api_key.permissions`
- **Location** — `session.tenant.location` (if not empty)

---

## Files to Modify

| File | Change |
|------|--------|
| `backend/api/routers/auth/queries/auth.py` | Add `SessionResponse`, `TenantInfo`, `ApiKeyInfo` schemas + `GET /session` endpoint |
| `frontend/src/types/api.ts` | Add `SessionInfo`, `TenantInfo`, `ApiKeySessionInfo` types; add `session?` to `AuthState` |
| `frontend/src/api/client.ts` | Add `getSession()`, update `validateAuth` to use it |
| `frontend/src/context/AuthContext.tsx` | Add `session` state, `fetchSession()`, update `displayName` derivation |
| `frontend/src/pages/Login.tsx` | Both login handlers fetch session after auth |
| `frontend/src/components/Layout/Sidebar.tsx` | Replace hardcoded "INSPECTOR" with `session?.role` |
| `frontend/src/pages/Settings.tsx` | Replace hardcoded role, show tenant name, role badge, permissions |

**No new files needed.** No changes to existing backend auth logic or API key verification.

---

## Verification

1. **API key login:** Enter API key → should see tenant name, role, permissions in sidebar and settings
2. **JWT login:** Enter email/password → should see user name, tenant name, role in sidebar and settings
3. **Invalid API key:** Should show "Invalid API key" error (401 from `/auth/session`)
4. **Invalid JWT:** Should show "Invalid email or password" error (401 from `/auth/token`)
5. **Session refresh on reload:** Refresh browser → session info reloads from backend (not just localStorage)
6. **Swagger:** `GET /api/v1/auth/session` visible at `http://localhost:8000/docs` with `SessionResponse` schema
7. **Test with curl:**
   ```bash
   # JWT auth
   curl -H "Authorization: Bearer $TOKEN" -H "X-Tenant-ID: $TENANT" \
     http://localhost:8000/api/v1/auth/session

   # API Key auth
   curl -H "X-API-Key: ise_..." \
     http://localhost:8000/api/v1/auth/session
   ```
