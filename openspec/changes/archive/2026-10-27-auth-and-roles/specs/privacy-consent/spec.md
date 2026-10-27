# Spec Delta

## Purpose

Records, per user, acceptance of the current privacy policy as verifiable evidence (version and timestamp), which later changes require before personal conversation data is processed.

## ADDED Requirements

### Requirement: Consent to the current policy version is recorded
`POST /api/v1/users/me/consent` SHALL accept only the privacy-policy version currently configured in the system, store it with the server-side acceptance time for the authenticated user, and return 200 with the updated profile.

#### Scenario: Accept the current version
- **WHEN** an authenticated user sends the configured current version
- **THEN** the response is 200 and `consent_version` and `consent_accepted_at` are set

#### Scenario: Any role may consent
- **WHEN** a teacher sends the current version
- **THEN** the response is 200

### Requirement: Other versions are rejected
A version different from the configured one SHALL be answered with 422, code `INVALID_CONSENT_VERSION` and `details.current_version`; an empty or over-long value SHALL be answered with 422 `VALIDATION_ERROR`. Stored consent MUST NOT change in either case.

#### Scenario: Outdated or arbitrary version
- **WHEN** an authenticated user sends a version that is not the configured current one
- **THEN** the response is 422 with `details.current_version` and the stored consent is unchanged

#### Scenario: Invalid value
- **WHEN** the version is empty or longer than 20 characters
- **THEN** the response is 422 `VALIDATION_ERROR` and nothing is stored

### Requirement: Re-acceptance updates the evidence
Accepting again SHALL overwrite the stored version and timestamp with the new acceptance.

#### Scenario: Second acceptance
- **WHEN** a user who already consented accepts the current version again
- **THEN** `consent_accepted_at` is later than before and `consent_version` is the current version

#### Scenario: Version changed in the configuration
- **WHEN** the configured version changes and the user accepts the new one
- **THEN** the stored version becomes the new one

### Requirement: Consent requires authentication and is per user
Recording consent SHALL require a valid token and SHALL affect only the caller's account.

#### Scenario: Unauthenticated
- **WHEN** no valid token is sent
- **THEN** the response is 401 and nothing is stored

#### Scenario: Isolation between users
- **WHEN** one user records consent
- **THEN** other users' consent fields are unchanged

### Requirement: Backend and UI policy versions are kept consistent
The repository SHALL contain a UI-side constant for the current policy version, and an automated check SHALL fail when it differs from the backend's default configured version or is not a valid version string (1 to 20 characters).

#### Scenario: Versions match
- **WHEN** the consistency check runs on the repository
- **THEN** the UI constant equals the backend default policy version

#### Scenario: Drift is detected
- **WHEN** either value is changed without the other
- **THEN** the check fails with a message naming both values

#### Scenario: Runtime drift is recoverable
- **WHEN** a client sends a version that is not the configured one
- **THEN** the 422 response carries the current version so the client can detect the mismatch

### Requirement: Current consent is the usage condition for later features
A user SHALL be considered to have valid consent only when the stored version equals the configured current version; enforcing this in chat belongs to the chat change and is not enforced by any endpoint of this change.

#### Scenario: Consent state evaluation
- **WHEN** a user has no consent, an outdated version, or the current version recorded
- **THEN** the consent state is respectively not valid, not valid and valid

### Requirement: The policy version setting is valid at startup
The configured current policy version SHALL be a non-empty string of at most 20 characters, otherwise startup fails naming `PRIVACY_POLICY_VERSION`.

#### Scenario: Invalid configured version
- **WHEN** `PRIVACY_POLICY_VERSION` is empty or longer than 20 characters
- **THEN** startup fails naming the variable
