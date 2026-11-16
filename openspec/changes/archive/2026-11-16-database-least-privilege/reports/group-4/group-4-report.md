# Group 4: bootstrap, adoption, grants and verify (2026-11-12)

Branch `feature/database-least-privilege`. Authorised by the owner: group 4 only; group 5 and later are not authorised, `.env` files are not to be modified (task 3.3b stays open). Nothing was run against the development PostgreSQL, no real role or password was created or changed, no `.env` file, Compose file, migration or container of the project was touched.

## Tasks

| Task | Result |
|---|---|
| 4.1 failing tests first | RED in `tdd-red.txt` (6 failed, 5 collection errors, before `app/db_admin` existed). GREEN: 42 unit test functions, and 34 integration test functions that expand to 75 cases, all passing in `run-integration-final.txt` |
| 4.2 `db-bootstrap` | `app/db_admin/bootstrap.py` |
| 4.3 `db-adopt` (+ rollback) | `app/db_admin/adopt.py`: dry run by default, `--apply`, `--rollback`, `--remove-roles` |
| 4.4 `db-migrate`, `db-grants` | `app/db_admin/migrate.py`, `grants.py`; `alembic/env.py` refuses a direct online run |
| 4.5 `db-verify` | `app/db_admin/verify.py`, read-only |
| 4.6 mutation checks | 29 mutations on scratch copies, all caught: `mutation-run.txt` (22: 21 caught and 1 survivor that exposed a real gap, fixed), `mutation-run-rerun-20.txt` (the survivor, now caught), `mutation-run-review-fixes.txt` (7 more for the fixes the second review asked for) |

## Where the tests ran

PostgreSQL 15.19 + pgvector 0.8.7 (`pgvector/pgvector:0.8.7-pg15`), throwaway superuser with a random password, `tmpfs`, 1 CPU / 1 GB, on an **internal** Docker network (no published port, no route to the real databases). The runner is the Python 3.12 backend image of `main` with a **copy** of the code that has no `.env` file (the harness checks it and prints the count), `pytest` and `httpx` installed from PyPI at the versions of `uv.lock`. Harness: `run_group4_tests.sh`, `run_group4_mutations.sh`, `mutations.py`. Both scripts refuse to start below 6 GB of free memory (they printed that refusal many times; the runs started at 6.01 to 6.79 GB). The tests refuse a cluster that holds anything except `postgres`, the templates and their own `tstdb_*_test` databases, or any role named `asistente*` (review S-06), and they need `TEST_CLUSTER_IS_DISPOSABLE=true`.

## What the live runs found (all fixed, all would have passed the unit tests)

1. `sweep_test_roles` passed a SQLAlchemy `text()` and then `.scalars()` to a psycopg connection: it crashed. The unit test fake had the same wrong shape.
2. The migrator inherited `search_path = pg_catalog, public`, and an unqualified `CREATE TABLE` went to `pg_catalog`: Alembic failed with "permission denied for schema pg_catalog". The migrator now keeps `public` (design DD-6).
3. Sessions run with `search_path = pg_catalog`, so `"users"` did not resolve (42P01) in grants and adoption: every table and type is now `"public"."name"` (review S-01).
4. `pg_shdepend` counts the default-privilege entries of a role as owned objects, which `REASSIGN OWNED` does not move: they are excluded from "still owns".
5. The owner has a grant option on its own tables: the grant-option check ignores the owner.
6. Mutation 20 survived: a default `GRANT EXECUTE ON FUNCTIONS` to another role was not detected. Fixed with a test.

## Evidence that was pending and is now reproduced and kept

| Pending item | Where it is now |
|---|---|
| Adoption of a database with data | `test_db_admin_adopt.py`: 7 tables, indexes and 2 enums re-owned in one transaction; rows and catalog fingerprint equal; idempotent; refused with unexpected objects or with any session on the database |
| Ownership recovery and safe rollback | `test_rollback_*`: `REASSIGN OWNED` in every database, `pg_shdepend` verification, then `DROP OWNED` and `DROP ROLE`; roles cannot be removed while they own anything (mutation 15 caught) |
| Catalog readability | `db-verify` runs as the migrator and reads every catalog it needs (31 drift kinds) |
| **Connection limits** | **Not reproduced.** `db-verify` checks the configured limit; a test that fills the limit and gets "too many connections" is task 5.1 |
| H3/H4 (`RETURNING` needs `SELECT (id)`) | Not part of group 4; task 5.4 |

## Independent security review

First pass (read-only subagent): **FAIL** with 19 findings. Fixed: S-01, S-02, S-03, S-05, S-06, S-07, S-08, S-09, S-10, S-11, S-14, S-15, S-16, S-19 and S-04 for grant options, strangers in the ACLs, TEMPORARY/CREATE on the database, row-level security, other types in `public` and `log_statement`. Not fixed, recorded for `docs/technical-debt.md` in group 18: S-04 for column-level grant options and the "each check as passed" output, S-12 (adoption compare under READ COMMITTED, `classid` in the extension filter), S-13 (race between the ownership check and `DROP OWNED` when removing roles), S-17 (the atomic-reader test is probabilistic; the deterministic guarantee is mutation 10), S-18 (`alembic check` and `current` now need a `db-check` command or the explicit-URL form). The second pass is in the next section.

## Second independent review (after the fixes)

Verdict **PASS WITH GAPS**: no regression and no new injection path; groups 4 and 5 may proceed. Claimed fixes verified: S-01, S-02, S-03, S-07, S-08, S-10, S-11, S-15, S-16 and most of S-04; accepted as debt: S-12, S-13, S-17, S-18. It found fixes without a failing test (S-05, S-09, S-14, S-19, reverse memberships) and these new findings:

| ID | Finding | Disposition |
|---|---|---|
| N-01 Medium | the login probe ignored the TLS parameters of the URL | fixed (`tls_parameters` shared by `connect` and the probe); tests and mutations 23 and 24 |
| N-02 Low | `quiet_logs` missed `log_min_duration_statement` and needs a superuser | `log_min_duration_statement=-1` added (mutation 28); the superuser requirement is documented in the code and goes to technical debt |
| N-03 Medium | fixes without a failing test | tests added for S-05, S-09, S-14, S-15, S-19 and 7 mutations (22 to 28), all caught |
| N-04 Low | adoption session check depends on seeing other users' rows (needs a superuser or `pg_read_all_stats`) | technical debt; the administrator of this project is a superuser |
| N-05 Low | verify does not cover `ALTER DATABASE ... SET` and column-level ACL grantees; `owners_verified` was unconditional | `owners_verified` fixed; the other two go to technical debt |

Technical debt to register in group 18: S-04 (column-level grant options, per-check "passed" output), S-12, S-13, S-17, S-18, N-02 (superuser requirement), N-04, N-05 (`ALTER DATABASE ... SET`, column ACLs). Not tested: the disposable-cluster guard itself (S-06) and the SQLAlchemy and Alembic branches of the error handler.

## Gates

| Gate | Result |
|---|---|
| `ruff check --no-cache`, `ruff format --check` | clean (`pyproject.toml` ignores `S608` only for `app/db_admin` and the db-admin test support: DDL cannot take bind parameters and every identifier is validated first) |
| `mypy --strict app tests` | no issues in 204 files |
| `pytest tests/unit` | 1081 passed, 110 skipped, 3 failed (the Windows ones classified in group 3) |
| Integration tests of the group | 75 passed on the disposable PostgreSQL |
| Integration collection | 928 tests collected; the rest of the integration suite was not run |
| `openspec validate --all --strict` | 18 of 18 |

## Deviations and limits

- Group 3 documented `docker compose exec ... alembic` with an explicit URL; this group replaces that with `db-migrate` and the guide was corrected. The old commands still work in containers built before this change.
- `db-bootstrap` now exits 1 on ownership drift (spec). In the Compose flow of group 6 that blocks `migrate` until `db-adopt` runs, which is intended.
- The pre-existing integration tests (API, worker, migrations) were not run in this stage; only the group 4 files were. The mutation harness never edits the repository (it edits scratch copies), so no restore or byte comparison was needed.
- `sslmode` and the other TLS parameters of a URL are honoured; nothing tests a TLS server.
- Nothing was run against `asistenteia`, `asistenteia_test`, the development server or its roles.

## Pending decisions and risks

- Authorise group 5 (privilege tests under the roles: denied operations, persisted state, `RETURNING` mutation, connection limits).
- `db-adopt --apply`, `db-bootstrap` and `db-migrate` against the development database need the owner's separate authorisation (groups 16 and 17).
- The cluster-wide `PUBLIC` revoke of the bootstrap affects every database of the server it runs on; the development server also hosts `asistenteia_test`.
