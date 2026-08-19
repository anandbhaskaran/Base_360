# Property Revenue Dashboard

Multi-tenant revenue dashboard. See `ASSIGNMENT.md` for the original debugging brief.

## Run

```bash
docker-compose up --build
# frontend: http://localhost:3000
# backend:  http://localhost:8000/docs
```

Postgres seeds from `database/schema.sql` + `database/seed.sql` on first start. To reseed, remove the postgres container.

## Credentials

| Tenant | Email | Password | Timezone |
|---|---|---|---|
| Sunset Properties (tenant-a) | `sunset@propertyflow.com` | `client_a_2024` | Europe/Paris |
| Ocean Rentals (tenant-b) | `ocean@propertyflow.com` | `client_b_2024` | America/New_York |

## Backend dev

```bash
cd backend
uv sync                # first time
uv run pytest tests/   # 7 tests
uv run uvicorn app.main:app --reload
```

## Frontend dev

```bash
cd frontend
npm install
npm run dev            # vite on :5173
npm run lint
```

## What was fixed

Full report and fix plan in [`docs/BUGS.md`](docs/BUGS.md). Shipped so far:

- **P0-1** Cache key includes `tenant_id` (was cross-tenant leak on shared `prop-001`).
- **P1-1** `/dashboard/summary` accepts `month`/`year`, uses property-local timezone bounds. Fixes Client A's "March mismatch".
- **P1-2** Silent DB-error mock removed; 503 on failure.
- **P1-3** Frontend `X-Simulated-Tenant` backdoor deleted.
- Plus latent bugs the P1-2 fix exposed: `DatabasePool` now reads `DATABASE_URL` (was reaching for non-existent Supabase attrs), and uses the async default pool instead of sync `QueuePool`.

New: `GET /api/v1/properties` (tenant-scoped). Dashboard now fetches the tenant's properties and renders one revenue card per property with month/year pickers, defaulting to March 2024 (the seeded data).

## Repo layout

- `backend/app/api/v1/` FastAPI routers (`dashboard`, `login`, `properties`, plus boilerplate leftovers)
- `backend/app/services/` `cache.py`, `reservations.py`, `properties.py`
- `backend/app/core/` auth, tenant resolver, database pool
- `backend/tests/` pytest, `uv run pytest tests/`
- `frontend/src/components/` `Dashboard.tsx`, `RevenueSummary.tsx`
- `frontend/src/lib/secureApi.ts` API client (huge — mostly unrelated boilerplate)
- `database/schema.sql`, `database/seed.sql` initial DB state
- `CLAUDE.md` guide for future AI edits
- `docs/BUGS.md` ranked bug report
