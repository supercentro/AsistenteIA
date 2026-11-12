# Development Guide

How to set up the environment, run the stack and run quality checks for AsistenteIA.

> Status: the scaffold (`project-scaffold`), authentication (`auth-and-roles`: users, JWT, roles, consent, admin CLI), subjects and enrollments, the documents schema and document ingestion (`document-ingestion`: upload API and background worker) are implemented. Items marked _(planned)_ arrive with later OpenSpec changes. When a command changes, update this guide in the same change.

## Prerequisites

- Docker and Docker Compose (primary, evaluated way to run the stack)
- Git
- For running tools outside Docker: `uv` (provisions Python 3.12) and Node.js LTS (>= 20.19) with npm

## 1. Clone and configure

```bash
git clone https://github.com/supercentro/AsistenteIA.git
cd AsistenteIA
cp backend/.env.example backend/.env
cp backend/.env.worker.example backend/.env.worker
cp backend/.env.db.example backend/.env.db
cp frontend/.env.example frontend/.env
```

Each Compose service reads **only its own file**, so a process never receives a variable it does not use: `backend/.env` (API), `backend/.env.worker` (ingestion worker, no `JWT_SECRET`, no CORS or HTTP setting) and `backend/.env.db` (PostgreSQL, only `POSTGRES_*`). The example files document every variable with **placeholder** values. Replace every `CHANGE_ME` locally and never commit the real files (`.env`, `.env.worker`, `.env.db` are git-ignored; the `*.example` files are tracked):

```bash
python -c "import secrets; print(secrets.token_hex(16))"   # e.g. for POSTGRES_PASSWORD (use the same value in .env.db and in the DATABASE_URL of .env and .env.worker)
```

Backend variables. The column **File** says where each one lives: `API` = `backend/.env`, `worker` = `backend/.env.worker`, `both` = `DATABASE_URL`, `APP_ENV`, `LOG_LEVEL`, `DB_CONNECT_TIMEOUT_SECONDS` and `DB_IDLE_IN_TRANSACTION_TIMEOUT_SECONDS` in each of the two files, `db` = `backend/.env.db`. A variable placed in the wrong file is ignored: neither process rejects settings it does not read, so a tuning put in `backend/.env` that belongs to the worker has no effect.

| Variable | File | Purpose | Default |
|---|---|---|---|
| `DATABASE_URL` | both | Application database (`postgresql+psycopg://...`). Host `db` inside compose, `127.0.0.1:5442` from the host | required |
| `APP_ENV` | both | `development`, `test` or `production` | `development` |
| `CORS_ORIGINS` | API | Comma-separated allowed origins. `*` is rejected. Mandatory and explicit when `APP_ENV=production` | `http://localhost:5173` (development only) |
| `LOG_LEVEL` | both | Python log level | `INFO` |
| `DB_CONNECT_TIMEOUT_SECONDS` | both | Seconds allowed to open a PostgreSQL connection (1-60); keeps `/health` from hanging | `5` |
| `JWT_SECRET` | API | HS256 signing key. **Required in every environment**, at least 32 bytes; values containing `CHANGE_ME`/`changeme` or with fewer than 8 distinct characters are rejected. Generate: `python -c "import secrets; print(secrets.token_urlsafe(48))"` | required |
| `JWT_ISSUER`, `JWT_AUDIENCE` | API | `iss` and `aud` claims, both validated on every request | `asistenteia`, `asistenteia-api` |
| `JWT_EXPIRE_MINUTES` | API | Access-token lifetime (1-1440) | `60` |
| `PRIVACY_POLICY_VERSION` | API | Current privacy-policy version (1-20 chars) that users must accept. Mirror any override in `frontend/src/lib/privacyPolicy.ts` | `2026-10-v1` |
| `LOGIN_RATE_LIMIT` | API | Login attempts per client address, `<n>/<second\|minute\|hour>` | `10/minute` |
| `REGISTER_RATE_LIMIT` | API | Registrations per client address (independent counters, same format) | `5/minute` |
| `MAX_UPLOAD_MB` | API | Size limit of one upload | `10` |
| `MAX_PDF_PAGES`, `MAX_EXTRACTED_CHARS`, `MAX_CHUNKS_PER_DOCUMENT` | worker | Page, extracted-text and chunk limits of one document | `300`, `2000000`, `2000` |
| `MAX_DOCUMENTS_PER_SUBJECT` | API | Documents of one subject in any status; the next upload gets `409` | `50` |
| `INGESTION_QUEUE_MAX`, `INGESTION_PENDING_BYTES_MAX_MB`, `UPLOAD_MAX_IN_FLIGHT` | API | Unfinished jobs, bytes waiting for the worker and uploads being received at once; above them uploads get `503` | `100`, `200`, `4` |
| `UPLOAD_RATE_LIMIT` | API | Uploads per client address (in memory, same limits as the login limiter) | `10/minute` |
| `UPLOAD_BODY_TIMEOUT_SECONDS`, `UPLOAD_BODY_IDLE_SECONDS` | API | Total deadline for the upload body and longest silence inside it (`408`) | `120`, `20` |
| `INGESTION_MAX_ATTEMPTS`, `INGESTION_LEASE_SECONDS`, `INGESTION_JOB_DEADLINE_SECONDS`, `INGESTION_JOB_MAX_AGE_HOURS`, `INGESTION_BATCH_SIZE` | worker | Worker: attempts per job, lease, deadline per attempt (must be greater than the lease), age after which an unprocessed job expires, embedding batch | `3`, `120`, `600`, `24`, `16` |
| `PDF_CHILD_MAX_MEMORY_MB`, `PDF_CHILD_CPU_SECONDS`, `PDF_CHILD_TIMEOUT_SECONDS`, `PDF_CHILD_MAX_OUTPUT_MB` | worker | Limits of the isolated PDF process | `768`, `20`, `30`, `8` |
| `DB_STATEMENT_TIMEOUT_API_SECONDS` | API | PostgreSQL `statement_timeout` of the API | `15` |
| `DB_STATEMENT_TIMEOUT_WORKER_SECONDS` | worker | PostgreSQL `statement_timeout` of the worker | `60` |
| `DB_IDLE_IN_TRANSACTION_TIMEOUT_SECONDS` | both | `idle_in_transaction_session_timeout` of each engine | `30` |
| `EMBEDDER_BACKEND`, `ALLOW_FAKE_EMBEDDER` | worker | `local` (real model) or `fake` (deterministic vectors). `fake` is accepted only with `APP_ENV=test`, or with `ALLOW_FAKE_EMBEDDER=true` outside production | `local`, `false` |
| `EMBEDDING_MODEL_PATH` | worker | Directory of the model inside the worker image | `/opt/models/paraphrase-multilingual-MiniLM-L12-v2` |
| `EMBEDDING_THREADS` | worker | Threads used for inference (1-256). Commented out in `.env.worker.example`: unset means the effective CPU quota of the container (cgroup), so a 4-CPU limit gives 4 threads | unset |
| `SEED_TEACHER_EMAIL`, `SEED_TEACHER_PASSWORD`, `SEED_STUDENT_EMAIL`, `SEED_STUDENT_PASSWORD` | API | Read only by `python -m app.cli seed`; no defaults exist | optional |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | db | Read by the `db` compose service | required for compose |
| `TEST_DATABASE_URL` | API (tests) | **Integration tests only**; never read by the application | required for integration tests |

Frontend (`frontend/.env`): `VITE_API_URL=http://localhost:8000/api/v1`.

> **Local databases created before migration `0002` was final:** the migration gained the `ck_users_email_ascii` check before being merged; run `docker compose exec backend alembic downgrade -1 && docker compose exec backend alembic upgrade head` (it drops the `users` table, so only for development data).

> **Upgrading an existing checkout:** the backend now refuses to start without a valid `JWT_SECRET`. Add one to your local `backend/.env` (never commit it) and run `alembic upgrade head`.

The variables above are read only through `core/config.py`: `WorkerSettings` (what the worker reads) and `Settings` (the API, which extends it with authentication, CORS and the upload limits). They are documented with placeholders in the three example files, and tests keep each example equal to the defaults of its settings class, free of secrets, and in agreement with Compose and `.gitignore`.

**One value is duplicated on purpose:** `DATABASE_URL` appears in `backend/.env` and in `backend/.env.worker` (and its user, password and database name must match `backend/.env.db`). Keeping one value in one file would require Compose interpolation from a root `.env` or an external secret store, which this project does not use. The risk is drift: after changing the password in one file, the worker (or the API) fails to connect with an authentication error in its log, never silently. Change the three files together, then `docker compose up -d --force-recreate`. Note that `POSTGRES_PASSWORD` only takes effect when the data volume is created; to change the password of an existing database use `ALTER USER` first.

> **Upgrading an existing checkout (hardening before group 16):** the worker and the database used to receive the whole `backend/.env`. Now run `cp backend/.env.worker.example backend/.env.worker` and `cp backend/.env.db.example backend/.env.db`, copy the real `DATABASE_URL` into `.env.worker` and the three `POSTGRES_*` values into `.env.db` (the same ones as before, so the existing data volume keeps working), keep any worker tuning you had in `.env` (`INGESTION_*`, `PDF_CHILD_*`, `EMBEDDER_*`) in `.env.worker`, and recreate the containers. `backend/.env` can keep its old lines: the API ignores what it does not read. `alembic` and `python -m app.cli` read the API settings, so run them in the `backend` container (or with `JWT_SECRET` set), not in the worker. _(planned)_ The Gemini and chat variables are added by the change that first uses them.

## 2. Run the full stack

```bash
docker compose up --build
```

Services: `db` (PostgreSQL 15 + pgvector, published on `127.0.0.1:5442`), `backend` (FastAPI on 127.0.0.1:8000, docs at `/docs`, auto-reload), `worker` (the ingestion worker, no published port, 4 CPUs and 2 GiB; see [Document ingestion](#document-ingestion-worker-model-and-limits)), `frontend` (Vite on 127.0.0.1:5173; file polling is enabled inside compose because bind mounts on Windows do not emit change events).

The database image is pinned to `pgvector/pgvector:0.8.7-pg15` (PostgreSQL 15 with pgvector 0.8.7) in `docker-compose.yml` and in the CI service, so the extension version no longer changes silently; the digest of this tag was identical to the previous floating `pg15` tag when it was pinned, so existing data volumes keep working. To move to a newer pgvector, change the tag in both files together, rerun the magnitude experiment in `openspec/changes/archive/2026-11-08-documents-schema-pgvector/reports/` (or its archived copy) because the valid vector range depends on the pgvector version, and run `ALTER EXTENSION vector UPDATE;` in each database after the new container starts.

`db` creates two databases on first start: `asistenteia` (development) and `asistenteia_test` (integration tests only). The init script runs only when the data volume is created; if the volume already existed, run `docker compose down -v` (deletes data) or `docker compose exec db createdb -U <POSTGRES_USER> asistenteia_test`.

If port 8000 or 5173 is already used by another application, see [Ports already in use](#ports-already-in-use) instead of changing the project's defaults.

The first build of the `worker` image downloads the embedding model once, at a pinned revision verified by hash (`backend/docker/fetch_model.py`), and bakes it into the image (about 3.2 GB with the CPU-only `torch`; several minutes). The `backend` (API) image has no machine-learning packages and no model. The worker then runs with the hub offline: nothing is downloaded at runtime.

## 3. Database

```bash
docker compose exec backend alembic upgrade head      # apply migrations (manual, not run on startup)
docker compose exec backend alembic downgrade -1      # revert last migration
```

Migration `0004` creates `documents`, `document_chunks` and the `document_status` type. A development database created before it stays at `0003` until you rebuild the backend image (`docker compose up -d --build backend`, or `docker compose build backend` followed by `docker compose run --rm --no-deps backend alembic upgrade head`) and apply the migration. Its `downgrade` drops both tables **with their data**, so use it only on development data, and take a `pg_dump -Fc` first if the database holds anything you want to keep. After a pgvector upgrade, also run `ALTER EXTENSION vector UPDATE;` (see section 2).

Before applying `0004` to a database that was not built from `0003` by Alembic, check that no stale `document_status` type exists (the migration creates it only if absent, so a leftover with other labels would not be noticed; TD-028):

```sql
SELECT t.typname, array_agg(e.enumlabel ORDER BY e.enumsortorder) AS labels
FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid
WHERE t.typname = 'document_status' GROUP BY t.typname;
```

No row is expected before the migration. After it, the labels must be exactly `pending, processing, ready, failed` in that order. If a row exists before the migration, inspect what uses the type, then drop or rename it before running `alembic upgrade head`.

Local backups of the development database (for example the dump taken before applying `0004`) are kept outside the repository and outside temporary directories, for example under `%USERPROFILE%\Backups\AsistenteIA\` with permissions restricted to your user; verify the SHA-256 after copying and with `pg_restore --list`. A container's `/tmp` is not durable. Do not delete a backup until the change that produced it has been merged and the owner of the project agrees.

**Never run `alembic downgrade` below `0005` with documents or jobs in flight.** The downgrade drops `ingestion_jobs` and `documents.error_code` but leaves the documents in `pending` or `processing`: after the next upgrade they stay `pending` for ever (the worker's claim and sweep both start from the job), they still count toward the 50 documents of the subject, and `failed` documents lose their `error_code` (the fixed message stays). Preflight that must pass before any downgrade (run it against the database you are about to change; it blocks the operation when it finds work in flight):

```bash
docker compose stop backend    # no new uploads; leave the worker running so it can finish
docker compose exec -T db psql -U asistente -d asistenteia -tAc "SELECT count(*) FROM documents d LEFT JOIN ingestion_jobs j ON j.document_id = d.id WHERE d.status::text IN ('pending','processing') OR j.payload IS NOT NULL" | grep -qx 0 \
  || { echo 'BLOCKED: documents or jobs in flight; wait for them or delete them first'; exit 1; }
```

If it prints `BLOCKED`, let the worker finish (or delete the documents from the application) and repeat the check; when it passes, run `docker compose stop worker` and then the downgrade. This procedure is documentation only: the migration itself was not changed.

Migration `0005` creates `ingestion_jobs` and adds `documents.error_code` with its check (see `data-model.md`). It has been verified on the isolated test database, on a scratch database for the upgrade/downgrade round trip and on a disposable PostgreSQL container during the manual verification of the change. **The development database `asistenteia` stays at `0004` until the owner approves applying `0005` to it as a separate operation**, with a verified backup (`pg_dump -Fc`, SHA-256, `pg_restore --list` and a restore test into a scratch database before the upgrade) and a recovery procedure (`alembic downgrade 0004` for the schema; restoring the verified backup for data). No backup or restore of that database was exercised by this change. The `downgrade` of `0005` drops `ingestion_jobs` with the jobs in flight and their bytes.

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

## Document ingestion: worker, model and limits

Uploads (`POST /api/v1/subjects/{id}/documents`) store the file and a job in PostgreSQL and answer `202`; the **worker** (`python -m app.worker`, Compose service `worker`, image target `worker`) extracts text, chunks it, embeds it with the real model and writes the chunks. The API never loads the model. Follow the progress by listing the documents of the subject (`status`: `pending`, `processing`, `ready`, `failed`; a failed document has `error_code` and `error_message`).

- **Start / stop:** `docker compose up -d --build worker` starts it (it waits for a healthy `db`); `docker compose logs worker` shows its log (job and document ids and failure codes only; never file names or text). `docker compose stop worker` is safe: its lease expires and another worker takes the job.
- **Restart and health:** the `worker` service has `restart: unless-stopped` and a healthcheck (`python -m app.worker_health`, every 30 s, 120 s start period for the model). The worker writes `/tmp/ingestion-worker.health` every 10 s **only while it makes progress**: the gap since its last finished step is under 120 s, or the step in progress is still inside the job deadline plus 120 s (a long inference is not a false positive). If neither holds, the worker ends itself with exit code **3** (`ingestion worker stalled` in the log) and the restart policy starts a new one; a healthcheck alone would not restart anything. An abnormal end (a crash or an out-of-memory kill) is restarted by the same policy, and the job is recovered by its lease like any other (attempt 2, no duplicate chunks). `docker compose ps` shows `healthy` or `starting`. Docker does **not** restart a container you stopped or killed by hand (`docker stop`, `docker kill`): start it again with `docker compose up -d worker`. A worker that refuses to start (exit code 2: bad model path, unsupported platform, invalid configuration) is restarted in a loop with Docker's growing back-off and a log line each time, without touching the database: read `docker compose logs worker`, fix the setting and recreate it. A frozen process that holds the interpreter lock, or a hang while the model loads, shows as `unhealthy` but is not restarted, and a database outage shows as healthy but idle (steps fail and are retried): watch `docker compose ps` and the log.
- **Read-only code:** the worker mounts `./backend/app` as `:ro` (the API keeps its writable mount for auto-reload). The worker writes only to `/tmp` (the health file and the PyTorch cache); the root file system of the container is still writable and not read-only (hardening for change 13).
- **Model:** `paraphrase-multilingual-MiniLM-L12-v2`, 384 dimensions, CPU, offline. The worker fails fast at start if the model is missing or returns vectors of another size. Fake embeddings (`EMBEDDER_BACKEND=fake`) exist for tests only and are refused in production.
- **Limits and what happens when one is exceeded:** `MAX_UPLOAD_MB` (413), `MAX_DOCUMENTS_PER_SUBJECT` (409), `INGESTION_QUEUE_MAX`, `INGESTION_PENDING_BYTES_MAX_MB` and `UPLOAD_MAX_IN_FLIGHT` (503 with `Retry-After`), `UPLOAD_RATE_LIMIT` (429), `MAX_PDF_PAGES`, `MAX_EXTRACTED_CHARS`, `MAX_CHUNKS_PER_DOCUMENT` and the PDF child limits (the document ends `failed` with `TOO_MANY_PAGES`, `TEXT_TOO_LARGE`, `TOO_MANY_CHUNKS`, `RESOURCE_LIMIT_EXCEEDED` or `PROCESSING_TIMEOUT`). The values are in the variables table above and in `.env.example`.
- **Bounded chunking:** a page is handed to the splitter in windows of at most 20,000 characters (cut on a paragraph, line, sentence or space), the cap of `MAX_CHUNKS_PER_DOCUMENT` is checked after each window and the job deadline is polled between windows, so a pathological text is refused in seconds instead of occupying the worker. A page that fits one window is chunked exactly as before; longer pages lose the 20-token overlap only across a window cut. The text normaliser also keeps at most 16 consecutive characters without content (whitespace, combining marks, zero-width and other invisible characters), so padding cannot inflate the cost of a document. Letters, digits, punctuation and symbols are never touched; the only real text that changes is a run of more than 16 whitespace or invisible characters (for example code indented by more than 16 spaces, 30 spaces of table padding or 20 blank lines), which is shortened to 16.
- **Database timeouts:** the API sets `statement_timeout` (`DB_STATEMENT_TIMEOUT_API_SECONDS`, 15 s) and the worker its own (60 s); both set `idle_in_transaction_session_timeout` (30 s), so a stalled client or process cannot hold a lock or a pooled connection indefinitely. A statement over the timeout is cancelled and the API answers `503`.
- **Threads and CPU:** `EMBEDDING_THREADS` defaults to the effective CPU quota of the container. Measured with 4 CPUs and 2 GiB: a 420 KB text (1,649 chunks) in about 43 s, about 2.8 cores on average, memory peak about 1.04 GiB (about 0.7 GiB idle after loading the model).
- **Linux only for PDFs:** the isolated PDF child needs Linux (resource limits). The worker image is the supported way to run it; tests that need the child run in that image.
- **Pins and the `pypdf` upgrade rule:** `pypdf`, `python-multipart`, `sentence-transformers` and `torch` are pinned exactly in `backend/pyproject.toml` and `uv.lock`. Upgrading `pypdf` is a reviewed change: read its advisories, rerun the PDF tests (`backend/tests/unit/test_pdf_*.py`, `test_loaders_*.py`) and the real-process tests.
- **Temporary bytes and backups (TD-029):** the uploaded bytes are held in `ingestion_jobs.payload` until the document is `ready` or `failed`, then set to NULL. The dead tuples, the table files, the write-ahead log and any backup, dump or replica made meanwhile still contain them (measured: about 21 MB of WAL per 10 MB job). Treat database backups as containing teachers' files for their retention period. To follow the cost (`pg_ls_waldir()` needs a superuser or `pg_monitor`):

```sql
-- dead tuples and last autovacuum of the queue table and of its TOAST table
SELECT s.relname, s.n_live_tup, s.n_dead_tup, s.last_autovacuum
FROM pg_stat_all_tables s
WHERE s.relname = 'ingestion_jobs'
   OR s.relid = (SELECT reltoastrelid FROM pg_class WHERE relname = 'ingestion_jobs');
-- size of the table with its TOAST data and indexes
SELECT pg_size_pretty(pg_total_relation_size('ingestion_jobs'));
-- WAL generated since the statistics were reset, and the WAL directory size
SELECT pg_size_pretty(wal_bytes) AS wal_generated FROM pg_stat_wal;
SELECT pg_size_pretty(sum(size)) AS wal_directory FROM pg_ls_waldir();
```

  Autovacuum removes the dead tuples but does not overwrite free pages. `VACUUM FULL ingestion_jobs` removes the bytes from the data files (about 30 ms for this small table, with a short exclusive lock) and is **manual maintenance approved by the operator** (for example before a base backup or after a sensitive upload); neither the worker nor its sweep ever runs it, and it does not clear the WAL or existing backups.
- **Manual verification without touching the development database:** use a disposable PostgreSQL 15 + pgvector container (internal Docker network, no published port, data on `tmpfs`), run `alembic upgrade head` and `alembic check` there, start the real API and worker on free ports and drive them with `curl`. The scripts and the evidence of the verification of this change are in `openspec/changes/archive/2026-11-11-document-ingestion/reports/step-13-evidence/`.

## 4. Quality commands

Backend (from `backend/`):

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict app tests
uv run pytest tests/unit
uv run pytest tests/integration --cov=app --cov-report=term-missing   # needs the db service and TEST_DATABASE_URL
uv run pytest -m realmodel tests/unit/test_embedder_realmodel.py tests/unit/test_chunker_realmodel.py   # real model; only inside the worker image (excluded by default and in CI)
```

The real-server and real-process tests (Uvicorn started with the production arguments, killed workers, PDF child limits) run on Linux. On a Windows host where Application Control blocks the virtual environment, run the suite in the worker image with the repository mounted and `TEST_DATABASE_URL` pointing to the test database through `host.docker.internal:5442`. Coverage of `app` is 99 %: every module created by the ingestion change is at 100 % and the lines missed belong to older modules.

Frontend (from `frontend/`):

```bash
npm ci
npm run lint && npm run format:check && npm run typecheck
npm run test:coverage              # Vitest with the 70 % thresholds on components and hooks
npm run check:api-types            # fails when src/types/api.generated.ts is stale
npm run generate:api               # regenerate it from docs/api-spec.yml after a contract change
npx playwright install chromium    # once
npm run test:e2e                   # mocked browser suite (no backend); reuses ANY server already on :5173 (see 'Ports already in use')
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

- A document stays `pending`: the worker is not running or cannot reach the database (`docker compose ps worker`, `docker compose logs worker`); after `INGESTION_JOB_MAX_AGE_HOURS` an unprocessed job ends `failed` with `JOB_EXPIRED`. A document `failed` with `PROCESSING_INTERRUPTED` lost its worker `INGESTION_MAX_ATTEMPTS` times.
- Uploads answer `503 INGESTION_QUEUE_FULL`: the queue, the pending bytes or the uploads in flight are at their limit; wait for the worker (`Retry-After`) or raise the corresponding setting.
- `extension "vector" is not available`: the database image must be a pgvector-enabled image (the pinned `pgvector/pgvector:0.8.7-pg15`).
- `port is already allocated` on 5432: the compose database is published on `127.0.0.1:5442` to avoid clashes with other local PostgreSQL instances; change the mapping in `docker-compose.yml` and `TEST_DATABASE_URL` together if 5442 is taken.
- Integration tests hang or time out connecting: use `127.0.0.1`, not `localhost`, in `TEST_DATABASE_URL`.
- Integration tests abort with `TEST_DATABASE_URL is required` or `Refusing to use database`: set a dedicated `*_test` database (see §3).
- Startup error `Invalid configuration - CORS_ORIGINS ...`: set explicit origins in production and never use `*`.
- Frontend page blank or `Failed to resolve import` after a dependency change: renew the container volume (`docker compose up -d --build -V frontend`).
- _(planned)_ Gemini 429/blocked responses locally: switch `LLM_PROVIDER=fake` to keep developing without the API.

### Ports already in use

The project publishes the backend on `127.0.0.1:8000`, the frontend on `127.0.0.1:5173` and the database on `127.0.0.1:5442`. Keep those defaults in the repository. If another application (for example another course project) already listens there, do not stop it and do not edit `docker-compose.yml`:

1. **Find out who owns the port.** `docker ps --format '{{.Names}} {{.Ports}}'` shows containers of this project (`asistenteia-*`). For host processes on Windows: `Get-NetTCPConnection -State Listen -LocalPort 8000,5173` and then `Get-CimInstance Win32_Process -Filter "ProcessId=<pid>" | Select-Object CommandLine`; the command line shows the project folder. A `200` from `/api/v1/health` does **not** prove it is AsistenteIA.
2. **Use a temporary Compose override kept outside the repository** (for example in the operating system temporary folder, never committed, never containing secrets), which only moves the host ports and the two URLs that must follow them:

```yaml
# %TEMP%\asistenteia.ports.override.yml
services:
  backend:
    ports: !override
      - "127.0.0.1:18000:8000"
    environment:
      CORS_ORIGINS: "http://localhost:15173"
  frontend:
    ports: !override
      - "127.0.0.1:15173:5173"
    environment:
      CHOKIDAR_USEPOLLING: "true"
      VITE_API_URL: "http://localhost:18000/api/v1"
```

   Run `docker compose -f docker-compose.yml -f <override> config` to check the result and `docker compose -f docker-compose.yml -f <override> up -d --build`, and stop only your services afterwards (`docker compose stop backend frontend`; do not use `down -v`). Do not name the file `docker-compose.override.yml`: Compose would load it automatically.
3. **Playwright reuses whatever answers on the base URL.** `playwright.config.ts` has `reuseExistingServer: true`, and Vite uses `strictPort: 5173`. With another project's Vite on 5173, `npm run test:e2e` runs against that project's pages and proves nothing. Start your own server on a free port and point the suite at it: `npx vite --host 127.0.0.1 --port 15173 --strictPort`, then `E2E_BASE_URL=http://127.0.0.1:15173 npm run test:e2e`; stop that server afterwards. The mocked suite stubs `http://localhost:8000`, so keep `VITE_API_URL` at its default for it. The real-backend specs create users in the development database and run only with `E2E_REAL_BACKEND=1`.
4. **Integration tests hang without an error when the `db` service is stopped.** Start it with `docker compose up -d db` (this does not run migrations).
