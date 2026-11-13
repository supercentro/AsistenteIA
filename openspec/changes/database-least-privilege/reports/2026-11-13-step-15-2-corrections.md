# Task 15.2: corrections of the independent review (2026-11-13)

Branch `feature/database-least-privilege`, starting from `5a6496e`. Authorised scope: task 15.2 only (limited authorisation of 2026-11-13). Groups 16 to 19 and task 3.3b were not run. The development database, its worker, the real `.env` files, the roles and the passwords were not touched (the real files were not read; the real stack was not recreated; `docker compose up` was not run on it; every container used was a disposable one with a throwaway cluster, 1 CPU, 1 GB, no published port, and more than 6 GB of free RAM before each run). Nothing was pushed. GitHub Actions has not run the workflow. Evidence: `group-15/` (RED and GREEN runs, final gates, mutations, frontend gates), `2026-11-13-credential-exposure-incident.md`.

## Status of every finding

| ID | Severity | Status | What was done / why it stays open |
|---|---|---|---|
| PG-01 | Medium (major) | **Fixed** | `app_factory` and `app.worker.main` ask the server for the effective identity (`is_superuser`, `rolsuper` of `session_user` and `current_user`) and refuse a superuser or an unverifiable connection; the test-only exception is rejected unless `APP_ENV=test`; the examples carry `asistente_app` and `asistente_worker`; the two tests that pinned the administrator are replaced; the guide is corrected |
| PG-02 | Medium (major) | **Fixed** | `db-migrate`, `db-migrate --downgrade` and `db-verify` open a first session and require `session_user` and `current_user` to be the migrator before Alembic or any statement |
| F-1 / B-1 | Medium | **Fixed** | `DELETE` of a document uses `commit_or_rollback`; the contract documents its `500` and `503`; unit, AST and real-PostgreSQL tests |
| F-2 | Low-Medium | **Fixed** | a lost connection at commit is a 503 and the contract says the outcome is uncertain; a refused write is a 500 (tests through the real handlers); the 500 no longer claims "nothing was stored" in every case |
| F-3 | Medium | **Mitigated, risk stays in TD-039** | no route was added; `test_commit_failure_responses.py` fails when a write route or handler is added without being classified and without the shared helper; the future erase and chat endpoints are written into TD-039 for their own changes |
| PG-07 | Low | **Fixed** | `db-bootstrap`, `db-adopt` and its rollback refuse `postgres`, `template0`, `template1` (any spelling) before connecting; the rollback acts only on the named database, reports the others and keeps refusing to remove the roles while any object remains |
| PG-08 | Low | **Documented, not changed (blocked)** | changing the row counts inside the adoption lock, the per-database rollback transaction, the cluster-wide closing of `PUBLIC` and the grantor handling changes the adoption procedure: recorded as TD-044 and in the dangerous-operations checklist; needs the owner's authorisation |
| PG-03 | Medium | **Open, recorded (TD-042)** | needs a migration (`payload_size`) and a change of the matrix: a new change |
| PG-04 | Low-Medium | **Open, recorded (TD-043)** | extends `db-verify`: a follow-up change |
| PG-05 | Low | **Open, recorded (TD-044)** | the grants outside Alembic's transaction: documented limit and rule "always `db-migrate`" |
| PG-06 | Low | **Open, recorded (TD-043)** | `attacl` of strangers not checked |
| PG-09, PG-10 | Info | Accepted | design risks R7, R9, D4; the spec wording of `db-verify` is a documentary difference left as is |
| F-4 | Low | **Open, recorded (TD-047)** | changes a documented, tested contract: owner's decision |
| F-5, F-6, F-7 | Info | Accepted | inherent to commit-then-respond / threadpool; F-6 stated in the contract |
| C-1 | Medium | **Open, recorded (TD-045)** | GitHub has never run the job; branch protection is the owner's |
| C-2 | Medium | **Partly fixed, open (TD-045)** | the guide now says 149 (it said 133); the floors were not changed: moving them changes the gate and its tests |
| C-3 | Medium | **Open, recorded (TD-046)** | a test of module classification is a follow-up |
| C-4, C-5, C-6 | Low | **Open, recorded (TD-045)** | pinning by SHA, the guard's trust in the URL host, linting `.github/scripts` |
| C-7, C-8 | Info | Accepted | inspected controls |
| D-1 | Medium | **Fixed** | TD-039 widened, TD-040 updated, TD-042 to TD-047 added, TD-038 linked to the incident |
| D-2 | Medium | **Fixed** | the development guide has seven mandatory preconditions and the known limits before any dangerous operation |
| D-3 | Low | **Fixed** | `tasks.md` header and the "Playwright not run in CI" sentence corrected |
| D-4 | Low | **Fixed** | L28 and L29 added to the lessons summary; L30 to L32 recorded |
| D-5 | Low | **Partly fixed** | `.env.roles.example` mentions `.env.cli`; the docstring count removed; the `SEED_*` lines in `.env.example` are commented examples, left as they are |
| Credential printed by a reviewer | incident | **Recorded, rotation prepared, not executed** | see the incident report |

No finding was closed only by being recorded as debt: every "open" row above is open.

## TDD evidence (RED then GREEN)

| Group | RED (before the code) | GREEN |
|---|---|---|
| PG-01 unit | `group-15/red-pg01.txt`: the module did not import | 21 passed |
| PG-01 examples | `red-pg01-examples.txt`: 3 failed against the old examples | 39 passed (deployment files) |
| PG-01 real PostgreSQL | **deviation**: written after the code; compensated by mutations 0 to 5 | 23 passed together with PG-02 (`green-pg02-identity.txt`) |
| PG-02 | `red-pg02-identity.txt`: 10 failed, 1 passed (the first test shows Alembic running as the administrator) | 11 passed |
| F-1/F-2 unit and contract | `red-transactions.txt`: 12 failed, 30 passed | 57 passed |
| F-1 on real PostgreSQL | **deviation**: `red-document-delete.txt` shows the new integration test passes with the previous handler, because a bare `commit()` already ended in `get_db`'s rollback; the RED of the fix is the unit and AST tests | `green-document-delete.txt`: 7 passed |
| PG-07 guard | `red-pg07-guard.txt`: failed with a connection error instead of the refusal | 25 passed |
| PG-07 rollback | `red-pg07-rollback.txt`: 3 failed, 1 passed | 35 passed with the adoption and bootstrap tests |

## Identity and privilege tests (real PostgreSQL 15.19 + pgvector 0.8.7)

The administrator, a superuser with a service-like name, `SET ROLE` to an unprivileged role from a superuser session, an unreachable server and a wrong password are refused; `asistente_app`-like and worker roles and an unprivileged role with an administrator-like name are accepted; the API process (a real Python process) refuses the administrator and starts as its own role; the worker process refuses the administrator with exit code 2; `db-migrate` as the administrator or the application role creates no table and changes no owner; `downgrade` as the administrator leaves revision `0006` and the migrator ownership; `db-verify` as the administrator or another role is refused; no message carries the password.

## Final gates on the final code (`group-15/final-*.txt`)

| Gate | Result |
|---|---|
| `ruff check --no-cache`, `ruff format --check`, `mypy --strict` (233 files) | clean |
| Unit, Linux (disposable) | **1376 passed**, 12 skipped, 0 failed |
| Unit, Windows host | 3 failed, 1275 passed, 110 skipped: the same three ids as the baseline of group 3 |
| Integration, ordinary job selection | 864 passed |
| Integration, role-bound suites (`-m role_bound`) | 438 passed (410 before this task; +28 new) |
| Existing tests under the production roles (`--least-privilege -m least_privilege`) | 484 passed |
| Migrations, administrative commands | included in the stages above |
| Frontend: lint, format, typecheck, `check:api-types`, `test:coverage` | all exit 0 (statements 97.68 %) |
| `openspec validate --all --strict` | 18 of 18 |

Mutations of the critical controls (`group-15/mutations-result.txt`, copies in a scratch directory, a fresh cluster per run, each baseline proved green): **20 of 20 caught** (superuser check removed or weakened or failing open, entry points not checking, the exception outside `APP_ENV=test`, the identity checks of the three commands, the bare `commit()`, the missing rollback, 503 and 500 swapped, the three system-database guards, the rollback in the wrong database, the unreported databases, the missing-database check). Limits: the runner stops at the first failing test of each mutant, so the integration twin of a unit target is not shown for the mutants that a unit test catches first; the contract text is not mutated (the harness copies `backend/` only).

## Behaviour change to know

On this machine the development API and worker still use the administrator (TD-040). With this code, restarting or rebuilding either with the current URL is refused with a clear message until group 17 gives them the restricted roles. Nothing was changed in the real files, and the test-only variable must not be used as a workaround.
