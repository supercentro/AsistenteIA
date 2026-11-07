# Tasks

Reports required by `docs/openspec-tasks-mandatory-steps.md` are saved in `openspec/changes/documents-schema-pgvector/reports/`. Every group writes its failing tests first and lands its own tests and documentation. Backend only: no frontend code and no endpoint change. Decisions D1-D11 are in `design.md`; items marked "verify in apply" there are gates: if one fails, stop and revise the artifacts with `/opsx:update` before coding on. The lessons in `docs/lessons-learned.md` and sections 9.2, 9.4, 9.7 and 9.8 of `docs/base-standards.md` apply. No `readme.md` or `prompts.md` edits without explicit approval.

## 0. Setup: Create Feature Branch (MANDATORY - FIRST STEP)

- [ ] 0.1 Verify the current branch is `feature/documents-schema-pgvector` (created from `main` at `db06d50` during planning; `git branch --show-current`) and that it contains no code changes yet
- [ ] 0.2 Confirm the branch is based on the published `main` (`git merge-base --is-ancestor db06d50 HEAD`)
- [ ] 0.3 Start the stack (`docker compose up -d db`), confirm `uv run pytest -q` is green on the starting point and record the baseline of `asistenteia` and `asistenteia_test` (extension version, tables, `alembic_version`, row counts)
- [ ] 0.4 Create `reports/YYYY-MM-DD-ai-usage-notes.md` and keep it updated with the literal user prompts, decisions and AI findings of this change (source for the later `prompts.md` proposal)

## 1. Compatibility Spike and Image Pin (GATE, verify in apply; isolated)

Isolation rules: a throwaway virtual environment outside the repository and a throwaway PostgreSQL container with its own scratch database and no port shared with the project (never `asistenteia`, `asistenteia_test` or any production database; no migration on the development database); nothing is installed in the project. Reports never contain vector values. If any item fails, stop, write the failure in the spike report and present alternatives to the user before changing architecture, migrations or standards.

- [x] 1.1 Image (D10): confirm `pgvector/pgvector:0.8.7-pg15` exists and pulls; start it as the scratch container; verify `SHOW server_version` is 15.x and `extversion` is `0.8.7`; confirm with read-only queries that the extension version matches the current development installation
- [x] 1.2 pgvector-python with psycopg 3 and SQLAlchemy (D7): in the throwaway environment install the current `pgvector` with the project's SQLAlchemy and psycopg versions; insert and read back a `vector(384)` without `register_vector`; run a cosine-distance query through `cosine_distance`; record the exact exception class for wrong dimension, `NaN`, infinity, zero vector, non-numeric items and `None` (library or PostgreSQL), and the behaviour on an empty database without the extension
- [x] 1.3 Alembic (D7): on the scratch database, autogenerate a revision for a model with the column and the hnsw index (`postgresql_using='hnsw'`, `postgresql_with`, `postgresql_ops`); verify the rendered migration, `upgrade`, `downgrade` and `alembic check`; record whether any drift is reported
- [x] 1.4 `vector_norm` CHECK (D8): on the scratch database create a table with `CHECK (vector_norm(embedding) > 0)`; verify it is accepted (immutability), rejects a zero vector on insert and update, accepts normal vectors, and does not interfere with the hnsw index build
- [x] 1.5 Write `reports/YYYY-MM-DD-compatibility-spike.md` (commands, versions, outcomes, decisions for D7, D8, D10) and tear down the scratch container and environment; present the report to the user if any item fails or a fallback is needed, and continue only with approval in that case

## 2. Dependency and Image Changes (after the gate passes)

- [x] 2.1 Add the exact `pgvector` version to `backend/pyproject.toml` and refresh `uv.lock` (lock file committed); `pip-audit` clean
- [x] 2.2 Replace the floating image tag with the verified tag in `docker-compose.yml` and `.github/workflows/ci.yml`; document the pin and the extension-update note in `docs/development_guide.md`

## 3. Migration and Models (TDD)

- [x] 3.1 Write failing migration tests (`backend/tests/integration/test_migrations_documents.py`): `0004` upgrade from `0003` and from an empty database creates the enum, both tables, the composite FK, the unique keys, the checks, the hnsw index with `vector_cosine_ops` and the b-tree indexes with convention names; since `alembic check` does not compare operator classes, `WITH` options or CHECK constraints (incident I1), assert them from the PostgreSQL catalog (hnsw access method, `vector_cosine_ops`, `m=16`, `ef_construction=64`, every CHECK definition including `vector_norm(embedding) BETWEEN 1e-6 AND 1e6`, composite FK columns with `ON DELETE CASCADE`, unique keys, enum labels) and keep `alembic check` itself in the gate; the `vector` extension, `users`, `subjects` and `enrollments` and their rows are untouched; downgrade removes tables and enum and keeps the extension; re-upgrade works; record the failing run (command and failure summary) in `reports/YYYY-MM-DD-tdd-evidence.md`
- [x] 3.2 Write failing integrity tests (SQL level, real PostgreSQL) for every scenario of `document-storage`: dimension 383/384/385, missing embedding, zero vector, non-finite values, norm below `1e-6` and above `1e6` (unit vector scaled by `1e-30` and `1e38`, accepted at the edges and for unit vectors; insert and update), chunk with another subject, chunk of a missing document, update of a document's subject while chunks exist, cascade on document delete and on subject delete (other subjects unaffected, a few hundred chunks), `RESTRICT` of a teacher with subjects, checks (negative values, blank content, `page_number` 0), duplicate `(document_id, chunk_index)` accepted in another document, invalid status, defaults; record the failing run
- [x] 3.2b Write the I2 test helper (`backend/tests/`): a log spy attached to the root logger and a factory of real SQL exceptions carrying row data (check violation with a `Failing row contains` detail, wrong dimension, foreign key violation), reusable by change 6; write failing tests proving that the application error handlers and the migration/integrity helpers never emit `exc.orig` text, SQL parameters, chunk text or embedding values to logs or responses; record the failing run
- [x] 3.3 Add the models `Document` and `DocumentChunk` (enum `document_status` with `create_type=False`, pgvector column type per D7) and migration `0004` with `downgrade`; verify 3.1 and 3.2 pass, `alembic upgrade head`, `downgrade -1` and `alembic check` work on the isolated test database and on a throwaway database created for the purpose (by user instruction the development database receives `0004` only in group 8, task 8.1, where `alembic check` is run on it too); `0001` to `0003` unchanged
- [x] 3.4 Mutation spot-check: remove the composite FK, the norm-range check and the cascade, and change the index operator class to `vector_l2_ops`, in turn, and verify a test fails for each (the operator class mutation proves the catalog assertions of I1); record results

## 4. Deterministic Test Fixtures (TDD)

- [x] 4.1 Write failing tests for the fixture helper itself (`backend/tests/`): embeddings are 384 finite non-zero floats, reproducible between runs, with the documented cosine similarity between named vectors (orthogonal, identical, opposite, 45 degrees); no model or network is used
- [x] 4.2 Implement the helper that inserts users, subjects, enrollments, documents and chunks by SQL for several subjects, teachers and students (no ORM write repositories, no change to the CLI seed); verify 4.1 passes and that the seed tests (`test_cli*.py`) still pass unchanged

## 5. Chunk Retrieval (TDD)

- [x] 5.1 Write failing unit tests for the validation of the query vector and `top_k` (383/385/0 components, NaN, infinity, zero norm, norms `1e-7`, `1e-30`, `1e7`, `1e38`, a single component pushing the norm above `1e6`, norms exactly `1e-6` and `1e6` accepted, unit vectors and unit vectors rounded to single precision accepted, non-numeric items, `None`, `top_k` 0, -1, 51); the validation helper holding the range constants is shared and reusable by change 6, including that the error message contains no component and that no statement is executed; record the failing run in the TDD evidence report
- [x] 5.2 Write failing integration tests for every scenario of `chunk-retrieval`: enrolled student, owning teacher, non-enrolled student, other teacher, removed enrollment, unknown subject, other subjects never returned, ranking against known similarities, limit, `ready`-only, complete results with many subjects compared with an exact search of the subject (recall check), parallel searches by different actors, statement-level error logging without vector or text, a real SQL exception with row data raised in the `find_similar` path with log spies (I2), a vector with extremely uneven components inside the range compared with an exact double-precision computation, and accuracy at the range edges (within `1e-6`); record the failing run
- [x] 5.3 Implement `ChunkRepository.find_similar` and `ScoredChunk` per D2, D3 and D8 (filter and authorization inside the SQL; the actor passed as a small immutable value; controlled domain error for invalid input); verify 5.1 and 5.2 pass; `ruff` and `mypy --strict` clean
- [x] 5.4 Capture `EXPLAIN (ANALYZE)` plans of the search on a mixed-subject dataset and record whether the planner uses hnsw, and compare results with the exact search (recall); do not force the index and do not change planner or pgvector settings in code; if the evidence shows incomplete results, present the alternatives to the user (D3) before coding any setting; write the evidence in `reports/YYYY-MM-DD-explain-and-recall.md`
- [x] 5.5 Mutation spot-check: remove in turn the subject filter, the enrollment condition, the ownership condition and the `ready` filter, and verify a test fails for each; record results

## 6. Review and Update Existing Unit Tests (MANDATORY)

- [x] 6.1 Re-read every scenario of `document-storage` and `chunk-retrieval` and confirm each has an automated test; confirm earlier suites (authentication, roles, consent, subjects, enrollments, CLI, health, errors) pass unchanged in intent; list in the TDD evidence report every deviation from test-first order with its justification and the mutation check that compensated it (or state that there were none)

## 7. Run Unit Tests and Verify Database State (MANDATORY)

- [ ] 7.1 Capture the pre-test baseline of `asistenteia` and `asistenteia_test` (extensions and versions, tables, `alembic_version`, row counts)
- [ ] 7.2 Run targeted tests per module, then the full backend suite with coverage (`services/` and `repositories/` at least 80 percent)
- [ ] 7.3 Re-check the same indicators and restore if tests left residue
- [ ] 7.4 Create report `openspec/changes/documents-schema-pgvector/reports/YYYY-MM-DD-step-7-unit-test-and-db-verification.md`

## 8. Manual Verification Against the Real Database (MANDATORY - AGENT MUST EXECUTE; no endpoints are added, so curl does not apply)

- [ ] 8.1 Rebuild the backend image and apply `alembic upgrade head` on the Compose development database; check tables, indexes, constraints and the enum with `psql`; run `alembic downgrade -1` and `upgrade head` again
- [ ] 8.2 With a script run in the backend container (not committed, or committed under the tests tree only if it is a test), load the deterministic fixtures into the development database, call `find_similar` as an enrolled student, as the owner, as a non-enrolled student and as another teacher, and verify results, scores and empty results; check that the backend still starts and `/health` and the login still answer
- [ ] 8.3 Delete the fixture subject and verify by queries that documents and chunks are gone; remove every row created for the test, verify the database equals the pre-test state, and document all commands and outcomes in `reports/YYYY-MM-DD-step-8-real-database-verification.md`

## 9. E2E Verification (not applicable to UI; regression only)

- [ ] 9.1 Record in a report that no frontend or user workflow changes, so the Playwright MCP interactive flow is not applicable; run the frontend gates and `npm run test:e2e` (mocked suite) to prove no regression; run the stack with `docker compose up` following the guide with the pinned image; browser sessions closed

## 10. Update Technical Documentation (MANDATORY)

- [ ] 10.1 Update `docs/data-model.md`: documents and chunks as implemented, composite FK and `UNIQUE (id, subject_id)`, the added referential row for `document_chunks`, checks, indexes, `ready`-only retrieval, migration `0004`; remove the "enforced by the repository when inserting" sentence for `subject_id`
- [ ] 10.2 Update `docs/backend-standards.md`: correct the seed line (users only, as approved in change 2), document the `find_similar` contract (actor, authorization in SQL, empty result for unauthorized, validation, no embeddings in logs) and the image pin
- [ ] 10.3 Update `docs/development_guide.md` (pinned image, migration `0004`, rebuild of the backend image, extension update note) and verify `docs/api-spec.yml` needs no change for this change (state it in the reconciliation report)
- [ ] 10.4 Add to `docs/technical-debt.md` the residual risks of this change: no per-subject document or chunk quota, embedding dimension fixed in the schema (model change needs migration and reindex), HNSW parameters and filtered-ANN behaviour to revisit with real data (change 12), and any risk accepted by the user after the review; keep IDs sequential from the register
- [ ] 10.5 Invoke the `update-docs` skill itself (not only its checklist), apply what it reports and note the invocation in the AI usage notes; confirm `prompts.md` is untouched and that `readme.md` is untouched (report the Ticket 3 divergences instead)
- [ ] 10.6 Write `reports/YYYY-MM-DD-contract-reconciliation.md` comparing, across the delta specs, `docs/data-model.md`, the models, the migration and the database catalog: columns, types, nullability, defaults, constraints, indexes, cascades and the status values; fix or report every mismatch

## 11. Adversarial Review (required for data isolation)

- [ ] 11.1 Run an independent adversarial review with the `adversarial-review` skill, executed by a separate subagent or a clean-context session (not the implementing session), read-only on the repository and probing only the isolated test database or the live stack; cover isolation between subjects, teachers and students, the composite FK, cascades, authorization conditions in the SQL, filtered-ANN completeness, extreme vectors, concurrency, log and error leakage and the migration; save `reports/YYYY-MM-DD-independent-review.md` with findings, severity, fixes and a final verdict
- [ ] 11.2 Fix findings of this change (tests first) and re-run affected tests; the change is not closed while a blocker or major finding is open; record accepted risks in `docs/technical-debt.md` with the user's agreement and, only for relevant findings or process deviations, append a lesson to `docs/lessons-learned.md`

## 12. Final Verification of MUST Quality Gates (`docs/base-standards.md` section 9)

- [ ] 12.1 Section 9.1 typing and validation: `uv run mypy --strict app tests`; no raw `dict` crossing the API layer (no API change)
- [ ] 12.2 Section 9.2 testing: unit and integration green on a real PostgreSQL with pgvector; every authorization rule has a negative test; no external service called; the TDD evidence report is complete; state why real-server tests do not apply (no behaviour depending on Uvicorn, headers or transport)
- [ ] 12.3 Sections 9.3 and 9.4 security and isolation: reads scoped by subject and actor in the repository, no secrets in repository or logs, dependency pinned in `uv.lock`, `pip-audit` clean
- [ ] 12.4 Section 9.6 lint and format: `ruff check` and `ruff format --check`; frontend lint, format, typecheck and tests still green
- [ ] 12.5 Section 9.7 migrations: `0004` upgrade and downgrade on a clean database, `alembic check` clean on the development and test databases, `0004` not edited after its first commit, earlier migrations unchanged, `docker compose up --build` starts the stack
- [ ] 12.6 Section 9.8 documentation and traceability updated in this change (status codes, limits, field rules and constraints agree across the specs, `docs/data-model.md`, tests and implementation); conventional commits prepared (commits, push and Pull Request only when the user asks)
- [ ] 12.7 Run `openspec validate documents-schema-pgvector --strict` and `openspec validate --all --strict`, and tick this change's tasks only after all items above pass

## Workflow follow-up

- Open the Pull Request from `feature/documents-schema-pgvector` to `main` when the user requests it and confirm the CI run is green (the CI database image is pinned in group 2).
- Archive with `/opsx:archive` after review and merge (the independent adversarial review in group 11 is a prerequisite).
- Propose to the user the `prompts.md` entry for this change, built from the AI usage notes (literal fragments versus summaries); do not edit `prompts.md` without approval.
