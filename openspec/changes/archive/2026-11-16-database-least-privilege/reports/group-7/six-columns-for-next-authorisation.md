# Six extra INSERT columns: record for the next authorisation (group 7)

Status: **nothing implemented**. The provisional matrix stays as it is during group 7. The analysis and experiment are in `reports/group-6/orm-insert-columns-analysis.md` and `test_orm_insert_columns.py`; this note adds what the owner asked to have on record.

## Feasibility of `server_default=FetchedValue()`

Feasible. The experiment (PostgreSQL 15.19, disposable cluster) shows that with `FetchedValue()` the ORM leaves the column out of the `INSERT`, so a role that may insert only the columns the code sets is accepted. It is a model-only change: no DDL, no migration, and `alembic check` ignores server defaults because `compare_server_default` is off.

Order proposed: `ingestion_jobs.locked_by` and `locked_until` first (fencing token, priority 1), then `documents.error_message` and `error_code`, then `users.consent_version` and `consent_accepted_at`.

## Risks of `RETURNING` and of defaults

- With `eager_defaults='auto'` (the default) the ORM adds columns that have a server default to `RETURNING`, and a `RETURNING` of a column needs `SELECT` on it. For `ingestion_jobs` the application must not read the fencing token, so the mapper needs `eager_defaults=False`; otherwise the insert fails with 42501. For `documents` and `users` the application already has `SELECT`, so the default is harmless.
- `eager_defaults=False` also stops the `RETURNING` of `attempts`, `available_at`, `created_at` and `updated_at` on `ingestion_jobs`; nothing reads them after the insert today.
- After the insert the attributes are expired, so a later read issues a `SELECT`; for the fencing token that `SELECT` is refused, which is the intended behaviour.
- `FetchedValue()` is a marker, not a database default: a new column added without a default would again be sent as `NULL`. The matrix comparison (a column without a decision) fails first, so the drift is caught.
- Setting one of these attributes explicitly in a constructor or a seed would still put it in the `INSERT`, and the narrow grant would refuse it. The consent endpoint sets `consent_version` and `consent_accepted_at` with an `UPDATE`, which keeps its own column grant; only the `INSERT` grant on those columns goes.
- Registration through the API and the CLI seed insert users without consent columns today (confirmed in the group 5 run).

## Impact on batch INSERT

SQLAlchemy 2.x uses "insertmanyvalues" for a flush of several objects of one mapper. Rows of a batch must share the same column set; "insert columns as none" exists to guarantee that. With `FetchedValue()` the column is out of every row of the batch, so the keys stay equal and batching is unaffected. The risk is a batch in which some objects set the attribute and others do not: the ORM then splits the batch by key set (more statements, same result), and a row that sets it is refused under the narrow grant. The repositories insert one document, one job or one user per call today; a test that adds several objects in one flush must be part of the change.

## Tests needed to remove the six permissions

1. RED first for each table: with the grant removed from the matrix, the real repository path (upload, registration, CLI seed) fails with 42501 under the application or CLI role.
2. GREEN after the model change: the same paths pass; `test_db_roles_paths.py` and `test_db_roles_denied.py` run under the narrowed matrix.
3. Refused statements added to the denied list for the application role: `INSERT INTO ingestion_jobs (document_id, payload, locked_by)`, `INSERT INTO documents (..., error_code)`, `INSERT INTO users (..., consent_version)`.
4. Batch test: several documents and jobs in one flush under the application role.
5. Unit comparison matrix versus inventory (`tests/privilege_inventory.py`) updated so that a column with a server default is not counted as sent and `eager_defaults=False` is modelled.
6. `alembic check` on the test database shows no drift.
7. Mutation check: put one column back in the model or the matrix and show a test fails.
8. Independent adversarial review, because it touches the data access of the three actors.
