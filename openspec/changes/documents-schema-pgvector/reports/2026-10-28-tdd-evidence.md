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

## Group 4 - deterministic embedding helpers and fixture catalog

### Failing run before the implementation
- Command: `uv run pytest -q -p no:cacheprovider --continue-on-collection-errors tests/unit/test_embedding_fixtures.py tests/integration/test_fixture_catalog.py`
- Result: **2 collection errors, 0 tests run** (`ModuleNotFoundError: No module named 'tests.embeddings'` and `'tests.catalog'`).
- Tests written first: `tests/unit/test_embedding_fixtures.py` (17 cases) and `tests/integration/test_fixture_catalog.py` (8 tests). Production-side files added afterwards: `tests/embeddings.py` (standard library only) and `tests/catalog.py`.

### Result after the implementation
- First run: 24 passed, 1 failed. The failure was a wrong expectation of mine: unit vectors stored as single precision have a norm between 0.99999997 and 1.00000002, not exactly 1; the assertion now allows `1e-6`. Two `mypy --strict` annotations were added to the tests.
- The pinned fingerprint of `deterministic_vector(7)` (`051e44ae9f471e7f`) was computed from the implementation once and is a regression guard, not an independent oracle; the cross-process test proves the value is identical under three different `PYTHONHASHSEED` values.
- Full backend suite: **587 passed** (562 before; +25 new). Coverage of `app` 98 %. The seed tests (`test_cli.py`, `test_cli_process.py`) pass unchanged; the CLI seed was not modified.

### Deviations from strict test-first order
1. The pinned fingerprint is derived from the implementation (see above); it protects against later accidental change only.
2. The catalog layout was refined while writing the tests (the best ready Algebra chunk is at 10 degrees, not on the query, so that Physics and Chemistry hold strictly nearer chunks): a test-design decision taken before the implementation.

### Mutation spot-check of the helpers (all restored; files verified identical)
| Mutation | Result |
|---|---|
| `at_angle`: sin replaced by cos | killed (`test_basis_and_angle_vectors_are_unit_length`) |
| `negate` returns the same vector | killed (`...documented_cosine_similarity[opposite]`) |
| deterministic vector not normalised | killed |
| seed ignored | killed (`test_deterministic_vectors_repeat_for_a_seed_and_differ_between_seeds`) |
| enrollment of `student_algebra` dropped | killed (`test_enrollments_cover_...`) |
| `failed` document marked `ready` | killed (`test_documents_cover_every_status_...`) |
| Physics document moved to the Algebra subject | killed |

## Group 5 - `ChunkRepository.find_similar` and vector validation

### Failing run before the implementation
- Command: `uv run pytest -q -p no:cacheprovider --continue-on-collection-errors tests/unit/test_vector_validation.py tests/integration/test_chunk_retrieval.py`
- Result: **2 collection errors, 0 tests run** (`ModuleNotFoundError: No module named 'app.core.vector_validation'`).
- Tests written first: `tests/unit/test_vector_validation.py` (45 cases) and `tests/integration/test_chunk_retrieval.py` (36 tests); support `tests/retrieval_support.py`. Production files added afterwards: `app/core/vector_validation.py`, `app/repositories/chunk_repository.py`.

### Result after the implementation
- First run: 80 passed, 1 failed. The failure was a wrong expectation of mine (the SQL of a student search contains no `subjects` table; a teacher search has no `enrollments`); the test now checks each role's statement separately.
- Full backend suite: **668 passed** (587 before; +81). Coverage of `app` 98 %; `vector_validation.py` and `chunk_repository.py` 100 %. `ruff`, `ruff format --check`, `mypy --strict` (105 files) and `pip-audit` clean.
- Note: integration tests hang (no error) when the compose `db` service is stopped; it was restarted with `docker compose up -d db` (no migration).

### Deviations from strict test-first order
1. The tie-break test first only checked that repeated searches gave the same order; the mutation check showed it could not detect removal of `DocumentChunk.id` from the ORDER BY (survived). It was strengthened to require ascending chunk id among equal similarities and the mutation is now killed.
2. The wrong expectation above (statement text per role).

### Mutation spot-check of `find_similar` (task 5.5; file restored and verified identical each time)
| Mutation | Result (failing tests) |
|---|---|
| subject filter removed | killed (14) |
| enrollment condition removed (`student_id`) | killed (7) |
| enrollment subject condition removed | killed (4) |
| ownership condition removed (`teacher_id`) | killed (5) |
| ownership subject condition removed | killed (3) |
| `ready` filter removed | killed (12) |
| authorization clause removed from WHERE | killed (11) |
| unknown role treated as authorized | killed (1) |
| order direction reversed | killed (7) |
| tie-break removed | survived first, **killed (1) after strengthening the test** |
| `top_k` ignored (fixed 50) | killed (3) |
| `top_k` validation skipped | killed (2) |
| embedding validation skipped | killed (3) |

## Group 6 - review of existing tests (task 6.1)
No new functionality, so there is no failing run. Findings and the scenario map are in `2026-11-07-group-6-regression-review.md`. One robustness fix: the downgrade test of migration `0004` used a relative `-1`; it now targets `0003` (it passed before and after). Full suite 668 passed, also in reverse file order. All deviations of the change are listed in that report.

## Group 11 - corrections after the independent review (see `2026-11-08-independent-review.md`)

### Failing runs before each correction
- F3 and F4 (`tests/unit/test_vector_validation.py`, 6 new cases): **5 failed** before the change (`10**400`, `-(10**400)`, and a sequence whose `__len__` says 384 but yields 383, 385 or 5000 items); the case yielding 0 items already passed because the zero vector was rejected. After the change: 51 passed.
- N2 (a numeric type whose `__float__` raises `ValueError` or `TypeError`, 2 cases): **2 failed**, then 53 passed.
- F2 (log test): strengthened with the real pgvector serialisation and the `hidden` marker. Mutation `hide_parameters=False` in `create_db_engine`: **killed** (it survived the previous version of the test). File restored; `git diff --ignore-cr-at-eol` empty.
- Full suite after the corrections: **676 passed** (668 before; +8). Coverage of `app` 98 %.

### Deviations from strict test-first order
1. **F1 (design I2) was a documentation defect, not a code defect:** the design promised that `find_similar` translates database errors into controlled errors; the implementation propagates them and the test `test_the_repository_does_not_swallow_or_rewrite_database_errors` asserts it, but the divergence was never recorded as a deviation. Found by the independent review. Corrected in `design.md` (I2, dependency row, divergence 6). Compensation: the leak tests (`test_error_text_exposure`, the search-path test) and their mutations show that handlers and middleware keep database error text out of responses and logs.
2. **F2:** the previous log test passed with parameters exposed; it was a weak test that the earlier mutation table did not cover (the hide-parameters mutation was only checked against another test). Now killed by the mutation above.
