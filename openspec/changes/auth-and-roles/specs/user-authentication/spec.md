# Spec Delta

## Purpose

Lets people create a student account, prove who they are with email and password, and call protected endpoints with a short-lived token, while keeping credentials, tokens and account existence safe from disclosure.

## ADDED Requirements

### Requirement: Public registration creates students only
`POST /api/v1/auth/register` SHALL create an account with role `student`, store the email in lowercase, and return 201 with the user profile. The request MUST NOT be able to choose the role.

#### Scenario: Successful registration
- **WHEN** a client registers with name, a valid email and a password of at least 10 characters
- **THEN** the response is 201 with `id`, `name`, lowercase `email`, `role` `student`, null consent fields, and no password or hash

#### Scenario: Role in the payload is ignored
- **WHEN** the request body also contains `"role": "teacher"`
- **THEN** the created account has role `student`

#### Scenario: Duplicate email
- **WHEN** a client registers an email that already exists, in any letter case
- **THEN** the response is 409 with an `Error` body and no second account is created

### Requirement: Registration input is validated
Registration SHALL reject, with 422 and field-level details that do not echo the submitted values, a password shorter than 10 or longer than 128 characters, an invalid email, and a name that is empty after trimming, longer than 100 characters or containing control characters (NUL, tabs, line breaks).

#### Scenario: Short password
- **WHEN** the password has 9 characters
- **THEN** the response is 422 and no account is created

#### Scenario: Oversized password
- **WHEN** the password has 129 characters
- **THEN** the response is 422 and no hashing is attempted

#### Scenario: Invalid email or name
- **WHEN** the email is malformed or the name is blank
- **THEN** the response is 422

#### Scenario: Unstorable characters never cause a server error
- **WHEN** the name contains a NUL or other control character, or login/registration inputs contain unusual Unicode
- **THEN** the response is 422 (or 401 for login), never 500

### Requirement: Passwords are stored as Argon2id hashes
The system SHALL store only an Argon2id hash of each password, SHALL NOT impose complexity rules beyond length, and MUST NOT return or log a password or hash.

#### Scenario: Stored value
- **WHEN** an account is registered
- **THEN** the stored credential is an Argon2id hash and differs from the password

#### Scenario: No credential in responses
- **WHEN** any endpoint returns a user profile
- **THEN** the body contains no password or hash field

### Requirement: Login issues an expiring token
`POST /api/v1/auth/login` SHALL accept email (case-insensitive) and password and return 200 with `access_token`, `token_type` `bearer` and `expires_in` equal to the configured lifetime in seconds.

#### Scenario: Successful login
- **WHEN** valid credentials are sent with the email in different letter case than registered
- **THEN** the response is 200 with a token whose lifetime matches `expires_in`

#### Scenario: Missing fields
- **WHEN** the email or password is missing
- **THEN** the response is 422

### Requirement: Login failures are uniform
Login SHALL answer a wrong password and an unknown email with the identical 401 status, code `INVALID_CREDENTIALS` and message, and SHALL spend comparable work in both cases so the response does not reveal whether the account exists.

#### Scenario: Wrong password
- **WHEN** a registered email is sent with a wrong password
- **THEN** the response is 401 with code `INVALID_CREDENTIALS`

#### Scenario: Unknown email
- **WHEN** an unregistered email is sent
- **THEN** the response is byte-for-byte equal in status and body to the wrong-password response

### Requirement: Login attempts are rate limited
Login SHALL allow at most the configured number of attempts per client within the configured window and answer further attempts with 429, code `RATE_LIMITED` and a `Retry-After` header, regardless of whether the credentials are correct; other endpoints are not limited by it.

#### Scenario: Limit exceeded
- **WHEN** a client exceeds the configured login attempts within the window
- **THEN** the next attempt, even with correct credentials, receives 429 with `Retry-After` and no token

#### Scenario: Window elapsed
- **WHEN** the window has elapsed after being limited
- **THEN** a login with correct credentials succeeds again

#### Scenario: Client-supplied address headers are not trusted
- **WHEN** a client sends `X-Forwarded-For`, `Forwarded` or `X-Real-IP` headers with varying values from the same connection
- **THEN** all its attempts count against the same limit, determined by the connection address

#### Scenario: Other endpoints unaffected
- **WHEN** a client is rate limited on login
- **THEN** its calls to other endpoints are not rejected with 429

### Requirement: Registration is rate limited
`POST /api/v1/auth/register` SHALL allow at most the configured number of requests per client address within the configured window (initially 5 per minute) and answer further requests with 429, code `RATE_LIMITED` and `Retry-After`, without hashing a password or storing an account.

#### Scenario: Limit exceeded
- **WHEN** a client exceeds the registration limit within the window
- **THEN** the next request receives 429 with `Retry-After`, no Argon2id hashing is performed and no account is created

#### Scenario: Forwarding headers are not trusted
- **WHEN** a client rotates `X-Forwarded-For`, `Forwarded` or `X-Real-IP` values
- **THEN** its requests still count against one limit determined by the connection address

#### Scenario: Independent from login
- **WHEN** a client is rate limited on registration
- **THEN** its login attempts are counted separately and are not rejected because of registration traffic

#### Scenario: Invalid requests count too
- **WHEN** registrations are sent with invalid payloads
- **THEN** they count against the limit

### Requirement: Tokens are strictly validated
Tokens SHALL be HS256 JWTs carrying `sub`, `iat`, `exp`, `iss` and `aud`, and protected endpoints SHALL accept a token only if its signature, algorithm, issuer, audience and expiry are valid and all those claims are present; any other token MUST yield 401 `UNAUTHORIZED` with `WWW-Authenticate: Bearer`.

#### Scenario: Valid token
- **WHEN** `GET /api/v1/users/me` is called with a freshly issued token
- **THEN** the response is 200

#### Scenario: Invalid tokens are rejected
- **WHEN** the token is expired, issued in the future, has a tampered signature, was signed with another secret, has another audience (or a list of audiences) or issuer, uses `alg` `none` or another algorithm, lacks a required claim, has non-numeric time claims, has a `sub` that is not a canonical lowercase hyphenated UUID, or is malformed
- **THEN** each case receives 401 with the same generic error body

#### Scenario: Missing or malformed header
- **WHEN** the `Authorization` header is absent or not of the form `Bearer <token>`
- **THEN** the response is 401

### Requirement: Token owner must still exist
A valid token SHALL authenticate only while its user exists in the database.

#### Scenario: Deleted user
- **WHEN** a request carries a valid, unexpired token whose user no longer exists
- **THEN** the response is 401

### Requirement: Authenticated profile
`GET /api/v1/users/me` SHALL return the caller's profile (`id`, `name`, `email`, `role`, `consent_version`, `consent_accepted_at`).

#### Scenario: Own profile
- **WHEN** an authenticated user calls the endpoint
- **THEN** the response is 200 with that user's data only

#### Scenario: Unauthenticated
- **WHEN** no valid token is sent
- **THEN** the response is 401

### Requirement: JWT secret and settings are safe at startup
The application SHALL refuse to start unless `JWT_SECRET` is set, is at least 32 bytes long and is not a placeholder or low-variety value, in every environment, and SHALL validate the token lifetime (1 to 1440 minutes), issuer, audience and the login and registration rate limit formats.

#### Scenario: Missing or short secret
- **WHEN** `JWT_SECRET` is missing or shorter than 32 bytes
- **THEN** startup fails naming `JWT_SECRET` without printing its value

#### Scenario: Placeholder secret
- **WHEN** `JWT_SECRET` contains `CHANGE_ME` or `changeme` (any case) or has fewer than 8 distinct characters
- **THEN** startup fails

#### Scenario: Invalid lifetime or rate limit
- **WHEN** the token lifetime is outside 1-1440 minutes or a rate limit string (login or registration) cannot be parsed
- **THEN** startup fails naming the variable

### Requirement: Authentication events do not leak secrets
Logs and error responses of authentication endpoints MUST NOT contain passwords, hashes, tokens, the JWT secret or the Authorization header; log entries identify users by id only.

#### Scenario: Logs after login and failures
- **WHEN** registrations, successful logins, failed logins and invalid-token requests are processed
- **THEN** the captured logs contain none of the submitted passwords, issued tokens or the secret
