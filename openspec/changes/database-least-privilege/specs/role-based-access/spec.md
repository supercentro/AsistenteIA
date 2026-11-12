## ADDED Requirements

### Requirement: The runtime database role cannot create teacher accounts
Public registration SHALL create students only, and the database identity used by the running API MUST be unable to insert a user whose role is teacher or to change any user's role, whatever the application code does. Teacher accounts SHALL be provisioned only through the administrative command, which uses a database identity that the API process does not hold.

#### Scenario: Forged teacher through the runtime role
- **WHEN** a session of the runtime API role inserts a `users` row with role teacher, or updates `users.role`
- **THEN** PostgreSQL refuses with insufficient privilege

#### Scenario: Public registration still creates students
- **WHEN** an anonymous client registers, including a payload that contains `"role": "teacher"`
- **THEN** a student account is created and its stored role is student

#### Scenario: Administrative provisioning
- **WHEN** the administrative command creates a teacher with the identity reserved for it
- **THEN** the account exists with the teacher role, the output contains neither password nor hash, and the API process holds no credential of that identity

#### Scenario: Seed accounts follow the same path
- **WHEN** the development seed command creates its teacher and student
- **THEN** it uses the administrative identity for the teacher and creates no account the runtime role could not create
