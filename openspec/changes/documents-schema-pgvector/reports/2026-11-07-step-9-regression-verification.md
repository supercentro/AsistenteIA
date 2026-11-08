# Step 9 - regression verification (no frontend or workflow change)

Date: 2026-11-07. Branch `feature/documents-schema-pgvector`, HEAD `6d104d5` at the start.

## Why the interactive browser flow does not apply
This change adds a migration, two SQLAlchemy models, a repository method and test helpers. It adds no endpoint, no response field and no screen, and it changes nothing under `frontend/`, so there is no user workflow to drive with the Playwright MCP. The proof of "no regression" is the frontend gates, the mocked Playwright suite and a full `docker compose` stack with the pinned database image. No browser session was opened by the agent (no Playwright MCP use); the Playwright Test browsers started by the suite exit with it.

## Environment constraint and how it was handled
Host ports 8000 and 5173 are used by development servers of a **different project** (`AI4Devs-finalproject`: uvicorn pid 49508 and Vite pid 27340). They were not touched, stopped or reused. Playwright's `webServer` has `reuseExistingServer: true` and Vite is `strictPort: 5173`, so a plain `npm run test:e2e` would have run against that other project's frontend and proved nothing. Instead:
- the mocked suite ran against a Vite server started by this verification on `127.0.0.1:15173` (`E2E_BASE_URL`), then stopped;
- the stack ran with a Compose override kept **outside the repository** (scratch directory) that only moves the published host ports (backend 18000, frontend 15173) and sets the matching `CORS_ORIGINS` and `VITE_API_URL`. `docker-compose.yml` and the `.env` files were not edited.

## Frontend gates (`frontend/`)
| Command | Result |
|---|---|
| `npm run lint` | clean |
| `npm run format:check` | all files formatted |
| `npm run typecheck` | clean |
| `npm run check:api-types` | "API types are up to date" |
| `npm test` (Vitest) | 16 files, **236 tests passed** |
| `npm run build` | built |
| `npm run test:e2e` (mocked Playwright suite, own server on 15173) | **11 passed, 6 skipped** (the 6 `real-backend` tests are gated by `E2E_REAL_BACKEND` and would write users to the development database, so they were not enabled) |

## Full stack with the pinned image
`docker compose -f docker-compose.yml -f <override outside the repo> up -d --build`:
- `db`: image `pgvector/pgvector:0.8.7-pg15`, healthy, port 5442; `backend` (rebuilt) and `frontend` (rebuilt) running.
- `GET /api/v1/health` on the backend: 200 `{"status":"ok"}`.
- Frontend on 15173: 200, title "AsistenteIA".
- CORS preflight of `POST /api/v1/auth/login` from `http://localhost:15173`: 200 with `access-control-allow-origin: http://localhost:15173`.
- Inside the stack: `alembic current` -> `0004 (head)`; `alembic check` -> "No new upgrade operations detected".
- Afterwards `docker compose stop` and `rm -f` for `backend` and `frontend` only (no `down`, no `-v`): the `db` service and the volume `asistenteia_db_data` stay. The development database snapshot is identical to the one after step 8 (revision `0004`, 0 rows in every data table) and `asistenteia_test` is empty as at the baseline. The other project's servers still listen on 8000 and 5173.

## Backend regression and gates (unchanged code)
Full suite **668 passed** (2 min 13 s), coverage of `app` 98 %; `ruff check`, `ruff format --check` clean; `mypy --strict` clean (105 files); `pip-audit` no known vulnerabilities; `openspec validate --all --strict` 13 of 13. Authorization, integrity, concurrency and log-protection tests are part of that run.

## Location and retention of the pre-migration backup (from step 8)
- Contents: `pg_dump -Fc` of `asistenteia` taken before `0004`, schema only (the data tables were empty), 8,261 bytes; no credentials inside (roles are not exported and the dump has no password; the run used `--no-owner` on restore).
- Locations: (1) the session scratch directory in the operating system temporary folder (file `asistenteia_pre_0004.dump`), outside the repository and never staged; (2) `/tmp/asistenteia_pre_0004.dump` inside the `asistenteia-db-1` container, which disappears if the container is recreated.
- Retention: it only matters while `0004` is new. Proposed: keep it until the change is merged and archived, then delete both copies. Nothing was deleted without the user's decision.

## Incidents and deviations
1. Ports 8000 and 5173 are occupied by another project; handled with the override above instead of `docker compose up` on the default ports (the guide's command is otherwise the same, with `--build` and detached).
2. The first attempt to start the stack failed because the Vite server started for the mocked suite still held port 15173 (its Windows process had to be stopped explicitly). It was this verification's own process; the second attempt succeeded.
3. The six real-backend tests were deliberately not run (they would create users in the development database; out of scope for a change with no API).

## Update at group 10 (2026-11-07): state of the pre-migration backup
- External copy: still present in the session scratch directory (operating system temporary folder, outside the repository), 8,261 bytes, sha256 prefix `f1bf54e5dc15a567` unchanged. It was not added to Git (`git ls-files` lists no dump).
- Copy inside the `asistenteia-db-1` container (`/tmp/asistenteia_pre_0004.dump`, same size): **not durable storage**; it disappears when the container is recreated. Do not rely on it.
- Restore status: restored with `pg_restore` into a throwaway database and compared with the source at step 8 (identical structure, extensions, revision and row counts); the throwaway database was dropped.
- Retention: nothing deleted. The operating system may clean its temporary folder, so if the backup must outlive this session, copy it to a folder chosen by the user outside the repository.
