# Spec Delta

## ADDED Requirements

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
