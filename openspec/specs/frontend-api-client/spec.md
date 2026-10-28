# frontend-api-client Specification

## Purpose
Defines how the web interface talks to the API: when it sends the token, how failures are classified and explained in Spanish without exposing server text, how retries behave, and how the types it relies on stay consistent with the canonical API contract.

## Requirements

### Requirement: The token is sent only to the API and only where needed
Requests to the configured API base URL SHALL carry `Authorization: Bearer <token>` when a session exists, except requests to the login and registration endpoints, which SHALL never carry it. The token SHALL never be sent to any other origin.

#### Scenario: Protected request
- **WHEN** a signed-in user triggers a request to a protected endpoint
- **THEN** the request carries the bearer token

#### Scenario: Authentication endpoints
- **WHEN** login or registration is requested
- **THEN** the request carries no `Authorization` header, even if a stale session exists

#### Scenario: Other origins
- **WHEN** a request targets a URL whose origin is not the origin of the API base URL
- **THEN** no token is attached

### Requirement: Errors are classified and explained in Spanish by code
Every failed request SHALL be converted into one error object with the HTTP status, the stable error `code` of the API body when present, and the `Retry-After` seconds when present. The message shown to the user SHALL be chosen from the Spanish copy module by `code` (or by status when the code is unknown or absent) and the server `message` and `details` SHALL NOT be displayed.

#### Scenario: Known code
- **WHEN** the API answers with a body whose `code` is one of `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `CONFLICT`, `VALIDATION_ERROR`, `INVALID_CREDENTIALS`, `RATE_LIMITED` or `SERVICE_UNAVAILABLE`
- **THEN** the user sees the matching Spanish message

#### Scenario: Unknown code or non-JSON body
- **WHEN** the body has an unknown `code`, is not JSON, or is empty
- **THEN** the user sees the generic Spanish message for that status class and nothing from the body

#### Scenario: Server text is never shown
- **WHEN** the API body carries a `message` or `details` containing arbitrary text or markup
- **THEN** that text appears nowhere in the interface

#### Scenario: Rate limited
- **WHEN** the API answers 429 with a numeric `Retry-After`
- **THEN** the message states the wait in seconds; a missing, non-numeric, negative or absurdly large value falls back to a message without a number

#### Scenario: Network failure or timeout
- **WHEN** the request fails without a response or exceeds the timeout
- **THEN** the user sees a Spanish connection error and can try again

### Requirement: Retries do not repeat client errors
The data-fetching layer SHALL NOT retry requests that failed with a 4xx status and SHALL retry transient failures (network errors and 5xx) at most once.

#### Scenario: 4xx is not retried
- **WHEN** a query fails with a 4xx status
- **THEN** exactly one request is sent

#### Scenario: Transient failure
- **WHEN** a query fails with a 503 and the retry succeeds
- **THEN** at most two requests are sent and the data is shown

### Requirement: Cached server data is isolated per user
Cached query results SHALL be keyed by the signed-in user and SHALL be removed when the session ends.

#### Scenario: Different users, different caches
- **WHEN** two users sign in one after another in the same tab
- **THEN** the second user's first render issues its own request and never shows the first user's data

### Requirement: API types come from the canonical contract
The TypeScript types used for requests and responses SHALL be generated from `docs/api-spec.yml` and committed, and a check SHALL fail when the committed file differs from a fresh generation. Hand-written types for API payloads SHALL NOT duplicate generated ones.

#### Scenario: Up to date
- **WHEN** the check runs and the contract has not changed
- **THEN** it passes

#### Scenario: Contract changed without regeneration
- **WHEN** `docs/api-spec.yml` changes and the generated file is not regenerated
- **THEN** the check fails and names the generation command

#### Scenario: Mocks follow the contract
- **WHEN** test fixtures and mock handlers build API payloads
- **THEN** they are typed with the generated types so a contract change breaks compilation

### Requirement: Behaviour is verified against the real backend
The authentication flow, the cross-origin access, the `Authorization` header, 401 responses and token expiry SHALL be verified against the running backend and reported, in addition to the mocked tests, because mocks cannot prove what the server accepts. The verification SHALL NOT modify the backend or leave temporary configuration or test data behind.

#### Scenario: Authentication against the real server
- **WHEN** a student registers and signs in through the interface against the running stack
- **THEN** the profile and the subject list load and the observed status codes and bodies match the API contract

#### Scenario: Cross-origin access
- **WHEN** a preflight request is sent from the allowed frontend origin and from a disallowed origin
- **THEN** the allowed origin is accepted with the `Authorization` and `Content-Type` headers and the disallowed origin is not

#### Scenario: Authorization header accepted by the server
- **WHEN** the interface calls a protected endpoint with the session token
- **THEN** the server accepts it, and the same call without the token is answered with 401

#### Scenario: Real 401 mid-session
- **WHEN** the server stops accepting the token during a session (invalid, tampered or signed with a rotated key)
- **THEN** the interface ends the session once and shows the login screen with the notice

#### Scenario: Real token expiry
- **WHEN** the backend issues a token with the minimum lifetime and that lifetime elapses
- **THEN** the interface signs out by itself and a request made with that token afterwards is answered with 401 by the server

### Requirement: Network diagnostics never expose sensitive data
Logging of failed requests MUST be limited to the method, the path without query string and the status, and MUST NOT include headers, bodies, tokens or form values.

#### Scenario: Failed request diagnostic
- **WHEN** a request fails and the interface logs a diagnostic
- **THEN** the log contains at most method, path and status
