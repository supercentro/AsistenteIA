# api-error-handling Specification

## Purpose
Defines how the HTTP API reports errors and which cross-origin and header protections apply to every response, so later endpoints inherit a consistent and safe behaviour.

## Requirements

### Requirement: Errors use the common Error body
Every error response produced by the API SHALL use the `Error` schema of `docs/api-spec.yml` (`code`, `message`, optional `details`) with the status code that corresponds to the failure.

#### Scenario: Unknown route
- **WHEN** a client requests a path that does not exist
- **THEN** the response is 404 with an `Error` body

#### Scenario: Invalid request payload
- **WHEN** a request fails Pydantic validation
- **THEN** the response is 422 with an `Error` body whose `details` lists the offending fields, without echoing the submitted values

#### Scenario: Domain errors are mapped
- **WHEN** application code raises a not-found, forbidden, conflict or unauthorized domain error
- **THEN** the response is respectively 404, 403, 409 or 401 with an `Error` body carrying a stable `code`

### Requirement: Internal failures do not leak internals
Unexpected exceptions SHALL produce a 500 `Error` body with a generic message; stack traces, SQL statements, file paths and secrets MUST NOT appear in responses or logs.

#### Scenario: Unhandled exception
- **WHEN** a handler raises an unexpected exception
- **THEN** the response is 500 with a generic `Error` body and the log entry contains no request body or message content

### Requirement: Each request runs in a single database transaction
The system SHALL commit the request's database work only if the request completes successfully and SHALL roll it back if an error is raised.

#### Scenario: Failure rolls back
- **WHEN** a request fails after writing to the database
- **THEN** none of its writes are persisted

### Requirement: CORS allows only configured origins
The API SHALL answer cross-origin requests only for the origins listed in the `CORS_ORIGINS` setting and MUST NOT use a wildcard origin when credentials are allowed.

#### Scenario: Allowed origin
- **WHEN** a request carries an `Origin` that is listed in `CORS_ORIGINS`
- **THEN** the response includes the matching `Access-Control-Allow-Origin` header

#### Scenario: Disallowed origin
- **WHEN** a request carries an `Origin` that is not listed
- **THEN** the response does not include `Access-Control-Allow-Origin`

### Requirement: Responses carry secure headers
Every API response SHALL include `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` and `Referrer-Policy: no-referrer`.

#### Scenario: Header presence
- **WHEN** any endpoint, including error responses, is called
- **THEN** the three headers are present
