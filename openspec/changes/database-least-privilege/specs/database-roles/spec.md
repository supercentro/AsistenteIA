# database-roles Specification

## Purpose
Defines the PostgreSQL identities, object ownership, privilege matrix, bootstrap, adoption, migration with grants, verification, denied administrative operations and data-preserving rollback that give the API, the worker and the migrations only the database privileges they need.

## ADDED Requirements

### Requirement: Four database identities exist
The system SHALL use four distinct PostgreSQL identities: the **administrator** (the bootstrap superuser of the database image, used only for cluster administration), a **migrator**, an **application role** (API and administrative CLI until the teacher-provisioning requirement of `role-based-access` is implemented) and a **worker role**.

#### Scenario: One identity per component
- **WHEN** the effective database URLs of the API, the worker, the migration service and the bootstrap are inspected by role name
- **THEN** the API uses the application role, the worker the worker role, the migration service the migrator, and only the bootstrap uses the administrator

### Requirement: The three working roles have minimal attributes
The migrator, application and worker roles MUST be login roles without superuser, create-database, create-role, replication and bypass-row-security attributes, MUST NOT be members of any role (predefined roles included) and MUST have a connection limit derived from the connection pools of their consumers.

#### Scenario: Attributes of the three roles
- **WHEN** the catalog is read after the bootstrap
- **THEN** the migrator, application and worker roles are login roles and every one of the attributes superuser, create-database, create-role, replication and bypass-row-security is false for each of them

#### Scenario: No memberships
- **WHEN** role memberships are read
- **THEN** none of the three roles is a member of any role, including `pg_read_all_data`, `pg_write_all_data` and `pg_execute_server_program`

#### Scenario: Connection limit equals real consumption
- **WHEN** a role opens connections up to its limit and one more
- **THEN** the extra connection is refused with "too many connections for role", and the limits of the application and worker roles are not lower than the pools of the API and the worker plus their maintenance sessions

### Requirement: Passwords are stored as client-computed SCRAM verifiers
The passwords of the three working roles SHALL be stored as SCRAM verifiers computed by the client, so the clear text never reaches the server.

#### Scenario: Clear text never reaches the server
- **WHEN** the bootstrap creates or updates the roles
- **THEN** the statements carry SCRAM verifiers, the stored password of each role starts with the SCRAM prefix, and no output of the command contains a password or a verifier

### Requirement: Only the migrator owns application objects
The migrator SHALL own every application table, index and enum type, including those created by later migrations; the application and worker roles MUST own nothing; the database and the `vector` extension remain owned by the administrator. The migrator SHALL hold `CONNECT` on the application database and `USAGE` and `CREATE` on schema `public`, and nothing else beyond what ownership implies.

#### Scenario: Ownership after migration on a clean database
- **WHEN** the bootstrap and the migrations run on an empty database
- **THEN** every table, index and enum type of schema `public` is owned by the migrator

#### Scenario: Object created by another role is reported
- **WHEN** an application table is owned by a role other than the migrator
- **THEN** `db-verify` reports the table and exits non-zero

### Requirement: Privileges are exactly the declared matrix
The privileges of the application and worker roles on application tables SHALL be exactly those of one declarative matrix, at table or column level, derived from the statements the code issues (including those implied by `RETURNING`, `SELECT ... FOR UPDATE` and foreign-key actions); every other privilege MUST be denied. The matrix MUST contain a decision for every table of the model, and a table without one MUST fail the test suite.

#### Scenario: Worker minimum
- **WHEN** the worker runs the real ingestion service on a one-chunk document and on a multi-chunk document
- **THEN** both reach `ready`, because the worker holds `INSERT` and `SELECT (id)` on `document_chunks` (the single-row insert returns the generated key) and the other worker privileges of the matrix

#### Scenario: Cascades need no privilege on the children
- **WHEN** the application role deletes a document and holds no `DELETE` on `document_chunks` or `ingestion_jobs`, or deletes a subject
- **THEN** the dependent chunks and jobs (and, for a subject, the documents and enrollments) are removed by the database, because referential actions run with the privileges of the table owner; the application role holds `DELETE` on `enrollments` only for the unenroll endpoint

#### Scenario: Roles cannot write what they do not own
- **WHEN** the application role updates `documents`, `ingestion_jobs` or `document_chunks`, or the worker updates `documents.filename` or `documents.subject_id`
- **THEN** PostgreSQL refuses with insufficient privilege

#### Scenario: Worker cannot reach accounts or subjects
- **WHEN** the worker reads or writes `users`, `subjects` or `enrollments`, or reads a `documents` column outside its list
- **THEN** PostgreSQL refuses with insufficient privilege

#### Scenario: Worker cannot read chunk text or embeddings
- **WHEN** the worker reads `document_chunks.content`, `document_chunks.embedding` or any column other than `id`
- **THEN** PostgreSQL refuses with insufficient privilege

#### Scenario: Migration bookkeeping is closed
- **WHEN** the application role or the worker reads or writes `alembic_version`
- **THEN** PostgreSQL refuses with insufficient privilege

#### Scenario: New table without decision
- **WHEN** a migration adds a table that the matrix does not mention
- **THEN** the matrix test fails, and until a decision is made the table is owner-only

#### Scenario: Application role cannot promote or forge accounts
- **WHEN** the application role updates `users.role`, `users.password_hash` or `subjects.teacher_id`
- **THEN** PostgreSQL refuses with insufficient privilege

### Requirement: Administrative operations are denied to the roles
The migrator, application and worker roles MUST be unable to run superuser-only or cluster-level operations, and the application and worker roles MUST also be unable to run DDL, `TRUNCATE` or create temporary tables.

#### Scenario: Denied operation list
- **WHEN** the application role and the worker role each attempt: creating roles, databases, extensions, schemas or functions; `COPY` to or from a program or a server file; reading server files or directories; importing a server file as a large object; `ALTER SYSTEM`; `SET ROLE` to another role; reading `pg_authid`; terminating other sessions
- **THEN** every attempt is refused (SQLSTATE 42501)

#### Scenario: The migrator is not a superuser either
- **WHEN** the migrator attempts `COPY ... TO PROGRAM`, `pg_read_file`, `ALTER SYSTEM`, `CREATE ROLE`, `CREATE EXTENSION` or reads `pg_authid`
- **THEN** every attempt is refused

#### Scenario: Other databases of the cluster
- **WHEN** a role connects to `postgres`, `template1` or another database
- **THEN** the connection is refused, because the bootstrap revoked `CONNECT` and `TEMPORARY` from `PUBLIC` on them

### Requirement: Grants travel with the schema and are applied atomically
The migrations and the grants of the matrix SHALL be applied by one command. The grants step SHALL revoke at table level and grant again inside one transaction, so a concurrent session never observes a missing privilege, and a table recreated by a downgrade and an upgrade MUST regain its privileges without a manual step. Running Alembic directly MUST NOT leave the roles silently without privileges.

#### Scenario: Concurrent reader during the grants step
- **WHEN** a session of the application role reads continuously while the grants step runs repeatedly
- **THEN** it observes no permission error

#### Scenario: Downgrade and upgrade round trip
- **WHEN** the migrator downgrades to revision `0004` and upgrades to head through the command
- **THEN** `db-verify` reports no difference and the worker can claim jobs again

#### Scenario: Direct Alembic run
- **WHEN** Alembic is run directly against a database managed by this change
- **THEN** it is refused or the grants are applied in the same run, never leaving a recreated table without privileges

### Requirement: The bootstrap is idempotent and runs hardened
The bootstrap SHALL run as the administrator with `search_path = pg_catalog` and schema-qualified names, SHALL do role and database work from the `postgres` database, SHALL only grant, revoke, create the extension and set default privileges inside the application database, and MUST be safe to run on every `docker compose up`.

#### Scenario: Second run changes nothing
- **WHEN** the bootstrap runs twice in a row
- **THEN** the second run succeeds, the catalog is identical and the passwords equal the environment values

#### Scenario: Planted objects do not run for the administrator
- **WHEN** the migrator has planted `public.lower(varchar)` and an operator `=(varchar, varchar)` in schema `public` and the bootstrap or `db-verify` runs
- **THEN** neither runs, because the administrator session uses `search_path = pg_catalog`

#### Scenario: Nothing secret is printed
- **WHEN** the bootstrap runs with any outcome
- **THEN** the output contains neither a password nor a verifier nor a connection string

### Requirement: The bootstrap closes access by default
The bootstrap SHALL create or update the roles, reset their role-level settings before applying its own, revoke from `PUBLIC` the access to the application database, to schema `public` and to every other database of the cluster, grant `CONNECT`, `USAGE` and (for the migrator) `CREATE`, create the `vector` extension, and revoke `EXECUTE` on future functions from `PUBLIC` for objects created by the migrator.

#### Scenario: Role self-tampering is undone
- **WHEN** a role has changed its own password or its own role-level settings (`ALTER ROLE ... SET search_path`, `statement_timeout`)
- **THEN** the next bootstrap run restores the password from the environment and the intended settings, and a login probe detects the change meanwhile

#### Scenario: Future functions are closed by default
- **WHEN** the migrator creates a function after the bootstrap
- **THEN** `PUBLIC` cannot execute it, while tables are owner-only and types remain usable

#### Scenario: Schema and databases closed to PUBLIC
- **WHEN** the access of `PUBLIC` is read after the bootstrap
- **THEN** it has no `CONNECT`, `TEMPORARY`, `USAGE` or `CREATE` on the application database or schema `public`, and no `CONNECT` or `TEMPORARY` on the other databases

### Requirement: Adoption of an existing database is explicit and controlled
Moving an existing database whose objects belong to the administrator to the migrator SHALL be done by a separate, explicit, one-time command that uses `ALTER TABLE ... OWNER TO` and `ALTER TYPE ... OWNER TO` (never `REASSIGN OWNED` of the administrator), runs with the API and the worker stopped and a `lock_timeout`, and leaves the catalog and the row counts unchanged. The idempotent bootstrap MUST only verify ownership and report drift, never adopt silently.

#### Scenario: Adoption preserves data
- **WHEN** the adoption runs on a database at the latest revision that holds rows
- **THEN** all 7 tables, their indexes and the enums belong to the migrator, the catalog fingerprint and the row counts are identical, and `alembic check` reports no operations

#### Scenario: Running services block adoption
- **WHEN** the adoption is requested while the API or the worker holds connections to the database
- **THEN** it stops without changing anything and says which sessions block it

#### Scenario: Drift is reported, not repaired
- **WHEN** the bootstrap finds a table owned by the administrator
- **THEN** it reports the table and exits non-zero, and does not change the owner

### Requirement: The verifier is read-only and compares the catalog with the matrix
The verifier command (`db-verify`) SHALL change nothing, SHALL compare the catalog with the matrix and the rules of this capability, SHALL run a login probe per role with the expected password, and its output MUST NOT contain secrets.

#### Scenario: Clean database
- **WHEN** `db-verify` runs after the bootstrap, the migrations and the grants
- **THEN** it exits 0 and reports each check as passed

#### Scenario: Each kind of drift is detected
- **WHEN** a test introduces a missing or an extra table or column privilege, a grant to `PUBLIC` or to an unknown role, a grant with grant option, a table or type owned by the administrator, a changed role attribute or membership or role-level setting, a changed password, a function, operator, trigger or type in `public` outside an extension, a row-level security object, a database that `PUBLIC` can connect to, or `log_statement` other than `none`
- **THEN** `db-verify` exits non-zero and names the difference

#### Scenario: Run with the least privileges it needs
- **WHEN** `db-verify` runs as the migrator
- **THEN** it reads every catalog it needs and the login probe uses only the passwords of the three roles

### Requirement: Rollback never destroys application objects
The documented rollback SHALL return ownership before removing anything: in every database of the cluster `REASSIGN OWNED BY` the migrator to the administrator, verify the owners, then `DROP OWNED` for the three roles (which then only revokes), re-grant what must remain (for example `CONNECT`), and `DROP ROLE` only when every database is clean. `DROP OWNED` of a table owner before reassigning MUST NOT appear in any procedure.

#### Scenario: Rollback on a database with data
- **WHEN** the rollback runs on an adopted database that holds rows
- **THEN** the tables, the catalog fingerprint and the row counts are identical to the state before the adoption and the services work again with the administrator URL

#### Scenario: Role removal waits for every database
- **WHEN** `DROP ROLE` is attempted while another database still holds objects or privileges of the role
- **THEN** it is refused and the procedure continues with that database first

### Requirement: Persisted state is asserted, not only status codes
Tests that run application operations under the least-privilege roles SHALL assert the persisted database state of every write, because a write that fails at commit after the response was sent would otherwise look successful. Every endpoint, the CLI and the worker flow SHALL be covered.

#### Scenario: Missing privilege behind a successful status
- **WHEN** the application role lacks the privilege a write needs and the endpoint still answers 200
- **THEN** the persisted-state assertion fails the test

#### Scenario: Coverage of operations
- **WHEN** the role-bound suite runs
- **THEN** it executes every route of the API, every subcommand of the CLI and the claim, renew, complete, fail and sweep paths of the worker, with at least one single-chunk and one multi-chunk document
