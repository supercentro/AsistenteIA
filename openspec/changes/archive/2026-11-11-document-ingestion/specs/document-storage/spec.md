# Spec Delta

## ADDED Requirements

### Requirement: Every document has at most one persistent job
The database SHALL hold a table of ingestion jobs with exactly one row per document, removed with the document, that carries the temporary file bytes (nullable), the attempt count, and the lease owner and expiry, so that a job survives restarts and can be claimed safely.

#### Scenario: One job per document
- **WHEN** a second job is inserted for the same document
- **THEN** the database rejects it

#### Scenario: Cascade
- **WHEN** a document or its subject is deleted
- **THEN** its job and the temporary bytes are deleted with it

#### Scenario: Lease consistency
- **WHEN** a row has a lease owner without an expiry, or an expiry without an owner
- **THEN** the database rejects it

#### Scenario: Claimable work is indexed
- **WHEN** the catalog is read
- **THEN** a partial index covers the jobs that still hold bytes and are waiting for a worker

### Requirement: A failure code exists only on failed documents
`documents` SHALL gain a nullable `error_code`, and the database MUST reject a non-null `error_code` on a document whose status is not `failed`. Existing rows and constraints are unchanged.

#### Scenario: Code on a ready document
- **WHEN** a `ready`, `pending` or `processing` document is written with an `error_code`
- **THEN** the database rejects it

#### Scenario: Existing data
- **WHEN** the migration is applied to a database with documents
- **THEN** every existing row keeps its values and has no `error_code`

### Requirement: The new schema is a reversible migration after 0004
The job table and the column SHALL be created by a new Alembic migration that has a working `downgrade`, runs on a clean database, leaves `alembic check` clean, and does not edit migration `0004`.

#### Scenario: Round trip
- **WHEN** the migration is upgraded, downgraded to `0004` and upgraded again
- **THEN** each step succeeds and the catalog after the last upgrade equals the first

#### Scenario: Earlier migrations
- **WHEN** the repository history is compared with the previous release
- **THEN** no earlier migration file changed

#### Scenario: Catalog properties
- **WHEN** the catalog is read after the upgrade
- **THEN** the foreign key with cascade, the uniqueness, the check constraints and the partial index are present as specified
