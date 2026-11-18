## MODIFIED Requirements

### Requirement: The role comes from the backend
The signed-in user and role SHALL be taken from `GET /users/me` and never from the contents of the token, which the interface does not decode. The consent fields of the profile SHALL be kept with the profile and SHALL be used only to decide whether a student is held at the consent screen (change `privacy-consent-ui`).

#### Scenario: Role from the profile
- **WHEN** the profile answers `role: student` or `role: teacher`
- **THEN** the navigation and the guarded routes follow that value

#### Scenario: Token claims are ignored
- **WHEN** a token contains a different role claim than the profile
- **THEN** the interface behaves according to the profile

#### Scenario: Consent fields drive only the consent gate
- **WHEN** the profile carries `consent_version` and `consent_accepted_at`
- **THEN** the interface compares the version with the current one to hold or release a student, and shows no other consent data outside the consent screen
