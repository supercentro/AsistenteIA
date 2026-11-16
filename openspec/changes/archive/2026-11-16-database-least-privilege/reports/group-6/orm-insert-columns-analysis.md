# The six extra INSERT columns of the ORM: cause, alternatives and proposal (group 6)

Status: **analysis and proposal only**. The matrix keeps the six columns provisionally, for the isolated tests, as the owner decided; they are not accepted as a security decision. Nothing in the application models or repositories was changed.

## 1. Why SQLAlchemy sends them

When the ORM flushes a new object it builds one `INSERT` per mapper and class of values. For every mapped column that has **no Python default and no server default** it includes the column with `NULL` if the attribute was not set (SQLAlchemy keeps these "insert columns as none" so that rows of one batch share the same keys). Columns with a `server_default` are left out and, if `eager_defaults` is `auto` (the default), are added to `RETURNING`. The group 5 run showed it with the real repositories (`permission denied for table documents`), and `tests/integration/test_orm_insert_columns.py` reproduces it on a throwaway table:

| Variant | What is sent | Under a role that may insert only `document_id, payload` |
|---|---|---|
| A. model as today | `INSERT ... (id?, document_id, payload, locked_by, locked_until)`, the two as `NULL` | refused, 42501 |
| D. `default=None` (Python-side) | the same two columns, still `NULL` | refused: it does not help |
| B. `server_default=FetchedValue()` on the two columns + `eager_defaults=False` on that mapper | only `document_id, payload`; nothing returned for the two columns | **accepted**, no `SELECT` on them needed |
| C. Core `insert().values(document_id=..., payload=...).returning(id)` | only those columns | **accepted** |

(`run: reports/group-6/orm-experiment-run.txt`, PostgreSQL 15.19 + pgvector 0.8.7, disposable cluster.)

## 2. Which grants can go back to narrow

| Table | Columns granted to `INSERT` only because of the ORM | Who | Way to remove the grant | Extra requirement |
|---|---|---|---|---|
| `ingestion_jobs` | `locked_by`, `locked_until` | application | B (model) or C (repository). **Priority 1** | with B, `eager_defaults=False` on `IngestionJob`: otherwise `RETURNING` of the two columns needs a `SELECT` the application must not have (the fencing token) |
| `documents` | `error_message`, `error_code` | application | B (`FetchedValue`) | the application already has `SELECT` on `documents`, so the default `RETURNING` is harmless |
| `users` | `consent_version`, `consent_accepted_at` | application and CLI | B (`FetchedValue`) | both roles have `SELECT` on `users` |

After the change the matrix returns to `INSERT` of the columns the code sets: `ingestion_jobs (document_id, payload)`, `documents (subject_id, filename, content_type, size_bytes, status)`, `users (name, email, password_hash)` for the application and `(name, email, password_hash, role)` for the CLI.

## 3. Alternatives considered

1. **Keep the wider grants** (today). Costs: a compromised API can create a job with a chosen token and a far-future lease (the job is never claimed) and queue a payload for a document it knows (the payload part exists regardless of this change), can insert documents with arbitrary `error_message`, and can set consent evidence on new accounts. Not acceptable as the final state: it widens a fencing-token column to satisfy the ORM.
2. **`FetchedValue()` on the nullable columns** (variant B). Model-only change, no DDL, no migration; `alembic check` ignores server defaults unless `compare_server_default` is on (it is not). The attributes are not populated by the INSERT, so after a flush they are expired and a later access issues a `SELECT`: the application never reads `locked_by` or `locked_until`, and if some code did, the `SELECT` would be refused, which is the intended behaviour.
3. **Core inserts in the repositories** (variant C). Explicit and independent of the model, but it bypasses the unit of work for `IngestionJob` and `Document`, and the repository tests that use the ORM objects (`document.id`, `created_at`) need rewriting. Best only for `ingestion_jobs` if B is rejected.
4. **A PostgreSQL default on the columns** (`DEFAULT NULL` in a migration) does not change the ORM, which decides from the model, so it does nothing here.
5. **Column privileges on `INSERT` cannot express "NULL only"**, so no database-side restriction is possible; a trigger would be heavier than the model change and is outside decision D4.

## 4. Proposed change (not implemented)

1. Models: add `server_default=FetchedValue()` to the six columns and `eager_defaults=False` to `IngestionJob` (priority 1), then `Document` and `User`.
2. Inventory (`tests/privilege_inventory.py`): treat a column with a `server_default` as not sent in `INSERT`, and model `eager_defaults=False` so that its columns are not added to the `SELECT` the `RETURNING` needs; restore assumption 1 of `ASSUMPTIONS`.
3. Matrix (`app/db_privileges.py`): remove the six columns from the `INSERT` lists; the unit comparison then proves it.
4. Tests: re-run `test_db_roles_paths.py` (upload, subjects, consent, worker paths) and the denied columns under the narrowed matrix; add `INSERT INTO ingestion_jobs (..., locked_by)` and `INSERT INTO documents (..., error_code)` to the refused list for the application role; `alembic check` on the test database; the repository tests that create documents, jobs and users.
5. Order: first `ingestion_jobs` (the fencing token), then `documents`, then `users`; each in its own commit with its own RED test (the refused insert).

## 5. Risks of the change

- The ORM objects created by the application no longer carry `None` for these attributes until loaded: any code or test that reads `job.locked_by` or `document.error_code` right after a flush would trigger a `SELECT`. The inventory and the repository tests show no such read today; the worker path is unaffected because it uses SQL, not the ORM objects.
- `eager_defaults=False` on `IngestionJob` also stops the `RETURNING` of `attempts`, `available_at`, `created_at` and `updated_at`; the application has `SELECT` on them, and nothing reads them after the insert.
- The `FetchedValue` marker is not a database default: a developer who adds a column without a default would again get a `NULL` in the INSERT. The matrix comparison (new column without a decision) fails first, so the drift is caught.
- The change touches the models and therefore all three actors; it needs its own authorisation and, because it touches data access, an independent review.

## 6. Where it fits

Not in group 6. Proposal: a new group between 8 and 9 (or a task 4.7 reopened by the owner), before the role-bound suite, so that the matrix the role-bound suite proves is the narrow one. Until then the DD-3 note 2 residual risks stay registered and group 18 lists them as accepted-provisional.
