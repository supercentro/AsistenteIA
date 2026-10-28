# frontend-session-auth Specification

## Purpose
Defines how people register and sign in through the web interface, how the signed-in session is held in memory and ended, and how routes are protected by authentication and role, so that every later screen can rely on a trustworthy session while the backend stays the authority on permissions.

## Requirements

### Requirement: Users sign in with email and password
The interface SHALL provide a login screen that sends the credentials to `POST /auth/login`, then loads the profile with `GET /users/me`, and only then treat the user as signed in and send them to the subject list. Both teachers and students use this screen.

#### Scenario: Student signs in
- **WHEN** a registered student submits valid credentials
- **THEN** the interface calls login, then `GET /users/me`, shows the subject list and the navigation of a student

#### Scenario: Teacher signs in
- **WHEN** a teacher created by the administrative command submits valid credentials
- **THEN** the interface shows the subject list and the navigation of a teacher

#### Scenario: Wrong credentials
- **WHEN** the API answers 401 `INVALID_CREDENTIALS`
- **THEN** the screen stays on the login form, shows one Spanish message that does not say whether the email or the password was wrong, keeps no token and does not redirect

#### Scenario: Profile cannot be loaded after a successful login
- **WHEN** login succeeds but `GET /users/me` fails
- **THEN** no session is established, the token is discarded and the user sees a generic Spanish error

#### Scenario: Required fields are validated before sending
- **WHEN** the email or the password is empty, the email is longer than 255 characters, the email contains non-ASCII characters, or the password is longer than 128 characters
- **THEN** no request is sent and the invalid fields show a Spanish error

#### Scenario: Submitting twice is prevented
- **WHEN** the form is submitted while a login request is in flight
- **THEN** the submit control is disabled and only one request is sent

#### Scenario: Too many attempts
- **WHEN** the API answers 429 and the browser can read a valid `Retry-After` header
- **THEN** the screen shows a Spanish message with the number of seconds to wait, without exposing any server text

#### Scenario: Too many attempts when the wait time is not readable
- **WHEN** the API answers 429 and `Retry-After` is missing, invalid or not exposed to the browser by the server's cross-origin configuration (TD-021)
- **THEN** the screen shows the generic Spanish rate-limit message without a number

#### Scenario: Server unavailable
- **WHEN** the API answers 503 or cannot be reached
- **THEN** the screen shows a Spanish message that the service is unavailable and allows trying again

### Requirement: Students register an account
The interface SHALL provide a registration screen for students that sends name, email and password to `POST /auth/register` and never sends a role. After a 201 response it SHALL redirect to the login screen with a success notice and SHALL NOT sign the user in automatically. Teacher accounts are never created from the interface.

#### Scenario: Successful registration
- **WHEN** a visitor submits a valid name, email and password and the API answers 201
- **THEN** the interface shows the login screen with a notice that the account was created, and no token or profile is stored

#### Scenario: Email already registered
- **WHEN** the API answers 409
- **THEN** the form shows a Spanish message that the email is already registered, according to the approved contract, and keeps the other fields

#### Scenario: Server-side validation failure
- **WHEN** the API answers 422
- **THEN** the form shows a generic Spanish validation message without echoing server text or the submitted values

#### Scenario: Limits are enforced before sending
- **WHEN** the name is empty or longer than 100 characters, the email is invalid, longer than 255 characters or not ASCII, or the password is shorter than 10 or longer than 128 characters
- **THEN** no request is sent and each invalid field shows a Spanish error

#### Scenario: No role in the payload
- **WHEN** a registration request is sent
- **THEN** its body contains only `name`, `email` and `password`

#### Scenario: Too many registrations
- **WHEN** the API answers 429
- **THEN** the form shows the wait time from `Retry-After` when it is readable, and the generic rate-limit message otherwise, as for login

### Requirement: The session lives only in memory
The access token and the user profile SHALL be held in one in-memory store. They MUST NOT be written to `localStorage`, `sessionStorage`, cookies, IndexedDB or the URL, and reloading the page SHALL return the user to the login screen. Signing out SHALL clear the token, the profile and every cached server response.

#### Scenario: Nothing is persisted
- **WHEN** a user signs in and the browser storage and cookies are inspected
- **THEN** no token, password or profile data is found in any of them

#### Scenario: Reload ends the session
- **WHEN** a signed-in user reloads the page
- **THEN** the login screen is shown and a protected route is not rendered until the user signs in again

#### Scenario: Sign-out clears everything
- **WHEN** the user chooses to sign out
- **THEN** the token, the profile and the cached subject data are cleared and the login screen is shown

#### Scenario: A second user on the same tab
- **WHEN** one user signs out and another signs in without reloading
- **THEN** the second user never sees data fetched for the first

### Requirement: The session ends when the token expires
The interface SHALL end the session automatically when the token reaches the lifetime announced by `expires_in`, and SHALL NOT send a request with a token it knows has expired.

#### Scenario: Automatic expiry
- **WHEN** the announced lifetime elapses while the user is on a protected screen
- **THEN** the session is cleared and the login screen is shown with a Spanish notice that the session expired

#### Scenario: Expired token is not sent
- **WHEN** a request is about to be sent after the lifetime elapsed (for example after the computer slept)
- **THEN** the session is cleared first and the request is not sent with the expired token

#### Scenario: Ending a session leaves no residue
- **WHEN** the session ends by expiry, by a 401 or by sign-out
- **THEN** the token, the profile, the cached server data and any pending expiry timer are gone, and a later sign-in starts from an empty state

### Requirement: A 401 on a protected request ends the session once
When the API answers 401 to a request that carried a token, the interface SHALL end the session and show the login screen with a notice. A 401 answered to login or registration SHALL be handled as a form error and SHALL NOT end a session or redirect, and several simultaneous 401 answers SHALL cause a single transition without loops.

#### Scenario: Token rejected by the API
- **WHEN** a protected request is answered with 401
- **THEN** the session is cleared once, the login screen is shown with a notice and no further protected requests are sent

#### Scenario: Late 401 for an earlier session
- **WHEN** a request sent with one user's token is answered with 401 after that user signed out and another user signed in
- **THEN** the new session is not affected

#### Scenario: Concurrent 401 answers
- **WHEN** several protected requests are answered with 401 at the same time
- **THEN** the session is cleared once and the navigation to the login screen happens once

#### Scenario: 401 from the login endpoint
- **WHEN** login is answered with 401
- **THEN** it is shown as a form error and no redirect or session change happens

### Requirement: The role comes from the backend
The signed-in user and role SHALL be taken from `GET /users/me` and never from the contents of the token, which the interface does not decode. The consent fields of the profile SHALL be kept with the profile and SHALL NOT be interpreted, displayed or enforced by this change.

#### Scenario: Role from the profile
- **WHEN** the profile answers `role: student` or `role: teacher`
- **THEN** the navigation and the guarded routes follow that value

#### Scenario: Token claims are ignored
- **WHEN** a token contains a different role claim than the profile
- **THEN** the interface behaves according to the profile

### Requirement: Routes are protected by authentication and role
Protected routes SHALL render only for a signed-in user, and role-restricted routes SHALL render only for the allowed roles. This is a usability layer: the backend stays the authority and answers 401 and 403 independently.

#### Scenario: Anonymous visitor
- **WHEN** an anonymous visitor opens a protected route
- **THEN** the login screen is shown and no protected data is requested

#### Scenario: Return to the requested page
- **WHEN** a visitor was redirected to login from an internal route and signs in
- **THEN** the interface returns to that route

#### Scenario: No return to the previous user's page after sign-out
- **WHEN** a user signs out deliberately
- **THEN** the login screen does not remember the page they were on, so the next person to sign in lands on the default home

#### Scenario: Unsafe return target
- **WHEN** the stored return target is an absolute URL, a protocol-relative URL (`//host`), or resolves to the login or registration routes (also through a different letter case, dot segments, a trailing slash or percent-encoding)
- **THEN** it is ignored and the user goes to the default home

#### Scenario: Wrong role
- **WHEN** a signed-in user opens a route reserved for the other role
- **THEN** a Spanish "not allowed" view is shown, the restricted content is not rendered and its data is not requested

#### Scenario: Signed-in user opens the authentication screens
- **WHEN** a signed-in user opens the login or registration route
- **THEN** the interface redirects to the default home

### Requirement: Sensitive data never reaches logs, messages or URLs
Passwords, tokens, emails and the submitted form values MUST NOT appear in console output, in error messages shown to the user, in query strings or in thrown error objects that the interface logs.

#### Scenario: Failed login is logged safely
- **WHEN** a login fails for any reason
- **THEN** the console output and the visible messages contain neither the password, the token nor the submitted email

#### Scenario: The token is never logged during the session lifecycle
- **WHEN** a user signs in, makes protected requests, hits a 401, lets the session expire or signs out
- **THEN** no console output, thrown error message or diagnostic at any step contains the token
