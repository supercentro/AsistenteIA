## ADDED Requirements

### Requirement: Database privilege tests are a mandatory gate
CI SHALL run, on every push and pull request, the bootstrap, the migrations with grants, `db-verify`, the positive and negative privilege tests and the role-bound integration suite against the database service container, and a failing or missing prerequisite (for example the administrator URL) MUST fail the job, never skip the tests. The role-bound suite SHALL use a dedicated `*_test` database and reserved role names, and SHALL NOT call external services.

#### Scenario: Gate runs and passes
- **WHEN** a pull request changes backend code
- **THEN** the privilege job runs after the bootstrap and the migrations and reports the number of privilege tests executed

#### Scenario: Missing prerequisite fails the job
- **WHEN** the administrator URL needed to create the test roles is absent
- **THEN** the job fails with a message naming the missing variable instead of skipping

#### Scenario: A new table without decision fails CI
- **WHEN** a pull request adds a table without a matrix decision
- **THEN** the privilege job fails and names the table
