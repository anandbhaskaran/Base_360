# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo purpose

Debugging exercise (see `ASSIGNMENT.md`). Multi-tenant "Property Revenue Dashboard". Two clients report: (a) revenue totals don't match, (b) sometimes see another tenant's numbers, (c) totals off by cents. Do NOT rebuild. Find bugs in the existing code and fix them.

Test credentials (also in `ASSIGNMENT.md`):
- Tenant A: `sunset@propertyflow.com` / `client_a_2024` (id `tenant-a`, Europe/Paris)
- Tenant B: `ocean@propertyflow.com` / `client_b_2024` (id `tenant-b`, America/New_York)

## Run / dev

```bash
docker-compose up --build          # full stack: frontend:3000, backend:8000, db:5433, redis:6380
make back                          # uvicorn app.main:app --reload (needs `make uv-install` first)
make front                         # vite dev on frontend
make pre-commit                    # install pre-commit hooks (ruff, prettier, eslint, conventional-commit)
```

Backend deps use `uv` (`backend/pyproject.toml`, `backend/uv.lock`). Docker uses `requirements.txt` instead.

Frontend: `cd frontend && npm run dev | build | lint`.

DB schema/seed auto-loaded from `database/schema.sql` + `database/seed.sql` on first postgres start. To reseed, remove the postgres container/volume.

No test suite exists. `pyproject.toml` declares `pytest` config but there is no `tests/` dir.

## Architecture — what matters for this exercise

### Request path for the reported bug
1. `frontend/src/components/RevenueSummary.tsx` calls `SecureAPI.getDashboardSummary(propertyId, ...)` in `frontend/src/lib/secureApi.ts`.
2. Backend `app/api/v1/dashboard.py` (`GET /api/v1/dashboard/summary?property_id=...`) reads `tenant_id` off the authenticated user, delegates to `app/services/cache.py::get_revenue_summary`.
3. `services/cache.py` checks Redis, on miss calls `app/services/reservations.py::calculate_total_revenue`, then `SETEX` for 5 min.
4. `services/reservations.py` queries via `app/core/database_pool.py`; on any DB failure it falls back to a hardcoded per-property mock dict.

This is the whole "revenue" surface. `main.py` mounts many other routers (`users_lightning`, `cities`, `city_access_*`, etc.) that are boilerplate leftovers; the assignment does not exercise them.

### Bug hotspots to check first
- `services/cache.py`: cache key derivation and its relationship to `tenant_id`.
- `services/reservations.py`: the mock fallback branch, and how month boundaries interact with property `timezone` in `calculate_monthly_revenue`.
- `api/v1/dashboard.py`: whether `property_id` is checked against the caller's tenant before returning data (`prop-001` exists in BOTH tenants in seed data, so cross-tenant confusion is easy).
- `RevenueSummary.tsx`: `debugTenant || 'candidate'` and the `simulatedTenant` header path via `SecureAPI` (dev override that can shadow the real tenant).
- `database/schema.sql`: `reservations.total_amount NUMERIC(10, 3)` combined with float coercion in `dashboard.py` (`float(revenue_data['total'])`) and JS-side `Math.round(x*100)/100` explains the "off by cents".

### Auth
- `api/v1/login.py` short-circuits the two client accounts and issues a JWT signed with `settings.secret_key` (HS256). `tenant_id` is embedded in `app_metadata`.
- `core/auth.py::authenticate_request` is the FastAPI dependency. It caches by SHA256(token) for 30 min in-process. `core/tenant_resolver.py::TenantResolver.resolve_tenant_id` is a hardcoded email → tenant map.
- `database.py::TenantAwareSupabase` wraps the Supabase client so PostgREST calls attach the request's bearer for RLS. When `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` are unset (the default in this env), it falls back to a `ChallengeClient` that returns empty data for every table op.

### Multi-tenancy model
- Properties table PK is composite `(id, tenant_id)`. `prop-001` intentionally exists for both `tenant-a` and `tenant-b`. Any code path that filters by `property_id` alone is a tenant-leak.
- RLS is enabled on `properties` and `reservations` but no policies are defined in `schema.sql`; real isolation must happen in application code.

## Conventions

- Backend logging: `logger = logging.getLogger(__name__)`. Emoji prefixes (`✅`, `🔄`) are common in `main.py` startup logs; keep the style if editing there.
- Frontend uses camelCase; backend uses snake_case. `app/utils/camel.py` and `frontend/src/utils/camel.ts` handle conversion at the API boundary.
- Pre-commit runs ruff (`--fix`), prettier, and eslint. Conventional commit prefix required: `feat|fix|ci|chore|test|infra|refactor`.

## How to work here

- **New code**: invoke the `tdd` skill (write failing test first, then minimal code to pass). No exceptions.
- **Cleanup**: invoke the `simplify` skill on changed code only. Do not run it over the whole repo.
- **Scout rule, bounded**: leave the file you touched slightly cleaner (obvious rename, dead-import removal, one clarifying comment). Do NOT refactor neighboring code, restructure modules, or introduce abstractions for future flexibility. If the cleanup is bigger than the fix itself, skip it and note it in the PR.
- **No over-engineering**: no new layers, no config-driven variants, no premature helpers. Three similar lines beat a bad abstraction. Delete before you add.
