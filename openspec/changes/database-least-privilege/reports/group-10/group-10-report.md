# Group 10: the PostgreSQL privilege gate in CI (2026-11-13)

Validated on the final code, commit `22f2f27`. Everything ran on disposable PostgreSQL 15.19 + pgvector 0.8.7 clusters on an internal Docker network without published ports, with free RAM above 6 GB. The development database stays at revision 0005 (migration 0006 and the narrow matrix were applied only to disposable clusters), `asistenteia-db-1` and `asistenteia-worker-1` were not touched, no real role, `.env` file or container was changed, `docker compose up` was not run, and no GitHub setting was modified (branch protection is only documented).

## Tasks

| Task | Result |
|---|---|
| 10.1 failing workflow test first, then the job | `tests/unit/test_ci_workflow.py` and `test_ci_gate_scripts.py` failed first (`red-workflow.txt`). Job `privileges` in `.github/workflows/ci.yml` with the logic in `.github/scripts/` (`privilege_gate.sh`, `assert_disposable_cluster.py`, `check_results.py`, `alembic_check.py`) |
| 10.2 a missing prerequisite fails, never skips; the number of tests is reported | scenario `missing-prerequisite`; the `summary` step prints and publishes the number of privilege tests executed (1043 in the final run) and fails on a missing report, a failure, an error, a skipped test or fewer tests than the floor |
| 10.3 workflow test, and a table without a decision fails | 51 unit tests of the workflow and the scripts; scenario `new-table` (a model and migration 0007 without a matrix decision): the job fails at `flow` with `[tables] table undecided_things has no decision in the matrix`; the matrix unit tests fail the same way in `privilege-unit` |

## Architecture of the CI cluster

Two PostgreSQL service containers of the same pinned image (`pgvector/pgvector:0.8.7-pg15`), created for each job run and destroyed with it: `flow` (port 5433) runs the real commands, `tests` (port 5434) runs the suites that build clusters of their own. Steps, in order (each is one subcommand of `privilege_gate.sh`, under `set -euo pipefail`): `prerequisites` (variables present, four ephemeral role credentials generated, masked, kept in a private file of the runner temp directory, never an artifact), `clusters` (each cluster is local, PostgreSQL 15, pgvector 0.8.7, superuser session, only the default databases and no `asistente*` role; the two are different servers), `flow` (`db-bootstrap`, `db-migrate` to 0006 with grants, `db-verify` without findings, `alembic check`, then a second idempotent pass), `drift-selfcheck` (a privilege outside the matrix is granted: `db-verify` must fail with that cause and `db-grants` must heal it), `privilege-unit`, `role-suites` (marker `role_bound`), `roles-mode` (`--least-privilege -m least_privilege`, a separate process because the role suites drop every `tstdb_*_test` database) and `summary` (`if: always()`). `TEST_CLUSTER_IS_DISPOSABLE=true` is exported by the script only after the `tests` cluster proved again that it is the exclusive empty one; it appears nowhere in the workflow file. The administrator credentials of a cluster reach only the commands that create roles and the tests that build clusters; the API and worker processes of the tests receive role URLs only.

## Results of the gate (`gate-*.txt`, final code, one process per step as in Actions)

| Scenario | Job result | Cause reported |
|---|---|---|
| happy | passed, exit 0 | 149 privilege unit + 410 role-bound + 484 roles-mode tests = 1043, 0 failed, 0 skipped; revision 0006; `alembic check` without drift; second pass idempotent; drift detected and healed |
| missing-prerequisite | failed at `prerequisites`, exit 1 | `missing prerequisite PG_ADMIN_PASSWORD` |
| foreign-database | failed at `clusters`, exit 1 | `the cluster holds the database asistenteia, it is not empty` |
| same-server | failed at `prerequisites`, exit 1 | `the two clusters need different ports` |
| failing-test | failed at `privilege-unit`, exit 1 | the application role lost a privilege the code needs |
| new-table | failed at `flow`, exit 1 | `table undecided_things has no decision in the matrix` |
| drift-blind | failed at `drift-selfcheck`, exit 1 | `db-verify did not detect a privilege outside the matrix` |
| skipped-test | failed at `summary`, exit 1 | `1 test(s) skipped (a privilege test never skips)` |
| too-few-tests | failed at `summary`, exit 1 | `175 tests executed, fewer than the expected 400` |

Also on the final code: unit 1208 passed + the 3 known Windows baseline failures; the `backend` job selection (`-m "not role_bound and not realmodel"`, `backend-job-integration.txt`); ruff, format, mypy strict and `openspec validate --all --strict` (see the chat report). Mutations of the gate: 29 of 29 caught (`mutation-gate.txt`): a `continue-on-error`, the token rights, a summary without `always()`, `pull_request_target`, `|| true`, a checkout that keeps the token, a self-hosted runner, two clusters on one port, an administrator URL job-wide, the role-bound tests back in the backend job, a dropped step, `set -u` instead of `set -euo`, the flag exported early, skipped tests or a shortfall accepted, problems that do not fail the process, any version, foreign databases, project roles or a remote host accepted, a summary without the role-bound report, lowered minimums, another marker, a roles mode without its option, a missing second pass, any drift failure accepted, the prefixes that make cluster tests role-bound, a database behind the head accepted and two names for one server.

## Independent review (read-only, clean context): PASS WITH GAPS

No Critical or High finding. Workflow security found clean (read-only token, no secrets, no `pull_request_target`, no expression reaching a shell, checkout without credentials, GitHub-hosted runner, no role test excluded from both jobs). Dispositions:

| ID | Disposition |
|---|---|
| M1 the local harness is not the real CI execution path | accepted and stated: the first run on GitHub is the proof of `uv run`, the service ports, the check name `privileges` and the fork behaviour (guide and below) |
| M2 the script wiring was not mutation-checked | fixed: wiring tests (summary reports and floors, `-m` selections, second pass, drift cause) and nine mutations |
| L1 `distinct` compares names | fixed: `localhost` and `127.0.0.1` are one server |
| L2 the host name is trusted | accepted: in CI the only reachable hosts are the two service ports |
| L3 the minimums are tight and one-sided | documented as floors to raise when the suites grow |
| L4 command substitution inside `env` lists | accepted: the credentials count is checked and every command fails without its variables |
| L5 any `db-verify` failure counted as drift | fixed: the failure must carry the cause of the injected privilege |
| L6 mutable tags, timeouts, token in the other jobs | partly fixed: timeouts and `persist-credentials: false` in all three jobs; SHA pinning documented as optional |
| L7 the coverage guards of group 9 are source greps | accepted; plus a new guard: every module that builds a cluster is `role_bound` and none is left out |
| L8 documentation | fixed: the branch protection proposal fits a single owner; revisions compared numerically |

## Group 9 corrections M1 and M2: evidence

`session_for` connects as the worker (the application role for retrieval) in the roles mode (`tests/ingestion_support.py`), the coverage guards derive the worker methods from `IngestionJobRepository` and check each route request (`test_least_privilege_coverage.py`), both run in the `role-suites` step (410 tests, 0 failed), and a regression is caught by the roles mode (484 tests) and by the guards.

## What cannot be proved locally

The first execution on GitHub Actions: `uv run --frozen` and `setup-uv` in the job, the host-mapped service ports on the hosted runner, the required-check name `privileges` on a real Pull Request, fork Pull Request behaviour, and branch protection itself (to be applied by the owner).
