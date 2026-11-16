# Spike summary: PostgreSQL least privilege (hypotheses H1 to H14)

Date 2026-11-12. Disposable PostgreSQL 15.19 + pgvector 0.8.7 (internal Docker network, no published port, `tmpfs`, random passwords, 1 CPU / 1 GB) plus a runner container with the application image of `main` (`3b312e4`). Nothing of the real stack was touched: the development database stayed at revision `0005` with its single role, and no real credential, `.env` file or container was used. Scripts and raw results: `spike/` (`s1_setup.py` ... `s8_extra.py`, `compose/`, `out/results.jsonl` with 186 records of the clean second run, `out/h13_compose.txt`).

**What is preserved and what is not.** The kept `results.jsonl` comes from the second run, which re-ran `s1`, `s2`, `s2c`, `s3`, `s4`, `s5`, `s5e` and `s8`. The scripts `s5d_debug.py` (the one-chunk failure), `s6_adopt.py`/`s6b_adopt.py` (adoption with data, rollback, catalog readability, connection limit) and `s7_final.py` (test-layer effects, the `REASSIGN OWNED` of the superuser) were run in the **first** run (246 records, superseded by harness mistakes) and were **not** re-run afterwards: their output was seen in the session but is not kept. The claims that rest only on them are marked "first run" below and in the traceability matrix of `design.md`, and are re-proved in tasks 4.5, 5.3, 5.4, 5.9, 9.1 and 16.2 before any real run. Tags `A-02`, `H8`, `H11`, `A-14`, `A-21` and `ADOPT` therefore do not exist in the kept file.

Names in the spike: `spk_admin`, `spk_migrator`, `spk_app`, `spk_worker`. The final run was authorised by the owner as decision D6 (2026-11-12).

## Hypotheses

| H | Result | Evidence |
|---|---|---|
| H1 referential actions and FK checks run as the table owner | Confirmed | `app` without `DELETE` on `document_chunks`/`ingestion_jobs`: deleting a document removed its chunks (5 to 1) and jobs; deleting a subject cascaded to documents, chunks, jobs and enrollments. Also with a child table of another owner, and an FK-checked insert by a role with no privilege on the referenced table (`s8_extra.py`, tag `H1x`) |
| H2 `SELECT ... FOR UPDATE` needs only a column-level `UPDATE` | Confirmed | upload (admission locks the subject row): HTTP 503 without any `UPDATE` on `subjects`, HTTP 202 with `UPDATE (description)` (`s5_flows.py`) |
| H3 `INSERT ... RETURNING` needs `SELECT` on the returned columns | Confirmed with consequence (first run) | the worker's insert for a one-chunk document is `INSERT ... RETURNING document_chunks.id` and failed with `permission denied`; the job ended `abandoned` (`s5d_debug.py`, output not kept); the kept run shows both paths succeeding once `SELECT (id)` is granted |
| H4 ORM bulk insert works with `INSERT` only | **Refuted** (first run) | multi-row inserts are `executemany` without `RETURNING`, single-row inserts use it; the worker needs `SELECT (id)` on `document_chunks`; task 5.4 re-proves it with a mutation |
| H5 `CREATE EXTENSION IF NOT EXISTS vector` as a non-superuser | Confirmed | no-op when the administrator created it; `0001` fails with permission denied when it is missing (`s2_clean.py`) |
| H6 Alembic as migrator | Confirmed | clean and adopted database: `upgrade head`, `current`, `check`, `downgrade 0004`, `upgrade head`; documents and chunks kept, the job row dropped by design; `downgrade base` fails and leaves revision `0005` (transactional DDL) |
| H7 ACLs of objects created by the migrator | Confirmed and corrected | tables and enums carry no ACL (tables owner-only, enums usable by `PUBLIC`); functions are executable by `PUBLIC` unless the global `ALTER DEFAULT PRIVILEGES FOR ROLE migrator REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC` is used; the `IN SCHEMA public` form had no effect (`s3_defaults.py`) |
| H8 `db-verify` reads what it needs without elevation | Observed (first run) | `app` and `migrator` read the 14 catalogs; `pg_roles` masks passwords, so a password change is invisible without the superuser; to be re-proved in task 4.5 |
| H9 SCRAM verifier computed in the client | Confirmed | accepted at `CREATE ROLE`; a failed `ALTER ROLE ... PASSWORD` writes the statement with the verifier to the server log (tag `A-22`) |
| H10 `ALTER TABLE ... OWNER TO` | Confirmed on a clean database (kept: 27 objects owned by the migrator); adoption with data observed in the first run | 7 tables, 18 indexes (27 objects with the 2 enums moved by `ALTER TYPE`) and TOAST follow; database and extension keep the administrator; catalog fingerprint and row counts unchanged (`s6_adopt.py`, output not kept); re-proved in tasks 5.3 and 16.2 |
| H11 `REASSIGN OWNED` rollback | Observed (first run) | `REASSIGN OWNED BY migrator TO administrator` returned all 27 objects; `DROP OWNED` afterwards only revoked (and removed `CONNECT`); `DROP ROLE` is refused until every database is clean; and `DROP OWNED` **before** reassigning dropped all tables (A-02); output not kept, re-proved in tasks 5.9 and 16.2 |
| H12 REVOKE semantics | Confirmed | a column-level `REVOKE` does not remove a table-level grant, a table-level `REVOKE` removes both (`s3_defaults.py`) |
| H13 Compose cold start | Confirmed with consequences | see `h13/` and `out/h13_compose.txt`: a plain `up -d` restarts finished one-shots; `restart` keeps the old environment; an inactive profile dependency makes the project invalid; atomic grants did not disturb the running services |
| H14 pgvector update with other objects in `public` | Weak | `ALTER EXTENSION vector UPDATE` works as administrator (already latest, no update script ran), the migrator cannot run it, and the query for foreign functions, operators and triggers in `public` finds the planted ones (`s8_extra.py`, tag `B-01`) |

## New findings of the spike

| ID | Finding |
|---|---|
| N-1 | An implicit commit after the response hides privilege failures: `POST /users/me/consent` answered 200 and stored nothing when the role lacked `UPDATE (consent_*)`; the API logged only `unhandled exception ProgrammingError` (`s5e_consent.py`, tag `N-1`) |
| N-2 | The worker needs `SELECT (id)` on `document_chunks` (H4) |
| N-3 | A role can change its own password and, with `ALTER ROLE self SET ...`, its own persistent settings (`search_path`, `statement_timeout`); only the superuser can see a password change (hashes are salted); the bootstrap heals both and a login probe detects them (`s8_extra.py`, tag `B-05`) |
| N-4 | `DROP OWNED BY` also revokes `CONNECT` on the database |
| N-5 | `PUBLIC` keeps `USAGE` on schema `public` by default; the migrator's `GRANT USAGE ON SCHEMA public` is silently ineffective (it does not own the schema) |
| N-6 | A function `lower(varchar)` or an operator `=(varchar, varchar)` planted in `public` wins over `pg_catalog` when `public` is in the `search_path`, even if `pg_catalog` comes first; sessions of the administrator must use `search_path = pg_catalog` (tag `B-01`) |
| N-7 | Non-atomic revoke-then-grant produced permission errors for a concurrent reader (2 of 98 reads); one transaction per cycle gave 0 of 99 (tag `B-03`) |
| N-8 | The application role can run `LOCK TABLE ... ACCESS EXCLUSIVE` on the tables where it holds table-level `DELETE` (availability only; the two `B-06` lines with `ok: false` are the proof, my expectation text assumed otherwise), can insert a `users` row with `role = 'teacher'`, and a compromised worker can insert chunks for any existing document (tag `B-06`) |

## Negative suite

69 refusals plus one role-attribute check, all as expected, for the application, worker and migrator roles (`s4_negative.py`, tag `NEG`) plus the ungranted-column checks of `s8_extra.py` and the connection refusals on `postgres`, `template1` and another database (`A-09r`).

## Harness mistakes (not product findings)

The first run (246 records) had: missing SQLSTATE on connection refusals (A-09), a schema-`USAGE` test that ignored `PUBLIC`'s default `USAGE` (A-08), `42P01` where `42501` was expected, my own negative test changed `spk_app`'s password (then recorded as N-3), a wrong consent body, a document count that forgot the bogus PDF, a delete of a failed instead of a ready document, a query on a table dropped by the downgrade, an `owners()` cast, and `DROP OWNED` removing `CONNECT` before a later test. The second, clean run keeps six `ok: false` records that are expectation errors, each explained here or in its record: `A-08` (invalid, superseded by `A-08r`), `A-08r` (`42P01` instead of `42501`, still blocked), two `B-06` lines (the application role holds table-level `DELETE`, so the `LOCK TABLE` is allowed: a finding, not a failure), `A-01` in `s5_flows.py` (superseded by the `N-1` record of `s5e_consent.py`) and one document-count line.
