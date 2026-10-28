# Spec Delta

## Purpose

Defines the persisted model of uploaded documents and their embedded text chunks, so that later changes can store and read course material with referential integrity between document, chunk and subject, and with the database enforcing what must never be inconsistent.

## ADDED Requirements

### Requirement: Migration 0004 creates the document model reversibly
Migration `0004` SHALL create the native enum `document_status` (`pending`, `processing`, `ready`, `failed`) and the tables `documents` and `document_chunks` exactly as described in `docs/data-model.md`, on top of migration `0003`, and its `downgrade` SHALL remove the tables and the enum without touching the `vector` extension, migrations `0001` to `0003` or any existing table.

#### Scenario: Upgrade on a database at 0003
- **WHEN** `alembic upgrade head` runs on a database at revision `0003`
- **THEN** `documents` and `document_chunks` exist with their constraints and indexes, and the `users`, `subjects` and `enrollments` tables and their rows are unchanged

#### Scenario: Upgrade on an empty database
- **WHEN** `alembic upgrade head` runs on a clean database
- **THEN** all migrations apply in order and the resulting schema has no drift between the models and the migrations (`alembic check` reports none)

#### Scenario: Downgrade and re-upgrade
- **WHEN** `alembic downgrade -1` runs from `0004` and then `alembic upgrade head` runs again
- **THEN** the downgrade removes both tables and the `document_status` type, the `vector` extension is still installed, and the second upgrade succeeds

### Requirement: Embeddings have a fixed dimension of 384
`document_chunks.embedding` SHALL be a mandatory `vector(384)` column, and the database MUST reject a chunk whose embedding is missing, has a different number of dimensions, or has zero norm.

#### Scenario: Valid embedding
- **WHEN** a chunk is inserted with 384 finite components and a non-zero norm
- **THEN** the row is stored and returned with the same values

#### Scenario: Wrong dimension
- **WHEN** a chunk is inserted with 383 or 385 components
- **THEN** the database rejects the insert and no row is stored

#### Scenario: Missing embedding
- **WHEN** a chunk is inserted without an embedding
- **THEN** the database rejects the insert

#### Scenario: Zero vector
- **WHEN** a chunk is inserted whose embedding has every component equal to zero
- **THEN** the database rejects the insert, because cosine distance is undefined for it

#### Scenario: Non-finite values
- **WHEN** a chunk is inserted whose embedding contains `NaN` or infinity
- **THEN** the database rejects the insert

### Requirement: A chunk can never belong to another subject than its document
`documents` SHALL have a unique key on `(id, subject_id)` and `document_chunks (document_id, subject_id)` SHALL reference it, so the denormalized `document_chunks.subject_id` always equals the subject of the document it belongs to.

#### Scenario: Consistent chunk
- **WHEN** a chunk is inserted with the `document_id` and `subject_id` of an existing document
- **THEN** the row is stored

#### Scenario: Chunk pointing to a different subject
- **WHEN** a chunk is inserted whose `subject_id` differs from the subject of its `document_id`
- **THEN** the database rejects the insert with a foreign key violation

#### Scenario: Chunk of a missing document
- **WHEN** a chunk is inserted for a `document_id` that does not exist
- **THEN** the database rejects the insert

#### Scenario: Subject of a document cannot change underneath its chunks
- **WHEN** an update tries to change `documents.subject_id` while the document has chunks
- **THEN** the database rejects the update and the chunks keep matching their document

### Requirement: Deleting data cascades through the hierarchy
Deleting a subject SHALL delete its documents and their chunks, and deleting a document SHALL delete its chunks, with no orphan rows left and no effect on other subjects, documents, users or enrollments.

#### Scenario: Delete a document
- **WHEN** a document with several chunks is deleted
- **THEN** all its chunks are deleted and the other documents of the same subject keep all their chunks

#### Scenario: Delete a subject
- **WHEN** a subject with documents and chunks is deleted
- **THEN** its documents and chunks are deleted, and the documents and chunks of other subjects, the users and the enrollments of other subjects are unchanged

#### Scenario: Teacher with subjects stays protected
- **WHEN** an attempt is made to delete a teacher who still owns a subject that has documents
- **THEN** the existing `RESTRICT` rule on `subjects.teacher_id` still rejects it and nothing is deleted

### Requirement: Document and chunk data obey integrity checks
The database SHALL enforce: `documents.size_bytes >= 0`, `documents.chunks_count >= 0`, `document_chunks.chunk_index >= 0`, `document_chunks.page_number >= 1` when present, a non-blank `content`, and uniqueness of `(document_id, chunk_index)`; `documents.status` MUST be one of the enum values and default to `pending`, and `chunks_count` MUST default to `0`.

#### Scenario: Negative or blank values
- **WHEN** a row is inserted with a negative `size_bytes`, `chunks_count` or `chunk_index`, a `page_number` below 1, or a `content` that is empty or only whitespace
- **THEN** the database rejects the insert

#### Scenario: Duplicate chunk position
- **WHEN** two chunks of the same document share a `chunk_index`
- **THEN** the second insert is rejected, and the same index in another document is accepted

#### Scenario: Invalid status
- **WHEN** a document is inserted with a status outside the enum
- **THEN** the database rejects the insert

#### Scenario: Defaults
- **WHEN** a document is inserted with only its mandatory metadata
- **THEN** its status is `pending`, `chunks_count` is `0`, `error_message` is null and `created_at` is set by the database

### Requirement: Indexes support subject-scoped similarity search
`document_chunks` SHALL have an `hnsw` index on `embedding` with the cosine operator class and default parameters, and a b-tree index on `subject_id`; `documents` SHALL have an index on `subject_id`.

#### Scenario: Indexes exist with the required definition
- **WHEN** the catalog of a migrated database is inspected
- **THEN** an `hnsw` index with `vector_cosine_ops` exists on `document_chunks.embedding`, and b-tree indexes exist on `document_chunks.subject_id` and `documents.subject_id`, all named with the project's naming convention

### Requirement: Logs and errors never expose chunk text or embeddings
Failures while storing or reading documents and chunks MUST NOT write chunk text, embeddings or SQL parameter values to application logs or error responses.

#### Scenario: Statement error on a chunk insert
- **WHEN** an insert of a chunk fails at statement level (for example, a wrong dimension)
- **THEN** the captured application log contains neither the chunk text nor any embedding value
