# Prerequisites of group 9: narrow INSERT columns (DD-14) and TD-039 (DD-15) (2026-11-13)

Authorised: only these two prerequisites; the full role-bound suite of group 9 was not run. Everything ran on disposable PostgreSQL 15.19 + pgvector 0.8.7 (free RAM above 6 GB for every container). The development database stays at revision 0005 (migration 0006 exists only in code), `asistenteia-db-1` and `asistenteia-worker-1` were not touched, no real role, `.env` file or container was changed, and `docker compose up` was not run.

## A. The six extra INSERT columns

`FetchedValue()` is safe for all three pairs: no semantic changed and no new `SELECT` was needed (the alternative of a Core insert was not required).

| Pair | Model change | Matrix change (application role unless stated) | Commit |
|---|---|---|---|
| 1 `ingestion_jobs.locked_by`, `locked_until` | `FetchedValue()` on both and `eager_defaults=False` on `IngestionJob` | `INSERT (document_id, payload)`; `SELECT (id, payload)` (the four other columns were only there for the `RETURNING`) | `b549357` |
| 2 `documents.error_message`, `error_code` | `FetchedValue()` on both | `INSERT (subject_id, filename, content_type, size_bytes, status)` | `8128430` |
| 3 `users.consent_version`, `consent_accepted_at` | `FetchedValue()` on both | application `INSERT (name, email, password_hash)`, CLI `INSERT (name, email, password_hash, role)` | `ee393b5` |

For each pair: tests that capture the emitted SQL failed first (the columns were in the `INSERT`), the model changed, the columns left the `INSERT` and its `RETURNING` (single object and batches of three), the matrix narrowed only afterwards, the real repositories and the upload and registration paths work under the minimal role, a forged value is refused with 42501, and the rows keep those columns NULL. `RETURNING` and defaults behave as designed: for `documents` and `users` the default `RETURNING` reads the columns (both roles already have `SELECT`); for `ingestion_jobs` the key only. Inventory (`tests/privilege_inventory.py`) models both behaviours, and the matrix comparison proves the narrow lists are exactly what the code needs.

## B. TD-039

`app.api.transaction.commit_or_rollback` runs after the service call and before the response in `POST /auth/register`, `POST` and `DELETE /subjects`, and the enrollment `POST` and `DELETE` (and the consent endpoint, refactored to the same helper). Commit `4577d7a`. Contracts, status codes and bodies are unchanged; the 404/409 paths do not commit; the later `get_db` commit has nothing left to write. TD-039 is updated with the evidence and stays open until the owner confirms.

Evidence: integration RED (`td039-red-integration.txt`): with PostgreSQL refusing the COMMIT (deferred constraint trigger) the API answered 201 and 204 with nothing stored; GREEN: 500 with the standard body, nothing stored, no sensitive value in the answer, and the next request succeeds once the trigger is dropped; duplicates give 409 and one row. The unit RED (`td039-red-unit.txt`) is a signature failure (the handlers had no `db` parameter): cite the integration RED as the behavioural one. A known property of commit-then-respond is tested and documented: a failure while building the response after the commit gives a 500 with the data committed.

## Results

| Check | Result |
|---|---|
| Unit | 1157 passed + the 3 known Windows baseline failures |
| Role-bound integration (SQL capture, paths, denied, teacher, consent, TD-039) | 311 passed after pair 3 and TD-039 |
| Legacy integration (authentication, users, subjects, enrollments, documents, ingestion, migrations, CLI) | 862 passed on the final code of each step |
| Mutations | 27 of 27 caught: `mutation-run-0-26.txt` (indices 0-19, 25, 26) and `mutation-run-20-24.txt` (the five endpoint mutations, repeated after fixing the harness, which had taken a log line as the first failure) |

## Independent review (read-only, clean context): PASS WITH GAPS

No Critical or High finding and no privilege added or widened (the matrix diff only removes). Dispositions: M1 integration-level mutations missing: 11 mutations added whose only target is an integration test or the inventory (and the second column of each pair); M2 unit RED is a signature failure: stated above; L1 tasks unchecked: ticked; L2 failure after the commit untested: test added; L3 `eager_defaults=False` trap: written as a rule in DD-14; I1/I2 incidental edits (ruff per-file ignores, matrix consistency tests narrowed, consent endpoint on the shared helper): accepted.
