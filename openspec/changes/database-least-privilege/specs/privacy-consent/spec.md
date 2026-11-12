## MODIFIED Requirements

### Requirement: Consent to the current policy version is recorded
`POST /api/v1/users/me/consent` SHALL accept only the privacy-policy version currently configured in the system, store it with the server-side acceptance time for the authenticated user, and return 200 with the updated profile. The write SHALL be committed before the response is sent, so a database refusal (for example a missing privilege) yields an error response and never a success without stored evidence.

#### Scenario: Accept the current version
- **WHEN** an authenticated user sends the configured current version
- **THEN** the response is 200 and `consent_version` and `consent_accepted_at` are set

#### Scenario: Any role may consent
- **WHEN** a teacher sends the current version
- **THEN** the response is 200

#### Scenario: Evidence is persisted before the answer
- **WHEN** the response is 200
- **THEN** a separate database session reads the same `consent_version` and `consent_accepted_at` for that user

#### Scenario: The database refuses the write
- **WHEN** the database refuses the consent update (insufficient privilege or any database error)
- **THEN** the response is an error response (HTTP 500 with the standard error body, as for any unexpected database failure) and no consent evidence is stored
