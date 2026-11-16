# Group 6: Compose services, deployment-file tests and H13 with the real commands (2026-11-13)

Branch `feature/database-least-privilege`. Authorised: group 6 only. No real role, password, `.env` file or container of the project was touched: the real stack (`asistenteia-db-1`, `asistenteia-worker-1`) kept running and healthy, nothing was recreated, `docker compose up` was never run on the project, and every start happened in the scratch project `g28h13` with synthetic credentials.

## Tasks

| Task | Result |
|---|---|
| 6.1 failing tests first | `tests/unit/test_compose_database_flow.py` (new) and `test_deployment_files.py` (updated for six services). RED: `tdd-red.txt`, 13 failures before the Compose change. GREEN: 55 tests |
| 6.2 services | `docker-compose.yml`: `bootstrap` (`db-bootstrap`, `.env.roles`) and `migrate` (`db-migrate`, `.env.migrate`) in the default profile, `restart: "no"`, no ports, no volumes, built from the `api` target; `backend` and `worker` depend on `db` healthy and `migrate` completed. `.env.roles` and `.env.migrate` are `required: false` so `ps`, `logs`, `exec` and `down` keep working where the files do not exist; running a one-shot without its file fails at once (case E below) |
| 6.3 guidance | `docs/development_guide.md`: the Compose flow, `up -d --build`, `restart` versus `up`, how to read a failed one-shot, a warning at the quick start, the Compose 2.24 requirement and the `$` caveat of env files |
| 6.4 H13 with the real commands | `run_h13_real.sh`, `compose.h13.real.override.yml`, `h13-real-output.txt` |

## H13 with the real commands (scratch project, disposable PostgreSQL 15.19 + pgvector 0.8.7, no published port)

Image `asistenteia-backend:g6-branch` built from this branch (`docker build --target api`), worker `asistenteia-worker:main-f455234`.

| Scenario | Result |
|---|---|
| A1 cold start from nothing | `up -d` rc 0: db healthy -> bootstrap exited 0 -> migrate exited 0 -> backend and worker healthy; roles with the designed limits (20/3/5/10), none superuser; revision 0005; all public tables owned by the migrator; one session each for the application and worker roles; `db-verify` run from a container: no findings; `/health` 200 |
| A2 secrets by container (variable names only) | `db`: `POSTGRES_*`; `bootstrap`: `ADMIN_DATABASE_URL` and the four passwords; `migrate`: `MIGRATION_DATABASE_URL`; `backend`: `DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGINS`; `worker`: `DATABASE_URL` and its limits, no JWT; no `TEST_*` anywhere; 0 published ports |
| A4 second `up -d` | bootstrap and migrate ran again; privilege fingerprint equal; backend and worker containers not recreated; `db-verify` clean |
| A5 `restart` versus `up -d` | `restart` kept `LOG_LEVEL=INFO`; `up -d` recreated the worker with `DEBUG` |
| A6 credential rotation | `up -d` recreated the worker, bootstrap applied the new password; checked over the network from another container: the old password is refused, the new one is accepted; `db-verify` clean |
| B bootstrap fails (wrong administrator password) | `up -d` rc 1; bootstrap exit 1 with `cannot connect to db:5432 as asistente (SQLSTATE none, OperationalError)` (no password); migrate, backend and worker `created`, never started; recovery after fixing: all healthy |
| C migrate fails (wrong migrator password) | `up -d` rc 1; migrate exit 1; backend and worker `created`; recovery: all healthy, revision 0005 |
| D second cold start | same as A1 |
| E one-shots started without their env files | see the output file: `up -d` fails, the one-shot stops naming the missing variable, the dependants stay `created` |
| every round | teardown left no container, volume or network; the other containers of the machine were identical before and after |

### What H13 does not cover (stated per review G6-03)

It overrides `build`, `command` (no `--reload`), `volumes` (no source mounts), `ports` and adds a healthcheck to `backend`, runs the worker on the image of `main` (the worker code did not change), excludes the frontend and replaces the env files with scratch files (except in case E). The `dev-environment` "clean start" scenario with the frontend on 5173 therefore has no evidence here; `asistenteia_test` is checked in the scratch database (created by `docker/db-init`). The unit tests prove the committed file; H13 proves the flow with real commands.

## Configuration security

Verified by tests and by H13: no service receives another service's secret (`.env.db`, `.env.roles`, `.env.migrate`, `.env` and `.env.worker` each reach one service; none shared); the API has no `POSTGRES_*`, `ADMIN_*`, `MIGRATION_*`, `DB_*_PASSWORD` or `TEST_*`; the worker has no `JWT_SECRET`; the migrator does not use the API `DATABASE_URL`; the one-shots run once and exit, mount nothing, publish nothing; 14 mutations of `docker-compose.yml` caught (`mutation-compose.txt`: broken order, missing dependency, restart, port, privileged, host network, docker socket, shared file, working-tree mount, profile, inline secret, loopback). Residual (G6-04): an exited `bootstrap` container keeps the administrator URL and the four passwords in its `Config.Env` until it is removed (`docker compose rm -f bootstrap`); recorded for group 18.

## The six extra INSERT columns

Analysis, experiment and proposal: `orm-insert-columns-analysis.md`, `test_orm_insert_columns.py`, `orm-experiment-run.txt`. Summary: SQLAlchemy sends every column that has no default of any kind as `NULL`; a Python-side `default=None` does not help; `server_default=FetchedValue()` (plus `eager_defaults=False` for `ingestion_jobs`) or a Core insert removes them; priority 1 is `locked_by`/`locked_until` for the API. Nothing was implemented; the matrix keeps the six columns provisionally.

## Independent review (second, read-only, clean context)

Verdict: group 5 PASS WITH GAPS (all claimed fixes verified, two evidence caveats) and group 6 PASS WITH GAPS (no Critical or High). Findings and dispositions:

| ID | Disposition |
|---|---|
| G6-01 missing-file behaviour untested | fixed: H13 case E |
| G6-02 guide stale and contradictory | fixed: line 24 and a warning at the quick start; debt entry for groups 16 and 17 |
| G6-03 H13 differs from the committed file | stated above; `asistenteia_test` check added |
| G6-04 exited bootstrap keeps secrets in its env | documented; debt |
| G6-05 H13 directory guard | fixed: the run refuses a non-empty directory |
| G6-06 mutation harness gaps | fixed: port mutation implemented, privileged, host network and docker socket added; docstring corrected; the intended test is printed |
| G6-07 negation-aware ignore test | fixed |
| G6-08 deny-list of risky keys | fixed (`test_no_service_asks_for_more_than_it_needs_from_the_host`) |
| G6-09 config grep may not fail | accepted: the variable-name listing is the evidence; debt |
| G6-10 Compose version and `$` | documented in the guide |
| G6-11 ORM analysis | confirmed correct; before implementing, verify `SELECT` on `documents.error_*` and `users.consent_*` for the application and CLI roles (they hold it) |
| G6-12 `up --no-deps`, `docker start` bypass `depends_on` | accepted: not a boundary, the database roles are; debt |
| G5-E1 mutation evidence older than the last test edit | fixed: mutations 29 to 36 re-run against the final files (`mutation-run.txt`) |
| G5-E2 stale failing run file | removed |
| G5-E3 / E4 | accepted: group 4 mutations were not re-run after the group 5 support edits; mutation 36 is caught through a fixture error |

## Recommendation for group 7

See the chat report.
