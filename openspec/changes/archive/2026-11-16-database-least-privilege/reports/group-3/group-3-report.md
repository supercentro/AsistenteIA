# Group 3: settings and environment files (2026-11-12)

Branch `feature/database-least-privilege`. Authorised by the owner: group 3 only; group 4 and later are not authorised. No Docker (free memory 5.9 GB, below the 6 GB gate), no database connection, no real role, password, `.env` file, Compose file or container was touched.

## Tasks

| Task | Result |
|---|---|
| 3.1 failing tests first | RED recorded in `tdd-red.txt` (26 failed, 8 passed, 3 collection errors, before any implementation); GREEN below |
| 3.2 `MigrationSettings`, `alembic/env.py`, CLI skeletons | `MigrationSettings` and `RolesSettings` (bootstrap) in `app/core/config.py`; `alembic/env.py` reads only `MigrationSettings`; the commands `db-bootstrap`, `db-adopt`, `db-migrate`, `db-grants`, `db-verify` are declared and fail with "not implemented yet" without loading the API settings. `CliSettings` stays in task 8.5 (it belongs to the CLI role, group 8) |
| 3.3 environment files | Examples `.env.migrate.example`, `.env.roles.example`, `.env.test.example`; `TEST_DATABASE_URL` removed from `.env.example`. `.gitignore`/`.dockerignore` already cover `.env.*` (proved by tests), so no pattern changed |
| 3.3b real files | **Not done, by order**: the real `backend/.env` was not read or edited in this stage (the spike record `A-04` found `POSTGRES_*` and `TEST_DATABASE_URL` in it); creating the real `.env.migrate`, `.env.roles`, `.env.test` and cleaning `.env` needs a specific authorisation. Task split as 3.3b and left open |
| 3.4 guard and role prefix | `tests/db_support.py`: `load_test_environment` (real env > `.env.test` > `.env`), the guard now fails closed when the application `DATABASE_URL` is missing (it used to skip the comparison silently), `require_test_admin_database_url`; `tests/role_support.py`: reserved prefix `tstrole_`, name validation, prefix-only sweep. Integration `conftest.py` uses the loader |
| 3.5 guide | `docs/development_guide.md`: new files, variable table, Alembic note, test environment |

## Configuration architecture

| Consumer | File | Variables | Settings class |
|---|---|---|---|
| API | `backend/.env` | `DATABASE_URL` (application role), JWT, CORS, limits | `Settings` (unchanged) |
| Worker | `backend/.env.worker` | `DATABASE_URL` (worker role), ingestion limits | `WorkerSettings` (unchanged) |
| Database container | `backend/.env.db` | `POSTGRES_*` | none |
| Migration service and manual Alembic | `backend/.env.migrate` | `MIGRATION_DATABASE_URL` only | `MigrationSettings` |
| Role bootstrap | `backend/.env.roles` | `ADMIN_DATABASE_URL`, four role passwords | `RolesSettings` |
| Host-only tests | `backend/.env.test` | `TEST_DATABASE_URL`, `TEST_ADMIN_DATABASE_URL` | read by `tests/db_support.py` |
| CLI role | (task 8.5) | | `CliSettings` later |

Rules enforced by tests: each secret variable is declared in exactly one example; the API example holds no `POSTGRES_*`, test, migration, administrator or role-password variable; `MIGRATION_DATABASE_URL` is deliberately not `DATABASE_URL`, so Alembic run with the API environment fails ("`MIGRATION_DATABASE_URL: Field required`") instead of using another credential; URLs and passwords are `SecretStr`, validation messages name the variable and never the value; role passwords must be at least 16 characters, not placeholders and all different; administrator URL for tests must name the same server as the test database and is refused in production.

## Behaviour changes (compatible where possible)

- **Alembic by hand now needs `MIGRATION_DATABASE_URL`.** A manual `alembic upgrade head` in the current API container fails by design. The guide gives an explicit one-liner (`docker compose exec -e MIGRATION_DATABASE_URL=... backend alembic ...`); I did not run it (no Docker in this stage). The tests and the CI are unaffected: they pass an explicit URL to Alembic. The `migrate` service of group 6 makes this permanent.
- The integration guard now requires `DATABASE_URL` (CI sets it; the real `backend/.env` has it). A legacy `TEST_DATABASE_URL` in `backend/.env` still works.
- `python -m app.cli` parses its arguments before loading the settings; the existing commands behave as before.

## Evidence

| File | What |
|---|---|
| `tdd-red.txt` | failing run before the implementation |
| `mutation-checks.txt` | five mutations (fall back to the API settings, silent guard, any role name accepted, repeated role passwords, test variable back in the API example): each fails the suite; files restored |
| `alembic-cli-evidence.txt` | the real `python -m alembic upgrade head --sql` with only `MIGRATION_DATABASE_URL` (works, no JWT) and with the API environment only (fails naming the variable); synthetic credentials, none appears in the output |
| `windows-baseline.txt` | classification of the three failing unit tests |

## Classification of the three Windows failures

All three fail identically in a clean worktree of `main` (`3b312e4`, venv outside the repository), so none is introduced by this change: `test_worker_health.py::test_the_defaults_leave_room_for_the_beat_interval` asserts a POSIX `/tmp/` path (Windows-dependent); the two `test_worker_settings.py` tests start a subprocess with `env={"PYTHONPATH", "PATH": ""}` and, without `SYSTEMROOT`, `import asyncio` fails with WinError 10106 (demonstrated with a probe: exit 1 without it, exit 0 with it). They pass in Linux CI. No existing test was modified to make them pass.

## Gates

| Gate | Result |
|---|---|
| `ruff check --no-cache .`, `ruff format --check .` | clean |
| `mypy --strict app tests` | no issues in 185 source files |
| `pytest tests/unit` | 1020 passed, 110 skipped, 3 failed (the three above); 106 new tests, all pass |
| `pytest tests/integration --collect-only` | 857 collected, no import error; **not run** (needs PostgreSQL in Docker and 6 GB free) |
| `openspec validate --all --strict` | 18 of 18 |

## Open points

- 3.3b needs the owner's specific authorisation.
- The integration suite was not executed against a database after the changes of `tests/db_support.py` and `tests/integration/conftest.py`; the guard behaviour is covered by unit tests with no connection. It must run in the next stage that has memory and authorisation (and in CI).
- The `docker compose exec -e` one-liner of the guide is untested here.
- Evidence still pending from group 2 (adoption with data, ownership recovery, catalog readability, connection limits, rollback) is untouched.
