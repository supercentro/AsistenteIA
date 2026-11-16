# Group 9: role-bound integration suite (2026-11-13)

Validated on the final code, commit `48cb744` (the documentation commit that follows changes no code). Everything ran on disposable PostgreSQL 15.19 + pgvector 0.8.7 (`pgvector/pgvector:0.8.7-pg15`), no published port, throwaway credentials, an isolated Docker network, and free RAM above 6 GB before every container (8 to 12 GB). The development database stays at revision 0005 (migration 0006 and the narrow matrix were applied only to the disposable clusters), `asistenteia-db-1` and `asistenteia-worker-1` were not touched, no real role, `.env` file or container was changed, and `docker compose up` was not run.

## Tasks

| Task | Result |
|---|---|
| 9.1 failing tests first, fixtures | `test_least_privilege_coverage.py` failed first (`red-coverage.txt`: the scenario module did not exist). Fixtures: the prepared database (bootstrap, migration to head, grants) of the existing `own_database`, the new roles mode (`tests/least_privilege.py`, `tests/conftest.py`) and the reserved `tstrole_`/`tstdb_` prefixes with the leftover sweep |
| 9.2 every route, subcommand and worker path | `test_db_roles_api_routes.py`: the 15 operations of the OpenAPI contract run under the application role with persisted-state assertions (TXT, Markdown and PDF uploads processed by the real service under the worker role, retrieved with `find_similar` under the application role, deletion with cascades); CLI: `create-teacher`, `seed` (CLI role) and the five `db-*` commands (administrator and migrator); worker: claim, renew, complete, `mark_failed`, `erase_payload` and sweep (`test_db_roles_paths.py`, with 1, 2 and 5 chunks). `test_least_privilege_coverage.py` fails when a route, a subcommand or a public method of `IngestionJobRepository` has no scenario, and checks that the scenarios really issue each route request |
| 9.3 existing tests under the roles | `pytest --least-privilege -m least_privilege`: 484 existing and mode tests (23 modules of the API and ingestion) with the API as the application role and the ingestion service and repository sessions as the worker role (`app` for retrieval); the helpers for seeding and inspection keep the administrator, so no assertion changed. `test_least_privilege_mode.py` proves `current_user` is `tstrole_app` / `tstrole_worker`, neither a superuser |
| 9.4 mutation | 11 of 11 caught (`mutation-run.txt`). See the limit below |

## Final-state runs (commit `48cb744`)

| Run | Result |
|---|---|
| Roles mode, marked tests (`final-1-least-privilege-mode.txt`) | 484 passed |
| Role suites: groups 4 and 5 privilege tests, bootstrap, adoption, grants, verify, lifecycle, denied operations, paths, teacher and CLI, ORM SQL inspection, consent persistence, TD-039, API routes, effective privileges, coverage (`final-2-role-suites.txt`) | 410 passed |
| Migrations 0001 to 0006 (`final-3-migrations.txt`) | 34 passed |
| Existing integration suite as the owner (`final-4-existing-integration.txt`) | 829 passed |
| Unit (`final-unit.txt`) | 1157 passed; 3 failures, the same Windows baseline as before, not hidden: `test_worker_health::test_the_defaults_leave_room_for_the_beat_interval`, `test_worker_settings::test_a_fresh_worker_process_loads_its_settings_without_any_api_variable`, `test_worker_settings::test_importing_the_worker_does_not_pull_in_the_api` |
| Gates | ruff check and format clean; mypy strict 226 files; `openspec validate --all --strict` 18/18; integration collection 1273 |

## Effective privileges (`effective-matrix.txt`)

Read from `information_schema` on the prepared database and compared with `app.db_privileges.MATRIX` by `test_db_roles_effective.py`: no extra grant, none to PUBLIC, no runtime role owns an object. Application: `users` INSERT (name, email, password_hash), UPDATE (consent_version, consent_accepted_at); `subjects` INSERT, DELETE, UPDATE (description); `enrollments` INSERT, DELETE; `documents` INSERT (five columns), DELETE; `ingestion_jobs` INSERT (document_id, payload), SELECT (id, payload); SELECT on the others as in the matrix. Worker: chunks INSERT and SELECT (id), documents UPDATE (status, chunks_count, error_code, error_message), jobs SELECT and UPDATE; nothing on users, subjects or enrollments. CLI: `users` SELECT and INSERT (name, email, password_hash, role), nothing else.

## Task 9.4: what the mutations show, and their limit

Mutation 0 removes the consent `UPDATE` grant and also moves the commit back after the answer (the TD-039 defect): the endpoint answers 200, `assert consent.status_code == 200` passes and only the persisted-state assertion fails (`mutation-cause-0.txt`: `[(None, False)] != [('2026-10-v1', True)]`). With the shipped code a missing privilege behind a write is a 500 (mutations 1 to 3 and 6 fail loudly), so the literal "removing a privilege while the endpoint still answers 200" is demonstrated only with the late commit reintroduced; that is the intent of the persisted-state requirement and is stated as such. The other mutations: the roles mode falling back to the owner, a route, a CLI subcommand or a worker method without a scenario, a scenario that stops calling its route, and the worker role without `UPDATE` on `ingestion_jobs`.

## Independent review (read-only, clean context): PASS WITH GAPS

No Critical or High finding; nothing lets a runtime role do more than the matrix; no unguarded path to a non-disposable database (the guards are the disposable-cluster flag and `assert_cluster_is_disposable`, which refuses any database not named `tstdb_*_test` and any `asistente%` role). Dispositions:

| ID | Disposition |
|---|---|
| M1 about 74 ingestion repository tests ran as the owner | fixed: `session_for` connects as the worker (`app` for the retrieval test); the full run found the one retrieval session and it was fixed |
| M2 coverage guards weak | fixed: worker methods derived from the repository, route calls checked, `erase_payload` scenario added, mutations for the CLI, worker and route guards |
| M3 9.4 only synthetic | stated above |
| L1 no failing-first runs for 9.2 and 9.3 | partly: the coverage guard failed first (9.1); the route scenarios passed on their first run, so the failing-first evidence for them is mutations 4 and 9; for the mode it is mutation 5 |
| L2 the gc fixture hides a connection-limit fragility | accepted and documented in the guide; the mode ran green on the last two full runs (483 and 484 tests); deterministic disposal of the leaking engines is left for group 18 |
| L3 sweep order | fixed: objects dropped first, then roles |
| L4 mixed sessions can drop the main test database | documented in the guide |
| L5 silent `role_url` fallback | covered by the mode test and mutation 5 |
| L6 the CLI role reads `password_hash` | accepted: the ORM `select(User)` of the duplicate check reads every column; narrowing it needs a repository change |
| L7 masking only the administrator password | accepted: throwaway credentials, no password found in the committed evidence |
| I1 `db-bootstrap` blocks the stack on a legacy database until `db-adopt --apply` | known and documented; groups 16 and 17 |
