# role-based-access Specification

## Purpose
Defines the teacher and student roles, how endpoints restrict access by role, and how teacher accounts are created, so that a role can never be self-assigned.

## Requirements

### Requirement: Role guards restrict endpoints by role
Endpoints restricted to teachers SHALL answer 403 `FORBIDDEN` to authenticated students, endpoints restricted to students SHALL answer 403 to authenticated teachers, and both SHALL answer 401 when unauthenticated.

#### Scenario: Teacher-only endpoint
- **WHEN** a teacher, a student and an anonymous client call a teacher-only endpoint
- **THEN** the responses are respectively success, 403 and 401

#### Scenario: Student-only endpoint
- **WHEN** a student, a teacher and an anonymous client call a student-only endpoint
- **THEN** the responses are respectively success, 403 and 401

### Requirement: Role is read from the database on every request
Authorization SHALL use the role stored in PostgreSQL at request time and MUST NOT trust any role in the token.

#### Scenario: Role changed after login
- **WHEN** a user's role is changed in the database after a token was issued
- **THEN** the same token is authorized according to the new role on the next request

#### Scenario: Role claim in a forged token
- **WHEN** a token carries an extra `role` claim that differs from the stored role
- **THEN** the stored role is the one applied

### Requirement: Teacher accounts cannot be created through the API
No HTTP endpoint SHALL create or promote a teacher account.

#### Scenario: No API path
- **WHEN** the OpenAPI document and registration payloads are examined
- **THEN** no endpoint creates teachers or changes roles, and registration with `"role": "teacher"` yields a student

### Requirement: Teachers are created by an administrative command
`python -m app.cli create-teacher` SHALL create a teacher account with an Argon2id password hash, read the password from a hidden interactive prompt or from standard input, never accept it as a command-line argument, and never print it or its hash.

#### Scenario: Successful creation
- **WHEN** the command runs with a new email and a password of at least 10 characters
- **THEN** a teacher account exists, the exit code is 0 and the output contains neither password nor hash

#### Scenario: Unsafe name
- **WHEN** `--name` contains control characters, line or paragraph separators or bidirectional overrides, or exceeds 100 characters
- **THEN** no account is created and the exit code is non-zero

#### Scenario: Rejected arguments are not echoed
- **WHEN** the command is invoked with an unsupported argument such as `--password <value>`
- **THEN** it exits with code 2 and the message does not repeat the supplied value

#### Scenario: Weak password
- **WHEN** the password has fewer than 10 characters
- **THEN** no account is created and the exit code is non-zero

#### Scenario: Non-ASCII email
- **WHEN** the email (for `create-teacher`, or either seed email) contains a non-ASCII character
- **THEN** no account is created and the exit code is non-zero

#### Scenario: Existing email
- **WHEN** the email already belongs to any account, including a student
- **THEN** nothing is created or modified, the role is not changed and the exit code is non-zero

### Requirement: Seed is explicit, idempotent and safe
`python -m app.cli seed` SHALL create at most one teacher and one student from credentials supplied through environment variables, SHALL create no subjects or other data, SHALL leave existing accounts untouched, and SHALL refuse to run when the environment is `production`.

#### Scenario: First run
- **WHEN** the seed runs in a development or test environment with valid variables on an empty database
- **THEN** exactly one teacher and one student are created and no password is printed

#### Scenario: Second run
- **WHEN** the seed runs again
- **THEN** no account is created or changed and the exit code is 0

#### Scenario: Production
- **WHEN** the environment is `production`
- **THEN** the seed does nothing and exits with a non-zero code

#### Scenario: Missing or weak credentials
- **WHEN** a seed email or password variable is missing, or a password has fewer than 10 characters
- **THEN** nothing is created and the exit code is non-zero; no default credentials exist in the code or in `.env.example`

### Requirement: The runtime database role cannot create teacher accounts
Public registration SHALL create students only, and the database identity used by the running API MUST be unable to insert a user whose role is teacher or to change any user's role, whatever the application code does. Teacher accounts SHALL be provisioned only through the administrative command, which uses the CLI database identity that the API process does not hold.

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
