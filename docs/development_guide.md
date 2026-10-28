# Development Guide

How to set up the environment, run the stack and run quality checks for AsistenteIA.

> Status: the scaffold (`project-scaffold`) and authentication (`auth-and-roles`: users, JWT, roles, consent, admin CLI) are implemented. Items marked _(planned)_ arrive with later OpenSpec changes. When a command changes, update this guide in the same change.

## Prerequisites

- Docker and Docker Compose (primary, evaluated way to run the stack)
- Git
- For running tools outside Docker: `uv` (provisions Python 3.12) and Node.js LTS (>= 20.19) with npm

## 1. Clone and configure

```bash
git clone https://github.com/supercentro/AsistenteIA.git
cd AsistenteIA
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

`.env.example` files document every variable with **placeholder** values. Replace every `CHANGE_ME` locally and never commit `.env`:

```bash
python -c "import secrets; print(secrets.token_hex(16))"   # e.g. for POSTGRES_PASSWORD (use the same value in both URLs)
```

Backend variables (`backend/.env`):

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | Application database (`postgresql+psycopg://...`). Host `db` inside compose, `127.0.0.1:5442` from the host | required |
| `APP_ENV` | `development`, `test` or `production` | `development` |
| `CORS_ORIGINS` | Comma-separated allowed origins. `*` is rejected. Mandatory and explicit when `APP_ENV=production` | `http://localhost:5173` (development only) |
| `LOG_LEVEL` | Python log level | `INFO` |
| `DB_CONNECT_TIMEOUT_SECONDS` | Seconds allowed to open a PostgreSQL connection (1-60); keeps `/health` from hanging | `5` |
| `JWT_SECRET` | HS256 signing key. **Required in every environment**, at least 32 bytes; values containing `CHANGE_ME`/`changeme` or with fewer than 8 distinct characters are rejected. Generate: `python -c "import secrets; print(secrets.token_urlsafe(48))"` | required |
| `JWT_ISSUER`, `JWT_AUDIENCE` | `iss` and `aud` claims, both validated on every request | `asistenteia`, `asistenteia-api` |
| `JWT_EXPIRE_MINUTES` | Access-token lifetime (1-1440) | `60` |
| `PRIVACY_POLICY_VERSION` | Current privacy-policy version (1-20 chars) that users must accept. Mirror any override in `frontend/src/lib/privacyPolicy.ts` | `2026-10-v1` |
| `LOGIN_RATE_LIMIT` | Login attempts per client address, `<n>/<second\|minute\|hour>` | `10/minute` |
| `REGISTER_RATE_LIMIT` | Registrations per client address (independent counters, same format) | `5/minute` |
| `SEED_TEACHER_EMAIL`, `SEED_TEACHER_PASSWORD`, `SEED_STUDENT_EMAIL`, `SEED_STUDENT_PASSWORD` | Read only by `python -m app.cli seed`; no defaults exist | optional |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Read by the `db` compose service | required for compose |
| `TEST_DATABASE_URL` | **Integration tests only**; never read by the application | required for integration tests |

Frontend (`frontend/.env`): `VITE_API_URL=http://localhost:8000/api/v1`.

> **Local databases created before migration `0002` was final:** the migration gained the `ck_users_email_ascii` check before being merged; run `docker compose exec backend alembic downgrade -1 && docker compose exec backend alembic upgrade head` (it drops the `users` table, so only for development data).

> **Upgrading an existing checkout:** the backend now refuses to start without a valid `JWT_SECRET`. Add one to your local `backend/.env` (never commit it) and run `alembic upgrade head`.

_(planned)_ Gemini, embedding, upload and similarity variables are added by the change that first uses them.

## 2. Run the full stack

```bash
docker compose up --build
```

Services: `db` (PostgreSQL 15 + pgvector, published on `127.0.0.1:5442`), `backend` (FastAPI on 127.0.0.1:8000, docs at `/docs`, auto-reload), `frontend` (Vite on 127.0.0.1:5173; file polling is enabled inside compose because bind mounts on Windows do not emit change events).

The database image is pinned to `pgvector/pgvector:0.8.7-pg15` (PostgreSQL 15 with pgvector 0.8.7) in `docker-compose.yml` and in the CI service, so the extension version no longer changes silently; the digest of this tag was identical to the previous floating `pg15` tag when it was pinned, so existing data volumes keep working. To move to a newer pgvector, change the tag in both files together, rerun the magnitude experiment in `openspec/changes/documents-schema-pgvector/reports/` (or its archived copy) because the valid vector range depends on the pgvector version, and run `ALTER EXTENSION vector UPDATE;` in each database after the new container starts.

`db` creates two databases on first start: `asistenteia` (development) and `asistenteia_test` (integration tests only). The init script runs only when the data volume is created; if the volume already existed, run `docker compose down -v` (deletes data) or `docker compose exec db createdb -U <POSTGRES_USER> asistenteia_test`.

_(planned)_ The first build of the ingestion change downloads the embedding model into a Docker volume (large image, several minutes).

## 3. Database

```bash
docker compose exec backend alembic upgrade head      # apply migrations (manual, not run on startup)
docker compose exec backend alembic downgrade -1      # revert last migration
```

Only `backend/app` is mounted into the backend container, so a **new migration file is not visible inside a running container**: rebuild it first (`docker compose up -d --build backend`) before running `alembic upgrade head` there, or run Alembic from the host with `DATABASE_URL` pointing to `127.0.0.1:5442`. Running `alembic current` in the container shows which head it knows. Check for drift between models and migrations with `alembic check` (it must report no new operations).

### Administrative commands (teacher accounts and demo data)

Teacher accounts can only be created from the command line; no HTTP endpoint creates teachers or changes roles.

```bash
# Interactive hidden prompt (asks twice). The password is never accepted as an argument.
docker compose exec backend python -m app.cli create-teacher --email teacher@example.com --name "Ana Teacher"
# Non-interactive: first line of standard input
printf '%s\n' "$TEACHER_PASSWORD" | docker compose exec -T backend python -m app.cli create-teacher --email teacher@example.com --password-stdin

# Demo accounts: one teacher and one student, no subjects. Development and test only.
# Set the four SEED_* variables first (in backend/.env or with `docker compose exec -e ...`).
docker compose exec backend python -m app.cli seed
```

- Passwords are 10-128 characters. Emails must be ASCII (lowercased; write internationalised domains in punycode, for example `user@xn--bcher-kva.com`). An existing email is never modified or promoted (non-zero exit).
- `seed` is idempotent (existing accounts are skipped), has no built-in credentials, prints no passwords, and refuses to run when `APP_ENV=production`.

### Login and registration rate limiting: limitations

`POST /api/v1/auth/login` (`LOGIN_RATE_LIMIT`, default 10/minute) and `POST /api/v1/auth/register` (`REGISTER_RATE_LIMIT`, default 5/minute) are limited per client address, with independent counters, and answer 429 with `Retry-After`. The counters live in the memory of each backend process: they reset on restart, are not shared between workers or instances, and a distributed attack on one account from many addresses (including rotation inside an IPv6 prefix) is not covered. The address is the connection peer. The application never reads `X-Forwarded-For`, `Forwarded` or `X-Real-IP`, and the project starts Uvicorn with **`--no-proxy-headers`** (Dockerfile and compose): by default Uvicorn trusts loopback and rewrites the client address from `X-Forwarded-For`, which lets a client behind a same-host proxy, tunnel or sidecar that forwards the header unchanged rotate its address and bypass both limits. Consequently, behind a reverse proxy all clients share the proxy's address (one bucket) until you deliberately enable proxy headers with an explicit `--forwarded-allow-ips` list **and** a proxy that overwrites (not appends) `X-Forwarded-For`. When running Uvicorn by hand on the host, pass `--no-proxy-headers` too. A shared store (for example Redis) is a later hardening step. Unexpected exceptions are answered by an outermost middleware that logs only the exception type, method and path (no traceback or request data reaches the server log), SQL parameters are hidden in database error text, and an unreachable database returns 503 `SERVICE_UNAVAILABLE` on every endpoint. Tokens cannot be revoked before they expire (default 60 minutes); the user and role are re-read from the database on every request.

Create migrations with `alembic revision --autogenerate -m "describe change"` and **review** the generated file; every migration needs a working `downgrade`.

### Test database isolation

Tests that run migrations or destructive cleanup use `TEST_DATABASE_URL` only. A guard (`app/core/db_safety.py`) runs before any such connection and refuses to continue unless the database name ends in `_test`, differs from the database in `DATABASE_URL`, and `APP_ENV` is not `production`. If `TEST_DATABASE_URL` is missing, integration tests abort before connecting. Use `127.0.0.1` (not `localhost`) in URLs from the host: `localhost` may resolve to IPv6 first and the port is published on IPv4 only.

## 4. Quality commands

Backend (from `backend/`):

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict app tests
uv run pytest tests/unit
uv run pytest tests/integration --cov=app --cov-report=term-missing   # needs the db service and TEST_DATABASE_URL
```

Frontend (from `frontend/`):

```bash
npm ci
npm run lint && npm run format:check && npm run typecheck
npm run test:coverage              # Vitest with the 70 % thresholds on components and hooks
npm run check:api-types            # fails when src/types/api.generated.ts is stale
npm run generate:api               # regenerate it from docs/api-spec.yml after a contract change
npx playwright install chromium    # once
npm run test:e2e                   # mocked browser suite (no backend); reuses the frontend on :5173 or starts it
# Against the real stack (docker compose up) - creates one student per run, see the header of the spec:
E2E_REAL_BACKEND=1 npm run test:e2e -- real-backend
```

After adding or upgrading frontend dependencies the compose frontend keeps its old `node_modules` volume: run `docker compose up -d --build -V frontend` (renews the anonymous volume).
The expiry checks need a backend with `JWT_EXPIRE_MINUTES=1`. Run it as a separate process against the `*_test` database with the settings in the process environment (never in a committed file), stop the compose backend meanwhile and start it again afterwards.

_(planned)_ `npm run test:e2e` will start the backend with `LLM_PROVIDER=fake` and a fake embedder when the main flow exists. Automated tests always use fake LLM and embedding providers.

## 5. Branching and commits

- `main` is the integration branch and is never committed to directly once implementation starts.
- Implementation: one branch `feature/<change-name>` per OpenSpec change, created from `main` and merged back through a Pull Request. Conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`) in English.
- Course delivery branches (`feature/entrega-N-AN`, `final-project-AN`) are cut from `main` only when submitting a delivery; see `academic-requirements.md` §3 and §9.
- Before committing, review which docs must be updated (see `documentation-standards.md`).

## 6. Continuous integration

GitHub Actions (`.github/workflows/ci.yml`) on every push and Pull Request: backend lint, format check, `mypy --strict`, unit and integration tests (PostgreSQL service with pgvector, database `asistenteia_test` created in the job); frontend lint, format check, type check, unit tests and build; `pip-audit` and `npm audit` as non-blocking steps. Gemini is never called in CI. Playwright Test is not run in CI yet.

## 7. Troubleshooting

- `extension "vector" is not available`: the database image must be a pgvector-enabled image (the pinned `pgvector/pgvector:0.8.7-pg15`).
- `port is already allocated` on 5432: the compose database is published on `127.0.0.1:5442` to avoid clashes with other local PostgreSQL instances; change the mapping in `docker-compose.yml` and `TEST_DATABASE_URL` together if 5442 is taken.
- Integration tests hang or time out connecting: use `127.0.0.1`, not `localhost`, in `TEST_DATABASE_URL`.
- Integration tests abort with `TEST_DATABASE_URL is required` or `Refusing to use database`: set a dedicated `*_test` database (see §3).
- Startup error `Invalid configuration - CORS_ORIGINS ...`: set explicit origins in production and never use `*`.
- Frontend page blank or `Failed to resolve import` after a dependency change: renew the container volume (`docker compose up -d --build -V frontend`).
- _(planned)_ Gemini 429/blocked responses locally: switch `LLM_PROVIDER=fake` to keep developing without the API.
