# Data Model (AsistenteIA)

Canonical database model. PostgreSQL 15 + `pgvector`. Managed only through Alembic migrations.
`readme.md` section 3 is a simplified academic summary; if they diverge, this document wins (see `base-standards.md` §0).

Status: `users`, `subjects`, `enrollments`, `documents` and `document_chunks` are **implemented** (migrations `0002` to `0004`); the conversation tables are a **proposed design for implementation**. The differences from the `readme.md` summary are listed in [Changes vs readme.md](#changes-vs-readmemd).

## Entity Relationship Diagram

```mermaid
erDiagram
    USERS ||--o{ SUBJECTS : "teaches"
    USERS ||--o{ ENROLLMENTS : "is enrolled (student)"
    SUBJECTS ||--o{ ENROLLMENTS : "has"
    SUBJECTS ||--o{ DOCUMENTS : "contains"
    DOCUMENTS ||--o{ DOCUMENT_CHUNKS : "is split into"
    SUBJECTS ||--o{ DOCUMENT_CHUNKS : "scopes"
    USERS ||--o{ CONVERSATIONS : "starts (student)"
    SUBJECTS ||--o{ CONVERSATIONS : "is queried in"
    CONVERSATIONS ||--o{ MESSAGES : "contains"
    MESSAGES ||--o{ MESSAGE_SOURCES : "cites"
    DOCUMENT_CHUNKS ||--o{ MESSAGE_SOURCES : "is cited by"

    USERS {
        uuid id PK
        string name
        string email UK
        string password_hash
        enum role "teacher | student"
        string consent_version "nullable until accepted"
        timestamptz consent_accepted_at "nullable"
        timestamptz created_at
    }
    SUBJECTS {
        uuid id PK
        string name
        text description
        uuid teacher_id FK
        timestamptz created_at
    }
    ENROLLMENTS {
        uuid id PK
        uuid subject_id FK
        uuid student_id FK
        timestamptz created_at
    }
    DOCUMENTS {
        uuid id PK
        uuid subject_id FK
        string filename
        string content_type
        bigint size_bytes
        enum status "pending | processing | ready | failed"
        text error_message "nullable"
        int chunks_count
        timestamptz created_at
    }
    DOCUMENT_CHUNKS {
        uuid id PK
        uuid document_id FK
        uuid subject_id FK "denormalized; composite FK with document_id"
        int chunk_index
        int page_number "nullable"
        text content
        vector_384 embedding
        timestamptz created_at
    }
    CONVERSATIONS {
        uuid id PK
        uuid student_id FK
        uuid subject_id FK
        timestamptz created_at
    }
    MESSAGES {
        uuid id PK
        uuid conversation_id FK
        enum role "user | assistant"
        text content
        timestamptz created_at
    }
    MESSAGE_SOURCES {
        uuid id PK
        uuid message_id FK
        uuid chunk_id FK "nullable (SET NULL)"
        string document_filename "snapshot"
        int page_number "nullable snapshot"
        int rank
        float score
    }
```

## Entities

### users
- `id` uuid PK (default `gen_random_uuid()`); `name` varchar(100) not null; `email` varchar(255) unique not null (ASCII only and stored lowercase, enforced by check constraints `ck_users_email_lowercase`: `email = lower(email)` and `ck_users_email_ascii`: `octet_length(email) = char_length(email)`; internationalised domains are stored in punycode); `password_hash` text not null (Argon2id); `role` PostgreSQL enum type `user_role` (`teacher`, `student`) not null.
- `consent_version` varchar(20) and `consent_accepted_at` timestamptz: evidence of the privacy-policy acceptance; only the latest acceptance is stored (re-acceptance overwrites both). The recorded version must equal the currently configured policy version (`PRIVACY_POLICY_VERSION`). The API must refuse chat usage until consent for the current version is recorded (enforced by the chat change).
- Teacher accounts are created only by the `python -m app.cli create-teacher` and `seed` commands (public registration creates students), so a role can never be self-assigned.
- Validation: email format and ASCII-only characters (look-alike Unicode addresses cannot become separate accounts); password length 10-128 (validated at the API layer, never stored; passwords are not Unicode-normalized).
- Created by migration `0002` (downgrade drops the table, then the `user_role` type).

### subjects
- `teacher_id` FK → users (must have role `teacher`, enforced in the service layer), `ON DELETE RESTRICT`. Unique `(teacher_id, name)`; names are compared exactly (case-sensitive) after trimming.
- `name` is `varchar(150)`, `description` is nullable `text` (API limit 2000 characters); input rules (single-line trimmed name, no control or direction characters) are enforced at the API layer.
- Listings are ordered by `name`, then `id`, and are not paginated in the MVP (TD-016 in `technical-debt.md`).
- Created by migration `0003` (downgrade drops `enrollments`, then `subjects`).

### enrollments
- Links a student to a subject. Unique `(subject_id, student_id)`. The student must have role `student` (service layer).
- Created by the subject's teacher (by student email; an unknown email or a non-student account is a 404, there is no pre-enrollment). Self-enrolment is not part of the MVP.
- Index `ix_enrollments_student_id` serves the student's subject listing and the later erasure of a student's data.
- `created_at` defaults to `clock_timestamp()` (not `now()`), so enrollments created in one transaction keep their insertion order; listings are ordered by `created_at`, then `id`.
- Both foreign keys are `ON DELETE CASCADE`: deleting a subject or a student account removes the enrollments (not the other party).
- Created by migration `0003`.

### documents
- One row per uploaded **original file**. The original binary is not stored in the database (see backend standards, "File handling"); only metadata and extracted chunks are.
- `status`: `pending` → `processing` → `ready` | `failed`. `error_message` is a short, non-sensitive reason for `failed`.
- Supported `content_type`: `application/pdf`, `text/plain` (and `text/markdown`). Max size configured via `MAX_UPLOAD_MB`. The database does not restrict `content_type` values (validated at upload), so a new type needs no migration.
- Columns: `id` uuid (`gen_random_uuid()`), `subject_id` uuid not null, `filename` varchar(255) not null, `content_type` varchar(100) not null, `size_bytes` bigint not null, `status` enum `document_status` (`pending`, `processing`, `ready`, `failed`) not null default `pending`, `error_message` text null, `chunks_count` integer not null default 0, `created_at` timestamptz not null default `now()`.
- Checks: `size_bytes >= 0`, `chunks_count >= 0`. Unique `(id, subject_id)` (`uq_documents_id`): the target of the composite foreign key of `document_chunks`. Index `ix_documents_subject_id`.
- `subject_id` cannot be changed while the document has chunks (the composite foreign key has no `ON UPDATE` action).
- Created by migration `0004` (downgrade drops `document_chunks`, then `documents`, then the `document_status` type; the `vector` extension is kept).

### document_chunks
- One row per **text fragment** with its embedding. `embedding` is `vector(384)` (`paraphrase-multilingual-MiniLM-L12-v2`).
- `subject_id` is intentionally denormalized so that every similarity query can filter by subject without a join and the index/scoping cannot be bypassed by forgetting the join. It always equals `documents.subject_id`, **enforced by the database**: the composite foreign key `(document_id, subject_id)` references `documents (id, subject_id)` (`ON DELETE CASCADE`), so a chunk of another subject than its document cannot be stored.
- Columns: `id` uuid (`gen_random_uuid()`), `document_id` and `subject_id` uuid not null, `chunk_index` integer not null, `page_number` integer null, `content` text not null, `embedding` `vector(384)` not null, `created_at` timestamptz not null default `now()`.
- Unique `(document_id, chunk_index)`.
- Checks: `chunk_index >= 0`, `page_number IS NULL OR page_number >= 1`, `content ~ '\S'` (at least one non-whitespace character), and `vector_norm(embedding)` between `1e-6` and `1e6`. The norm range rejects the zero vector (cosine distance is `NaN` for it) and the magnitudes for which pgvector 0.8.7 returns `NaN` or a wrong distance; embeddings are neither normalised nor rescaled. `NaN`, infinity and a wrong dimension are rejected by the `vector(384)` type. The application helper `validate_embedding` is stricter than the CHECK on purpose: it measures the norm on the single-precision values the database stores and rejects norms within a relative `1e-12` of either limit, so a vector it accepts also passes the CHECK (bind the vector it returns). The range depends on the pgvector version: see `openspec/changes/archive/2026-11-08-documents-schema-pgvector/reports/2026-10-28-magnitude-experiment.md`.
- Indexes: `ix_document_chunks_embedding` `hnsw (embedding vector_cosine_ops)` with `m=16` and `ef_construction=64` (defaults); b-tree `ix_document_chunks_subject_id`. Alembic does not compare operator classes, index options or CHECK constraints, so the migration tests assert them from the PostgreSQL catalog.
- Retrieval reads only chunks of documents in status `ready` through `ChunkRepository.find_similar`, which filters by subject and checks the actor's enrollment or ownership inside the SQL statement (see `backend-standards.md`, section 7). The search is an exact, subject-filtered scan; the hnsw index is not used by the current plan (TD-022 in `technical-debt.md`).
- Created by migration `0004`.
- Chunk size must fit the embedding model's input limit (about 128 word pieces; verify against the model card) — see backend standards.

### conversations
- One thread of a student about one subject. The student must be enrolled in the subject when the conversation is created.
- Index on `(student_id, subject_id, created_at)`.

### messages
- `role` enum `user|assistant`. Assistant messages have 0..N `message_sources`.

### message_sources
- Citation of a chunk used to build an assistant answer. `document_filename` and `page_number` are **snapshots** so a citation remains readable if the document is later deleted (`chunk_id` becomes NULL).
- `rank` (1 = most relevant) and `score` (cosine similarity) allow RAG quality analysis.

## Referential actions

| Relationship | On delete |
|---|---|
| subjects.teacher_id → users | RESTRICT (a teacher's subjects must be deleted/reassigned first) |
| enrollments.subject_id → subjects | CASCADE |
| enrollments.student_id → users | CASCADE |
| documents.subject_id → subjects | CASCADE |
| document_chunks.(document_id, subject_id) → documents.(id, subject_id) | CASCADE (composite foreign key; a single-column foreign key on `document_id` does not exist) |
| conversations.student_id → users | CASCADE (right to erasure) |
| conversations.subject_id → subjects | CASCADE |
| messages.conversation_id → conversations | CASCADE |
| message_sources.message_id → messages | CASCADE |
| message_sources.chunk_id → document_chunks | SET NULL |

## Data protection rules

- Personal data: `users` (name, email), conversation content, consent evidence. No other personal data is stored.
- Right to erasure: deleting one conversation, deleting all of a student's conversations, or deleting the account removes rows physically (no soft delete) via the cascades above.
- Retention: conversation data lives until the user deletes it or the account is deleted. Application logs must not contain message content or document text.
- Third-party processing: message text and retrieved chunks are sent to Gemini. This must be disclosed in the privacy policy shown at consent time.

## Changes vs readme.md

1. Added `enrollments` (the readme requires "enrolled student" but had no entity).
2. Split the readme's `DOCUMENT` into `documents` (original file) and `document_chunks` (fragment + embedding).
3. Replaced `MESSAGE.source_document_id` by `message_sources` (an answer cites 1..N chunks).
4. Added consent fields to `users` and `status`/`error_message` to `documents`.
5. Index changed from `ivfflat` to `hnsw` (ivfflat quality depends on data existing when the index is built).
6. `document_chunks.subject_id` is tied to its document by a composite foreign key instead of being checked by the repository, and `documents` gained `ix_documents_subject_id`.

The `readme.md` summary (sections 2.5, 3, 4, 5 and 6) was aligned with these changes with the user's approval.
