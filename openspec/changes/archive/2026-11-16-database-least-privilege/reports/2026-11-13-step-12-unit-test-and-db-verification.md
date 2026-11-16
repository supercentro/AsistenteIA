# Step 12: unit tests and database state verification (2026-11-13)

Branch `feature/database-least-privilege`, code at `58f633c` (the later commits of this step add reports and evidence only). Authorised scope: tasks 12.1 to 12.4. Nothing here touched the development database except read-only queries, no role, grant, migration, `.env`, container or service was created, changed or recreated, `docker compose up` was not run, nothing was pushed, and GitHub Actions has not run the new workflow (the branch is not on the remote): nothing below is remote validation.

## 12.1 Baseline before the tests (`group-12/snapshot-before.txt`)

Read-only: every statement is a `SELECT` or `SHOW` in a session with `default_transaction_read_only = on`, run with `docker exec` in the existing containers; no connection string or password is printed.

| Item | Development database `asistenteia` |
|---|---|
| Containers | `asistenteia-db-1` healthy, `asistenteia-worker-1` healthy |
| Server | PostgreSQL 15.19, extensions `plpgsql 1.0`, `vector 0.8.7` |
| `alembic current` / head of the code in the worker image | 0005 / 0005 |
| `alembic check` (inside the worker container, read-only session) | no new upgrade operations: no drift |
| Migration 0006 applied | no: `users.role` has no default (`(none)`) |
| Roles | only the owner `asistente` (superuser); new roles `asistente_*` or `tstrole_*`: 0 |
| Databases | `asistenteia`, `asistenteia_test`, `postgres`, templates; `tstdb_*`: 0 |
| Tables and owners | the seven tables are owned by `asistente` with the default ACL |
| Rows | users, subjects, enrollments, documents, document_chunks, ingestion_jobs: all 0 |
| `ingestion_jobs` | total 0, with payload 0, leased 0, max attempts 0 |
| Connections | two sessions of `asistente` (one active, one idle), 0 idle in transaction, no open transaction, 0 prepared transactions |
| Test database `asistenteia_test` of that cluster | exists, no `alembic_version`, 0 tables (empty); the tests of this step never used it: they ran on their own disposable clusters |

## 12.2 Tests

All Linux runs used PostgreSQL 15.19 + pgvector 0.8.7 in a disposable container on an internal Docker network without published ports, throwaway administrator and role credentials, 1 CPU / 1 GB, a copy of the repository without `.env` files, and the 6 GB memory gate (10 to 11 GB were free). Runner image: the Python 3.12 backend/worker image of `main`.

| Stage (output file in `group-12/`) | Result |
|---|---|
| 1 targeted unit tests of this change (`1-targeted-unit.txt`): endpoint commits, teacher provisioning, `FetchedValue` columns, matrix, inventory, generated SQL, CI workflow and gate scripts, Compose flow, environment files, consent endpoint | 233 passed, 4 skipped |
| 2 targeted role-bound integration (`2-targeted-role-bound.txt`): consent and TD-039 persistence, teacher and CLI, ORM SQL inspection, effective privileges, coverage guards | 33 passed |
| 3 migrations 0001 to 0006 (`3-targeted-migrations.txt`), including the 0006 upgrade, downgrade and round trip and `alembic check` | 34 passed |
| 4 **full unit suite on Linux** (`4-full-unit-linux.txt`) | **1309 passed, 12 skipped, 23 deselected, 0 failed** |
| 5 full integration, ordinary job selection `-m "not role_bound and not realmodel"` (`5-full-integration-ordinary.txt`) | 864 passed, 410 deselected |
| 6 full role-bound suites `-m role_bound` (`6-full-role-bound.txt`): bootstrap, adoption, grants, verify (`db-verify`), lifecycle, denied operations under the API, worker, CLI and migrator identities, paths, effective privileges, coverage | 410 passed, 864 deselected |
| 7 existing API and ingestion tests under the production roles `--least-privilege -m least_privilege` (`7-full-roles-mode.txt`) | 484 passed, 790 deselected |
| Windows host unit suite (`windows-unit.txt`) | **3 failed, 1208 passed, 110 skipped, 23 deselected** |

**The three Windows failures against the baseline of group 3** (`reports/group-3/windows-baseline.txt`, taken in a clean worktree of `main`): the same three ids fail, no more and no fewer: `test_worker_health::test_the_defaults_leave_room_for_the_beat_interval`, `test_worker_settings::test_a_fresh_worker_process_loads_its_settings_without_any_api_variable`, `test_worker_settings::test_importing_the_worker_does_not_pull_in_the_api`. They pass on Linux (stage 4), so they are specific to the Windows host and predate this change; nothing was edited to obtain a green run.

Skips, with their reasons (nothing is skipped without one): on Windows, 110 of PDF-child and resource-limit tests that run on Linux only (73 + 36 + 1), which stage 4 and the role stages cover on Linux (the PDF scenarios of stage 6 and 7 passed); on Linux, 12: 11 tests that need the Git metadata, which the copy of the repository does not carry (they ran and passed on the Windows host, and run in CI where the checkout has it), and 1 AES test that needs the `cryptography` package, which the runner image lacks (it ran on the Windows host).

Static gates (`static-gates.txt`, `openspec-validate.txt`, `pip-audit.txt`): `ruff check --no-cache` clean, `ruff format --check` 230 files already formatted, `mypy --strict app tests` no issues in 228 source files, `openspec validate --all --strict` 18 of 18, `pip-audit` no known vulnerabilities (exit 0).

## 12.3 State after the tests (`group-12/snapshot-after.txt`, `snapshot-diff.txt`)

The deterministic part of the snapshot (alembic revision, extensions, `users.role` default, databases, roles, tables with owners and ACLs, row counts, documents, users and `ingestion_jobs` states) is **identical** before and after (31 lines, no diff). The same read-only checks give: both containers healthy, `alembic current` 0005, `alembic check` without drift, the 0006 default absent, no new role, no `tstdb_*` database, two sessions of the owner, 0 idle in transaction, no open transaction, 0 prepared transactions. No restore was needed. No container or network of the tests is left (`docker ps -a` and `docker network ls`).

## Deviations and risks

- The first run of stage 4 gave 2 failures (`FileNotFoundError` for `frontend/src/lib/privacyPolicy.ts`): the runner copy of the repository did not include that file, which a unit test compares with the backend constant. The code and the tests were not changed; the runner script now copies that one file and stage 4 was re-run (1309 passed, 0 failed). The output of the first run was overwritten by the re-run (the file holds the re-run); the two failures are quoted here from that first run.
- The Linux runs use a local runner image and internal host names; they are not GitHub Actions runs. The workflow job `privileges` has not run on GitHub, branch protection is not applied, and the marker-based split between the ordinary job and the gate depends on file-name prefixes (see the regression review of group 11).
- The development database still runs without the roles, 0006 and the narrow matrix (TD-040): everything above proves the target state only on disposable clusters.
- `docs/technical-debt.md` was not changed in this step.

## Reproduce

`group-12/db_snapshot.sh <label>` (read-only, needs Docker and the existing containers), `group-12/run_linux_tests.sh <output> <pytest arguments>` (needs Docker and 6 GB free), and the commands of `group-12/static-gates.txt` from `backend/`.
