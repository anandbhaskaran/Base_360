# Property Revenue Dashboard — Bug Report

Investigated by fanning out 5 parallel bug-hunters (cache, tenant-auth, precision, timezone, frontend) + adversarial verify pass. 33 candidate findings, 30 kept after verify, deduped to 18 distinct bugs below. Ranked P0 → P3.

Symptom → bug map:
- **Client B "sees another company's numbers"** → P0-1 (cache key), and amplified by P1-3 (X-Simulated-Tenant header)
- **Client A "March totals don't match"** → P1-1 (endpoint has no month/year param and returns lifetime, not March) + P0-1 pollution
- **Finance "off by cents"** → P2-1 (float cast) + P2-2 (JS Math.round)

---

## P0 — Critical (ship-blocker)

### P0-1. Redis cache key omits tenant_id → cross-tenant revenue leak - FIXED
- **File**: `backend/app/services/cache.py:13`
- **Root cause**: `cache_key = f"revenue:{property_id}"`. `prop-001` exists for BOTH `tenant-a` (Beach House Alpha) and `tenant-b` (Mountain Lodge Beta) (`database/seed.sql:8-9`). First tenant populates `revenue:prop-001` for 300s; every other tenant querying the same property_id gets a cache HIT with the first tenant's numbers.
- **Repro**: flush Redis → login as `sunset@` → GET `/api/v1/dashboard/summary?property_id=prop-001` (caches tenant-a's $2,250) → login as `ocean@` within 5min → GET same → sees tenant-a's $2,250 instead of tenant-b's Mountain Lodge total.
- **Fix**:
  ```python
  cache_key = f"revenue:{tenant_id}:{property_id}"
  ```
  Also bump a version prefix on deploy (`v2:revenue:...`) to invalidate poisoned keys. Defence-in-depth: assert `cached['tenant_id'] == tenant_id` on read.

---

## P1 — High (direct client complaint or silent data corruption)

### P1-1. `/dashboard/summary` returns lifetime revenue, not "March" - FIXED
- **File**: `backend/app/api/v1/dashboard.py:8-25` + `backend/app/services/reservations.py:51-59`
- **Root cause**: `calculate_total_revenue` has NO date filter. Endpoint accepts no `month`/`year` params. The dashboard shows all-time totals but the client thinks they're seeing March. `calculate_monthly_revenue` exists but is a stub (`return Decimal('0')`) and is not wired to anything.
- **Fix**:
  1. Add `month: int | None = Query(None, ge=1, le=12), year: int | None = Query(None, ge=2000, le=2100)` to the endpoint.
  2. Implement `calculate_monthly_revenue` with a real SQL query, tz-aware bounds (see P2-3).
  3. Thread month/year into cache key: `revenue:{tenant_id}:{property_id}:{year}-{month}`.
  4. If month/year omitted, return `period: 'lifetime'` explicitly in the response so no one confuses lifetime for a month.

### P1-2. Silent mock fallback fabricates wrong totals on any DB error - FIXED
- **File**: `backend/app/services/reservations.py:88-109`
- **Root cause**: bare `except Exception` swallows every DB error and returns hardcoded per-property totals (e.g. `prop-001 → $1,000.00`) that don't match real data. Finance can't distinguish "DB down" from "real number". Compounds P0-1: mocks get cached under the shared key.
- **Fix**: delete the mock branch. On DB failure `raise HTTPException(503, 'Revenue service unavailable')`. Never cache error responses. If mocks are needed for local dev, gate on `settings.env == 'local'` and set `data_source: 'mock'` in the response so the UI can badge it. Narrow the `except` to `SQLAlchemyError`.

### P1-3. Shipped dev backdoor: `X-Simulated-Tenant` header from a client-controlled prop - FIXED
- **File**: `frontend/src/components/RevenueSummary.tsx:22, 30-33` + `frontend/src/lib/secureApi.ts:1455-1469`
- **Root cause**: `RevenueSummary` accepts a `debugTenant` prop and forwards it as `X-Simulated-Tenant` on every dashboard call. Even though the backend today reads tenant from the JWT, any future middleware honoring this header is an instant cross-tenant impersonation from the browser. The default value `'candidate'` also ships in production traffic.
- **Fix**:
  1. Delete the `debugTenant` prop, the `activeTenant` const, and the whole options object on the `SecureAPI.getDashboardSummary` call.
  2. In `secureApi.ts` `getDashboardSummary`, remove the `options` param and the `X-Simulated-Tenant` header write.
  3. Add a CI grep for `X-Simulated-Tenant` and `'candidate'` in `frontend/src/`.

---

## P2 — Medium (precision, correctness, hardening)

### P2-1. Backend `float()` cast on `NUMERIC(10,3)` loses precision
- **File**: `backend/app/api/v1/dashboard.py:18`
- **Root cause**: `float(revenue_data['total'])` converts `Decimal('4523.675')` to IEEE-754 `4523.6749999999997`. Seed data `res-dec-1/2/3` (333.333, 333.333, 333.334) intentionally sums to 1000.000 but demonstrates the artifact.
- **Fix**: quantize with `Decimal` and serialize as string.
  ```python
  from decimal import Decimal, ROUND_HALF_UP
  total = Decimal(revenue_data['total']).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
  return {..., "total_revenue": str(total), "total_revenue_minor_units": int(total * 100)}
  ```

### P2-2. Frontend `Math.round(x*100)/100` inherits float error
- **File**: `frontend/src/components/RevenueSummary.tsx:64`
- **Root cause**: Even after P2-1, if the API returns a JS `number` at all, `4523.6749999999997 * 100 = 452367.49999999994` → `Math.round` → 452367 → `/100` → 4523.67 (right by luck). Any value that lands the other side of `.5` rounds the wrong way.
- **Fix**: change `RevenueData.total_revenue` to `string`. Render with `Intl.NumberFormat(locale, { style: 'currency', currency: data.currency, minimumFractionDigits: 2, maximumFractionDigits: 2 })` fed from the string or minor-units. Drop `Math.round`.

### P2-3. `calculate_monthly_revenue` uses naive UTC month bounds, ignores property timezone - FIXED (with P1-1)
- **File**: `backend/app/services/reservations.py:5-32`
- **Root cause**: `datetime(year, month, 1)` is naive. `res-tz-1` (`2024-02-29 23:30:00+00`, `prop-001/tenant-a`, `Europe/Paris`) is March 1 00:30 in Paris but Feb 29 in UTC. A naive-UTC filter puts it in February; Paris-based clients expect it in March. Function is currently dead code (a stub) but will bite as soon as P1-1 is implemented.
- **Fix**:
  ```python
  from zoneinfo import ZoneInfo
  tz = ZoneInfo(property_timezone)  # fetch from properties.timezone
  start = datetime(year, month, 1, tzinfo=tz)
  end   = datetime(year + (month == 12), (month % 12) + 1, 1, tzinfo=tz)
  ```
  Pass tz-aware datetimes to the query.

### P2-4. `TenantResolver.resolve_tenant_id` defaults every unknown user to `tenant-a`
- **File**: `backend/app/core/tenant_resolver.py:92`
- **Root cause**: `return "tenant-a"` for anything that's not in the hardcoded email map. Any misconfigured/new user silently reads tenant-a's data.
- **Fix**: return `Optional[str]` and return `None` when unknown. Force `authenticate_request` to `raise HTTPException(403, 'No tenant')`. Prefer JWT `app_metadata.tenant_id` before the email map.

### P2-5. `authenticate_request` discards JWT `tenant_id` claim
- **File**: `backend/app/core/auth.py:256`
- **Root cause**: login.py embeds `tenant_id` in `app_metadata` on the JWT, but auth.py ignores it and re-derives via the email map. If the map ever drifts from the JWT, tenants swap.
- **Fix**: `tenant_id = payload.get('app_metadata', {}).get('tenant_id') or payload.get('tenant_id')`. Only fall back to `TenantResolver` for legacy tokens with no claim.

### P2-6. `dashboard.py` never verifies `property_id` belongs to caller's tenant
- **File**: `backend/app/api/v1/dashboard.py:14`
- **Root cause**: `getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"` silently coerces missing tenants into a shared bucket, AND the handler never checks that `property_id` exists under `tenant_id`. Combined with P0-1 this lets `prop-001` traffic mix even at the DB layer.
- **Fix**: refuse when tenant_id is falsy (`raise HTTPException(401)`). Query `properties WHERE id=:pid AND tenant_id=:tid`; `raise HTTPException(404)` if not found (404, not 403, to avoid leaking existence across tenants).

### P2-7. `timestamp: Date.now()` cache-buster defeats frontend dedup - FIXED (with P1-3)
- **File**: `frontend/src/components/RevenueSummary.tsx:32` + `frontend/src/lib/secureApi.ts:1457-1459`
- **Root cause**: `SecureAPI.generateCacheKey` includes all query params. Passing a fresh epoch on every render gives every request a unique key → the 5s request cache and pending-request dedup never hit. Doubles backend load on every mount and amplifies the P0-1 window.
- **Fix**: drop `timestamp: Date.now()` (folds into P1-3's fix). If manual refresh is needed, call the existing `SecureAPI.clearEndpointCache('/dashboard/summary')`.

---

## P3 — Low (dead code, defence-in-depth, nits)

### P3-1. No cache invalidation helper in `services/cache.py`
- **File**: `backend/app/services/cache.py:1-29`
- **Fix**: add `async def invalidate_revenue_summary(property_id, tenant_id)` that DELs the tenant-scoped key. Currently nothing writes reservations, so this only matters after write endpoints are added.

### P3-2. Cached payload echoes `tenant_id` back, no verify on read
- **File**: `backend/app/services/cache.py:16-18`
- **Fix**: after JSON-decoding a cache hit, assert `cached['tenant_id'] == tenant_id`; on mismatch DEL the key and fall through to DB. Defence-in-depth for any future cache-key regression.

### P3-3. Auth cache key truncates SHA256 to 16 hex chars (64 bits)
- **File**: `backend/app/core/auth.py:81`
- **Fix**: drop the `[:16]` slice; use full digest. Better: use HMAC keyed with `settings.secret_key` and re-verify the stored digest on cache hit.

### P3-4. Tenant metadata re-write on every non-cached request
- **File**: `backend/app/core/auth.py:265`
- **Fix**: delete the `create_task(update_user_tenant_metadata(...))` call; the resolver is not trustworthy enough to write back to storage, and `update_user_tenant_metadata` is a no-op anyway.

### P3-5. Currency column ignored — SUM across mixed currencies
- **File**: `backend/app/services/reservations.py:51-84`
- **Fix**: either add a CHECK constraint enforcing one currency per property and `GROUP BY property_id, currency`, or accept a `report_currency` query param + FX table. At minimum, return `currency` from the SUM rather than hardcoding `"USD"`.

### P3-6. `NUMERIC(10,3)` vs 2-decimal display schema mismatch
- **File**: `database/schema.sql:28`
- **Fix**: decide the policy. If billing is always in cents, migrate column to `NUMERIC(12,2)` with `ROUND(total_amount, 2)` and reconcile diffs. If sub-cent is intentional (FX, taxes), keep 3 decimals and quantize with `ROUND_HALF_EVEN` at the API boundary.

### P3-7. `calculate_monthly_revenue` is a stub with a wrong signature
- **File**: `backend/app/services/reservations.py:5-32`
- **Notes**: SQL is commented out, function returns `Decimal('0')`, signature lacks `tenant_id` even though the query references `$2`. Fix as part of P1-1.

### P3-8. Redundant `Decimal(str(row.total_revenue))`
- **File**: `backend/app/services/reservations.py:68`
- **Fix**: `row.total_revenue` is already a `Decimal` from psycopg. Use `row.total_revenue.quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN)` at the boundary.

### P3-9. Persisted react-query cache (IndexedDB, 24h) survives logout
- **File**: `frontend/src/App.tsx:73-88` + `frontend/src/contexts/AuthContext.new.tsx:267-329`
- **Fix**: in `signOut`, before the redirect: `await queryClient.clear(); await localforage.clear();`. Extract `queryClient`/`persister` to `src/lib/queryClient.ts` to avoid a circular import from App.

### P3-10. Hardcoded `'candidate'` fallback tenant sent as header - FIXED (with P1-3)
- **File**: `frontend/src/components/RevenueSummary.tsx:22`
- **Fix**: folds into P1-3. Delete line 22.

---

## Implementation order (recommended)

1. **P0-1** (cache key) — one-line change, closes the privacy incident. Also bump cache version prefix.
2. **P1-3** (frontend backdoor) — delete the debugTenant/simulatedTenant surface end-to-end.
3. **P1-2** (mock fallback) — stop lying to finance.
4. **P1-1** (month/year endpoint) — implement `calculate_monthly_revenue`, add query params, tz-aware bounds (folds P2-3 in).
5. **P2-1 + P2-2** (precision) — Decimal string end-to-end + `Intl.NumberFormat`.
6. **P2-4/5/6** (tenant authorization hardening).
7. **P2-7** (drop `timestamp:` cache-buster).
8. **P3 batch** — sweep in one PR.

## Notes / unresolved

- **`calculate_monthly_revenue` vs `calculate_total_revenue`**: the assignment says "March mismatch" but the wired code path (`calculate_total_revenue`) returns lifetime. Either the client thinks the dashboard means "March" when it means "lifetime" (product/UX gap) or the plan was always to swap in the monthly function. Assumed the latter; P1-1 reflects that.
- **Currency**: seed data is all USD-implicit but the schema has a `currency` column. Multi-currency support (P3-5) is out of scope for the reported bugs but worth flagging.
- **Auth email map**: `TenantResolver` is a stopgap. Longer term, tenant identity should come from the JWT claim only (P2-5), and the resolver should die.
