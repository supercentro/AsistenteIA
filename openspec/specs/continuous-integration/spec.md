# continuous-integration Specification

## Purpose
Ensures that every push and Pull Request is checked automatically against the project's MUST quality gates without calling any external paid or networked AI service.

## Requirements

### Requirement: CI runs quality gates on push and pull request
A GitHub Actions workflow SHALL run on pushes and Pull Requests and execute backend lint, format check, `mypy --strict`, unit tests and integration tests against a PostgreSQL 15 + pgvector service, plus frontend lint, format check, type check, unit tests and build.

#### Scenario: All gates green
- **WHEN** a change that satisfies every gate is pushed
- **THEN** every CI job completes successfully

#### Scenario: A gate fails
- **WHEN** any lint, type, test or build step fails
- **THEN** the workflow is marked failed and the failing step is identifiable

### Requirement: CI never calls external AI services
CI SHALL run without `GEMINI_API_KEY` or any other provider secret, and tests MUST NOT perform outbound network calls to AI providers.

#### Scenario: No provider secrets
- **WHEN** the workflow definition is inspected
- **THEN** it references no AI-provider secret and uses fake providers wherever a provider would be needed

### Requirement: Dependency vulnerability scan is reported
CI SHALL run `pip-audit` and `npm audit` and report their findings without failing the pipeline on them in this change (the standards mark the scan as SHOULD).

#### Scenario: Audit step present
- **WHEN** the workflow runs
- **THEN** both audit steps execute and their output is visible in the logs

### Requirement: CI verifies the frontend contract types, coverage and mocked end-to-end flows
The frontend CI job SHALL fail when the committed API types differ from a fresh generation from `docs/api-spec.yml`, when coverage falls below the thresholds of `docs/frontend-standards.md`, or when the mocked end-to-end suite fails. The mocked suite SHALL need neither the backend, nor a database, nor any external service.

#### Scenario: Types are stale
- **WHEN** `docs/api-spec.yml` changes without regenerating the committed types
- **THEN** the frontend job fails at the type consistency step

#### Scenario: Coverage below threshold
- **WHEN** coverage of components or hooks drops below 70 %
- **THEN** the frontend job fails at the coverage step

#### Scenario: Mocked browser flows
- **WHEN** the workflow runs on a push or Pull Request
- **THEN** the browser suite runs against mocked API responses and passes without starting the backend or the database

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
