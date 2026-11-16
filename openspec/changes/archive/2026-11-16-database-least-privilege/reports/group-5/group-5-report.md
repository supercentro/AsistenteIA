# Group 5: privilege tests under the roles (2026-11-13)

Branch `feature/database-least-privilege`. Authorised by the owner: group 5 only; group 6 and later are not authorised. Everything that needs PostgreSQL ran in a **disposable** cluster (`pgvector/pgvector:0.8.7-pg15`, PostgreSQL 15.19 + pgvector 0.8.7, random throwaway superuser, `tmpfs`, 1 CPU / 1 GB, internal Docker network, no published port, a fresh cluster for each mutation run). Nothing was run against `asistenteia`, `asistenteia_test` or the development server; no real role, password, `.env`, Compose file or container was touched. The harness refuses to start below 6 GB of free memory (`run_group5_tests.sh`, `run_group5_mutations.sh`; started at 6.0 to 6.1 GB).

## Task traceability

| Task | Tests | Where |
|---|---|---|
| 5.1 attributes, memberships, limits | `test_db_roles_lifecycle.py` (limit refused at N+1 for the four roles, recovery after releasing, other roles unaffected, the API pool of 5+10 inside the application limit); attributes and memberships in `test_db_admin_bootstrap.py` and `test_db_admin_verify.py` | `run-privileges.txt` |
| 5.2 SCRAM storage, no secrets | `test_db_admin_bootstrap.py` (stored prefix, login with each password, no secret in output, logs or errors) | group 4 and 5 runs |
| 5.3 ownership | `test_db_admin_adopt.py`, `test_db_admin_grants.py` | group 4 and 5 runs |
| 5.4 matrix under the roles | `test_db_roles_paths.py`: real repositories under the application and worker roles (upload, subjects, enrolments, consent persisted and read back, cascades without `DELETE` on children, claim, renew, complete with 1, 2 and 5 chunks, fail, sweep on its three branches), 29 ungranted columns and operations refused with nothing changed, the live `SELECT (id)` mutation | `run-privileges.txt` |
| 5.5 denied operations | `test_db_roles_denied.py`: four roles against about 40 statements (DDL, `TRUNCATE`, extensions, schemas, functions, `COPY` to/from program and file, file reads, large objects, `ALTER SYSTEM`, `CREATE ROLE`/`DATABASE`, `SET ROLE`, `pg_authid`/`pg_shadow`, terminating and cancelling sessions, other databases, temporary tables, event triggers, tablespaces, publications, `LOAD`, cross-role `ALTER ROLE`, `ALTER ROLE ALL`), role switching, `GRANT` to `PUBLIC`, session settings, `pg_stat_activity` redaction, prepared transactions | `run-privileges.txt` |
| 5.6 atomic grants, round trip, `downgrade base` | `test_db_admin_grants.py`, `test_db_roles_lifecycle.py` | group 4 and 5 runs |
| 5.7 hardening and planting | `test_db_admin_bootstrap.py` | group 4 run |
| 5.8 drift kinds | `test_db_admin_verify.py` (31 kinds) | group 4 run |
| 5.9 rollback | `test_db_admin_adopt.py` (also the second-database case) | group 4 and 5 runs |
| 5.10 self-tampering and residuals | `test_db_roles_lifecycle.py`, `test_db_roles_paths.py`, `test_db_roles_denied.py` | `run-privileges.txt` |

## What the live runs found

1. **The ORM sends every column without a server default, as `NULL`.** The first assumption of the group 2 inventory ("only the columns passed to the constructor") was refuted by the first upload under the application role (`permission denied for table documents`). The inventory was corrected and the matrix widened by six `INSERT` columns: `documents.error_message, error_code`, `users.consent_version, consent_accepted_at` (application and CLI) and `ingestion_jobs.locked_by, locked_until`. Design DD-3 note 2 records the consequences. The unit tests of groups 2 and 4 were updated and pass.
2. `GRANT ... TO PUBLIC` by a role that holds no privilege on the table is an error (42501); by a role that holds some privilege it is a warning that grants nothing. The test now asserts both.
3. A second database prepared in the same cluster makes `db-verify` report (correctly) that the roles can connect to it: tests that run `verify` use a database of their own.
4. A database created after the bootstrap is open to `PUBLIC` until the next run; `db-verify` reports it (test and documented residual).
5. Registration cannot create a user under the application role until task 8.4 (the code still inserts `role`): asserted as the known gap. **Group 17 must not switch the real `DATABASE_URL` before 8.4** (gate added to `tasks.md`).

## Connection limits (evidence kept)

`test_a_role_is_refused_beyond_its_limit_and_recovers_when_a_session_is_released`, once per role: `limit` sessions open, the next is refused with `FATAL: too many connections for role "<role>"` (SQLSTATE 53300 is not exposed by the driver at connect time, so the message is asserted), the existing sessions keep answering, another role still connects, and after one session is closed a new one is accepted. `test_an_exhausted_pool_of_the_api_waits_instead_of_opening_more_than_the_limit`: 15 sessions held through an engine of the API's size, the sixteenth request times out in the pool and the role never exceeds its limit. Mutation 32 (limit far above the pool) is caught.

## Mutation testing

Group 4 had 29 mutations; group 5 adds 8 (indices 29 to 36), all caught with the strict criterion (exit code 1 and the failing test is one of the targets): the worker loses `SELECT (id)`, the application role may update `users.role`, may read the fencing token, a connection limit far above the pool, the runtime roles may create in `public`, roles created with `CREATEROLE`, other databases left open to `PUBLIC`, the migrator with the catalog-first search path. Two mutations survived before the harness and one mutation were fixed: one was equivalent (the following step undid it) and the other was masked because the cluster kept the state of the baseline run; each run now starts a new cluster. Evidence: `mutation-run.txt`.

## Independent review (read-only, clean context)

Verdict **FAIL** for closing as it stood (no Critical, three Major). Dispositions:

| ID | Finding | Disposition |
|---|---|---|
| G5-01 | evidence files incomplete | moot: the review read them while the runs were being written; final evidence is in this folder |
| G5-02 | sweep test vacuous | fixed: three admin-prepared cases through the real `sweep`, exact counts `(1, 1, 1)` |
| G5-03 | `COPY FROM PROGRAM` missing | fixed, plus `pg_read_binary_file`, `pg_stat_file`, `lo_export`, `LOAD`, `pg_switch_wal` |
| G5-04 | design table stale | fixed (DD-3 table and note 2); residuals listed below |
| G5-05 | consent columns insertable | accepted: it could already update them; debt |
| G5-06 | the CLI can read `password_hash` | accepted: the code loads the whole `User` entity; debt |
| G5-07 | missing escalation cases | fixed: cross-role `ALTER ROLE` (password, setting, in database), `ALTER ROLE ALL`, own connection limit, drop role, terminate/cancel between runtime roles, event trigger, tablespace, publication, prepared transactions disabled |
| G5-08 | lock and resource DoS | accepted, debt: no `statement_timeout`/`lock_timeout` per role; `LOCK TABLE` shown possible where the role may write |
| G5-09 | limit not derived from the worker settings | debt (API derived from the real engine) |
| G5-10 | assertions accept any 42501 | debt |
| G5-11 | `pg_stat_activity` test weak | fixed: rows present and every query redacted |
| G5-12 | pooled-connection state | debt |
| G5-13 | administrator password in a dataclass repr | fixed (`field(repr=False)`) |
| G5-14 | harness marks any non-zero exit as caught | fixed: exit code 1 and a target test must fail, otherwise `FAILED-ELSEWHERE` |
| G5-15 | mutation gaps | partly fixed (8 added); the rest is debt |
| G5-16 | comment and gate for task 8.4 | fixed |
| G5-17 | cross-subject chunk | the composite key rejects it (test); same-subject poisoning remains a documented residual |
| G5-18 | "real ingestion service" | the tests use the repository; debt or wording change |
| G5-19 | role removal across databases | fixed (test) |
| G5-20 | migrator is a trust root | accepted residual |
| G5-21 | admin password in `docker inspect` of the disposable container | accepted |

Technical debt to register in group 18: G5-05, G5-06, G5-08, G5-09, G5-10, G5-12, G5-15 (rest), G5-18, G5-20, plus the group 4 list (S-04 rest, S-12, S-13, S-17, S-18, N-02, N-04, N-05) and the consequences of the widened `INSERT` columns (a compromised API can create a job with a chosen token and lease, queue a payload for any document it knows, set `error_message` and consent on new rows).

## Regression of the previous groups

- Pre-existing integration suite (API, worker, migrations, CLI, real server and process tests), unchanged tests, against the disposable PostgreSQL: **857 passed** (`run-integration-legacy.txt`). It validates the changes of group 3 in `tests/db_support.py` and `tests/integration/conftest.py`. A first pass showed 5 failures that came from the harness copy (it lacked `.env.example`, `docker-compose.yml` and the `/repo/backend` layout) and was repeated after fixing the harness; the copy still contains no real environment file (counted: 0).
- Group 4 and 5 privilege suites together: **363 passed** (`run-privileges.txt`). The first version of the file `run-first-failures.txt` is the failing-first evidence (2 failures that found the ORM `INSERT` behaviour).
- The three Windows unit-test failures of the group 3 baseline are unchanged; no new failure.

## Gates

| Gate | Result |
|---|---|
| `ruff check --no-cache`, `ruff format --check` | clean |
| `mypy --strict app tests` | no issues in 208 files |
| `pytest tests/unit` | 1093 passed, 110 skipped, 3 failed (the Windows baseline) |
| Integration | 857 (previous suite) + 363 (privileges) passed on the disposable PostgreSQL; 1220 collected |
| `openspec validate --all --strict` | 18 of 18 |

## Recommendation for group 6

**GO**, with conditions: (1) the real-database steps stay behind their own authorisation (groups 16 and 17); (2) group 17 does not run before task 8.4; (3) the debt listed above is registered in group 18; (4) the owner accepts the widened `INSERT` columns recorded in DD-3 note 2 or asks for the ORM-omission change first.
