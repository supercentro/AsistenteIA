# Tasks

Reports required by `docs/openspec-tasks-mandatory-steps.md` are saved in `openspec/changes/project-scaffold/reports/` (the guide's `specs/<change-name>/reports/` would create a spec-less directory under `specs/`; this path is the one used here).

## 0. Setup: Create Feature Branch (MANDATORY - FIRST STEP)

- [x] 0.1 Create branch `feature/project-scaffold` from `main` and verify with `git branch --show-current`
- [x] 0.2 Verify toolchain (`docker compose version`, `uv --version`, `node --version`) and that `uv` can provision Python 3.12

## 1. Repository Base

- [x] 1.1 Extend `.gitignore` only if needed for new tooling output (e.g. `.env` files stay ignored, `!.env.example` kept) and verify with `git check-ignore -v backend/.env frontend/.env`
- [x] 1.2 Create `docker-compose.yml` with `db` (`pgvector/pgvector:pg15`, healthcheck, named volume) and an init script in `docker/db-init/` creating `asistenteia_test` next to `asistenteia`; verify `docker compose config` is valid, `docker compose up db` becomes healthy and both databases exist
- [x] 1.3 Verify `CREATE EXTENSION vector` works in both databases (`docker compose exec db psql ...`)

## 2. Backend: Tooling and Structure

- [x] 2.1 Create `backend/pyproject.toml` (Python 3.12, runtime and dev dependencies from design D10, ruff and mypy `--strict` config, pytest config) and commit-ready `uv.lock`; verify `uv sync` succeeds
- [x] 2.2 Create the package layout of `docs/backend-standards.md` §2 (empty layers with `__init__.py`, `tests/unit`, `tests/integration`); verify `uv run mypy --strict app` and `uv run ruff check . && uv run ruff format --check .` pass
- [x] 2.3 Create `backend/.env.example` with placeholders for `DATABASE_URL`, `APP_ENV`, `CORS_ORIGINS`, `LOG_LEVEL` and `TEST_DATABASE_URL` (documented as integration-tests-only); verify no real secret is present

## 3. Backend: Configuration, Errors, Headers, Transactions (TDD)

- [x] 3.1 Write failing unit tests (spec `dev-environment`): missing `DATABASE_URL` names the variable; development defaults (`LOG_LEVEL=INFO`, CORS `http://localhost:5173`); `CORS_ORIGINS` parsed to a list; wildcard rejected in every environment; production without explicit `CORS_ORIGINS` rejected; startup works with `TEST_DATABASE_URL` unset; verify they fail for the right reason
- [x] 3.2 Implement `core/config.py` and `core/logging.py` (ids only, no content); verify 3.1 tests pass
- [x] 3.3 Write failing unit/integration tests for `api-error-handling`: unknown route 404, 422 with field details and no echoed values, each domain error mapped to its status/code, unhandled exception → generic 500 with no internals, secure headers on success and error responses, CORS allowed vs disallowed origin
- [x] 3.4 Implement `core/errors.py`, exception handlers and middleware (design D5, D6); verify 3.3 tests pass
- [x] 3.5 Write a failing integration test that a request failing after a DB write leaves nothing persisted and a successful one commits (uses a temporary table created by the test and removed afterwards)
- [x] 3.6 Implement the SQLAlchemy engine/session factory, `DeclarativeBase` with naming convention and the `get_db` dependency (design D4); verify 3.5 passes
- [x] 3.7 Update `docs/backend-standards.md` only if the implemented behaviour differs from it, and verify there is no divergence

## 4. Backend: Test Database Isolation, Health Endpoint and Migrations (TDD)

- [x] 4.0a Write failing unit tests for `assert_safe_test_database` (valid test DB passes; same server and name as `DATABASE_URL` rejected; name not ending in `_test` rejected; `APP_ENV=production` rejected) and for the integration fixture failing fast when `TEST_DATABASE_URL` is unset, before any connection
- [x] 4.0b Implement `core/db_safety.py` and the guarded integration fixtures (engine, Alembic config override, destructive helpers only in `tests/`); verify 4.0a passes

- [x] 4.0c Review follow-up: add automated tests that the guard rejects unsafe configurations (missing variable, production, same name, wrong suffix, unparsable URL) before any engine is created or connection opened, including the re-check in destructive helpers; verified by a temporary mutation that removes the re-check and makes the tests fail
- [x] 4.0d Review follow-up (TDD): write failing tests for a configurable 5 second PostgreSQL connection timeout (default, override, range, driver argument, silent server returns 503 quickly), then implement `DB_CONNECT_TIMEOUT_SECONDS` in settings, engine creation, `.env.example` and the development guide
- [x] 4.1 Write failing integration tests for `service-health`: 200 `{"status": "ok"}` without token; body contains only `status`; 503 `Error` body (no connection details) when the database is unreachable
- [x] 4.2 Implement `GET /api/v1/health` and router assembly in `main.py`; verify 4.1 passes
- [x] 4.3 Write a failing migration test (real PostgreSQL via the guarded `TEST_DATABASE_URL` fixture): upgrade head → extension present, downgrade base → extension absent, upgrade again
- [x] 4.4 Initialise Alembic and add revision `0001` enabling `vector` with a working `downgrade` (design D7); verify 4.3 passes
- [x] 4.5 Update `docs/api-spec.yml` (`/health` documented with exactly 200 and 503 `SERVICE_UNAVAILABLE`, generic `Error.code` values; no new paths) and verify the spec still parses (`python -c "import yaml; yaml.safe_load(open('docs/api-spec.yml'))"` or an OpenAPI validator)

## 5. Backend: Container

- [x] 5.1 Create `backend/Dockerfile` (pinned `python:3.12-slim`, `uv sync --frozen`, non-root user, no embedding model) and add the `backend` service to compose (waits for healthy `db`); verify `docker compose build backend` succeeds
- [x] 5.2 Verify `docker compose up backend` serves `GET http://localhost:8000/api/v1/health` = 200 and `/docs` loads

## 6. Frontend: Tooling and Structure

- [x] 6.1 Create `frontend/` with Vite + React 18 + TypeScript `strict` + Tailwind and the scripts `dev`, `build`, `test`, `test:e2e`, `lint`, `format:check`, `typecheck`; commit-ready `package-lock.json`; verify `npm ci` and `npm run build` succeed
- [x] 6.2 Configure ESLint (typescript-eslint, react-hooks, jsx-a11y) and Prettier; verify `npm run lint && npm run format:check && npm run typecheck` pass
- [x] 6.3 Create the folder layout of `docs/frontend-standards.md` §2, `frontend/.env.example` (`VITE_API_URL`) and `lib/strings.es.ts` (single Spanish UI-strings module); verify layout and that `.env` stays ignored

## 7. Frontend: Providers and Home Page (TDD)

- [x] 7.1 Write a failing Vitest + React Testing Library test (MSW configured in `tests/`) that the home page renders its heading from `strings.es.ts`, is reachable via the router and is queried by role/label
- [x] 7.2 Implement providers (React Router, TanStack Query), the Axios instance reading `VITE_API_URL` and the placeholder home page; verify `npm test` passes
- [x] 7.3 Add `Dockerfile` for the frontend dev server and the `frontend` compose service (bind mount, `node_modules` anonymous volume, polling file watcher inside compose); verify `docker compose build frontend`

## 8. Continuous Integration

- [x] 8.1 Create `.github/workflows/ci.yml` with the backend job (pgvector service, a setup step creating `asistenteia` and `asistenteia_test`, ruff, format check, mypy, unit + integration tests with coverage), the frontend job (lint, format check, typecheck, tests, build) and non-blocking `pip-audit` / `npm audit`; verify the YAML parses and references no provider secret (`grep -i gemini .github/workflows/ci.yml` returns nothing)
- [x] 8.2 Run the same commands the workflow runs locally and verify all exit 0 (a remote run is verified after the Pull Request is opened)

## 9. Backend: Review and Update Existing Unit Tests (MANDATORY)

- [x] 9.1 Confirm there were no pre-existing tests (greenfield), review all tests added in groups 3, 4 and 7 against the specs' scenarios, and add any missing scenario test

## 10. Backend: Run Unit Tests and Verify Database State (MANDATORY)

- [x] 10.1 Capture the pre-test baseline of the test database (extensions, table list, row counts, `alembic_version`)
- [x] 10.2 Run targeted tests (`uv run pytest tests/unit`, then each integration module) and record results
- [x] 10.3 Run the full suite `uv run pytest tests --cov=app --cov-report=term-missing` and record totals, runtime and flaky behaviour
- [x] 10.4 Re-check the same database indicators; restore state if tests left any residue
- [x] 10.5 Create report `openspec/changes/project-scaffold/reports/YYYY-MM-DD-step-10-unit-test-and-db-verification.md` using the template in `docs/openspec-tasks-mandatory-steps.md`
- [x] 10.6 Mark this step complete only after tests pass and the report exists

## 11. Backend: Manual Endpoint Testing with curl (MANDATORY - AGENT MUST EXECUTE)

- [x] 11.1 Start the stack with `docker compose up -d db backend` and apply `alembic upgrade head`
- [x] 11.2 `curl -i http://localhost:8000/api/v1/health` → 200 `{"status":"ok"}` with the three secure headers and no `Authorization` required
- [x] 11.3 `curl -i http://localhost:8000/api/v1/does-not-exist` → 404 `Error` body
- [x] 11.4 `curl -i -H "Origin: http://localhost:5173" ...` → `Access-Control-Allow-Origin` present; with `Origin: http://evil.example` → header absent
- [x] 11.5 Stop `db` (`docker compose stop db`), call `/health` → 503 `Error` body without internals; restart `db` and re-check 200
- [x] 11.6 Verify database state equals the pre-test state (no tables beyond `alembic_version`) and document every command and response in `openspec/changes/project-scaffold/reports/YYYY-MM-DD-step-11-curl-verification.md`

## 12. Frontend: E2E Verification (MANDATORY - AGENT MUST EXECUTE)

- [x] 12.1 Run `docker compose up -d` (all three services) and verify the frontend is served on `http://localhost:5173`
- [x] 12.2 Use Playwright MCP (`browser_navigate`, `browser_snapshot`) to open the app, verify the home page content and that there are no console errors (Playwright CLI only if MCP is unavailable, and say so in the report)
- [x] 12.3 Add the Playwright Test smoke spec (home page loads) and run `npm run test:e2e`; verify it passes
- [x] 12.4 Close the browser, stop the stack, confirm database state unchanged and write `openspec/changes/project-scaffold/reports/YYYY-MM-DD-step-12-e2e-verification.md`

## 13. Update Technical Documentation (MANDATORY)

- [x] 13.1 Update `docs/development_guide.md`: commands now real (compose services, migration command, `TEST_DATABASE_URL`, quality commands), embedding-model note moved to the ingestion change, Windows file-watching note; verify every documented command was executed as written during this change
- [x] 13.2 Run the `update-docs` skill checklist and confirm `docs/api-spec.yml`, `docs/data-model.md` (unchanged), and standards are consistent; report any divergence to the user instead of fixing it silently
- [x] 13.3 Confirm `readme.md` and `prompts.md` are untouched (`git diff --stat -- readme.md prompts.md` is empty); propose, but do not apply, any README change that Entrega 2 may require

## 14. Final Verification of MUST Quality Gates (`docs/base-standards.md` §9)

- [x] 14.1 §9.1 Typing: `uv run mypy --strict app` and `npm run typecheck` clean; no `any` without justification
- [x] 14.2 §9.2 Testing: unit and integration suites pass against real PostgreSQL+pgvector; no external service called
- [x] 14.2a Isolation: guard tests pass and a manual attempt with `TEST_DATABASE_URL` pointing to `asistenteia` is rejected without touching the database
- [x] 14.3 §9.3 Secrets: `.env` ignored, `.env.example` placeholders only, lock files committed (`uv.lock`, `package-lock.json`)
- [x] 14.4 §9.6 Lint/format: `ruff check`, `ruff format --check`, ESLint, Prettier all clean
- [x] 14.5 §9.7 Reproducibility: migrations upgrade/downgrade on a clean DB; the full stack starts with `docker compose up --build` following the guide; runtime versions pinned (Python 3.12, Node LTS, PostgreSQL 15)
- [x] 14.6 §9.8 Documentation updated in this change; conventional commit messages prepared (commits and Pull Request only when the user asks)
- [x] 14.7 Run `openspec validate project-scaffold --strict` and tick this change's tasks only after all items above pass

## Workflow follow-up

- Open the Pull Request from `feature/project-scaffold` to `main` when the user requests it, and confirm the remote CI run is green.
- Archive with `/opsx:archive` after review (no `adversarial-review` required: no auth, upload, chat or personal data is touched).
- Ask the user whether to record notable AI usage in `prompts.md`.
