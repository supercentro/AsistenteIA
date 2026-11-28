# Development Guide

How to set up the environment, run the stack and run quality checks for AsistenteIA.

> Status: the scaffold (`project-scaffold`), authentication (`auth-and-roles`: users, JWT, roles, consent, admin CLI), subjects and enrollments, the documents schema and document ingestion (`document-ingestion`: upload API and background worker), and the RAG chat endpoint (`chat-rag-endpoint`: POST /chat, conversations, Gemini LLM, embedder at startup) are implemented. Items marked _(planned)_ arrive with later OpenSpec changes. When a command changes, update this guide in the same change.

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

**Environment files of the database roles** (change `database-least-privilege`). Besides `backend/.env`, `backend/.env.worker` and `backend/.env.db`, the least-privilege design uses `backend/.env.migrate` (`MIGRATION_DATABASE_URL`, the migrator role; read by Alembic, `db-migrate`, `db-grants` and `db-verify`), `backend/.env.roles` (the administrator URL and the four working-role passwords; read only by the role bootstrap and by `db-verify`), `backend/.env.cli` (`CLI_DATABASE_URL`; read by the administrative commands) and `backend/.env.test` (`TEST_DATABASE_URL`, `TEST_ADMIN_DATABASE_URL`; host-only, read by pytest, never by a container). A new checkout creates each one from its `*.example` file. On the development machine of the project they have existed since 2026-11-14 (stage S21 of the real run): `backend/.env` and `backend/.env.worker` name the restricted roles and hold no `POSTGRES_*` or test variable. A `TEST_DATABASE_URL` left in `backend/.env` is still honoured by the tests, with `.env.test` taking precedence.

Each Compose service reads **only its own file**, so a process never receives a variable it does not use: `backend/.env` (API), `backend/.env.worker` (ingestion worker, no `JWT_SECRET`, no CORS or HTTP setting) and `backend/.env.db` (PostgreSQL, only `POSTGRES_*`). The example files document every variable with **placeholder** values. Replace every `CHANGE_ME` locally and never commit the real files (`.env`, `.env.worker`, `.env.db` are git-ignored; the `*.example` files are tracked):

```bash
python -c "import secrets; print(secrets.token_hex(16))"   # e.g. for POSTGRES_PASSWORD (the database ADMINISTRATOR: .env.db and ADMIN_DATABASE_URL of .env.roles; the API and the worker use their own role passwords, see below)
```

Backend variables. The column **File** says where each one lives: `API` = `backend/.env`, `worker` = `backend/.env.worker`, `both` = `DATABASE_URL`, `APP_ENV`, `LOG_LEVEL`, `DB_CONNECT_TIMEOUT_SECONDS` and `DB_IDLE_IN_TRANSACTION_TIMEOUT_SECONDS` in each of the two files, `db` = `backend/.env.db`. A variable placed in the wrong file is ignored: neither process rejects settings it does not read, so a tuning put in `backend/.env` that belongs to the worker has no effect.

| Variable | File | Purpose | Default |
|---|---|---|---|
| `DATABASE_URL` | both | Application database (`postgresql+psycopg://...`). Host `db` inside compose, `127.0.0.1:5442` from the host. The user is the restricted role of each service (`asistente_app` in `.env`, `asistente_worker` in `.env.worker`), never the administrator: the API and the worker **refuse to start as a PostgreSQL superuser** (they ask the server; the test-only `ALLOW_SUPERUSER_DATABASE_ROLE` is rejected unless `APP_ENV=test`) | required |
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
| `EMBEDDER_BACKEND`, `ALLOW_FAKE_EMBEDDER` | both | `local` (real model) or `fake` (deterministic vectors). `fake` is accepted only with `APP_ENV=test`, or with `ALLOW_FAKE_EMBEDDER=true` outside production. The API loads the embedder at startup for RAG queries; the worker loads it for document ingestion | `local`, `false` |
| `EMBEDDING_MODEL_PATH` | both | Directory of the model inside the API and worker images | `/opt/models/paraphrase-multilingual-MiniLM-L12-v2` |
| `EMBEDDING_THREADS` | worker | Threads used for inference (1-256). Commented out in `.env.worker.example`: unset means the effective CPU quota of the container (cgroup), so a 4-CPU limit gives 4 threads | unset |
| `SEED_TEACHER_EMAIL`, `SEED_TEACHER_PASSWORD`, `SEED_STUDENT_EMAIL`, `SEED_STUDENT_PASSWORD` | CLI | Read only by `python -m app.cli seed` (environment, `backend/.env.cli` or `backend/.env`); no defaults exist | optional |
| `CLI_DATABASE_URL` | CLI (`.env.cli`) | URL of the CLI database role used by `create-teacher` and `seed`; deliberately not `DATABASE_URL` | required for the commands |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | db | Read by the `db` compose service | required for compose |
| `TEST_DATABASE_URL` | `.env.test` (host only) | **Integration tests only**; never read by the application and not part of `backend/.env.example` any more. A legacy value in `backend/.env` is still honoured | required for integration tests |
| `TEST_ADMIN_DATABASE_URL` | `.env.test` (host only) | Administrator URL of the role-bound tests (same server as `TEST_DATABASE_URL`); they fail, not skip, when it is missing | required for role-bound tests |
| `MIGRATION_DATABASE_URL` | `.env.migrate` | URL of the migrator role, read by `alembic/env.py` through `MigrationSettings`; **never falls back to `DATABASE_URL`** and needs no `JWT_SECRET` | required to run Alembic |
| `ADMIN_DATABASE_URL`, `DB_MIGRATOR_PASSWORD`, `DB_APP_PASSWORD`, `DB_WORKER_PASSWORD`, `DB_CLI_PASSWORD` | `.env.roles` | Read only by the role bootstrap (`RolesSettings`): administrator URL and the four working-role passwords (at least 16 characters, all different, no placeholder) | required for the bootstrap and `db-verify` |

Frontend (`frontend/.env`): `VITE_API_URL=http://localhost:8000/api/v1`, and optionally `VITE_TEACHER_ACTIVITY_ENABLED=false` (the default; the teacher activity page needs `true` here **and** `TEACHER_ACTIVITY_ENABLED=true` in the backend, which a real installation must not set before TD-069 is closed). The Playwright dev server of `playwright.config.ts` sets it to `true` for the mocked suite only; a dev server that is already running without it shows no link, so run the mocked spec of the activity page against a server started with the flag.

The topic views (change `frequent-questions-and-topics`) need `VITE_TEACHER_TOPICS_ENABLED=true` on top of it and `TEACHER_TOPICS_ENABLED=true` on top of `TEACHER_ACTIVITY_ENABLED=true` in `backend/.env`; both default to `false` and are used with fictitious data only (TD-073, TD-074). The Playwright dev server sets both for the mocked suite. Reading bookmarks at ingestion is not behind a switch and stores no student data; documents uploaded earlier get topics only if their teacher defines them.

> **Migration `0009` and a mounted working tree:** the Compose services mount `backend/app` and `docker compose up` runs `migrate`. Starting this code against an existing volume applies `0009` to it, and a worker that restarts with this code against a database without `0009` fails the ingestion of every PDF that has bookmark topics. Until applying it to a database is authorised, run it in disposable containers, or from a separate git worktree that no running container mounts.

> **Local databases created before migration `0002` was final:** the migration gained the `ck_users_email_ascii` check before being merged; run `docker compose exec backend alembic downgrade -1 && docker compose exec backend alembic upgrade head` (it drops the `users` table, so only for development data).

> **Upgrading an existing checkout:** the backend now refuses to start without a valid `JWT_SECRET`. Add one to your local `backend/.env` (never commit it) and run `alembic upgrade head`.

The variables above are read only through `core/config.py`: `WorkerSettings` (what the worker reads) and `Settings` (the API, which extends it with authentication, CORS and the upload limits). They are documented with placeholders in the three example files, and tests keep each example equal to the defaults of its settings class, free of secrets, and in agreement with Compose and `.gitignore`.

**`DATABASE_URL` appears in `backend/.env` and in `backend/.env.worker` with different users:** the same host and database, `asistente_app` in the API file and `asistente_worker` in the worker file, each with its own password (`DB_APP_PASSWORD`, `DB_WORKER_PASSWORD` of `backend/.env.roles`); neither is the administrator of `backend/.env.db`. The risk is drift: after changing a password in one file, that service fails to connect with an authentication error in its log, never silently. Change `.env.roles` and the service file together, then recreate the service. `POSTGRES_PASSWORD` only takes effect when the data volume is created; to change the password of an existing database use `ALTER ROLE` first and recreate the container (a container keeps the environment it was created with, lesson L29).

> **State of this machine (TD-040 in `technical-debt.md` records the former state):** since the real run of 2026-11-14 the API and the worker connect as `asistente_app` and `asistente_worker` (see "State after the real run" in section 3). The code refuses to start as a PostgreSQL superuser: the development `backend` service mounts `backend/app` and runs Uvicorn with `--reload`, so a file edit while it runs triggers a new start, and the worker has `restart: unless-stopped`, so a service given an administrator URL exits (the worker with code 2) and is restarted in a loop until it is given its role (the identity is checked before the embedding model is loaded, so the loop is cheap): "the database connection uses a PostgreSQL superuser: refusing to start". The API also refuses to start when the database is down at boot, because it cannot prove its identity; `depends_on` with the health check of `db` avoids it in Compose. Never work around the refusal with the test-only `ALLOW_SUPERUSER_DATABASE_ROLE`.

> **Upgrading an existing checkout (hardening before group 16):** the worker and the database used to receive the whole `backend/.env`. Now run `cp backend/.env.worker.example backend/.env.worker` and `cp backend/.env.db.example backend/.env.db`, copy the real `DATABASE_URL` into `.env.worker` and the three `POSTGRES_*` values into `.env.db` (the same ones as before, so the existing data volume keeps working; _historical: the worker of a stack that still uses the administrator is refused by the code of `database-least-privilege` until the roles are adopted, see the note on the state of this machine_), keep any worker tuning you had in `.env` (`INGESTION_*`, `PDF_CHILD_*`, `EMBEDDER_*`) in `.env.worker`, and recreate the containers. `backend/.env` can keep its old lines: the API ignores what it does not read. `alembic` and `python -m app.cli` read the API settings, so run them in the `backend` container (or with `JWT_SECRET` set), not in the worker. The administrator URL in these files applied only until the roles were adopted (2026-11-14); the examples already carry the restricted users. _(planned)_ The Gemini and chat variables are added by the change that first uses them.

## 2. Run the full stack

> **Warning (database roles).** `docker-compose.yml` starts `bootstrap` and `migrate` before `backend` and `worker`. A checkout without `backend/.env.roles` and `backend/.env.migrate` fails at `bootstrap` at once and leaves `backend` and `worker` created but **not started**, and `up` may recreate them. On the development machine of the project the real files exist and the database was adopted (2026-11-14), but the full flow (`docker compose up` with both one-shots) has **not been exercised there**: the stack was moved with `up -d --no-deps --force-recreate` of `backend` and `worker`, and the database container was recreated alone on 2026-11-15. `bootstrap` re-sets the four working-role passwords from `.env.roles` on every run and refuses an administrator URL that no longer authenticates, so `ADMIN_DATABASE_URL` must always hold the current administrator password. `ps`, `logs`, `exec` and `down` keep working (never `down -v` on a database with data). Before the first full `up` on a machine that holds data, check the services state, take a verified backup and follow the preconditions of section 3. Needs Docker Compose 2.24 or newer (`env_file` with `required`); env-file values are interpolated, so a password containing `$` is altered: avoid it.

```bash
docker compose up --build
```

Services: `db` (PostgreSQL 15 + pgvector, published on `127.0.0.1:5442`), `backend` (FastAPI on 127.0.0.1:8000, docs at `/docs`; no auto-reload, run `docker compose restart backend` after editing `app/`), `worker` (the ingestion worker, no published port, 4 CPUs and 2 GiB; see [Document ingestion](#document-ingestion-worker-model-and-limits)), `frontend` (Vite on 127.0.0.1:5173; file polling is enabled inside compose because bind mounts on Windows do not emit change events).

The database image is pinned to `pgvector/pgvector:0.8.7-pg15` (PostgreSQL 15 with pgvector 0.8.7) in `docker-compose.yml` and in the CI service, so the extension version no longer changes silently; the digest of this tag was identical to the previous floating `pg15` tag when it was pinned, so existing data volumes keep working. To move to a newer pgvector, change the tag in both files together, rerun the magnitude experiment in `openspec/changes/archive/2026-11-08-documents-schema-pgvector/reports/` (or its archived copy) because the valid vector range depends on the pgvector version, and run `ALTER EXTENSION vector UPDATE;` in each database after the new container starts.

`db` creates two databases on first start: `asistenteia` (development) and `asistenteia_test` (integration tests only). The init script runs only when the data volume is created; if the volume already existed, run `docker compose down -v` (deletes data) or `docker compose exec db createdb -U <POSTGRES_USER> asistenteia_test`.

If port 8000 or 5173 is already used by another application, see [Ports already in use](#ports-already-in-use) instead of changing the project's defaults.

The first build of both the `worker` and `backend` (API) images downloads the embedding model once per target, at a pinned revision verified by hash (`backend/docker/fetch_model.py`), and bakes it into the image. The worker image is larger (about 3.2 GB with the CPU-only `torch`); the API image includes the `embedding` extra (sentence-transformers and, because it depends on it, the same CPU-only `torch`) but not `ingestion`; its size has not been measured for this change. Both run with the hub offline: nothing is downloaded at runtime. The API loads the embedder at startup to serve RAG queries; the worker loads it for document ingestion. Memory requirement: the API process needs about 700 MiB additional memory when the model is loaded.

## 3. Database

```bash
docker compose exec backend alembic upgrade head      # apply migrations (manual, not run on startup)
docker compose exec backend alembic downgrade -1      # revert last migration
```

**Compose flow of the database roles** (change `database-least-privilege`, group 6). `docker-compose.yml` now starts `db` (healthy) -> `bootstrap` (completed) -> `migrate` (completed) -> `backend` and `worker`. `bootstrap` runs `db-bootstrap` with `backend/.env.roles` (administrator URL and the four role passwords); `migrate` runs `db-migrate` with `backend/.env.migrate` (the migrator URL only). Rules that matter:

- Both are one-shots that exit (`restart: "no"`); each **runs on every `up`** (a plain `up` starts finished containers again), so both are idempotent. They are in the default profile on purpose.
- They run the code of the **image**, not your working tree: after `app/` or `alembic/` change, use `docker compose up -d --build`.
- If either fails, `backend` and `worker` are created but never started. Read why with `docker compose logs bootstrap migrate`; after fixing the cause, `docker compose up -d` repeats the flow.
- **The development API runs without `--reload`** (decision of 2026-11-17, evidence in `openspec/changes/archive/2026-11-17-chat-rag-endpoint/reports/2026-11-17-round5-m2-backend.md`). With `--reload` and `./backend/app` bind-mounted, every edit of the working tree restarted the API of the running container: a container created before a change kept serving the new code with its old environment and image, crashed on every reload (127 of 145 reloads in one case) while `docker compose ps` still said `Up`, and its file watcher can fail (`watchfiles ... Cannot allocate memory`), which stopped it. Apply a code edit with `docker compose restart backend` (the mount supplies the new code; it does not apply a changed environment or image, see the next bullet). The mount stays.
- `docker compose restart <service>` keeps the environment the container was created with: **`restart` does not apply a changed environment**. A changed `.env*` file or credential needs `docker compose up -d`, which recreates the services whose environment changed (this is also how a rotated password reaches a service).
- The flow was proved on disposable clusters (the cold start of the planned flow, the rehearsal on a restored backup and the CI privilege gate). On the development machine the stack was moved after the adoption with `up -d --no-deps --force-recreate` of `backend` and `worker` (2026-11-14); a plain `docker compose up`, which runs `bootstrap` and `migrate`, has not been exercised there yet (see the warning in section 2).

**Migrations go through `python -m app.cli db-migrate`** (change `database-least-privilege`, groups 3 and 4). `alembic/env.py` reads `MIGRATION_DATABASE_URL` (never `DATABASE_URL`) and refuses an online run without an explicit URL, because the privileges of a recreated table vanish unless the grants run afterwards. The two commands above therefore stop working once the image contains this change; they keep working in the containers that exist today, which were built before it. The commands of the new tooling (all of them read only their own file, none needs `JWT_SECRET`):

```bash
python -m app.cli db-bootstrap [--database asistenteia]   # administrator: roles, access, extension (.env.roles)
python -m app.cli db-adopt [--database asistenteia]       # dry run; add --apply to change ownership (.env.roles)
python -m app.cli db-adopt --rollback [--remove-roles]    # give the objects back (and drop the roles)
python -m app.cli db-migrate [--downgrade REVISION]       # Alembic as the migrator, then the grants (.env.migrate)
python -m app.cli db-grants                               # only the grants, in one transaction (.env.migrate)
python -m app.cli db-verify                               # read-only; exit 1 on any difference (.env.migrate + .env.roles)
```

`db-bootstrap`, `db-adopt --apply` and `db-migrate` were run against the development database once, on 2026-11-14 (stages S22 to S25 of the real run, each with the owner's explicit authorisation, with the API and the worker stopped); `db-verify` ran afterwards without findings and is the read-only check to repeat after any later change. `db-adopt` never runs by itself.

**Dangerous operations: mandatory preconditions** (`db-bootstrap` on a real cluster, `db-adopt --apply`, `db-adopt --rollback --apply`, `--remove-roles`, `db-migrate --downgrade`). Do not start one until every item is true and written down with its evidence:

1. **Owner's explicit authorisation** for that command on that database, in writing, for that session only.
2. **A verified backup** that exists before the command: file size and checksum recorded, `pg_restore --list` readable, and a restore into a disposable server proved at least once (group 16). A backup that was never restored is not a backup.
3. **Unambiguous cluster and database**: print `host:port`, `current_database()`, `inet_server_port()`, the data volume name and the container name, and compare them with what the owner named. `postgres`, `template0` and `template1` are refused by the commands; the cluster itself is not checked for you.
4. **Services stopped when the command needs it**: the API, the worker and the CLI for adoption, its rollback and role removal; the commands refuse while a role holds a session, but a stopped service must not restart in the middle (a restart as the administrator is refused by the code, as a restart under a dropped role would fail).
5. **A written rollback plan** before the first statement: for adoption `db-adopt --rollback` for that database (it acts on that database only; repeat it for every database where it reports remaining objects), what is restored from the backup if it fails, and who decides.
6. **Roles and ownership validated** before and after: `db-verify` (it must show no findings after adoption and none new after a rollback), the owners of the seven tables and of the enum types, the row counts, and the catalog fingerprint.
7. **Evidence before and after**, saved outside the secrets: the output of the commands (they print no secret), the counts, the owners and the revision, plus the time and the person.

The detailed plan for the real run (runbook, backup and recovery, credentials order, GO/NO-GO checklist, tested rollback and the tools `prepare_env_files.py`, `snapshot_*.sql`, `compare_snapshots.sh`, `restore_public_*.sql`, `compose.rollback.override.yml`) is in `openspec/changes/archive/2026-11-16-database-least-privilege/reports/group-17a/` (prepared in group 17A). Its execution on the development database on 2026-11-14 is recorded in `reports/2026-11-14-step-17b-window-closure.md` and `reports/2026-11-14-step-17b5-functional-closure.md` of the same change. **Where each procedure lives** (not repeated here): the runbook and the rollback of the real run in `reports/group-17a/runbook-17b.md` and `reports/group-17b/recovery-matrix.md`; the rotation of the administrator password and its recovery table in `reports/group-17b/rotation/README-17b6.md`; the rotation of the migrator password in `reports/2026-11-14-sec-17b-01-migrator-password-exposure.md`. After the change is archived these folders move to `openspec/changes/archive/`.

Known limits of the procedure, recorded in `docs/technical-debt.md` (TD-044), which is **open**: they are documented, neither remediated nor expressly accepted by the owner (no formal acceptance exists). The rollback returns the ownership and drops the grants of the runtime roles, but it does not restore the access that the bootstrap removed from `PUBLIC`: that recovery is a manual step, documented and rehearsed in 17A (`restore_public_cluster.sql` and `restore_public_schema.sql`), and its automation is pending. The other limits: the row counts of the adoption run inside the exclusive-lock transaction (fine for the empty development database, to be rethought before a large one); the rollback runs one connection per statement and can stop half way (it is idempotent: run it again); the bootstrap closes `PUBLIC` on every database of the cluster, so do not run it on a shared cluster; the grants run after Alembic and not inside its transaction, so after a column is added the column is visible to a table-level grant until `db-migrate` finishes (always use `db-migrate`, never `alembic upgrade` alone, which `alembic/env.py` refuses).

**Credential protection (database).** Rules for every file above and for any tool that touches them:

- The real `backend/.env*` files are git-ignored and are never committed, copied into an image, attached to a report or pasted into a conversation; the reports of this change contain variable **names**, never values. On Windows each real file has an owner-only ACL (inheritance disabled, one rule for your user): check it with `powershell -NoProfile -ExecutionPolicy Bypass -File openspec/changes/archive/2026-11-16-database-least-privilege/reports/group-17c/tools/secure_file_acl.ps1 -Path <file> -Rights Modify -VerifyOnly` and apply it by dropping `-VerifyOnly`.
- Each service reads only its own file. The administrator password exists only in `.env.db` (the `db` container), `ADMIN_DATABASE_URL` of `.env.roles` and the host-only `.env.test`, never in the API or worker files. `POSTGRES_PASSWORD` only takes effect when the data volume is created.
- Never show output that can echo a connection string: the URL parser of a database driver can print its input in an error (incident SEC-17B-01, TD-050), so one-off scripts catch exceptions and print only their type; the rotation tools do this by design.
- A password is rotated with the tools of `reports/group-17b/rotation/`, never by editing files by hand: they change the database first and the files second, keep a verified backup of the old files and scan the containers for the old value. A container keeps the environment it was created with (lesson L29), so after a rotation recreate only the service concerned.
- The copies of the files taken before the real run (`backend/.env*.pre-17b`) keep the old values; they are git-ignored and their clean-up is a separate decision of the owner (TD-038, `reports/group-17b/operational-decisions.md`).

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

Migration `0005` creates `ingestion_jobs` and adds `documents.error_code` with its check (see `data-model.md`). It has been verified on the isolated test database, on a scratch database for the upgrade/downgrade round trip and on a disposable PostgreSQL container during the manual verification of the change. **On 2026-11-12 the owner approved applying it to the local development database `asistenteia`, and it was applied** (see "State of the local development environment" below). It has not been applied anywhere else and there is no production environment. Any other database needs the same separate, explicitly approved operation, with a verified backup (`pg_dump -Fc`, SHA-256, `pg_restore --list` and a restore test in a disposable server before the upgrade) and a recovery procedure (`alembic downgrade 0004` for the schema; restoring the verified backup for data). The `downgrade` of `0005` drops `ingestion_jobs` with the jobs in flight and their bytes.

#### State of the local development environment (2026-11-12)

This describes the Compose stack of one development machine. It is not a production or a shared environment (none exists). The three kinds of information are kept apart: this table is the **current state**; the plan that follows is the **reproducible procedure** for another database (a new environment built from `main` simply runs `docker compose run --rm --no-deps backend alembic upgrade head` on an empty database); the **recovery procedure** is in sections 5 and 5b of that plan.

| Item | State |
|---|---|
| Database `asistenteia` | revision `0005` (applied with `alembic upgrade head` from the rebuilt backend image: `Running upgrade 0004 -> 0005`); `alembic check` clean; the catalog equals the rehearsal on the restored backup; PostgreSQL 15.19, pgvector 0.8.7; no application rows |
| Backup before the change | `pg_dump -Fc`, SHA-256 verified, `pg_restore --list` readable (51 entries), kept outside the repository with restricted permissions and a second verified copy in the owner's personal cloud storage (schema only, no rows) |
| Recovery rehearsal | restored into a disposable PostgreSQL 15.19 + pgvector 0.8.7 (identical catalog and rows, revision `0004`), then `upgrade 0005`, `alembic check`, `downgrade 0004` (identical to the restored state) and `upgrade 0005` again (identical to the first upgrade) |
| Images | rebuilt from `main` (`f455234`) and tagged `main-f455234`; `asistenteia-backend:latest` and `asistenteia-worker:latest` now point to them; the previous images are kept as `:pre-0005`; `alembic heads` reports `0005` in both and the code equals `main` |
| Services | `db` and `worker` running and `healthy` (worker: 4 CPUs, 2 GB, model loaded offline, connected to the database, no restarts); `backend` (API) and `frontend` stopped. A temporary Compose override outside the repository published the API only on `127.0.0.1:18080` for the validation below, because another project of the machine holds 8000 and 5173 (see "Ports already in use") |
| Functional validation | with the API and the worker, using synthetic data deleted afterwards: 45 of 45 checks of authentication, authorisation and uploads (TXT, Markdown and PDF answer `202` and reach `ready`; the chunks are stored; every embedding has 384 dimensions; the temporary bytes are cleared) and 17 of 17 checks of deletion (chunks and jobs removed, tables back to zero). `ChunkRepository.find_similar` was exercised **through code inside the worker container with the real model**, not over HTTP: no retrieval endpoint exists yet, and chat and RAG are not implemented. The logs held no token, password or document text. The detailed working report is kept outside the repository |
| Environment of the `db` container | it was recreated on 2026-11-12 (see the finding below); it now holds only `POSTGRES_USER`, `POSTGRES_PASSWORD` and `POSTGRES_DB` besides the variables of the image |

**Finding (fixed on 2026-11-12): a container keeps the environment it was created with.** The `asistenteia-db-1` container had been created on 2026-10-28, before the environment files were split (commit `172288a`), so besides `POSTGRES_*` it still carried `JWT_SECRET`, `DATABASE_URL`, `TEST_DATABASE_URL`, `CORS_ORIGINS`, `APP_ENV` and `LOG_LEVEL` of the API, although `docker-compose.yml` already gave it only the `POSTGRES_*` variables of `backend/.env.db`. It was found while checking the secrets of the worker. The fix was a controlled recreation: worker stopped, `docker compose up -d --no-build --no-deps db` (a `--dry-run` first showed that only `db` would be recreated), worker started again. The image (PostgreSQL 15.19, pgvector 0.8.7), the volume `asistenteia_db_data`, the port and the network were kept; the catalog, the rows and the revision `0005` were identical before and after, and the worker came back `healthy` with no restarts. No value was printed or recorded. Removing a variable from a container does not rotate it: the values were not changed (TD-038), and the shared superuser account (TD-030) is unchanged and still open.

#### State after the real run of `database-least-privilege` (2026-11-14 and 2026-11-15)

| Item | State |
|---|---|
| Database `asistenteia` | revision `0006` (server default `student` on `users.role`); `db-verify` without findings; application tables with 0 rows (the synthetic data of the functional check was removed) |
| Roles and ownership | the five identities of `data-model.md` ("Database identities and privileges"); the nine objects owned by `asistente_migrator`; `PUBLIC` without privileges |
| Services | `backend` as `asistente_app` and `worker` as `asistente_worker`, both operating; one session of each role and none of the administrator |
| Real run | 2026-11-14, window 18:30-20:00, stage by stage under the owner's authorisation: bootstrap, adoption, migration `0005` to `0006` with the grants, `db-verify`, recreation of `backend` and `worker` (about 36 minutes of unavailability), 25 of 25 functional checks |
| Credentials | the migrator password was rotated on 2026-11-14 (SEC-17B-01) and the administrator password on 2026-11-15, after which only the `db` container was recreated keeping the volume `asistenteia_db_data`; `JWT_SECRET` has **not** been rotated (TD-038) |
| Backups and recovery | two verified copies of the dump taken before the real run, kept outside the repository; the `backend/.env*.pre-17b` copies and the `:pre-17b` image tags of `backend` and `worker`; the git recovery refs. Nothing was deleted and the clean-up of the `*.pre-17b` copies is not authorised |
| Not exercised on this machine | a plain `docker compose up` (the one-shots `bootstrap` and `migrate`), see the warning in section 2 |

#### Plan: applying `0005` to the development database (prepared and executed on the local development database on 2026-11-12)

This plan was written before the operation and followed on 2026-11-12; it stays as the reproducible procedure for another database, and the headings that say *planned* are the original wording. The corrections found while executing it are listed after section 4. Applying it to any other database needs the owner's explicit authorisation. Section 1 describes the state **before** the operation.

**1. Read-only state before the operation (checked 2026-11-12)**

| Item | Observed |
|---|---|
| Migration chain | `0001` → `0002` → `0003` → `0004` → `0005` → `0006` → `0007` → `0008` → `0009` (single head); `0009` adds `document_topic_sets` and `document_topics`, applied to disposable databases only; `0008` adds the nullable `subjects.last_unenrolment_at` (change `activity-privacy-hardening`; the column grant `UPDATE (last_unenrolment_at)` to the application role comes with `python -m app.cli db-migrate`, which runs Alembic and then the grants, and is checked with `db-verify`; never by hand and never `alembic upgrade` alone; run it and a clean `db-verify` **before** the API of this version takes traffic, because without the grant a removal of an enrolment fails with 500 and rolls back as one unit); `0007` creates `conversations`, `messages` and `message_sources` with foreign keys and indexes for the RAG chat feature (the privileges are not in the migration: `db-grants` applies the matrix of `backend/app/db_privileges.py`); `0006` creates the least-privilege database roles; `0005` adds `documents.error_code` with `ck_documents_error_code_only_when_failed`, creates `ingestion_jobs` |
| Development database | `asistenteia`, revision `0004`; tables `users`, `subjects`, `enrollments`, `documents`, `document_chunks`, `alembic_version`; **0 rows** in every application table; 8 MB; no `ingestion_jobs` |
| Server | container `asistenteia-db-1` (project `asistenteia`), PostgreSQL 15.19, pgvector 0.8.7 (the pinned image `pgvector/pgvector:0.8.7-pg15`), data in the named volume `asistenteia_db_data`, 915 GB free; port published on `127.0.0.1:5442` only |
| Account | the application account is the bootstrap superuser of the image (can create objects; also what API and worker use, see TD-030) |
| Images | `asistenteia-backend:latest` and `asistenteia-worker:latest` were built on 2026-11-09 and **do not contain `0005`** (their `alembic/versions` stops at `0004`): they must be rebuilt before the migration can run in a container |
| Environment files | `backend/.env`, `backend/.env.worker`, `backend/.env.db` and `frontend/.env` exist and are git-ignored; the three backend files hold the expected variable names (values not recorded here); API and worker point at `db:5432`, the tests at `127.0.0.1:5442/asistenteia_test` |
| Models, migrations, code | `alembic check` on the isolated test database is part of the suite (`test_migrations_ingestion.py`: upgrade, downgrade, round trip, CHECKs and index predicate read from the catalog) and passed on `main` |
| Earlier backup | the dump taken before `0004` is outside the repository (`%USERPROFILE%\Backups\AsistenteIA\`); it is the owner's and must not be touched |

**2. Preconditions (planned)**
1. `main` is at the merged commit, `docker compose config -q` is valid, the three backend environment files exist with real values, and the owner has authorised the operation.
2. No uploads or jobs in flight: stop the API first (`docker compose stop backend`). At `0004` there is no queue, so the database holds no work to lose; the downgrade preflight above applies to any later downgrade.
3. Versions: `SELECT version()` reports PostgreSQL 15 and `SELECT extversion FROM pg_extension WHERE extname = 'vector'` reports `0.8.7`; free space is at least ten times the database size (the database is 8 MB).
4. Tag the current images so the previous state can be restored: `docker tag asistenteia-backend:latest asistenteia-backend:pre-0005` and the same for `asistenteia-worker`.

**3. Backup and restore test (planned)**
1. Dump inside the container, so no shell re-encodes the binary stream: `docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d asistenteia -Fc -f /tmp/asistenteia_pre_0005.dump'`.
2. Verify inside the container: `sha256sum /tmp/asistenteia_pre_0005.dump` and `pg_restore --list /tmp/asistenteia_pre_0005.dump` (the list must name the six tables, the `vector` extension and the `document_status` type).
3. Copy it out to a durable place outside the repository and outside temporary directories (`docker cp`), restrict its permissions to your user, and check that the SHA-256 of the copy equals the one inside the container.
4. Restore test in a disposable server, never in the development one: `docker run -d --name asistenteia-restore-check` with the same image `pgvector/pgvector:0.8.7-pg15`, data on `tmpfs`, a random password, no published port; copy the dump in, `CREATE DATABASE`, `CREATE EXTENSION vector` is part of the dump, `pg_restore -d`; then check `alembic_version` = `0004`, the table list, the row counts and `\dx`. Then rehearse the recovery on that restored copy: `alembic upgrade head` (`0004` → `0005`), the checks of step 4.4, `alembic downgrade 0004` (the tables must match the restored ones again) and `alembic upgrade head` once more. This validates the schema recovery on the real data shape, in isolation, before anything touches `asistenteia`. Remove only that container afterwards.
5. Keep the dump until the owner agrees to delete it.

**4. Apply (planned)**
1. `docker compose stop backend worker`.
2. `docker compose build backend worker`, **before** the upgrade: the current images only know `0004`, so `alembic upgrade head` in them would end successfully without doing anything and leave the database at `0004`. After the build, `docker compose run --rm --no-deps backend alembic heads` must report `0005 (head)`; if it does not, stop. (The worker image is 3.2 GB and downloads the model from its pinned revision; if the network fails, repeat; do not use `--no-cache` unless needed).
3. `docker compose run --rm --no-deps backend alembic upgrade head`; expected last line `Running upgrade 0004 -> 0005`. Alembic runs with the API settings (`load_settings`), so it needs `backend/.env`, not the worker file. PostgreSQL DDL is transactional: if the upgrade fails, nothing is applied. _(Historical: with the image of `database-least-privilege` this command is replaced by `python -m app.cli db-migrate`, and a direct `alembic upgrade` with the API settings is refused by design.)_
4. Verify: `alembic current` reports `0005 (head)`; `alembic check` reports no new upgrade operations; catalog queries find `ingestion_jobs`, `uq_ingestion_jobs_document_id`, `ck_ingestion_jobs_attempts_non_negative`, `ck_ingestion_jobs_lease_consistent`, `ix_ingestion_jobs_claimable` with its predicate `payload IS NOT NULL`, `documents.error_code` and its check; the application tables still have 0 rows.
5. Start `docker compose up -d backend worker` and wait for the worker to be `healthy` (the first beat takes up to the 120 s start period). **Start the worker only after the migration**: before it, the worker has no `ingestion_jobs` table to claim from.
6. Optional smoke test (needs its own authorisation because it writes data): create a teacher with the documented administrative command, upload a small text file, wait for `ready`, then delete the document and the test account.

**4b. Corrections found when it was executed**
- `docker compose run` does not accept `--no-build` (it uses the existing image and builds only if it is missing); `docker compose up` does.
- The images were built with `docker build -t asistenteia-backend:main-<sha> --target api backend` (and `--target worker`), and `:latest` was re-tagged afterwards, so the previous images stayed untouched and the switch is reversible with `:pre-0005`.
- The operations that use the worker image need at least 6 GB of free host memory when they start (the worker build dipped to about 3 GB); measure it just before.
- The host ports 8000 and 5173 may belong to another project: publish the API on a free port with a temporary override outside the repository, or do not start it.
- The upgrade took about 2 s and the worker was `healthy` about 15 s after it started.

**5. Recovery (planned)**
- *The upgrade fails or is interrupted:* nothing was applied; confirm `alembic current` is still `0004`, fix the cause and repeat.
- *`0005` is applied but not wanted yet, before any upload:* stop the API and the worker, run the downgrade preflight, then `alembic downgrade 0004`; the schema returns to `0004` exactly (round trip tested); start the previous images (`:pre-0005` tags).
- *Anything else, or doubt about the data:* stop API and worker, recreate the database and restore the verified dump (`DROP DATABASE`, `CREATE DATABASE`, `pg_restore`), then check `alembic current` = `0004`. The development database is empty today, so recreating it by `alembic upgrade 0004` is equivalent.

**5b. Rollback, downgrade and restore are three different operations**

| | PostgreSQL transaction rollback | `alembic downgrade 0004` | Restore from the backup |
|---|---|---|---|
| When it applies | only inside the failing `alembic upgrade` itself (one transaction); once the upgrade has committed it no longer exists | after `0005` is committed and is not wanted | after a serious problem, or when the data is in doubt |
| What it does | the database stays exactly as before the attempt; `alembic_version` stays `0004` | runs the migration's `downgrade`: drops `ingestion_jobs` and `documents.error_code` with its check | recreates the whole database from the dump |
| What can be lost | nothing | the jobs in flight and their bytes; `error_code` of failed documents (their fixed message stays); documents left `pending` or `processing` stay stuck (hence the preflight); data of `0004` is kept | everything written after the backup was taken (users, subjects, documents, chunks); the database is dropped first |
| Needs | nothing, it is automatic | API and worker stopped and the preflight passed | API and worker stopped, an explicit decision, a verified dump |
| Validated how | PostgreSQL transactional DDL; the upgrade has no non-transactional statement | `test_migrations_ingestion.py` (round trip) and the rehearsal of step 3.4 on a restored copy of the real backup | the restore test of step 3.4 |

The three are not interchangeable: a rollback cannot be used after the commit, a downgrade does not recover data that a failed upgrade or an operator mistake damaged, and a restore discards later work. Use the least destructive one that fits.

**6. Risk classification for the deployment decision** (the text of each risk stays in `technical-debt.md`)

| Class | Items |
|---|---|
| Needed before the migration operation | authorisation; rebuilt images; verified backup and restore test; API and worker stopped during the upgrade; migration before worker start |
| Blocks any deployment beyond the controlled MVP (public, untrusted uploaders, more than one API process) | TD-030 (one superuser account for API and worker, PDF child bounded but not a sandbox); TD-035 (upload limiter and slots in the memory of each API process); TD-034 (one worker, occupation up to about 55 s per pathological file, T-01 included, no fairness between subjects) |
| Accepted for the controlled MVP (local or course deployment, trusted teachers, one API process) | the three above, TD-029 (bytes in the table until terminal), TD-031 to TD-033 (fixture coverage of PDFs, no OCR, model validated on a small corpus) and TD-037 (time and shared-session sensitivity of some tests; CI only) |

Other points seen in the Docker review: the database, API and frontend ports are bound to `127.0.0.1`; only the worker has CPU and memory limits (4 CPUs, 2 GB) and a restart policy; the database, API and frontend have no limits and the database does not restart by itself; the API has no healthcheck; the API runs with `--reload` and a writable code mount, which is for development only; the worker code mount is read-only; the secrets are split per service and none is in an image or a versioned file. These are deployment topics, not blockers of the development migration.

Only `backend/app` is mounted into the backend container, so a **new migration file is not visible inside a running container**: rebuild it first (`docker compose up -d --build backend`) before running `alembic upgrade head` there, or run Alembic from the host with `DATABASE_URL` pointing to `127.0.0.1:5442` _(historical: after `database-least-privilege` use `db-migrate` with `MIGRATION_DATABASE_URL`; `db-migrate`, `db-migrate --downgrade` and `db-verify` also refuse to run unless the session is the migrator, before any statement)_. Running `alembic current` in the container shows which head it knows. Check for drift between models and migrations with `alembic check` (it must report no new operations).

### Administrative commands (teacher accounts and demo data)

Teacher accounts can only be created from the command line; no HTTP endpoint creates teachers or changes roles.

The commands run under the **CLI database role** (`asistente_cli`), with the credential in `backend/.env.cli` (copy `backend/.env.cli.example`; the password is `DB_CLI_PASSWORD` of `backend/.env.roles`). The API container never receives that file, and the API database role cannot insert a teacher or change a role (change `database-least-privilege`, group 8). The `cli` Compose service is in the profile `cli`, so a plain `up` never starts it; it waits for `migrate`. The older form `docker compose exec backend python -m app.cli ...` no longer works: the command needs `CLI_DATABASE_URL`, which only `backend/.env.cli` provides. `docker compose run --rm cli ...` starts the dependencies of the service (`bootstrap` and `migrate`) first; add `--no-deps` to skip them once the roles exist.

```bash
# Interactive hidden prompt (asks twice). The password is never accepted as an argument.
docker compose run --rm cli create-teacher --email teacher@example.com --name "Ana Teacher"
# Non-interactive: first line of standard input
printf '%s\n' "$TEACHER_PASSWORD" | docker compose run --rm -T cli create-teacher --email teacher@example.com --password-stdin

# Demo accounts: one teacher and one student, no subjects. Development and test only.
# Set the four SEED_* variables first (in backend/.env.cli or with `docker compose run --rm -e ...`).
# APP_ENV is not read from any API file and defaults to production, where the seed is refused:
# pass `-e APP_ENV=development` (or `test`) explicitly.
docker compose run --rm -e APP_ENV=development cli seed
```

- Passwords are 10-128 characters. Emails must be ASCII (lowercased; write internationalised domains in punycode, for example `user@xn--bcher-kva.com`). An existing email is never modified or promoted (non-zero exit).
- `seed` is idempotent (existing accounts are skipped), has no built-in credentials, prints no passwords, and refuses to run when `APP_ENV=production`.

### MVP local test circuit (fictitious data only)

The MVP is run by its developer with fictitious users, documents and data only. The privacy policy is an internal draft (TD-003, TD-063, TD-064): never use real students, real documents or personal data. Gemini is called for real only from this local stack, with the free-tier key in `backend/.env` (`GOOGLE_API_KEY`; the default model is `gemini-3.1-flash-lite`).

**What the interface offers today** (`http://localhost:5173`): register and sign in, the draft policy at `/privacy`, the consent screen that holds a student until the policy is accepted, the list of subjects, and for a teacher creating a subject, uploading documents (PDF, `.txt`, `.md`; fictitious material only), following their processing status and enrolling or removing registered students by e-mail on the subject page (`teacher-material-ui`, `teacher-enrollment-ui`). A student also has the chat of each subject at `/subjects/{id}/chat` (questions with their sources, history, deleting a conversation or the whole history; `student-chat-ui`), so the whole circuit can be tried in the interface. The API documentation is still useful for anything the screens do not cover: use the API documentation at `http://127.0.0.1:8000/docs` (sign in with `POST /auth/login`, then `Authorize` with the access token).

1. **Teacher:** create it from the command line (section above), then `POST /auth/login`.
2. **Subject:** in the interface, the form on the teacher's subject list (or `POST /subjects` with `{"name": "...", "description": "..."}`).
3. **Document:** in the interface, open the subject and use the upload form; the status goes from pending to ready by itself (or `POST /subjects/{subject_id}/documents`, multipart field `file`, answers 202; poll `GET /subjects/{subject_id}/documents` until `status` is `ready`; `failed` carries an error code).
4. **Student:** register at `/register` (or `POST /auth/register`) with a fictitious email; sign in at `/login`, tick the box on the consent screen. The teacher enrols the student on the subject page, section "Estudiantes inscritos" (the student account must exist: register first), or with `POST /subjects/{subject_id}/enrollments` and `{"student_email": "..."}`.
5. **Ask:** in the interface, open the subject from the student's list ("Preguntar sobre ..."), write a question and send it; the conversation list is labelled by date because the API gives no preview (TD-066). With the API: `POST /chat` with `{"subject_id": "...", "message": "..."}`; repeat with the returned `conversation_id` to continue the conversation. Each answer carries its `sources` (file name, page when the format has pages, rank, snippet). A question without relevant material answers `no_material` without calling Gemini.
6. **History:** `GET /conversations` and `GET /conversations/{id}/messages` (answers keep their sources); `DELETE /conversations/{id}` and `DELETE /users/me/conversations` erase them.

Checked on 2026-11-18 against the running stack with Gemini: 34 of 34 checks of the circuit above (including the authorization negatives, unenrolment and re-enrolment, and deletion) passed. The script is not part of the repository.

**Limits of the MVP to know when testing:** chat is limited to 20 requests per minute per client by default (`CHAT_RATE_LIMIT`); the teacher activity route (`GET /subjects/{id}/activity`) answers 404 unless `TEACHER_ACTIVITY_ENABLED=true`, which a real installation must not set before the privacy text, the legal review and the consent version are in place (TD-069); retrieval uses only the current message, so an elliptic follow-up such as "and in the dark phase?" answers `no_material`; the citation markers of the model are not guaranteed (TD-062); `gemini-2.5-flash` and `gemini-2.5-flash-lite` answer 404 for new keys and a high-demand 503 shows as `LLM_UNAVAILABLE`; accounts created in tests cannot be deleted through the API (`DELETE /users/me` is not implemented, TD-064); `docker compose up --build` is needed to run the current code in `worker`.

### Login and registration rate limiting: limitations

`POST /api/v1/auth/login` (`LOGIN_RATE_LIMIT`, default 10/minute) and `POST /api/v1/auth/register` (`REGISTER_RATE_LIMIT`, default 5/minute) are limited per client address, with independent counters, and answer 429 with `Retry-After`. The counters live in the memory of each backend process: they reset on restart, are not shared between workers or instances, and a distributed attack on one account from many addresses (including rotation inside an IPv6 prefix) is not covered. The address is the connection peer. The application never reads `X-Forwarded-For`, `Forwarded` or `X-Real-IP`, and the project starts Uvicorn with **`--no-proxy-headers`** (Dockerfile and compose): by default Uvicorn trusts loopback and rewrites the client address from `X-Forwarded-For`, which lets a client behind a same-host proxy, tunnel or sidecar that forwards the header unchanged rotate its address and bypass both limits. Consequently, behind a reverse proxy all clients share the proxy's address (one bucket) until you deliberately enable proxy headers with an explicit `--forwarded-allow-ips` list **and** a proxy that overwrites (not appends) `X-Forwarded-For`. When running Uvicorn by hand on the host, pass `--no-proxy-headers` too. A shared store (for example Redis) is a later hardening step. Unexpected exceptions are answered by an outermost middleware that logs only the exception type, method and path (no traceback or request data reaches the server log), SQL parameters are hidden in database error text, and an unreachable database returns 503 `SERVICE_UNAVAILABLE` on every endpoint. Tokens cannot be revoked before they expire (default 60 minutes); the user and role are re-read from the database on every request.

Create migrations with `alembic revision --autogenerate -m "describe change"` and **review** the generated file; every migration needs a working `downgrade`.

### Test database isolation

Tests that run migrations or destructive cleanup use `TEST_DATABASE_URL` only (from `backend/.env.test`, with `backend/.env` still supplying the application `DATABASE_URL` that the guard compares with; if that one is missing the tests abort, they never skip the comparison). Roles created by tests carry the reserved prefix `tstrole_` (`tests/role_support.py`), which no real role can match, and leftovers are swept by prefix only. A guard (`app/core/db_safety.py`) runs before any such connection and refuses to continue unless the database name ends in `_test`, differs from the database in `DATABASE_URL`, and `APP_ENV` is not `production`. If `TEST_DATABASE_URL` is missing, integration tests abort before connecting. Use `127.0.0.1` (not `localhost`) in URLs from the host: `localhost` may resolve to IPv6 first and the port is published on IPv4 only.

## Document ingestion: worker, model and limits

Uploads (`POST /api/v1/subjects/{id}/documents`) store the file and a job in PostgreSQL and answer `202`; the **worker** (`python -m app.worker`, Compose service `worker`, image target `worker`) extracts text, chunks it, embeds it with the real model and writes the chunks. The API also loads the embedding model at startup for RAG queries (`POST /chat`). Follow the progress by listing the documents of the subject (`status`: `pending`, `processing`, `ready`, `failed`; a failed document has `error_code` and `error_message`).

- **Start / stop:** `docker compose up -d --build worker` starts it (it waits for a healthy `db`); `docker compose logs worker` shows its log (job and document ids and failure codes only; never file names or text). `docker compose stop worker` is safe: its lease expires and another worker takes the job.
- **Restart and health:** the `worker` service has `restart: unless-stopped` and a healthcheck (`python -m app.worker_health`, every 30 s, 120 s start period for the model). The worker writes `/tmp/ingestion-worker.health` every 10 s **only while it makes progress**: the gap since its last finished step is under 120 s, or the step in progress is still inside the job deadline plus 120 s (a long inference is not a false positive). If neither holds, the worker ends itself with exit code **3** (`ingestion worker stalled` in the log) and the restart policy starts a new one; a healthcheck alone would not restart anything. An abnormal end (a crash or an out-of-memory kill) is restarted by the same policy, and the job is recovered by its lease like any other (attempt 2, no duplicate chunks). `docker compose ps` shows `healthy` or `starting`. Docker does **not** restart a container you stopped or killed by hand (`docker stop`, `docker kill`): start it again with `docker compose up -d worker`. A worker that refuses to start (exit code 2: bad model path, unsupported platform, invalid configuration) is restarted in a loop with Docker's growing back-off and a log line each time, without touching the database: read `docker compose logs worker`, fix the setting and recreate it. A frozen process that holds the interpreter lock, or a hang while the model loads, shows as `unhealthy` but is not restarted, and a database outage shows as healthy but idle (steps fail and are retried): watch `docker compose ps` and the log.
- **Read-only code:** the worker mounts `./backend/app` as `:ro` (the API keeps its writable mount so that a restart picks up your edits). The worker writes only to `/tmp` (the health file and the PyTorch cache); the root file system of the container is still writable and not read-only (hardening for change 13).
- **Model:** `paraphrase-multilingual-MiniLM-L12-v2`, 384 dimensions, CPU, offline. Both the API and the worker fail fast at start if the model is missing or returns vectors of another size. The API loads the embedder once at startup (`app.state.embedder`) and injects it into the chat endpoint. Fake embeddings (`EMBEDDER_BACKEND=fake`) exist for tests only and are refused in production.
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

**RAG evaluation (change `rag-golden-set-evaluation`).** `backend/tests/evaluation/` measures retrieval, refusal and source attribution of the chat pipeline on a fictitious golden set (`backend/tests/evaluation/golden_set/`, version in `VERSION`, README states that everything is fictitious). It uses the production functions and works only on the isolated test database (`TEST_DATABASE_URL`, name ending in `_test`, different from `DATABASE_URL`); it creates synthetic users, subjects, documents and conversations and deletes exactly those at the end, also when it fails. With `--create-schema` it migrates an empty test database and drops the schema it created; a database that already has a schema must be at the migration head and is never dropped.

```bash
# mechanics only (fake embedder and fake model), from backend/: what the automated suite checks
uv run python -m tests.evaluation --embedder fake --mode answers --llm fake --create-schema --env-file .env.test --env-file .env
# real embedding model (retrieval metrics and the threshold / top-k sweep): inside the backend container,
# with the harness mounted for the run (nothing in docker-compose.yml changes)
docker compose run --rm --no-deps -e PYTHONPATH=/app:/extra -e PYTHONDONTWRITEBYTECODE=1   -v <repo>/backend/tests:/eval/tests:ro -v <repo>/backend/.env.test:/eval/.env.test:ro   -v <repo>/backend/.venv/Lib/site-packages/langchain_text_splitters:/extra/langchain_text_splitters:ro   -v <output dir>:/eval/out -w /eval backend python -m tests.evaluation --mode retrieval --embedder local   --create-schema --env-file /eval/.env.test --db-host db --db-port 5432 --out /eval/out --revision <git revision>
```

The backend image has the embedding model and the Gemini client but not `langchain_text_splitters` (only the worker image has it), so the run mounts that pure-Python package from the host virtual environment; no image or dependency changes. The answers mode with the real model adds `--mode answers --llm gemini --allow-real-llm --max-calls 50 --ledger <ledger file, mounted writable>`: free tier, fictitious data only, never from CI. The ledger (`openspec/changes/rag-golden-set-evaluation/reports/real-request-ledger.json`) holds the total of real requests the owner authorised and what was spent. The run stops before its first call when it needs more than what is left, **reserves** its calls in the ledger before the first request (a killed process still leaves them spent) and settles the real number at the end; a ledger that cannot be written stops the run before any call. Mount the ledger's **directory** writable (a single bind-mounted file cannot be replaced atomically; the harness then writes it in place). Real runs are serial: the ledger is not locked (two processes started at the same time could both pass the check, so never start two real runs together; the rule "one authorisation, one run" assumes it). It guards against mistakes of the harness and the operator; it is not a security boundary (the file is in the repository), and only the owner raises `authorised_total`, at or above `spent` plus the requests planned. The harness builds the Gemini client with **one attempt per call** (the application's client retries on its own, which would turn one call into several requests), runs every call in one event loop, stops after two failures in a row and refuses a cap above 50 (the owner's authorisation); `--pause-seconds` (default 6) spaces the calls and `--only id1,id2` repeats only some cases. Do not run it at the same time as the integration suite: both use the same `_test` database, and `--create-schema` drops the schema it created. Reports (Markdown and JSON, with the golden set version, revision, embedder, model and settings) go to `--out`; secrets are scrubbed from everything written. Unanswerable questions that reach the model are listed with their answers for a person to read; nothing grades them automatically.

**Single controlled run of the answers baseline (task 3.3b of `rag-golden-set-evaluation`).** Tried twice on 2026-11-23 (18 requests, 10 of 45 cases answered, the rest failed with `503` and `504` of the provider, each run stopped by the rule of two failures; see `reports/2026-11-23-answers-runs-1-and-2.md`); task 3.3b stays open and a new attempt needs the owner's decision. The procedure below is what was followed. Facts: model `gemini-3.1-flash-lite`, free plan without billing; limits read by the owner in AI Studio on 2026-11-22: 15 requests per minute, 250 000 tokens per minute and 500 requests per day (per project, the day resets at midnight Pacific time); the pause of 6 seconds keeps the run at about 10 requests per minute. The golden set `v0.2-draft` sends **45** cases to the model (24 answerable, 8 follow-ups, 6 traps, 6 unanswerable, the injection question) and the ceiling of the harness is 50; a dry run with the real embedder and the fake model counted the 45 and kept the 45 answers.

Before the run, the owner: reads the usage of the day in AI Studio; edits `authorised_total` of the ledger to a value that leaves room for the 50 requests (**204 = `spent` 154, the historical estimate that is not reset or corrected, plus 50**); authorises the run expressly; and makes sure nothing else uses the key meanwhile. **One authorisation covers one run**: the run records in the ledger the total it ran under and a later run under the same value is refused before any call even when requests are left, so a second run needs a different value that the owner sets on purpose (the tool never writes `authorised_total` and never rewrites the history). The harness runs from the container as described above, with the directory of the ledger mounted writable at `/eval/out` (the file is `openspec/changes/rag-golden-set-evaluation/reports/real-request-ledger.json`):

```bash
python -m tests.evaluation --mode answers --embedder local --llm gemini --allow-real-llm \
  --max-calls 50 --pause-seconds 6 --ledger /eval/out/real-request-ledger.json --create-schema \
  --env-file /eval/.env.test --db-host db --db-port 5432 --out /eval/out --revision <git revision>
```

It stops by itself after two failed calls in a row and records the real number of requests in the ledger. The report keeps all the answers (fictitious data); read it before drawing conclusions, and do not compare it with the `v0.1` results without saying so.

**Role-bound mode (change `database-least-privilege`, group 9).** The same API and ingestion integration tests (the modules listed in `tests/conftest.py`, marker `least_privilege`) can run with the code under test connected as its production role instead of the superuser of the test cluster:

```bash
TEST_CLUSTER_IS_DISPOSABLE=true uv run pytest tests/integration --least-privilege -m least_privilege
```

The guarded test database is then built like production (bootstrap with the reserved `tstrole_` names, Alembic as the migrator, grants); `build_settings` (the API) uses the application role and `built_service` (the ingestion service) the worker role, while the seeding and inspection helpers keep the administrator URL, so no assertion changes. `TEST_CLUSTER_IS_DISPOSABLE=true` and `TEST_ADMIN_DATABASE_URL` (see `backend/.env.test.example`) are mandatory because the bootstrap closes `PUBLIC` on every database of the cluster: use the disposable test cluster, never the development database. `tests/integration/test_least_privilege_coverage.py` fails when an API route, a CLI subcommand or a worker path has no role-bound scenario, and `test_db_roles_effective.py` compares the privileges of the catalog with the matrix (run it with `-s` to print them).

Limits of the mode, so nobody over-reads it: the code under test is the API (`build_settings`), the ingestion service (`built_service`) and the ingestion repository sessions (`session_for`, worker role by default, `role="app"` for retrieval); seeding and inspection stay with the administrator, and repository-level tests of other modules (for example `test_chunk_retrieval`) are not in the marked list and run as before. The roles have connection limits (application 20): the fixture `release_leaked_connections` collects engines that a test left behind, and a failure with `database unavailable` in this mode means a test leaks connections, not that the limit should be raised. Do not combine, in one pytest process, the role fixtures that drop every `tstdb_%_test` database (`cluster`, used by the `test_db_*` files) with the session database of this mode: run them as separate invocations.

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

_(planned)_ `npm run test:e2e` will start the backend with `LLM_BACKEND=fake` and `EMBEDDER_BACKEND=fake` when the main flow exists. Automated tests always use fake LLM and embedding providers.

## 5. Branching and commits

- `main` is the integration branch and is never committed to directly once implementation starts.
- Implementation: one branch `feature/<change-name>` per OpenSpec change, created from `main` and merged back through a Pull Request. Conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`) in English.
- Course delivery branches (`feature/entrega-N-AN`, `final-project-AN`) are cut from `main` only when submitting a delivery; see `academic-requirements.md` §3 and §9.
- Before committing, review which docs must be updated (see `documentation-standards.md`).

## 6. Continuous integration

GitHub Actions (`.github/workflows/ci.yml`) on every push and Pull Request: backend lint, format check, `mypy --strict`, unit and integration tests (PostgreSQL service with pgvector, database `asistenteia_test` created in the job); frontend lint, format check, type check, unit tests and build; `pip-audit` and `npm audit` as non-blocking steps. Gemini is never called in CI. The mocked Playwright suite (`npm run test:e2e`) runs in the CI job `frontend`; the real-backend suite (`E2E_REAL_BACKEND=1`) is opt-in and does not run in CI (TD-041).

### The privilege gate (job `privileges`)

Change `database-least-privilege`, decision D5. The job `privileges` of the workflow is **mandatory**: it is what makes a backend change valid with respect to PostgreSQL privileges. It runs on every push and Pull Request against two PostgreSQL 15 + pgvector 0.8.7 service containers that exist only for that run (`flow` on port 5433 and `tests` on 5434; the throwaway administrator password in the workflow belongs to containers that live for the job on the runner and protects nothing). All logic lives in `.github/scripts/privilege_gate.sh`, one step per subcommand, so the same steps can be run locally (see below):

| Step | What it proves |
|---|---|
| `prerequisites` | every variable is present, otherwise the job fails naming it; four ephemeral role credentials are generated, masked in the log and kept in a private file of the runner temp directory (never an artifact) |
| `clusters` | each cluster is local, PostgreSQL 15 with pgvector 0.8.7, a superuser session, holds only the default databases (and, for `tests`, its own `tstdb_*_test`) and no `asistente*` role; the two are different servers. Nothing destructive happens before this passes, and it is checked again right before the flag `TEST_CLUSTER_IS_DISPOSABLE=true` is exported |
| `flow` | the real commands: `db-bootstrap`, `db-migrate` (Alembic to 0006 and the grants), `db-verify` without findings, `alembic check`, then a second idempotent pass |
| `drift-selfcheck` | a privilege outside the matrix is granted on purpose: `db-verify` must fail, and `db-grants` must heal it. A verifier that cannot see drift fails the job |
| `privilege-unit` | matrix, inventory (a table without a decision fails and is named), generated SQL, `FetchedValue` columns, and the workflow and script tests |
| `role-suites` | the role-bound integration suites (marker `role_bound`): bootstrap, adoption, grants, verify, lifecycle, denied operations, paths, teacher and CLI, ORM SQL inspection, consent and TD-039 persistence, API routes, effective privileges, coverage guards |
| `roles-mode` | the existing API and ingestion tests with the code under test as its production role (`--least-privilege -m least_privilege`), in a separate process so the fixtures of the previous step cannot interfere |
| `summary` | runs even after a failure: every report must exist, have no failure, no error, **no skipped test** and at least the expected number of tests (`MIN_UNIT`, `MIN_ROLE_SUITES`, `MIN_ROLES_MODE`); it prints the number of privilege tests executed and appends it to the job summary |

Rules the gate keeps (and `tests/unit/test_ci_workflow.py` enforces): `permissions: contents: read` for the whole workflow, no `secrets.*`, only `push` and `pull_request` triggers (never `pull_request_target`), GitHub-hosted runner with a time limit, checkout without keeping the token, no `continue-on-error`, `|| true`, `set +e` or `exit 0` in the job, `TEST_CLUSTER_IS_DISPOSABLE` set only by the gate script, and no administrator or role credential in the job-wide environment. The ordinary `backend` job runs the integration tests with `-m "not role_bound"`; the role-bound ones need the clusters of this job and are never skipped silently.

**Branch protection (to be applied by the repository owner; this change does not modify GitHub settings).** Require these status checks on `main` before merging, with "Require branches to be up to date" and no bypass for administrators if the owner wants the gate to bind everyone:

```bash
# Proposal only: nothing in this repository runs it. Replace OWNER/REPO and review before use.
gh api -X PUT repos/OWNER/REPO/branches/main/protection --input - <<'JSON'
{
  "required_status_checks": { "strict": true, "contexts": ["backend", "privileges", "frontend"] },
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null
}
JSON
```

The proposal is written for a repository with a single owner: with `enforce_admins: true` and a required review the owner could not merge their own Pull Request, so both are left off here; a team should turn them on. The `contexts` field is the classic form; a ruleset with the same three checks is equivalent.

What the gate does not prove, so nobody over-reads it: it was first validated step by step against disposable clusters with `run_gate_local.sh` (the semantics of Actions, a prebuilt local runner image and internal host names) and has since run on GitHub Actions for real (the pushes of `53031a1` and `8931d67`, with `backend`, `privileges` and `frontend` green; TD-045). No Pull Request has been opened yet, so the check name `privileges` on a real Pull Request and the behaviour for forks (which get a read-only token and no secret) are still unproved, and branch protection is not available on the current plan, so the gate is advisory until it is (TD-045). The minimums of executed tests (`MIN_UNIT` 60, `MIN_ROLE_SUITES` 400, `MIN_ROLES_MODE` 480, set below the 149, 410 and 484 tests of the last local run) are floors: raise them in `.github/scripts/privilege_gate.sh` when the suites grow, otherwise a deleted group of tests could go unnoticed. Actions are pinned to major tags; pin them to commit SHAs if the supply chain of the actions is a concern.

The job names `backend`, `privileges` and `frontend` are the check names; renaming a job removes it from the required checks without any warning, which is why the workflow test pins the job and its steps.

**Running the gate locally** needs Docker and at least 6 GB of free memory: `openspec/changes/archive/2026-11-16-database-least-privilege/reports/group-10/run_gate_local.sh <output> <scenario>` creates two disposable clusters on an internal network (no published port), runs the eight steps with the semantics of Actions (the first failing step stops the job, the summary always runs) and removes everything; the scenarios `missing-prerequisite`, `foreign-database`, `same-server`, `failing-test`, `new-table`, `skipped-test`, `too-few-tests` and `drift-blind` show that the job fails and why.

## 7. Troubleshooting

- A document stays `pending`: the worker is not running or cannot reach the database (`docker compose ps worker`, `docker compose logs worker`); after `INGESTION_JOB_MAX_AGE_HOURS` an unprocessed job ends `failed` with `JOB_EXPIRED`. A document `failed` with `PROCESSING_INTERRUPTED` lost its worker `INGESTION_MAX_ATTEMPTS` times.
- Uploads answer `503 INGESTION_QUEUE_FULL`: the queue, the pending bytes or the uploads in flight are at their limit; wait for the worker (`Retry-After`) or raise the corresponding setting.
- `extension "vector" is not available`: the database image must be a pgvector-enabled image (the pinned `pgvector/pgvector:0.8.7-pg15`).
- `port is already allocated` on 5432: the compose database is published on `127.0.0.1:5442` to avoid clashes with other local PostgreSQL instances; change the mapping in `docker-compose.yml` and `TEST_DATABASE_URL` together if 5442 is taken.
- Integration tests hang or time out connecting: use `127.0.0.1`, not `localhost`, in `TEST_DATABASE_URL`.
- Integration tests abort with `TEST_DATABASE_URL is required` or `Refusing to use database`: set a dedicated `*_test` database (see §3).
- Startup error `Invalid configuration - CORS_ORIGINS ...`: set explicit origins in production and never use `*`.
- Frontend page blank or `Failed to resolve import` after a dependency change: renew the container volume (`docker compose up -d --build -V frontend`).
- A container still has an old variable, or does not see a changed one: the effective environment of an existing container is the one it was created with, not what Compose or the `.env` files say now. List the variable **names** it holds (`docker exec <container> env | cut -d= -f1 | sort`) and compare them with its `env_file`; `docker compose up -d --no-build --no-deps --dry-run <service>` prints `Recreate` when the container no longer matches the configuration. Recreate only that service (`docker compose up -d --no-build --no-deps <service>`; named volumes are kept; never use `down -v`), after stopping the services that connect to a database you are recreating. Removing a variable from a container does not rotate its value: change the secret itself if the old container could have exposed it (TD-038).
- The administrator password is lost or rejected, or a role cannot log in: do not edit files by hand. While the `db` container runs, the rotation tool resets a role through the container's local socket without needing its old password (`rotate_db_role.py alter`, see the recovery table of `reports/group-17b/rotation/README-17b6.md`); the four working roles are also re-set from `.env.roles` by `db-bootstrap`.
- Gemini key and data: the free tier of the Gemini API may use what it receives to improve Google products and is not covered by a data processing addendum, so use it only with fictitious users and documents (TD-063). The MVP runs only with fictitious data; the pilot with real students over 18 needs the conditions of TD-003, TD-063 and TD-064 first. The default model is `gemini-3.1-flash-lite`; older defaults answer 404.
- Gemini 429/blocked responses locally: switch `LLM_BACKEND=fake` and `ALLOW_FAKE_LLM=true` in `backend/.env` to keep developing without the Gemini API. Restart the backend service.

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
