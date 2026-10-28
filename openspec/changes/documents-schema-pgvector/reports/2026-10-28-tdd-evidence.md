# TDD Evidence (change documents-schema-pgvector)

Records the failing run before the implementation of each functional group (`docs/base-standards.md` 9.2, lesson L01) and every deviation. Group 3 is complete; later groups append their sections.

## Group 3 - migration 0004, models, integrity, error-text exposure

### Failing run before the implementation
- Date: 2026-10-28
- Command: `uv run pytest -q -p no:cacheprovider --continue-on-collection-errors tests/integration/test_migrations_documents.py tests/integration/test_document_storage_integrity.py tests/integration/test_document_models.py tests/integration/test_error_text_exposure.py tests/integration/test_migrations_subjects.py`
- Result: **62 failed, 5 passed, 1 collection error** in 20 s.
  - `test_migrations_documents.py`: 9 failed (tables, enum and catalog objects do not exist; `psycopg.errors.UndefinedTable: relation "documents" does not exist`).
  - `test_document_storage_integrity.py`: 45 failed (same cause).
  - `test_error_text_exposure.py`: 8 failed (the helper cannot build its violations without the tables).
  - `test_document_models.py`: collection error `ModuleNotFoundError: No module named 'app.models.document'`.
  - The 5 passes are the unchanged `test_migrations_subjects.py` tests and one test that does not need the new tables.
- Files added before any production file: `tests/sql_support.py`, `tests/leak_support.py` and the four test modules above. Production files added afterwards: `app/models/document.py`, `app/models/__init__.py` (exports), `alembic/versions/0004_create_documents_and_chunks.py`.

### Result after the implementation
- First green attempt: 74 passed, 1 failed. Then 4 test-expectation errors of mine were corrected: PostgreSQL prints the norm bounds as `(0.000001)::double precision` and `('1000000'::numeric)::double precision`; the FK violation DETAIL carries identifiers, not the chunk text; PostgreSQL prints the embedding component as `1.2345675e+06`; the helper engine does not hide parameters (the application engine does, covered by a test on `create_db_engine`).
- One failure was a **real defect found by the test**, not a test mistake: `blank content` accepted `"\n\t "` because `btrim` strips only spaces. The CHECK was changed from `length(btrim(content)) > 0` to `content ~ '\S'` (a non-whitespace character). The design text was updated.
- Final: targeted modules 75 passed; full backend suite **562 passed** (494 before the change, +68 new); coverage of `app` 98 % (repositories 97 to 100 %).

### Deviations from strict test-first order
1. **`tests/integration/test_migrations_subjects.py`, one existing test edited** (`downgrade -1` became `downgrade 0002`): the test assumed `0003` is the head. It passed before and after the change; the edit keeps its intent. No compensation needed.
2. **`test_error_text_exposure.py` (spike incident I2) tests passed once the tables existed** because the application handlers already log only the exception type. They were red before only because of the missing tables. Compensation: mutation check, see below.
3. **Four of my own test expectations were wrong** (listed above) and were fixed after seeing the real PostgreSQL output; they were corrected against evidence from the catalog and the error messages, not weakened.

### Mutation spot-checks (task 3.4)
Each mutation was applied to migration `0004` (restored afterwards; the file was verified identical), and the storage tests were run.

| Mutation | Catalog tests | Behaviour tests only (integrity module) |
|---|---|---|
| norm-range check replaced by `norm > 0` | killed | killed (`test_magnitude_outside_the_reliable_range_is_rejected_on_insert[5e-07]`) |
| composite FK replaced by a single-column FK | killed | killed (`test_chunk_with_another_subject_than_its_document_is_rejected`) |
| cascade removed from the chunk FK | killed | killed (`test_deleting_a_document_deletes_only_its_chunks`) |
| cascade removed from `documents.subject_id` | killed | killed (`test_deleting_a_subject_deletes_documents_and_chunks_only_of_that_subject`) |
| non-blank content check removed | killed | killed (`test_blank_content_is_rejected[]`) |
| hnsw operator class `vector_cosine_ops` to `vector_l2_ops` | **killed** | survived, as expected: only the catalog assertion sees it (incident I1) |
| hnsw `m` 16 to 24 | **killed** | survived, as expected (catalog only) |

`alembic check` was also run in the mutation of the operator class during the spike (not detected) and the same mutation is detected here only by the catalog test, which confirms the decision I1.

Log-leak guard (I2): the middleware was temporarily changed to log `str(exc)`. The six parametrised cases of `test_application_never_logs_or_returns_database_error_text` failed (killed); the file was restored (`git diff` empty) and the tests pass again.
