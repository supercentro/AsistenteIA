# Step 11 Report - Manual Endpoint Testing with curl

- Date: 2026-10-27
- Change: project-scaffold
- Agent: Claude Code (Sonnet 5.5)

Stack: `docker compose up -d` (db, backend, frontend). Migration applied manually with
`docker compose exec backend alembic upgrade head` (log: `Running upgrade  -> 0001, Enable the pgvector extension.`).
The change adds one endpoint (`GET /api/v1/health`) and performs no writes, so there is no data to create or delete.

## Results

| # | Command | Expected | Observed |
|---|---|---|---|
| 11.2 | `curl -i http://localhost:8000/api/v1/health` | 200, body only `status`, secure headers, no token | `200 OK`, `{"status":"ok"}`, headers `x-content-type-options: nosniff`, `x-frame-options: DENY`, `referrer-policy: no-referrer` |
| 11.3 | `curl -i http://localhost:8000/api/v1/does-not-exist` | 404 `Error` body | `404`, `{"code":"NOT_FOUND","message":"Resource not found"}`, secure headers present |
| 11.3b | `curl -i -X POST http://localhost:8000/api/v1/health` | 405 `Error` body | `405`, `{"code":"METHOD_NOT_ALLOWED","message":"Request could not be processed"}` |
| 11.4 | `curl -i -H "Origin: http://localhost:5173" .../health` | `Access-Control-Allow-Origin` present | `access-control-allow-origin: http://localhost:5173` |
| 11.4b | `curl -i -H "Origin: http://evil.example" .../health` | header absent | no `access-control-allow-origin` header |
| 11.5 | `docker compose stop db`, then `curl -i .../health` | 503 `Error` body without internals | `503 Service Unavailable`, `{"code":"SERVICE_UNAVAILABLE","message":"Service unavailable"}`, secure headers present |
| 11.5b | `docker compose start db`, wait healthy, `curl .../health` | back to 200 | `200`, `{"status":"ok"}` |

## Database State
- Before: `asistenteia` had extension `plpgsql` and no tables.
- After the manual migration: extensions `plpgsql`, `vector`; table `alembic_version` (`0001`). This is the intended result of `alembic upgrade head`, not residue of the curl tests.
- The curl tests wrote nothing; state after them equals state after the migration. `asistenteia_test` was untouched (`plpgsql` only, no tables).

## Outcome
- Step 11 status: PASS
- Blocking issues: none
