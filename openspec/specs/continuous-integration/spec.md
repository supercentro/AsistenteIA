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
