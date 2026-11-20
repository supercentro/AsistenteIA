# frontend-teacher-materials Specification

## Purpose
Lets a teacher manage the material of their subjects from the web interface: create a subject, upload documents, follow their processing status and delete them, using the existing API and leaving every authorization decision to the backend.

## ADDED Requirements

### Requirement: A teacher creates a subject from the subject list
A teacher SHALL see a form on the subject list with a name (1 to 150 characters after trimming) and an optional description (up to 2000 characters), sent to `POST /subjects`. The limits SHALL mirror the API without being stricter or looser. On 201 the subject appears in the list. A student SHALL NOT see the form.

#### Scenario: Subject created
- **WHEN** a teacher submits a valid name and description
- **THEN** the interface sends them, the new subject appears in the list, and the form is cleared and ready for another subject

#### Scenario: Blank or too long name
- **WHEN** the name is blank after trimming, or longer than 150 characters, or the description is longer than 2000 characters
- **THEN** no request is sent, the first invalid field receives focus and each error is linked to its field

#### Scenario: Name already used by this teacher
- **WHEN** the API answers 409
- **THEN** the form shows that the name is already used, keeps the values, and the list is unchanged

#### Scenario: Server refusal, network failure or expired session
- **WHEN** the API answers 422, 5xx or does not answer, or answers 401
- **THEN** a 422 or failure shows a Spanish error and keeps the values so the teacher can retry, and a 401 ends the session as for any other request

#### Scenario: Submission in flight
- **WHEN** the request is pending
- **THEN** the submit control is disabled so the same subject is not sent twice

#### Scenario: Student does not see the form
- **WHEN** a student opens the subject list
- **THEN** no create control is present

#### Scenario: Markup is text
- **WHEN** a name or description contains markup
- **THEN** it is shown literally after creation, never interpreted

### Requirement: A teacher opens the page of one of their subjects
A teacher SHALL be able to open `/subjects/{subject_id}` from the subject list. The page SHALL show the subject name and description and the list of its documents, with loading, empty and error states. Students and visitors without a teacher session SHALL NOT see it.

#### Scenario: Owner opens the page
- **WHEN** the owner teacher opens the page of their subject
- **THEN** the subject and its documents (name, type, size, chunk count, status) are shown in the order received

#### Scenario: Subject of another teacher or unknown subject
- **WHEN** the API answers 404 for the subject or for its documents
- **THEN** the interface shows a not-found view that does not reveal whether the subject exists, with a link back to the list

#### Scenario: Student opens the route
- **WHEN** a student opens `/subjects/{subject_id}`
- **THEN** the forbidden screen is shown and no request about that subject is sent

#### Scenario: Anonymous visitor opens the route
- **WHEN** a visitor without a session opens the route
- **THEN** the interface redirects to login and, after signing in as a teacher, returns to the page

#### Scenario: Subject without documents
- **WHEN** the subject has no documents
- **THEN** an empty state explains that no material has been uploaded yet and points to the upload control

#### Scenario: Loading and failure
- **WHEN** the documents are loading or the request fails
- **THEN** a loading state or an error state with a retry control is shown, and a 401 ends the session without flashing an error

### Requirement: A teacher uploads one document at a time
The page SHALL let the teacher choose one file and send it to `POST /subjects/{subject_id}/documents` as the single field `file`. The interface SHALL NOT decide the type or the size itself: the API does, and each documented failure SHALL have its own Spanish message chosen by the stable code (and, for 422, by `details.reason`). On 202 the document SHALL appear with status `pending`.

#### Scenario: Upload accepted
- **WHEN** the teacher chooses a file and the API answers 202
- **THEN** the document appears at once as pending with its name, type and size, and the file control is cleared

#### Scenario: No file chosen
- **WHEN** the teacher submits without a file
- **THEN** no request is sent and an error asks to choose a file

#### Scenario: Refusals of the API
- **WHEN** the API answers 413, 415, 409 `DOCUMENT_QUOTA_EXCEEDED`, 422 (with each reason `MALFORMED_MULTIPART`, `FILE_PART_MISSING`, `UNEXPECTED_FIELDS`, `EMPTY_FILE` or `INVALID_FILENAME`), 408, 429 or 503
- **THEN** each case shows a different Spanish message, the 429 and 503 messages tell how many seconds to wait when `Retry-After` is present, and the document list is unchanged

#### Scenario: Slow upload
- **WHEN** the upload takes longer than the client limit for uploads (120 seconds)
- **THEN** the interface says the upload took too long and that the list of documents must be checked before trying again, because the file may have arrived

#### Scenario: Other failure
- **WHEN** the upload fails with a network error or an unlisted status
- **THEN** a generic Spanish error with a retry path is shown and no document is added

#### Scenario: Submission in flight
- **WHEN** an upload is pending
- **THEN** the upload control is disabled so the same file is not sent twice

#### Scenario: File name is text
- **WHEN** a file name contains markup, long unbroken text or direction characters
- **THEN** it is shown as text, wraps inside its container without horizontal scrolling, and is never interpreted

#### Scenario: Notice about the material
- **WHEN** the upload area is shown
- **THEN** it states the accepted formats and that this MVP is for tests, so only fictitious documents must be uploaded, without personal data or confidential content

#### Scenario: Subject no longer available
- **WHEN** the API answers 404 or 403 to the upload
- **THEN** the interface shows the not-found or forbidden view for the subject and keeps no stale document

### Requirement: The processing status is shown and followed
Each document SHALL show its status (`pending`, `processing`, `ready`, `failed`) as text, not only by colour. While any document is `pending` or `processing` the list SHALL refresh by itself, and it SHALL stop refreshing when all are final. A `failed` document SHALL show a Spanish explanation chosen by its `error_code`; the server `error_message` SHALL NOT be shown. A manual refresh control SHALL always be available.

#### Scenario: Pending becomes ready
- **WHEN** a document changes from `pending` or `processing` to `ready`
- **THEN** the list shows the new status and its chunk count without a manual action, and the change is announced politely to assistive technology, every document that finished in the same refresh included

#### Scenario: An older answer does not undo a change
- **WHEN** a refresh that started before an upload or a deletion answers after it
- **THEN** the uploaded document is still shown and the deleted one is not shown again

#### Scenario: Failed document
- **WHEN** a document is `failed` with any code of the closed list in `docs/api-spec.yml`
- **THEN** the row shows a Spanish explanation specific to that code, and a code outside the list shows a generic explanation

#### Scenario: Refresh stops when everything is final
- **WHEN** every document is `ready` or `failed`
- **THEN** no further automatic requests are sent

#### Scenario: A refresh fails
- **WHEN** an automatic refresh fails with a network error or 5xx
- **THEN** the last known list stays visible with a notice, automatic refresh continues, and a 401 ends the session

#### Scenario: Manual refresh
- **WHEN** the teacher activates the refresh control
- **THEN** the list is requested once and the result replaces the previous one

#### Scenario: Leaving the page
- **WHEN** the teacher leaves the subject page or the tab is hidden
- **THEN** automatic refresh does not continue in the background

### Requirement: A teacher deletes a document after confirmation
The page SHALL offer to delete a document with an explicit confirmation that states the deletion is irreversible and removes its fragments. The action SHALL call `DELETE /subjects/{subject_id}/documents/{document_id}` only after confirming, and SHALL be available for a document in any status.

#### Scenario: Confirmed deletion
- **WHEN** the teacher confirms
- **THEN** the interface deletes the document, it disappears from the list on 204, and the subject's document count is free again

#### Scenario: Cancelled deletion
- **WHEN** the teacher cancels or leaves the confirmation
- **THEN** no request is sent and the document stays

#### Scenario: Document already gone
- **WHEN** the API answers 404 to the deletion
- **THEN** the document is removed from the list and a notice says it no longer existed

#### Scenario: Deletion fails
- **WHEN** the API answers 5xx or does not answer
- **THEN** the document stays, a Spanish error is shown, and the teacher can try again

#### Scenario: Deletion while processing
- **WHEN** the teacher deletes a `pending` or `processing` document
- **THEN** the same confirmation applies and the request is sent

#### Scenario: Double submission
- **WHEN** a deletion is pending
- **THEN** every confirm control is disabled, and when the row is gone the focus moves to the documents heading

### Requirement: The material screens follow the shared UI rules
Every new screen and message SHALL use the single Spanish copy module, accessible forms and controls (labels, visible focus, keyboard operation, errors linked to fields), no horizontal scrolling at 320 px, and the loading, empty and error states of the application shell. No token, file content or server message SHALL be shown or logged.

#### Scenario: Copy
- **WHEN** the copy check runs on the new screens and components
- **THEN** no user-facing string is written inline

#### Scenario: Accessibility
- **WHEN** the automated accessibility scan runs on the subject list with the form and on the subject page in each state
- **THEN** it reports no serious violation

#### Scenario: Keyboard and narrow screens
- **WHEN** the screens are used with the keyboard only and at 320 px width
- **THEN** every control is reachable and operable and nothing requires horizontal scrolling

#### Scenario: Nothing sensitive in diagnostics
- **WHEN** an upload or deletion fails
- **THEN** diagnostics contain only method, path without query, and status, never the file name, the file content or the server message
