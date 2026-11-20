# frontend-student-chat Specification

## Purpose
Lets a student ask questions about the material of a subject they are enrolled in, read the answers with the fragments the backend associates with them, continue earlier conversations and delete their conversations, using the existing API and leaving every authorization decision to the backend.

## ADDED Requirements

### Requirement: A student opens the chat of an enrolled subject
The interface SHALL provide `/subjects/{subject_id}/chat` for students, reached from a link on each card of the student's subject list. Teachers and visitors without a student session SHALL NOT see it, and a student who has lost access SHALL be told so.

#### Scenario: Student opens the chat
- **WHEN** an enrolled student opens the page
- **THEN** it shows the subject name, the conversations of the subject, the message box and the notice that this is a test version, with loading, empty and error states

#### Scenario: Teacher opens the route
- **WHEN** a teacher opens the page
- **THEN** the forbidden screen is shown and no chat or conversation request is sent

#### Scenario: Anonymous visitor
- **WHEN** a visitor without a session opens the page
- **THEN** the interface redirects to login and, after a student signs in, returns to the page

#### Scenario: Student without current consent
- **WHEN** a student whose consent is missing or outdated opens the page
- **THEN** the consent screen holds them first, as for any student route

#### Scenario: Not enrolled or subject gone
- **WHEN** the API answers 403 or 404 to the subject's data or to a question
- **THEN** the page says that the subject is not available to this account, with a link back to the list, and no stale conversation is shown

#### Scenario: Link from the list
- **WHEN** a student sees the subject list
- **THEN** each subject has a link to its chat, and a teacher's list has none

### Requirement: A student asks a question and reads a plain-text answer
The message box SHALL accept 1 to 2000 characters, send `POST /chat` with the subject and, when a conversation is open, its id, and show the answer as plain text. While the request is pending the send control SHALL be disabled and a polite status SHALL say that the assistant is answering. A "no material" answer SHALL appear as an ordinary assistant message.

#### Scenario: Question answered
- **WHEN** the student sends a valid question
- **THEN** the question appears at once, the answer appears below it when it arrives, the box is cleared and keeps the focus, and the conversation is open for the next question

#### Scenario: Invalid question
- **WHEN** the box is empty, only blanks or over 2000 characters
- **THEN** no request is sent, the box receives focus and the error is linked to it

#### Scenario: Answer without material
- **WHEN** the API answers with `no_material` and no sources
- **THEN** the answer text is shown as a normal assistant message with no sources list

#### Scenario: Text is plain
- **WHEN** a question or an answer contains markup, Markdown, long unbroken text or line breaks
- **THEN** it is shown literally, wraps without horizontal scrolling and keeps its line breaks

#### Scenario: Double submission
- **WHEN** a question is pending
- **THEN** the send control is disabled so the same question is not sent twice

#### Scenario: The open conversation does not change while a question is pending
- **WHEN** a question is pending
- **THEN** the conversation list, the new-conversation action and every confirm control are disabled, and the answer appears in the conversation the question was asked in, which stays selected

#### Scenario: New messages are announced
- **WHEN** an answer arrives
- **THEN** it is announced politely to assistive technology

### Requirement: Sources are shown as provided, without guarantees
Each assistant message SHALL list the sources given by the API as "material consulted": file name, page when there is one, and the snippet in an expandable detail. The interface SHALL NOT state or imply that a source proves a statement, and SHALL show a neutral note that the information must be checked in the original document.

#### Scenario: Answer with sources
- **WHEN** an answer has sources
- **THEN** each source shows its file name and page (when not null) and an expandable snippet shown as text, in the order given by the API, under a label that says material consulted

#### Scenario: Source whose document was deleted
- **WHEN** a source has no chunk or document id
- **THEN** it is shown the same way, with its stored file name and page

#### Scenario: Neutral wording
- **WHEN** sources are shown
- **THEN** no text says that they support, prove or guarantee the answer, and a note says that the information must be checked in the original

#### Scenario: Sources are text
- **WHEN** a file name or snippet contains markup or direction characters
- **THEN** it is shown as text and never interpreted

### Requirement: The student reads and continues the conversations of the subject
The page SHALL list the student's conversations of that subject, newest first, each labelled by the preview given by the API or, when the API gives none, by its date and time, SHALL open one to show its messages with their sources in order, and SHALL let the student continue it or start a new one.

#### Scenario: List of conversations
- **WHEN** the student has conversations in the subject
- **THEN** they are listed newest first by preview, only those of this subject, and none of another student

#### Scenario: Conversation without a preview
- **WHEN** the API gives a conversation no preview (`last_message_preview` null)
- **THEN** it is labelled with its date and time, so several conversations stay distinguishable

#### Scenario: Open a conversation
- **WHEN** the student opens a conversation
- **THEN** its messages appear in order, answers with their sources, and the next question continues that conversation

#### Scenario: New conversation
- **WHEN** the student starts a new conversation
- **THEN** the thread is empty and the next question sends no conversation id

#### Scenario: No conversations
- **WHEN** the subject has none
- **THEN** an empty state invites the student to ask the first question

#### Scenario: Conversation no longer available
- **WHEN** the API answers 404 to the messages of a conversation
- **THEN** the thread says that the conversation is not available and the list is refreshed

#### Scenario: Older answers do not undo a change
- **WHEN** a list or messages request that started before a question, an answer or a deletion answers after it
- **THEN** the new message is still shown and the deleted conversation does not come back

### Requirement: A student deletes one conversation after confirmation
Each conversation SHALL offer a delete action that asks for an inline confirmation stating that the conversation and its messages are permanently deleted, and only then calls `DELETE /conversations/{id}`.

#### Scenario: Confirmed deletion
- **WHEN** the student confirms
- **THEN** the conversation leaves the list, and if it was open the thread returns to the empty state

#### Scenario: Cancelled deletion
- **WHEN** the student cancels
- **THEN** no request is sent and the focus returns to the delete action

#### Scenario: Already gone or failed
- **WHEN** the API answers 404 the conversation is removed with a notice; when it answers 5xx or does not answer it stays with an error and the student can try again

#### Scenario: Deletion in flight
- **WHEN** a deletion is pending
- **THEN** every confirm control is disabled

### Requirement: A student deletes the whole history after confirmation
The student's subject list SHALL offer a "delete my whole history" action with an inline confirmation stating that it permanently deletes every conversation of the account in every subject, including subjects the student no longer sees, and does not delete the account. Only then SHALL it call `DELETE /users/me/conversations`.

#### Scenario: Confirmed deletion
- **WHEN** the student confirms
- **THEN** the request is sent, every conversation list is emptied and a notice says the history was deleted

#### Scenario: Cancelled or failed
- **WHEN** the student cancels, nothing is sent; when the request fails the history stays and an error is shown

#### Scenario: Teacher
- **WHEN** a teacher opens the subject list
- **THEN** no such action is present

### Requirement: Limits and failures are explained and never lose the question
Every documented failure of `POST /chat` SHALL have its own Spanish message, chosen by status and code, and the typed question SHALL stay in the box. The client limit for a question SHALL be longer than the model's limit.

#### Scenario: Rate limit
- **WHEN** the API answers 429
- **THEN** the message says to wait the seconds given by `Retry-After` when present and that the limit may be shared by users of the same connection

#### Scenario: Provider unavailable
- **WHEN** the API answers 502 `LLM_UNAVAILABLE`
- **THEN** the message says that the assistant is not available and to try again, and the question stays in the box

#### Scenario: Answer blocked
- **WHEN** the API answers 502 `LLM_BLOCKED`
- **THEN** the message says that the answer could not be given and to rephrase, and the question stays in the box

#### Scenario: The conversation is gone
- **WHEN** the API answers 404 to a question that carried a conversation id
- **THEN** the page says that the conversation is not available, keeps the subject, the list (refreshed) and the question in the box, and the next question starts a new conversation

#### Scenario: Server or network failure
- **WHEN** the API answers 5xx, 422 or does not answer
- **THEN** a Spanish error is shown, the question stays in the box and nothing is added to the thread

#### Scenario: Timeout
- **WHEN** a question exceeds the client limit
- **THEN** the message says that the answer may have been saved, the conversation and the list are requested again, and the student reviews them before asking again

#### Scenario: Consent changed
- **WHEN** the API answers 403 `CONSENT_REQUIRED`
- **THEN** the student is held at the consent screen by the existing gate and the question is not sent again by the interface

#### Scenario: Session expired
- **WHEN** the API answers 401
- **THEN** the session ends as for any other request and no error is flashed

### Requirement: The chat follows the shared UI and privacy rules
Every new screen and message SHALL use the single Spanish copy module, accessible and keyboard-operable controls, no horizontal scrolling at 320 px, and the shared loading, empty and error states. The chat page SHALL show a notice that this is a test version, that questions and fragments go to Gemini (Google) and that only fictitious data must be used, with a link to the privacy draft that does not end the session. No token, question, answer or server message SHALL be logged.

#### Scenario: Copy and accessibility
- **WHEN** the copy check and the automated accessibility scan run on the chat page in each state
- **THEN** no user-facing string is inline and no serious violation is reported

#### Scenario: Notice and policy link
- **WHEN** the chat page is shown
- **THEN** the notice is visible and its link to the policy opens in a new tab without ending the session

#### Scenario: Nothing sensitive in diagnostics
- **WHEN** a question fails
- **THEN** diagnostics contain only method, path without query, and status
