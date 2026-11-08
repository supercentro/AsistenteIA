# Proposal

## Why

Every later feature of the RAG assistant (ingestion, material management, chat, erasure) reads or writes `documents` and `document_chunks`, and every chunk read must be isolated by subject and by the acting user (`docs/base-standards.md` section 9.4). This change creates that storage and the one retrieval primitive that enforces the isolation, before any code writes real data (change 5 of 13 in the approved plan, Ticket 3 of `readme.md`). Doing the schema first lets the integrity rules (composite foreign key, cascades, checks) and the pgvector behaviour (dimension, index, cosine search) be proven on a real PostgreSQL before ingestion and chat depend on them.

The scope is defined by Ticket 3 of `readme.md` plus the decisions D1-D9 approved by the user for this change (recorded in `design.md`); it is not defined by a pre-existing OpenSpec capability.

## What Changes

- Migration `0004` (with `downgrade`) creating the native enum `document_status` and the tables `documents` and `document_chunks` as defined in `docs/data-model.md`, with `embedding vector(384)`, an `hnsw (embedding vector_cosine_ops)` index with default parameters, a b-tree index on `document_chunks.subject_id`, `CHECK` constraints and cascades. The `vector` extension stays owned by migration `0001`; earlier migrations are not edited.
- Integrity by composite foreign key: `documents` gains `UNIQUE (id, subject_id)` and `document_chunks (document_id, subject_id)` references it, so a chunk can never carry a `subject_id` different from its document's (D1).
- SQLAlchemy models `Document` and `DocumentChunk`, and the pgvector column type (compatibility spike result and fallback in `design.md`, D7).
- `ChunkRepository.find_similar` (the only repository of this change): takes the acting user, the subject, a 384-dimension query embedding and `top_k`; verifies enrollment (student) or ownership (teacher) **inside the SQL**; returns scored chunks ordered by cosine similarity; rejects zero, non-finite and wrongly sized vectors before touching the database (D2, D3, D8). There is no authorization bypass and no generic read method.
- Deterministic test fixtures (SQL inserts with precomputed embeddings) for documents and chunks; no model is loaded and no production seed is created (D4, D5). The existing seed (users only) is unchanged.
- The search is exact and subject-filtered as the functional reference; HNSW is created per the contract but is neither forced nor tuned without `EXPLAIN` and recall evidence.
- Pin the PostgreSQL image (PostgreSQL 15, same pgvector version as the current installation) to a verified `pgvector/pgvector:<version>-pg15` tag in Docker Compose and CI, after verifying it during the apply (compatibility item of the user's approval).
- Documentation: `docs/data-model.md` (composite FK, referential-action row, implemented status), `docs/backend-standards.md` (seed line contradicting the approved decision, `find_similar` contract), `docs/development_guide.md` (image pin, migration), `docs/technical-debt.md` (new residual risks). `readme.md` Ticket 3 is **not** edited; its divergences are reported (see `design.md`, "Reported divergences").

Out of scope (not added): file upload and validation, text extraction, chunking, embedding generation or any embedding model, RAG search over HTTP and chat, `MIN_SIMILARITY` thresholding, document or chunk write repositories and services (`add_many`, status transitions, deletion), document endpoints (already in `docs/api-spec.yml`; implemented in changes 6 and 7), conversations and messages (change 8), production or demo seed data, frontend screens, retention or per-subject quota limits, ivfflat or alternative index types, and HNSW tuning.

**BREAKING**: none. No existing table, column, endpoint or migration changes.

## Capabilities

### New Capabilities
- `document-storage`: the persisted model of uploaded documents and their embedded chunks: migration `0004`, status enum, vector dimension, referential integrity between document, chunk and subject, cascades and `CHECK` constraints, reversibility.
- `chunk-retrieval`: actor-scoped similarity search over chunks: authorization inside SQL for students and teachers, cosine ordering and score, validation of the query vector and `top_k`, behaviour when the actor has no access, and no leakage of vectors or text in errors and logs.

### Modified Capabilities
<!-- None: no existing requirement changes. -->

## Impact

- **Authorization / data isolation**: new chunk reads are scoped by subject **and** by the acting user in the repository layer (`docs/base-standards.md` section 9.4). A student not enrolled, a teacher who does not own the subject and any other role receive no rows. Every rule has a negative test, and mutation checks prove the filters matter. An independent adversarial review is required (it is isolation logic).
- **Personal data (GDPR)**: documents and chunks hold course material, not personal data of students. Cascades from subject deletion are fixed here so that change 11 (erasure) inherits them. Logs must never contain chunk text or embeddings.
- **External services**: none. Gemini is not involved and no embedding model is called; the vector dimension (384) is pinned to the planned `paraphrase-multilingual-MiniLM-L12-v2` model.
- **Dependencies**: adds the Python package `pgvector` and pins the database image, only if the compatibility spike of the apply confirms them (`design.md`, D7 and D10); `uv.lock` is committed.
- **Code**: `backend/alembic/versions/0004_*`, `backend/app/{models,repositories}`, `backend/pyproject.toml`/`uv.lock`, `docker-compose.yml`, `.github/workflows/ci.yml`, backend tests and fixtures.
- **Docs**: `docs/data-model.md`, `docs/backend-standards.md`, `docs/development_guide.md`, `docs/technical-debt.md`, and `docs/lessons-learned.md` only if the review or process yields a lesson. `docs/api-spec.yml` does **not** change in this change (its `Document` schema lacks `required`; that is corrected with evidence in change 6).
- **Dependent changes**: 6 `document-ingestion` writes documents and chunks (needs this schema and the ownership-in-SQL write rule), 7 `teacher-material-ui` lists and deletes documents, 9 `rag-chat` calls `find_similar` and applies `MIN_SIMILARITY`, 11 `personal-data-erasure` relies on the cascades, 12 and 13 use the fixtures for E2E and decide demo data and image pinning for delivery.
