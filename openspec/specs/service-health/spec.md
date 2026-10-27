# service-health Specification

## Purpose
Lets operators, the platform and CI verify that the API process is alive and can reach its database, without needing credentials.

## Requirements

### Requirement: Health endpoint reports liveness and database connectivity
The system SHALL expose `GET /api/v1/health`, which requires no authentication and returns HTTP 200 with `{"status": "ok"}` when the API can execute a trivial query against the database.

#### Scenario: Healthy service
- **WHEN** a client calls `GET /api/v1/health` without a token and the database is reachable
- **THEN** the response is 200 with body `{"status": "ok"}`

#### Scenario: Database unreachable
- **WHEN** a client calls `GET /api/v1/health` and the database cannot be reached
- **THEN** the response is 503 using the common `Error` body with code `SERVICE_UNAVAILABLE` and contains no connection string, host or stack trace

### Requirement: Health endpoint has a stable two-response contract
`GET /api/v1/health` SHALL return only 200 (`{"status": "ok"}`) or 503 (common `Error` body with code `SERVICE_UNAVAILABLE`), and this change SHALL NOT add any other endpoint.

#### Scenario: Only documented statuses
- **WHEN** the endpoint is called under any condition (database up or down)
- **THEN** the status is either 200 or 503, matching `docs/api-spec.yml`

#### Scenario: No additional endpoints
- **WHEN** the OpenAPI document of the API is inspected after this change
- **THEN** `/api/v1/health` is the only API path besides the interactive documentation

### Requirement: Health endpoint exposes no sensitive information
The health response SHALL NOT include configuration values, versions of dependencies, credentials or user data.

#### Scenario: Response content
- **WHEN** a client calls `GET /api/v1/health`
- **THEN** the body contains only the `status` field
