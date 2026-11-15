# Proposal

## Why

The API, the ingestion worker, Alembic, the CLI, the tests and the CI all connect to PostgreSQL as the bootstrap **superuser** of the official image (`TD-030`, accepted only for the controlled MVP). A SQL injection, a stolen connection string or a flaw in the PDF parser would therefore reach `COPY ... PROGRAM`, `pg_read_file`, `ALTER SYSTEM`, other databases and the whole cluster, not just the ingestion tables. `TD-030` already lists "a database role for the worker limited to the ingestion tables" inside the container-hardening change 13; this change carves the **database part** out as its own change, because it touches migrations, Compose start order, environment files and the test layer and needs its own review.

The analysis and a spike on a disposable PostgreSQL (2026-11-12, `reports/`) showed that the idea is sound and also found defects that a naive role split would have shipped: a one-chunk document needs `SELECT (id)` for the worker, a write that fails at commit is reported as `200` (consent endpoint), grants disappear when a downgrade recreates a table, and a bootstrap run with the default `search_path` can be hijacked from the application schema.

## What Changes

- **Five database identities** with minimal attributes: the existing administrator (cluster administration only), a **migrator** (owns every object, runs Alembic), an **application role** (API), a **worker role** and a **CLI role** (administrative commands: teacher provisioning and the seed; approved by the owner on 2026-11-12 as decision DD-9, option A, implemented in group 8). Only the migrator owns objects; none of the four non-administrator roles is a superuser, can create roles or databases, or belongs to any role.
- **A single declarative privilege matrix** (table and column level) derived mechanically from the statements the code really issues, including those implied by `RETURNING` and row locks, enforced by tests; a table without a decision fails the suite and is closed by default.
- **Commands** (`db-bootstrap`, `db-adopt`, `db-migrate` with its `db-grants` step, `db-verify`): an idempotent privileged bootstrap that runs with `search_path = pg_catalog`; an explicit, one-time adoption of an existing database; one command that applies Alembic and the grants in a single transaction per step so grants travel with the schema; a read-only verifier that compares the catalog with the matrix. The names are working names fixed in `design.md`.
- **Compose**: one-shot `bootstrap` and `migrate` services in the **default profile** between `db` and the API and worker (`service_healthy` then `service_completed_successfully`); idempotent on every `up`; roles switch with `up -d --force-recreate`.
- **Environment files**: each service receives only its own secrets; the superuser password and `TEST_DATABASE_URL` leave `backend/.env` (today they reach the API container); the migration service stops needing `JWT_SECRET`; tests get a host-only file.
- **Tests**: positive and negative privilege tests as a **mandatory CI gate**, integration tests that run the real API, CLI and worker under the roles and assert the **persisted state**, concurrency and planting tests for the risks found by the reviews.
- **Prerequisites of the role-bound suite (owner, 2026-11-13)**: the six extra `INSERT` columns are removed from the matrix through `FetchedValue()` (DD-14) and TD-039 is fixed with an explicit commit in registration, subjects and enrollments (DD-15), both before group 9.
- **Consent endpoint**: an explicit commit before the response and a persisted-state test (the defect is designed here; the code change is a separate functional commit in a later group).
- **Teacher provisioning**: public student registration is separated from administrative teacher provisioning also at database level. The owner approved option A of `design.md` DD-9 on 2026-11-12 as the target design (CLI role, column-level `INSERT` for the application role without `role`, server default `'student'` through a reversible migration `0006`); it was authorised and implemented in group 8 (migration `0006`, applied to the development database on 2026-11-14).
- Documentation (`docs/development_guide.md`, `docs/backend-standards.md`, `docs/data-model.md`, `docs/technical-debt.md` split of `TD-030` and new entries for the residual risks, `docs/lessons-learned.md`), the independent reviews and the rehearsal on a restored copy of the real backup.

Out of scope (decided by the owner, 2026-11-12): row-level security, `SECURITY DEFINER` functions, changes to `pg_hba.conf`, moving pgvector out of `public`, the PDF sandbox and the container hardening (read-only root file system, `cap_drop`, egress policy, process limits), rotating existing secrets (`TD-038`), any user interface, production deployment. The change stays inside the approved MVP scope: it protects authentication, role-based authorization and data isolation without adding product features.

**BREAKING**: for developers, `backend/.env` no longer holds the superuser password or `TEST_DATABASE_URL`, `DATABASE_URL` of the API and the worker point to different roles, and migrations run through the new command. Existing development data is kept; the rollout and rollback procedures are rehearsed on a restored backup first.

## Capabilities

### New Capabilities
- `database-roles`: the identities, ownership, privilege matrix, bootstrap, adoption, migration-with-grants, verification, denied administrative operations and data-preserving rollback that give each component only the database privileges it needs.

### Modified Capabilities
- `dev-environment`: Compose start order and idempotent one-shot services, per-service secrets, the host-only test variable and the role-bound test isolation, and the administrator-only `downgrade base`.
- `document-storage`: a table is closed until its privilege decision exists (and the matrix covers it).
- `privacy-consent`: the consent write is durable before the response and its persistence is tested.
- `role-based-access`: the runtime API database role cannot create teacher accounts; teachers are provisioned through the administrative path.
- `continuous-integration`: the privilege tests are a mandatory gate and fail, not skip, when their prerequisites are missing.

## Impact

- **Authorization / data isolation**: the database becomes a second line of defence: the worker cannot read `users`, `subjects` or `enrollments`, cannot create or delete documents or jobs and cannot update document fields it does not own; the API cannot update documents, jobs or chunks and cannot reach administrative features. The matrix keeps every existing repository-level scoping unchanged. Residual: a compromised worker can still write chunks for any existing document and read pending payloads (inherent to direct table access; row-level security is out of scope), recorded as technical debt.
- **Personal data (GDPR)**: password hashes and consent evidence stay readable only by the roles that need them; no value (password, verifier, token, connection string) is written to documents, logs or reports. The reports contain variable **names**, never values.
- **External services**: none.
- **Dependencies**: none new (psycopg's client-side SCRAM helper and Alembic are already installed).
- **Code**: `backend/app/core/` (settings for migration, privilege matrix), `backend/app/cli.py` (new subcommands), `backend/alembic/env.py`, `backend/app/api/v1/endpoints/users.py` or its service (explicit commit), later a migration `0006` only if the owner approves the recommended teacher-provisioning option; `docker-compose.yml`, `backend/.env*.example`, `.github/workflows/ci.yml`, `backend/tests/` (support, guard, new suites).
- **Docs**: `docs/data-model.md` (privileges), `docs/development_guide.md`, `docs/backend-standards.md` (least privilege), `docs/technical-debt.md` (TD-030 split, new entries), `docs/lessons-learned.md`; `docs/api-spec.yml` does not change.
- **Technical debt touched**: `TD-030` (database part resolved, the rest stays with change 13), `TD-038` (unchanged: secrets are not rotated here), new entries for the residual risks listed in `design.md`.
- **Dependent changes**: change 13 keeps the container hardening and the PDF isolation; change 12 may reuse `db-verify`.
