# Spec Delta

## MODIFIED Requirements

### Requirement: Health endpoint has a stable two-response contract
`GET /api/v1/health` SHALL return only 200 (`{"status": "ok"}`) or 503 (common `Error` body with code `SERVICE_UNAVAILABLE`), and its contract MUST NOT change when other endpoints are added to the API.

#### Scenario: Only documented statuses
- **WHEN** the endpoint is called under any condition (database up or down)
- **THEN** the status is either 200 or 503, matching `docs/api-spec.yml`

#### Scenario: No additional endpoints
- **WHEN** the OpenAPI document is inspected after other endpoints (such as authentication) were added to the API
- **THEN** `/api/v1/health` still declares exactly the 200 and 503 responses and requires no authentication
