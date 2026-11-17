# Spec Delta

## Purpose

Persists student conversations with their messages and source citations, and provides endpoints for listing, reading and deleting conversation history, isolated per student.

## ADDED Requirements

### Requirement: List conversations for the authenticated student

`GET /conversations` SHALL return the conversations of the authenticated student, ordered by creation time descending. An optional `subject_id` query parameter SHALL filter by subject. Only students SHALL access this endpoint; teachers SHALL receive 403.

#### Scenario: Student lists all conversations
- **WHEN** a student with conversations calls `GET /conversations`
- **THEN** the response is an array of conversations with `id`, `subject_id`, `created_at`, and `last_message_preview`, ordered by `created_at` descending

#### Scenario: Student filters by subject
- **WHEN** a student calls `GET /conversations?subject_id=<uuid>`
- **THEN** only conversations of that subject are returned

#### Scenario: Student with no conversations
- **WHEN** a student with no conversations calls `GET /conversations`
- **THEN** the response is an empty array

#### Scenario: Teacher attempts to list
- **WHEN** a teacher calls `GET /conversations`
- **THEN** the endpoint returns 403

#### Scenario: Student sees only own conversations
- **WHEN** two students each have conversations
- **THEN** each student sees only their own conversations

### Requirement: Read messages of a conversation with sources

`GET /conversations/{conversation_id}/messages` SHALL return the messages of a conversation belonging to the authenticated student, ordered by `created_at` ascending. Each message SHALL include its `sources` array (empty for user messages). A conversation belonging to another student or non-existent SHALL return 404.

#### Scenario: Student reads own conversation
- **WHEN** a student requests messages of their own conversation
- **THEN** the response is an array of messages with `id`, `role`, `content`, `created_at`, and `sources`

#### Scenario: Assistant message includes sources
- **WHEN** an assistant message has persisted sources
- **THEN** the `sources` array contains entries with `chunk_id`, `document_id`, `filename`, `page_number`, `rank`, and `snippet`

#### Scenario: Another student's conversation
- **WHEN** a student requests messages of another student's conversation
- **THEN** the endpoint returns 404

#### Scenario: Non-existent conversation
- **WHEN** a student requests messages of a conversation that does not exist
- **THEN** the endpoint returns 404

### Requirement: Delete a single conversation permanently

`DELETE /conversations/{conversation_id}` SHALL permanently delete the conversation, its messages, and their message_sources for the authenticated student. A conversation belonging to another student or non-existent SHALL return 404. The deletion SHALL be committed before the 204 response.

#### Scenario: Student deletes own conversation
- **WHEN** a student deletes their own conversation
- **THEN** the conversation, its messages, and message_sources are removed and the endpoint returns 204

#### Scenario: Another student's conversation
- **WHEN** a student attempts to delete another student's conversation
- **THEN** the endpoint returns 404

#### Scenario: Deletion is durable
- **WHEN** a student deletes a conversation and then lists conversations
- **THEN** the deleted conversation does not appear

### Requirement: Delete all conversations for the authenticated student

`DELETE /users/me/conversations` SHALL permanently delete all conversations, messages, and message_sources belonging to the authenticated student. Only students SHALL access this endpoint. The response is 204 even when the student has no conversations.

#### Scenario: Student deletes all conversations
- **WHEN** a student with conversations calls `DELETE /users/me/conversations`
- **THEN** all their conversations, messages, and message_sources are removed and the endpoint returns 204

#### Scenario: Student with no conversations
- **WHEN** a student with no conversations calls the endpoint
- **THEN** the endpoint returns 204

#### Scenario: Teacher attempts bulk delete
- **WHEN** a teacher calls `DELETE /users/me/conversations`
- **THEN** the endpoint returns 403

#### Scenario: Other students unaffected
- **WHEN** a student deletes all their conversations
- **THEN** conversations of other students remain intact

### Requirement: Conversation data is isolated per student

A student SHALL only access (list, read, delete) conversations they created. No endpoint SHALL expose another student's conversation data. Authorization failures on conversation access SHALL return 404, not 403, to avoid revealing existence.

#### Scenario: Cross-student read attempt
- **WHEN** student A tries to read student B's conversation messages
- **THEN** the endpoint returns 404

#### Scenario: Cross-student delete attempt
- **WHEN** student A tries to delete student B's conversation
- **THEN** the endpoint returns 404

#### Scenario: Filtered list isolation
- **WHEN** student A lists conversations for a subject where student B also has conversations
- **THEN** student A sees only their own conversations

### Requirement: Conversations of a subject the student is no longer enrolled in are not visible

A conversation SHALL be visible to its owner only while the student is enrolled in its subject. Unenrolment SHALL NOT delete data, and the right to erasure SHALL be unaffected.

#### Scenario: Unenrolled student lists conversations
- **WHEN** a student who was unenrolled from a subject lists conversations
- **THEN** the conversations of that subject are not in the response

#### Scenario: Unenrolled student reads messages
- **WHEN** a student who was unenrolled from a subject requests the messages of one of its conversations
- **THEN** the endpoint returns 404 and exposes no message, source, document id or snippet

#### Scenario: Unenrolled student continues the conversation
- **WHEN** a student who was unenrolled from a subject sends `POST /chat` with that conversation's `conversation_id`
- **THEN** the endpoint returns 403

#### Scenario: Unenrolled student can still erase
- **WHEN** a student who was unenrolled from a subject deletes that conversation, or all their conversations
- **THEN** the endpoint returns 204 and the data is removed

#### Scenario: Re-enrolment restores visibility
- **WHEN** the student is enrolled again in the subject
- **THEN** the earlier conversations are visible again

### Requirement: Conversation tables follow the least-privilege model

The three new tables (`conversations`, `messages`, `message_sources`) SHALL be created by the migrator role, closed by default to all runtime roles, and granted exactly the privileges of the privilege matrix (`app/db_privileges.py`, `docs/data-model.md`, verified by `db-verify`). No role SHALL be granted UPDATE.

#### Scenario: App role can read and insert
- **WHEN** the API process (asistente_app) operates on conversation tables
- **THEN** SELECT and INSERT (only the columns the code sets) succeed on all three tables and DELETE succeeds on `conversations` only

#### Scenario: Deleting a conversation removes its messages and sources
- **WHEN** the API process deletes a conversation
- **THEN** its messages and message_sources are removed by `ON DELETE CASCADE` without a DELETE grant on them, and `message_sources.chunk_id` is set to NULL when a chunk is deleted

#### Scenario: App role cannot update or delete children directly
- **WHEN** the API process attempts an UPDATE on a conversation table, or a DELETE on `messages` or `message_sources`
- **THEN** the database denies it

#### Scenario: Worker role has no access
- **WHEN** the worker process (asistente_worker) attempts any operation on conversation tables
- **THEN** the database denies it

#### Scenario: CLI role can read and delete conversations
- **WHEN** the CLI process (asistente_cli) reads `conversations` or `messages`, or deletes from `conversations`
- **THEN** SELECT and DELETE succeed (the CLI has no DELETE on `messages`)

#### Scenario: CLI role cannot insert or read sources
- **WHEN** the CLI process attempts an INSERT on a conversation table, or any access to `message_sources`
- **THEN** the database denies it
