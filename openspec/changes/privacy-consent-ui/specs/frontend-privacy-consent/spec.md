## ADDED Requirements

### Requirement: The privacy policy is public and complete
The interface SHALL provide a public page at `/privacy`, reachable without signing in, that shows the text of the current policy version in Spanish. The text SHALL state what is stored, that questions, history and retrieved fragments are sent to Gemini, how long data is kept, and how conversations are deleted.

#### Scenario: Anonymous visitor reads the policy
- **WHEN** an anonymous visitor opens `/privacy`
- **THEN** the page shows the policy text and the version, and no request is sent to the API

#### Scenario: The policy names Gemini and the deletion options
- **WHEN** the policy is shown
- **THEN** it names Gemini as the service that receives the data, lists what is sent to it, and describes deleting one conversation and deleting all of the user's conversations

#### Scenario: Policy reachable from the entry points
- **WHEN** the registration screen or the consent screen is shown
- **THEN** each contains a link to `/privacy`

#### Scenario: Reading the policy does not end the session
- **WHEN** a held student opens the policy from the consent screen
- **THEN** it opens in a new browsing context and the student's session and consent screen stay as they were

### Requirement: The policy follows Ley 25.326 and claims nothing the owner has not supplied
The text SHALL state the audience (people over 18), the data needed and the effect of not accepting, that Gemini may process the data outside Argentina, the rights of Ley 25.326 with their legal deadlines, the revocation of consent and the supervisory authority. Items only the owner can state SHALL appear as marked placeholders and SHALL NOT be asserted.

#### Scenario: Audience and obligation
- **WHEN** the policy is shown
- **THEN** it says the service is only for people over 18 and that students declare it when accepting, which account data is needed, and that without accepting the application only allows reading the policy and signing out

#### Scenario: Processing outside Argentina
- **WHEN** the policy describes the data sent to Gemini
- **THEN** it says that Gemini may process the data outside Argentina, including countries not recognised as adequate, and does not assert that Google is a processor

#### Scenario: Rights and deadlines
- **WHEN** the policy lists the rights
- **THEN** it lists access (10 calendar days), rectification, update and suppression (5 business days), the revocation of the consent without retroactive effect and habeas data, refers to the supervisory authority without naming it, and does not list the portability or restriction rights of the GDPR

#### Scenario: Owner items stay marked
- **WHEN** the owner has not supplied the controller, the legal basis, the Google conditions and transfer basis, the account retention, the backups or the means to exercise the rights
- **THEN** each appears as a marked placeholder, and the release check fails while any remains

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

#### Scenario: Declaration of being over 18
- **WHEN** the consent screen is shown
- **THEN** the label of the tick box includes the declaration of being over 18 years old

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
