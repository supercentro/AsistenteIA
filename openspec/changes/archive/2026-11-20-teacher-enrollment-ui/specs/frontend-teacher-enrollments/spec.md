# frontend-teacher-enrollments Specification

## Purpose
Lets a teacher decide who may ask about their subject: see the students enrolled in it, enroll a registered student by e-mail and remove an enrollment, from the subject page, using the existing API and leaving every authorization decision to the backend.

## ADDED Requirements

### Requirement: The subject page lists the enrolled students
The teacher's subject page SHALL show the students enrolled in the subject, as returned by `GET /subjects/{subject_id}/enrollments`, each with the e-mail given by the API and nothing else, with loading, empty and error states. Students and visitors without a teacher session SHALL NOT see it.

#### Scenario: Owner sees the enrolled students
- **WHEN** the owner teacher opens the page of a subject with enrolled students
- **THEN** the section lists them in the order received, each by e-mail, shown as text

#### Scenario: No enrolled students
- **WHEN** the subject has no enrollments
- **THEN** an empty state explains that no student is enrolled and points to the form

#### Scenario: Loading and failure
- **WHEN** the list is loading or its request fails
- **THEN** a loading state or an error state with a retry control is shown, the rest of the page stays usable, and a 401 ends the session without flashing an error

#### Scenario: Subject of another teacher or unknown subject
- **WHEN** the API answers 404 or 403 to the list
- **THEN** the interface shows the same not-found or forbidden view as for the rest of the page and no stale list

#### Scenario: Student opens the route
- **WHEN** a student opens the subject page
- **THEN** the forbidden screen is shown and no enrollment request is sent

#### Scenario: Markup and long e-mails are text
- **WHEN** an e-mail contains markup or long unbroken text
- **THEN** it is shown literally and wraps inside its container without horizontal scrolling

### Requirement: A teacher enrolls a registered student by e-mail
The section SHALL offer a form with one e-mail field that sends `POST /subjects/{subject_id}/enrollments` with `student_email`, validated with the same rules as the registration e-mail without being stricter or looser, and SHALL tell that the student must already have an account. On 201 the student SHALL appear in the list and the field SHALL be cleared.

#### Scenario: Student enrolled
- **WHEN** the teacher submits the e-mail of a registered student
- **THEN** the e-mail is sent as typed, the student appears in the list with the e-mail returned by the API, the field is cleared and the focus stays usable for the next e-mail

#### Scenario: Invalid e-mail
- **WHEN** the field is empty, malformed, non-ASCII or longer than 255 characters
- **THEN** no request is sent, the field receives focus and the error is linked to it

#### Scenario: E-mail without a student account
- **WHEN** the API answers 404 to the enrollment
- **THEN** one neutral message says that no registered student was found with that e-mail, it does not say whether the e-mail belongs to a teacher, the typed value stays in the field, and the page checks that the subject still exists

#### Scenario: Subject no longer available
- **WHEN** the check after a 404 shows that the subject itself is gone
- **THEN** the page shows the not-found view for the subject

#### Scenario: Student already enrolled
- **WHEN** the API answers 409
- **THEN** a message says that the student is already enrolled, the list is unchanged and the value stays in the field

#### Scenario: Other failures
- **WHEN** the API answers 422, 429, 5xx or does not answer
- **THEN** a Spanish error (with the wait for a 429 when `Retry-After` is sent) is shown, the value stays in the field and nothing is added to the list; a 401 ends the session as for any other request

#### Scenario: Submission in flight
- **WHEN** the request is pending
- **THEN** the submit control is disabled so the same student is not sent twice

#### Scenario: The list is not loaded yet
- **WHEN** a student is enrolled while the list is loading or has failed
- **THEN** the list is requested again and shown whole, and a list with only the new student is never shown

#### Scenario: Stale error
- **WHEN** an enrollment error is shown and the teacher edits the field
- **THEN** the error disappears

#### Scenario: The e-mail is not echoed
- **WHEN** any error is shown
- **THEN** the message is chosen by the interface from the status and code; the server message and the submitted value are neither displayed nor logged

### Requirement: A teacher removes an enrollment after confirmation
Each listed student SHALL have a remove action that asks for an inline confirmation and only then calls `DELETE /subjects/{subject_id}/enrollments/{student_id}`. The confirmation SHALL say that the student stops seeing the subject and their conversations in it, that nothing is deleted and that the student can be enrolled again.

#### Scenario: Confirmed removal
- **WHEN** the teacher confirms
- **THEN** the interface sends the deletion, the student disappears from the list on 204, and the focus moves to the section heading

#### Scenario: Cancelled removal
- **WHEN** the teacher cancels
- **THEN** no request is sent, the student stays and the focus returns to the remove action

#### Scenario: Enrollment already gone
- **WHEN** the API answers 404 to the deletion
- **THEN** the student is removed from the list, a notice says the enrollment no longer existed, and the subject and the list are requested again

#### Scenario: Subject gone
- **WHEN** the check after a 404 on the deletion shows that the subject itself is gone
- **THEN** the page shows the not-found view for the subject

#### Scenario: Removal fails
- **WHEN** the API answers 5xx or does not answer
- **THEN** the student stays, a Spanish error is shown on that row and the teacher can try again

#### Scenario: Removal in flight
- **WHEN** a removal is pending
- **THEN** every confirm control is disabled

#### Scenario: Another teacher or a student
- **WHEN** the API answers 403 or 404 because the subject is not available to the account
- **THEN** the page shows the forbidden or not-found view

### Requirement: Changes to the list are not undone by older answers
A list request that started before an enrollment or a removal SHALL NOT bring back a removed student or hide an enrolled one when it answers afterwards.

#### Scenario: Older refresh after an enrollment
- **WHEN** a refresh that started before an enrollment answers after it
- **THEN** the enrolled student is still shown

#### Scenario: Older refresh after a removal
- **WHEN** a refresh that started before a removal answers after it
- **THEN** the removed student is not shown again

### Requirement: The enrollment section follows the shared UI rules
The section SHALL use the single Spanish copy module, labelled and keyboard-operable controls, errors linked to the field, no horizontal scrolling at 320 px, and the loading, empty and error states of the application shell, and the confirmation SHALL be the same component as the one of the document deletion.

#### Scenario: Copy and accessibility
- **WHEN** the copy check and the automated accessibility scan run on the subject page with the section in each state
- **THEN** no user-facing string is inline and no serious violation is reported

#### Scenario: Document deletion keeps working
- **WHEN** a document is deleted after the confirmation was extracted into the shared component
- **THEN** its confirmation, focus handling and tests behave exactly as before
