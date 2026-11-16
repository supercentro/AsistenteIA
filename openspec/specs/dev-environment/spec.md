# dev-environment Specification

## Purpose
Guarantees that any developer or reviewer can start the full stack, configure it safely and migrate a clean pgvector database from the repository alone.

## Requirements

### Requirement: Full stack starts with docker compose
`docker compose up --build` SHALL start a PostgreSQL 15 database with the `pgvector` extension available, run the one-shot `bootstrap` and `migrate` services, and then start the backend on port 8000, the ingestion worker and the frontend dev server on port 5173, following `docs/development_guide.md`.

#### Scenario: The one-shot services run in order before the application
- **WHEN** the stack starts
- **THEN** `bootstrap` and `migrate` belong to the default profile and run in that order after the database reports healthy (`service_healthy`), and the backend and the worker start only after both completed successfully (`service_completed_successfully`)

#### Scenario: The one-shot services are idempotent
- **WHEN** a plain `docker compose up` starts the finished one-shot containers again
- **THEN** both `bootstrap` and `migrate` are idempotent and change nothing that is already as designed
#### Scenario: Clean start
- **WHEN** a developer copies the `.env.example` files and runs `docker compose up --build` on a machine without prior state
- **THEN** the roles exist, the migrations and grants are applied, `GET http://localhost:8000/api/v1/health` returns 200, the worker is healthy as the worker role, `http://localhost:5173` serves the frontend page, and a separate `asistenteia_test` database exists next to `asistenteia`

#### Scenario: Backend waits for the database
- **WHEN** the stack starts and the database is not yet accepting connections
- **THEN** the backend starts only after the database reports healthy

#### Scenario: A failed migration stops the dependants
- **WHEN** the `migrate` service exits with a non-zero code
- **THEN** `docker compose up` reports the failure and neither the backend nor the worker starts

#### Scenario: Second start on an existing volume
- **WHEN** `docker compose up -d` runs again on a stack that is already up
- **THEN** the finished one-shot services run again without error and without changing the catalog, the passwords equal the environment values, and the running backend and worker containers are not recreated

#### Scenario: One-shot services are not in an inactive profile
- **WHEN** the Compose file is validated without `--profile` options
- **THEN** it is valid, because no service that another service depends on belongs to a profile that is not active

#### Scenario: Credentials changed
- **WHEN** a role password changes in the environment files
- **THEN** `docker compose up -d` recreates the service whose environment changed, the bootstrap applies the new password, and `docker compose restart` alone is documented as not applying it

### Requirement: Configuration comes only from environment variables
The backend SHALL read all configuration through typed settings modules and MUST fail at startup with a clear message when a required variable is missing; the repository MUST NOT contain real secrets. `DATABASE_URL` is required; `APP_ENV` defaults to `development`, `LOG_LEVEL` to `INFO`, and `CORS_ORIGINS` to the local frontend origin only in development.

#### Scenario: Each Compose service receives only the secrets it needs
- **WHEN** the environment of each Compose service is inspected
- **THEN** the API holds the application-role URL and the JWT secret, the worker holds the worker-role URL and no API secret, the migration service holds the migrator URL and no JWT secret, the bootstrap holds the administrator password and the role passwords, and no application container holds the administrator password, the migrator credentials or `TEST_DATABASE_URL`
#### Scenario: Missing required variable
- **WHEN** the backend starts without `DATABASE_URL`
- **THEN** startup fails naming the missing variable and does not serve requests

#### Scenario: Development defaults
- **WHEN** the backend starts in `development` with only `DATABASE_URL` set
- **THEN** it starts with `LOG_LEVEL=INFO` and CORS limited to `http://localhost:5173`

#### Scenario: Placeholders only
- **WHEN** `backend/.env.example`, the other `.env.*.example` files and `frontend/.env.example` are inspected
- **THEN** every variable consumed by the code is documented with a placeholder value and the real `.env` files are git-ignored

#### Scenario: Secrets are scoped per service
- **WHEN** the effective environment of each running container is inspected by variable name
- **THEN** the API has no administrator, migrator or test-database variable, the worker has no JWT or CORS variable, the migration service has no JWT secret, and only the database and the bootstrap hold the administrator password

#### Scenario: Migrations do not need the API settings
- **WHEN** Alembic runs with only the migrator URL in its environment
- **THEN** it starts and migrates, without `JWT_SECRET` or `CORS_ORIGINS`

### Requirement: Production never runs with open or implicit CORS
When `APP_ENV` is `production`, the backend SHALL require `CORS_ORIGINS` to be set explicitly and MUST refuse to start if it is empty; a wildcard (`*`) SHALL be rejected in every environment.

#### Scenario: Production without explicit origins
- **WHEN** the backend starts with `APP_ENV=production` and no `CORS_ORIGINS`
- **THEN** startup fails naming `CORS_ORIGINS`

#### Scenario: Wildcard origin
- **WHEN** `CORS_ORIGINS` contains `*` in any environment
- **THEN** startup fails with a clear message

### Requirement: Database connections time out quickly
Every database connection attempt SHALL fail after `DB_CONNECT_TIMEOUT_SECONDS` seconds (default 5, allowed range 1-60), so an unreachable or unresponsive database never blocks a request indefinitely.

#### Scenario: Default timeout
- **WHEN** the backend starts without `DB_CONNECT_TIMEOUT_SECONDS`
- **THEN** connection attempts use a 5 second timeout

#### Scenario: Invalid timeout
- **WHEN** `DB_CONNECT_TIMEOUT_SECONDS` is outside 1-60 or not a number
- **THEN** startup fails naming the variable

#### Scenario: Unresponsive database
- **WHEN** the database accepts the TCP connection but never answers and a request needs it
- **THEN** the request fails with the documented 503 within the configured timeout instead of hanging

### Requirement: Test database variable is needed only by integration tests
`TEST_DATABASE_URL` and the administrator URL used by the role-bound tests SHALL be required only when integration tests run, MUST live in a host-only environment file that no container receives, and MUST NOT be required, read or validated when the backend starts normally.

#### Scenario: Normal startup without test variable
- **WHEN** the backend starts with `DATABASE_URL` set and `TEST_DATABASE_URL` unset
- **THEN** it starts normally

#### Scenario: Integration tests without test variable
- **WHEN** integration tests run and `TEST_DATABASE_URL` is unset
- **THEN** they fail immediately with a message naming `TEST_DATABASE_URL`, without touching any database

#### Scenario: Test variables never reach a container
- **WHEN** the Compose configuration is rendered
- **THEN** no service receives `TEST_DATABASE_URL`, the administrator URL of the tests or a variable of the host-only test file

### Requirement: Test database is isolated from development and production
Tests that run migrations or perform destructive cleanup (downgrade, drop, truncate, role creation) SHALL do so only against a database that passes a guard: its name ends in `_test`, its name differs from the database name in `DATABASE_URL` whatever the host, and `APP_ENV` is not `production`. The guard MUST run before any connection that mutates data and MUST NOT disclose credentials.

#### Scenario: The guard still receives the application URL
- **WHEN** the test variables live in a separate file
- **THEN** the guard still receives the application `DATABASE_URL` from the application environment

#### Scenario: Role-creating tests use a reserved prefix
- **WHEN** a test creates roles
- **THEN** it uses names with a reserved test prefix that cannot match the real role names, and it removes the leftovers of that prefix before each run
#### Scenario: Valid test database
- **WHEN** `TEST_DATABASE_URL` points to `asistenteia_test` and `DATABASE_URL` to `asistenteia`
- **THEN** the guard passes and destructive test operations may run

#### Scenario: Test URL equals application URL
- **WHEN** `TEST_DATABASE_URL` points to the same server and database as `DATABASE_URL`
- **THEN** the guard rejects it and no migration or cleanup is executed

#### Scenario: Same database name on another host alias
- **WHEN** `TEST_DATABASE_URL` and `DATABASE_URL` use different hosts (for example `db` and `127.0.0.1`) but the same database name
- **THEN** the guard rejects it, because both can be the same server

#### Scenario: Rejection aborts the run without disclosing credentials
- **WHEN** the guard rejects `TEST_DATABASE_URL` at the start of an integration run
- **THEN** the run aborts before any test executes, and the message names the reason but contains neither the password nor the full URL

#### Scenario: Rejection happens before any connection
- **WHEN** the guard rejects a configuration (missing variable, production, same name, wrong suffix, unparsable URL)
- **THEN** no engine is created and no connection is opened by the integration support code

#### Scenario: Name not marked as test
- **WHEN** the database name in `TEST_DATABASE_URL` does not end in `_test`
- **THEN** the guard rejects it and no migration or cleanup is executed

#### Scenario: Production environment
- **WHEN** `APP_ENV` is `production`
- **THEN** the guard rejects any test database operation

#### Scenario: Guard keeps its reference when test variables are separate
- **WHEN** the test variables are read from the host-only file and the application `DATABASE_URL` is set in the application environment
- **THEN** the comparison between both database names is still performed, and a missing application URL does not silently disable it

#### Scenario: Test roles cannot touch the real roles
- **WHEN** the role-bound tests create and drop roles
- **THEN** every role name starts with the reserved test prefix, no real role name matches it, and leftovers of the prefix are removed before the run

### Requirement: Migrations run on a clean database and are reversible
The first Alembic migration SHALL enable the `vector` extension, and `upgrade head` followed by `downgrade base` SHALL succeed on an empty test database when run by the administrator. The migrator role SHALL run `upgrade head`, `check`, `downgrade` to any revision after `0001` and `upgrade` again, on a database prepared by the bootstrap, which creates the extension beforehand; `downgrade base` removes the extension and is an administrator operation.

#### Scenario: Upgrade and downgrade
- **WHEN** migrations are applied to an empty test database that passed the isolation guard by the administrator and then reverted to base
- **THEN** both operations succeed and the `vector` extension is present after upgrade and absent after downgrade

#### Scenario: Migrator round trip
- **WHEN** the migrator upgrades to head, checks, downgrades to `0004` and upgrades again on a prepared database
- **THEN** every step succeeds, `alembic check` reports no operations, and the privileges of the matrix are present at the end

#### Scenario: Base downgrade needs the administrator
- **WHEN** the migrator runs `downgrade base`
- **THEN** the downgrade is refused at the extension removal, the whole transaction is rolled back and the revision stays at head

### Requirement: Layered project structure
The backend SHALL be organised as `api → services → repositories → models` plus `schemas`, `core` and `rag` packages, and the frontend as `pages`, `components`, `hooks`, `services`, `types`, `lib` and `tests`, matching `docs/backend-standards.md` §2 and `docs/frontend-standards.md` §2.

#### Scenario: Structure present
- **WHEN** the repository is inspected after this change
- **THEN** the directories above exist and the backend passes `mypy --strict` and `ruff`

### Requirement: Standard quality commands are available
The backend and frontend SHALL expose the commands listed in `docs/development_guide.md` §4 (lint, format check, type check, unit and integration tests, build, and the frontend scripts `dev`, `build`, `test`, `test:e2e`, `lint`, `format:check`, `typecheck`), with lock files committed.

#### Scenario: Commands pass on the scaffold
- **WHEN** each quality command is run on a fresh checkout after dependency installation
- **THEN** all of them exit successfully
