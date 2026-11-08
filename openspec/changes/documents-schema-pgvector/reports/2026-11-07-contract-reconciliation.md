# Contract reconciliation (task 10.6)

Date: 2026-11-07. Sources compared: the delta specs `document-storage` and `chunk-retrieval`, `docs/data-model.md` (updated in this group), the models (`backend/app/models/document.py`), migration `0004`, and the live PostgreSQL catalog of the development database `asistenteia` at revision `0004` (read-only). Method: an automated comparison of the SQLAlchemy metadata with the catalog (columns, types, nullability, default presence, indexes, unique, check and foreign-key constraints, cascades, enum labels) plus a manual reading of the specs and of `data-model.md`. The comparison script is not committed; the catalog assertions that stay in the repository are in `tests/integration/test_migrations_documents.py`.

## Result of the automated model-to-catalog comparison
No mismatch. `documents` (9 columns) and `document_chunks` (8 columns) agree between model and database on type, nullability and default presence; the two b-tree indexes, the hnsw index, the unique keys (`uq_documents_id` on `(id, subject_id)`, `uq_document_chunks_document_id` on `(document_id, chunk_index)`), the six check names, the two foreign keys with `ON DELETE CASCADE` (the one of `document_chunks` is composite on `(document_id, subject_id)`) and the four enum labels are identical. `alembic check` reports no drift (group 8). The model reports `DateTime(timezone=True)` and the catalog `timestamptz`: same type.

## Item by item
| Item | Spec | `data-model.md` | Model | Migration `0004` | Catalog | Verdict |
|---|---|---|---|---|---|---|
| `documents` columns, types, nullability, defaults | `document-storage` (defaults scenario) | documents section (updated) | `Document` | yes | `filename` varchar(255), `content_type` varchar(100), `size_bytes` bigint, `status` default `pending`, `chunks_count` default 0, `created_at` default `now()` | match |
| `size_bytes` type | not stated | ERD said `int`; now `bigint` | `BigInteger` | `bigint` | `int8` | **fixed** in `data-model.md` (was a document error, not a code error) |
| `document_chunks` columns | embedding dimension 384, nullable `page_number` | updated | `DocumentChunk` | yes | `vector(384) NOT NULL`, `page_number` null | match |
| Status values | `pending`, `processing`, `ready`, `failed` | same | `DocumentStatus` | enum | same four labels | match |
| Checks | negatives, blank, page >= 1, norm range | listed | six `CheckConstraint`s | six | six | match |
| Composite FK / `UNIQUE (id, subject_id)` | "A chunk can never belong to another subject than its document" | described, referential table row added | `ForeignKeyConstraint` | yes | `FOREIGN KEY (document_id, subject_id) REFERENCES documents(id, subject_id) ON DELETE CASCADE` | match |
| Cascades | document, subject, teacher protected | referential table | `ondelete` | yes | `confdeltype = c` (both); `subjects.teacher_id` stays RESTRICT (unchanged) | match |
| `ON UPDATE` of the composite FK | "subject of a document cannot change under its chunks" | documented | default | default | `confupdtype = a` (no action) | match |
| Indexes | hnsw cosine, b-tree on `subject_id` of both tables | updated (`m=16`, `ef_construction=64`) | `Index(...)` | yes | hnsw `vector_cosine_ops` reloptions `{m=16,ef_construction=64}`; two b-tree | match |
| `ready`-only retrieval, scoping, ordering, validation | `chunk-retrieval` | `data-model.md` and `backend-standards.md` section 7 | `ChunkRepository.find_similar` | n/a | covered by tests | match |
| Norm range `1e-6` to `1e6` | spec and design D8 | documented with the reference to the experiment | check constraint | yes | check present | match |
| Seed | design D5 (no seed) | n/a | n/a | n/a | n/a | `backend-standards.md` seed line **corrected** (users only) |
| `find_similar` signature | spec (actor first) | n/a | `find_similar(actor, subject_id, query_embedding, top_k)` | n/a | n/a | `backend-standards.md` section 6 and 7 **corrected** |

## Contract documents that need no change
- `docs/api-spec.yml`: this change adds no endpoint. The `Document` schema (`id`, `subject_id`, `filename`, `content_type`, `size_bytes` integer, `status` with the four values, `error_message` nullable, `chunks_count`, `created_at`) matches the table, and `size_bytes` as a JSON integer is compatible with `bigint`. The upload and listing endpoints belong to changes 6 and 7. **Verified: no change required.**
- `readme.md` and `prompts.md`: untouched (`git status` shows no change to either).

## Divergences with the Ticket 3 text of `readme.md` (reported, not fixed; the readme needs the user's approval)
1. Ticket 3 (line 687) asks for a seed of test documents with precomputed embeddings; `docs/backend-standards.md` also said the seed creates "sample chunks". The seed approved in change 2 creates users only. Resolved by D5: no seed, deterministic fixtures in the tests (`tests/catalog.py`).
2. Ticket 3 (line 686) gives `find_similar(subject_id, query_embedding, top_k)`; `docs/base-standards.md` 9.4 requires scoping by the authenticated user in the repository. Implemented as `find_similar(actor, subject_id, query_embedding, top_k)` (D2). The readme text and the RAG ticket (line 634) still describe the shorter signature.
3. The readme's data model summary (line 317) says `subject_id` is denormalized "to always filter by subject"; the implementation additionally ties it to the document with a composite foreign key. Compatible, but the readme does not mention it.
4. Ticket 3 states "Dependencias: ninguna", but the tables need `subjects` (change 3, merged). Informational.
5. The readme asks for an hnsw index on the embedding; it exists but the exact search does not use it (TD-022). Informational for the RAG ticket.

## Documentation changes made in this group (task 10.1 to 10.4)
`docs/data-model.md` (implemented tables, columns, checks, composite FK, indexes, `ready`-only retrieval, migration `0004`; the sentence "enforced by the repository when inserting" removed; `size_bytes` bigint), `docs/backend-standards.md` (seed line, `find_similar` contract, image pin), `docs/development_guide.md` (migration `0004`, rebuild and downgrade warning, "Ports already in use" with the temporary Compose override, how to check who owns a port, Playwright `reuseExistingServer` and the stopped-`db` hang), `docs/technical-debt.md` (TD-023 quota, TD-024 fixed dimension and pgvector-version dependence, TD-025 hnsw parameters and filtered approximate search; TD-022 was added in group 6). No risk was accepted by the user after a review yet: the adversarial review is group 11, and its accepted risks will be added then with the next IDs.
