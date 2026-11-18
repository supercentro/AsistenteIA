## ADDED Requirements

### Requirement: The privacy policy is public and complete
The interface SHALL provide a public page at `/privacy`, reachable without signing in, that shows the text of the current policy version in Spanish. The text SHALL state what is stored, that questions, history and retrieved fragments are sent to Gemini as processor, how long data is kept, and how conversations are deleted.

#### Scenario: Anonymous visitor reads the policy
- **WHEN** an anonymous visitor opens `/privacy`
- **THEN** the page shows the policy text and the version, and no request is sent to the API

#### Scenario: The policy names the processor and the deletion options
- **WHEN** the policy is shown
- **THEN** it names Gemini as processor, lists what is sent to it, and describes deleting one conversation and deleting all of the user's conversations

#### Scenario: Policy reachable from the entry points
- **WHEN** the registration screen or the consent screen is shown
- **THEN** each contains a link to `/privacy`

#### Scenario: Reading the policy does not end the session
- **WHEN** a held student opens the policy from the consent screen
- **THEN** it opens in a new browsing context and the student's session and consent screen stay as they were

### Requirement: A student without current consent is held at the consent screen
A signed-in student whose profile `consent_version` is not the current version SHALL be redirected to `/consent` from every student route, and SHALL return to the original target after accepting. Teachers and anonymous visitors SHALL NOT be sent there.

#### Scenario: Student who never accepted
- **WHEN** a student whose `consent_version` is null signs in or opens a student route
- **THEN** the interface shows `/consent` and the requested route is not rendered

#### Scenario: Student with an outdated version
- **WHEN** a student's stored version differs from the current version
- **THEN** the consent screen is shown with a notice that the policy changed

#### Scenario: Student with current consent
- **WHEN** a student's stored version equals the current version
- **THEN** the student routes render normally and `/consent` redirects to the home route

#### Scenario: Teacher is not held
- **WHEN** a teacher signs in
- **THEN** the interface goes to the subject list and never shows `/consent`

#### Scenario: Anonymous visitor
- **WHEN** an anonymous visitor opens `/consent`
- **THEN** the interface redirects to the login screen

### Requirement: Consent is explicit and recorded through the API
The consent screen SHALL show the policy version and text, an unchecked tick box and an Accept action that stays disabled until the box is ticked. Accepting SHALL send `POST /users/me/consent` with the current version, and on 200 SHALL replace the stored profile with the response and go to the original target.

#### Scenario: Accept
- **WHEN** the student ticks the box and activates Accept
- **THEN** the interface sends the current version, updates the profile and leaves `/consent`

#### Scenario: Box not ticked
- **WHEN** the box is unticked
- **THEN** Accept is disabled and no request is sent

#### Scenario: Version rejected by the API
- **WHEN** the API answers 422 `INVALID_CONSENT_VERSION`
- **THEN** the screen shows an error that the policy changed and asks to reload, and the student stays held

#### Scenario: Network or server failure
- **WHEN** the request fails with a network error or a 5xx
- **THEN** the screen shows an error with a retry control and the profile is unchanged

#### Scenario: Expired session
- **WHEN** the API answers 401
- **THEN** the session ends as for any other request

#### Scenario: Late answer of an earlier session
- **WHEN** the answer to an acceptance arrives after that session ended and another user is signed in
- **THEN** the profile of the open session is not changed

### Requirement: A consent refusal by the API sends the student to the consent screen
When any request of a signed-in student is answered with 403 `CONSENT_REQUIRED`, the interface SHALL refresh the profile consent state and show `/consent`, and SHALL NOT retry the request on its own.

#### Scenario: Policy changed during the session
- **WHEN** the API answers 403 `CONSENT_REQUIRED` to a student's request
- **THEN** the student is taken to `/consent` with the notice that the policy changed

#### Scenario: Other 403 answers
- **WHEN** the API answers 403 with another code
- **THEN** the behaviour is unchanged and the consent screen is not shown

### Requirement: Not accepting leaves only sign-out and the policy
On the consent screen the student SHALL be able to read the policy and sign out, and SHALL NOT be able to reach any other student route until accepting. Signing out SHALL clear the session as elsewhere.

#### Scenario: Student does not accept
- **WHEN** the student signs out from the consent screen
- **THEN** the session is cleared and the login screen is shown

#### Scenario: Direct navigation
- **WHEN** a held student types the address of another student route
- **THEN** the consent screen is shown again

### Requirement: The consent screens are accessible and carry no sensitive values
The policy and consent screens SHALL take every string from the single Spanish copy module, have a visible heading that receives focus on arrival, a labelled tick box, keyboard operation with a visible focus indicator, and no horizontal scrolling from 320 px. They MUST NOT log or show tokens, emails or form values in errors.

#### Scenario: Keyboard use
- **WHEN** the student uses only the keyboard
- **THEN** the policy link, the tick box, Accept and sign-out are reachable and operable in a logical order

#### Scenario: Narrow viewport
- **WHEN** the viewport is 320 px wide
- **THEN** the policy text and controls are readable without horizontal page scrolling

#### Scenario: Version constant stays in sync
- **WHEN** the UI version constant differs from the backend default version
- **THEN** the existing automated check fails
