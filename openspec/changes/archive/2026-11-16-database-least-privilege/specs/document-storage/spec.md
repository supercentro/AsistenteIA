## ADDED Requirements

### Requirement: A table is closed until its privilege decision exists
Every table of the model SHALL have an explicit decision in the privilege matrix of `database-roles` (which role may do what, or nothing) before it can be used by the application. A table created by a migration is owned by the migrator and unreachable for the application and worker roles until the matrix grants it; a change that adds a table or a column used by a statement of the code MUST update the matrix in the same change.

#### Scenario: New table is closed by default
- **WHEN** a migration creates a table and the matrix is not updated
- **THEN** the application and worker roles are refused with insufficient privilege, and the matrix completeness test fails

#### Scenario: New column used by the worker
- **WHEN** a worker statement starts reading or writing a column
- **THEN** the privilege inventory test reports the missing column grant before the change can pass the quality gates

#### Scenario: Recreated table regains its privileges
- **WHEN** migration `0005` is downgraded and applied again
- **THEN** `ingestion_jobs` has exactly the privileges of the matrix without a manual step
