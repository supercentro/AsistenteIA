# document-management Specification

## Purpose
Defines how a teacher uploads, lists and deletes the course material of a subject over HTTP, including validation, limits, ownership rules and the error contract, so that the material can be processed safely in the background.

## Requirements

### Requirement: Only the owning teacher manages the documents of a subject
`POST`, `GET` and `DELETE` on `/subjects/{subject_id}/documents` SHALL require an authenticated teacher who owns the subject. The same `404` MUST answer "does not exist" and "not yours".

#### Scenario: Owning teacher
- **WHEN** the teacher who owns the subject uploads, lists or deletes a document
- **THEN** the operation is performed on that subject only

#### Scenario: Student
- **WHEN** a student calls any of the three endpoints
- **THEN** the response is `403` and nothing is read or written

#### Scenario: Another teacher or unknown subject
- **WHEN** a teacher who does not own the subject, or any teacher with an unknown subject id, calls any of the three endpoints
- **THEN** the response is `404`, identical for both cases, and nothing is read or written

#### Scenario: Another subject's document
- **WHEN** the owner of subject A deletes a document id that belongs to subject B
- **THEN** the response is `404` and the document of B is untouched

#### Scenario: No credentials
- **WHEN** a request without a valid token calls any of the three endpoints
- **THEN** the response is `401`

### Requirement: An accepted upload is durable before the response
`POST` SHALL answer `202` with a `Document` in status `pending` only after the document row, its processing job and the uploaded bytes are committed together. If that commit fails, the response MUST be an error and no partial rows may remain.

#### Scenario: Accepted upload
- **WHEN** a valid file is uploaded
- **THEN** the response is `202` with status `pending`, and a restart of every process before processing starts does not lose the document

#### Scenario: Storage failure
- **WHEN** the database fails while the upload is being stored
- **THEN** the response is `503` with a fixed message, and neither a document nor a job nor bytes remain

#### Scenario: Not reported as accepted too early
- **WHEN** the commit of the upload has not completed
- **THEN** no `202` has been sent for it

#### Scenario: Reception interrupted
- **WHEN** the client closes the connection before the body is complete
- **THEN** no document, job, bytes or temporary file remain, and no log line contains the file name or content

### Requirement: Exactly one non-empty file is accepted
The multipart request SHALL contain exactly one part named `file` with at least one byte. Anything else MUST be rejected with `422` before the file is processed.

Each rejection SHALL be a controlled `422` whose `details.reason` is a fixed value (`MALFORMED_MULTIPART`, `FILE_PART_MISSING`, `UNEXPECTED_FIELDS`, `EMPTY_FILE` or `INVALID_FILENAME`), never the parser's default `400` and never parser text.

#### Scenario: Missing part
- **WHEN** the request has no `file` part
- **THEN** the response is `422` with reason `FILE_PART_MISSING`

#### Scenario: Several files
- **WHEN** the request carries two or more file parts
- **THEN** the response is `422` with reason `UNEXPECTED_FIELDS` and nothing is stored

#### Scenario: Unexpected form fields
- **WHEN** the request carries fields other than `file`
- **THEN** the response is `422` with reason `UNEXPECTED_FIELDS` and nothing is stored

#### Scenario: Malformed multipart
- **WHEN** the multipart structure is invalid or exceeds the limits of parts, fields or headers
- **THEN** the response is `422` with reason `MALFORMED_MULTIPART` and nothing is stored

#### Scenario: Empty file
- **WHEN** the file has zero bytes
- **THEN** the response is `422` with reason `EMPTY_FILE`

### Requirement: The filename is cleaned before it is stored
The stored filename SHALL be the last path component of the client name, without control, line-separator or bidirectional characters, at most 255 characters, and never used as a filesystem path. A name that is empty after cleaning MUST be rejected with `422`.

#### Scenario: Path components
- **WHEN** the client name is `..\..\notes/unit1.pdf`
- **THEN** the stored name is `unit1.pdf`

#### Scenario: Hostile characters
- **WHEN** the name contains control, newline or right-to-left override characters
- **THEN** they are removed or the upload is rejected with `422`, and no such character is stored or returned

#### Scenario: Too long
- **WHEN** the cleaned name exceeds 255 characters
- **THEN** the response is `422` with reason `INVALID_FILENAME`

### Requirement: The file type is decided from the content
The upload SHALL be accepted only when the extension is `.pdf`, `.txt` or `.md` and the content agrees with it: a PDF signature for `.pdf`, and valid UTF-8 without NUL bytes for `.txt` and `.md`. The client `Content-Type` MUST be ignored. Otherwise the response is `415`.

#### Scenario: Valid PDF
- **WHEN** a file named `unit1.pdf` starts with the PDF signature
- **THEN** it is accepted and stored with content type `application/pdf`

#### Scenario: Renamed executable
- **WHEN** an executable is uploaded as `unit1.pdf` or `notes.txt`
- **THEN** the response is `415`

#### Scenario: Unsupported extension
- **WHEN** the extension is `.exe`, `.docx` or none
- **THEN** the response is `415`

#### Scenario: Misleading client type
- **WHEN** the client declares `application/pdf` for a text file named `notes.txt`
- **THEN** the stored content type is `text/plain`

#### Scenario: Invalid UTF-8
- **WHEN** a `.txt` or `.md` file contains bytes that are not valid UTF-8, or a NUL byte
- **THEN** the response is `415`

### Requirement: The size limit is enforced while the body is read
Uploads larger than `MAX_UPLOAD_MB` (10 MB by default) SHALL be rejected with `413` (a different answer from a malformed request or a missing file) as soon as the bytes actually received exceed the limit, whatever `Content-Length` says or whether it is present, without reading or keeping the rest of the body. The stored size is the number of bytes received.

#### Scenario: Declared size too large
- **WHEN** `Content-Length` already exceeds the limit
- **THEN** the response is `413` before the body is read

#### Scenario: Undeclared size too large
- **WHEN** the body is sent in chunks without a `Content-Length` and passes the limit
- **THEN** the response is `413`, the rest of the body is not stored, and no document, job or temporary file remains

#### Scenario: Declared small, sent large
- **WHEN** `Content-Length` declares a small body but the client sends more than the limit
- **THEN** the response is `413` and nothing is stored

#### Scenario: Declared large, sent small
- **WHEN** `Content-Length` declares more than the limit but the client sends a valid small file
- **THEN** the declared value alone decides nothing beyond the early check, and the stored size equals the bytes received

#### Scenario: Exactly at the limit
- **WHEN** the file size equals the limit
- **THEN** the upload is accepted

### Requirement: The number of documents per subject is capped under concurrency
A subject SHALL hold at most `MAX_DOCUMENTS_PER_SUBJECT` (50 by default) documents of any status. The count and the insert MUST be serialised per subject so that simultaneous uploads cannot exceed the cap. Beyond it the response is `409` with code `DOCUMENT_QUOTA_EXCEEDED`.

#### Scenario: At the cap
- **WHEN** the subject already holds 50 documents and another is uploaded
- **THEN** the response is `409` with code `DOCUMENT_QUOTA_EXCEEDED` and nothing is stored

#### Scenario: Simultaneous uploads
- **WHEN** many uploads to a subject with 49 documents arrive at once
- **THEN** exactly one is accepted and the subject never holds more than 50 documents

#### Scenario: Space freed by deletion
- **WHEN** a document is deleted from a full subject
- **THEN** a new upload is accepted

### Requirement: Saturation and abuse are answered with explicit errors
Uploads SHALL be rate limited per client address (`429` with `Retry-After`), and SHALL be refused with `503`, code `INGESTION_QUEUE_FULL` and `Retry-After` when the unfinished jobs reach `INGESTION_QUEUE_MAX` or their total size would exceed `INGESTION_PENDING_BYTES_MAX_MB`. These limits are hard under concurrency. A refused upload stores nothing.

#### Scenario: Rate limit
- **WHEN** a client exceeds the upload rate limit
- **THEN** the response is `429` with `Retry-After` and nothing is stored

#### Scenario: Queue full
- **WHEN** the unfinished jobs reach the configured maximum
- **THEN** the response is `503` with code `INGESTION_QUEUE_FULL` and `Retry-After`, and nothing is stored

#### Scenario: Pending bytes full
- **WHEN** accepting the file would take the pending bytes over the configured maximum
- **THEN** the response is `503` with code `INGESTION_QUEUE_FULL` and `Retry-After`, and nothing is stored

#### Scenario: Limits under concurrency
- **WHEN** many simultaneous uploads from different subjects compete for the last free queue slot or the last free bytes
- **THEN** the number of unfinished jobs and their total size never exceed the limits

### Requirement: A stalled upload is abandoned without side effects
The service SHALL stop reading an upload body not completed within `UPLOAD_BODY_TIMEOUT_SECONDS` (120 by default) or that makes no progress for `UPLOAD_BODY_IDLE_SECONDS` (20 by default), both configurable, store nothing and release its resources, and SHALL refuse with the same `503` as a full queue when more than `UPLOAD_MAX_IN_FLIGHT` uploads are being received. A slow client MUST NOT hold a database connection while its body is read.

#### Scenario: Slow client that stays connected
- **WHEN** a client keeps the connection open but sends the body too slowly to finish in time
- **THEN** the body is abandoned, nothing is stored, the temporary data is released and the client receives `408` with code `REQUEST_TIMEOUT`, whether it stays idle or sends the body too slowly

#### Scenario: Idle client
- **WHEN** a connected client sends no byte for longer than the idle limit
- **THEN** it receives `408` after about that limit, even if the total deadline has not been reached

#### Scenario: Client that disconnects
- **WHEN** the client closes the connection while the body is being sent
- **THEN** no response is promised or attempted beyond what the transport allows, nothing is stored or left behind, and no error trace is logged for the disconnect

#### Scenario: Too many uploads at once
- **WHEN** more uploads than the in-flight limit arrive at the same time
- **THEN** the extra ones receive `503` with code `INGESTION_QUEUE_FULL` and `Retry-After`

#### Scenario: Other requests during slow uploads
- **WHEN** several slow uploads are in progress
- **THEN** other endpoints such as login and listing still answer normally

### Requirement: Listing returns the processing state without content
`GET` SHALL return the documents of the subject, newest first, each with id, filename, content type, size, status, `error_code`, `error_message`, chunk count and creation time, and never chunk text, embeddings or file bytes. The list is bounded by the per-subject cap.

#### Scenario: Polling a processing document
- **WHEN** the owner lists the documents while one is being processed
- **THEN** that document shows `pending` or `processing` with no `error_code`

#### Scenario: Finished documents
- **WHEN** a document is `ready`
- **THEN** it shows its chunk count; and a `failed` one shows a stable `error_code` with a fixed safe message

#### Scenario: Empty subject
- **WHEN** a subject has no documents
- **THEN** the response is `200` with an empty list

### Requirement: Deleting a document removes everything derived from it
`DELETE` SHALL remove the document, its chunks, its job and any temporary bytes, and answer `204`, including while the document is being processed. Processing in progress MUST then end without leaving rows or bytes.

#### Scenario: Ready document
- **WHEN** the owner deletes a `ready` document
- **THEN** its chunks are gone and it can no longer be found by similarity search

#### Scenario: Document being processed
- **WHEN** the owner deletes a document that a worker is processing
- **THEN** the response is `204`, and the worker ends without creating chunks or changing any other row

#### Scenario: Unknown document
- **WHEN** the document id does not exist in the subject
- **THEN** the response is `404`

### Requirement: Errors and logs never expose files or internals
Error responses and logs of these endpoints SHALL contain only fixed messages, stable codes and identifiers. They MUST NOT contain file names, file content, extracted text, parser or database error text, filesystem paths or stack traces.

#### Scenario: Hostile input
- **WHEN** a request carries a recognisable marker in the filename, the content and the PDF metadata and fails in any way
- **THEN** the marker appears in no response body and in no captured log

#### Scenario: Unexpected failure
- **WHEN** an unexpected exception occurs while handling an upload
- **THEN** the response is the generic error and the log records only the exception type, the method and the path

### Requirement: The contract change is additive and published
`docs/api-spec.yml` SHALL describe the new responses (`401`, `408` for clients that stay connected, `409`, `422` with its fixed reasons, `429`, `503`), the `error_code` field and the `required` fields of `Document`, without removing or renaming anything, and the generated frontend types SHALL be regenerated. The `408` behaviour was verified against a real server and MUST be covered by a real-server test.

#### Scenario: Contract check
- **WHEN** the type generation check runs against the updated contract
- **THEN** it reports that the generated types are up to date

#### Scenario: Existing clients
- **WHEN** a client written for the previous contract calls the endpoints
- **THEN** it keeps working, because only new optional fields and new error responses were added
