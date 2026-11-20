# Design

## Context

See `proposal.md` (Why). State verified in the repository on `main` (`12bc127`):

- Backend, unchanged by this change: `POST /subjects` (201, 409 duplicate name per teacher, 422), `GET /subjects/{id}`, `GET` and `POST /subjects/{id}/documents` (202 with `status: pending`; 408, 409 `DOCUMENT_QUOTA_EXCEEDED`, 413, 415, 422 with `details.reason`, 429 with `Retry-After`, 503 `INGESTION_QUEUE_FULL`), `DELETE /subjects/{id}/documents/{document_id}` (204, valid in any status), and the `Document` schema with `status`, the closed list of 12 `error_code` values and `chunks_count`. Another teacher's subject answers 404; a student 403. Defaults: `MAX_UPLOAD_MB=10`, `MAX_DOCUMENTS_PER_SUBJECT=50`.
- Frontend: `SubjectsPage` is a read-only list (spec `frontend-app-shell`); `subjectService.list`, `useSubjects(userId)` and generated types for `Subject`, `SubjectCreate` and `Document` exist (`types/api.generated.ts`; `types/api.ts` has no `Document` alias yet); `RequireRole` and `RequireConsent` already wrap the routes (teachers are not held); `ApiError` keeps only `status`, `code` and `retryAfterSeconds` and never the server message or details; copy lives in `lib/strings.es.ts`; forms use React Hook Form with Zod schemas in `lib/schemas.ts`; the shared `Button`, `FormField`, `Alert`, `LoadingState`, `EmptyState` and `ErrorState` exist; React Query does not retry 4xx and retries network errors and 5xx once. `@headlessui/react` is named in the standards but is **not installed**.
- Standards: `docs/frontend-standards.md` (hooks call services, query keys include the user id, deletions need a confirmation that says it is irreversible, forms mirror API limits, a11y, 320 px), `docs/openspec-tasks-mandatory-steps.md`.

## Goals / Non-Goals

**Goals:** a teacher can, from the web interface, create a subject, upload a document, see when it is `ready` or why it `failed`, and delete it, with every documented API failure explained in Spanish.

**Non-Goals:** enrollment, subject edit or delete, the chat, preview or download of documents, bulk or drag-and-drop upload, a progress bar, document search, any backend or contract change, and any change to `privacy-consent-ui` (decisions and TD-003, TD-063, TD-064 stay as they are).

## Decisions

### D1. Routes: a teacher-only subject page
`/subjects/:subjectId` is added inside the existing `RequireAuth` > `RequireConsent` > `AppShell` tree, wrapped in `RequireRole roles={['teacher']}` and loaded lazily. A student gets the existing forbidden screen without any request. Teacher cards on `/subjects` link to it; student cards stay unchanged (no detail page until `student-chat-ui`). *Alternative:* management inside the list (rejected: a list with upload rows for many subjects is hard to make accessible and to test, and the standards already name a `TeacherSubjectPage`).

### D2. Layers
New `services/documentService.ts` (`list`, `upload`, `remove`) and additions to `subjectService` (`create`, `get`); hooks `useSubject`, `useCreateSubject`, `useDocuments`, `useUploadDocument`, `useDeleteDocument`; page `TeacherSubjectPage`; small components for the create form, the upload form and the document row. Query keys include the user id and the subject id (`['subjects', userId]`, `['subject', userId, id]`, `['documents', userId, id]`). Creating a subject invalidates the list; uploading and deleting update or invalidate the documents key. `types/api.ts` gets the `Document`, `SubjectCreate` and `DocumentStatus` aliases from the generated file (no hand-written payload types).

### D3. Create form on the subject list
An inline form above the teacher's list (React Hook Form + Zod in `lib/schemas.ts`): name trimmed 1 to 150, description up to 2000, optional; control characters are left to the API (a 422 shows the generic validation message) so the client is never stricter. A blank description is not sent. *Alternative:* a separate route or modal (rejected: more navigation and a dialog dependency for one short form).

### D4. Upload: the API decides
A native file input (`accept=".pdf,.txt,.md"` as a hint only) and a submit button; the file goes as `FormData` with the single field `file` through the existing Axios client, without setting `Content-Type` by hand so the boundary is correct. The client checks only that a file was chosen. It does not check size or type: `MAX_UPLOAD_MB` is configurable and the type is decided from the content (415), so a client rule would be wrong in one direction or the other. The `accept` attribute is only a hint for the file chooser (the user can still choose any file). Trade-off: a file over the limit is sent until the server answers 413 (the server answers as soon as the limit is exceeded). Uploads use a 120-second time limit instead of the 15 seconds of ordinary requests, and a timeout tells the teacher to check the list before trying again, because the file may have arrived. The input and the button are disabled while the request is pending.

### D5. Reading the reason of a 422
The upload 422 carries `details.reason` from a closed list. `ApiError` today keeps no details by design (they can echo user input). The change adds one optional field, `reason`, that `toApiError` fills **only** when the value is one of the five documented strings; anything else is dropped. Text is then chosen by our own table, so no server text is shown or stored. *Alternative:* one message for every 422 (rejected: `EMPTY_FILE` and `UNEXPECTED_FIELDS` need different advice). This touches `lib/apiError.ts` and its tests.

### D6. Status follow-up by polling
`useDocuments` uses React Query `refetchInterval` as a function: 3 seconds while any document is `pending` or `processing`, `false` otherwise; background tabs do not poll (`refetchIntervalInBackground` stays off) and the query is torn down when the page unmounts. A failed poll keeps the last data on screen with a notice and the next interval retries; a 401 follows the existing session-end path. A manual refresh button is always visible. Status is shown as a text label (plus an icon or tone that is not the only signal), and a polite live region announces transitions to `ready` or `failed`. `failed` rows show a Spanish sentence chosen by `error_code` from a table of the 12 codes plus a generic one; `error_message` is never shown. *Alternatives:* server-sent events or websockets (rejected: new backend capability); exponential backoff (rejected for the MVP: one teacher, one tab, 3 s is cheap and the list endpoint has no rate limit).

### D7. Confirmation of deletion without a new dependency
The confirmation is an inline panel in the row ("Eliminar «name»? No se puede deshacer. Se borran también sus fragmentos." with Confirm and Cancel; focus moves to the panel and returns to the row on cancel). **Architecture-affecting choice for approval:** the standards list Headless UI but it is not installed, and adding it for one confirmation is a dependency and bundle decision. *Alternatives:* add `@headlessui/react` and a modal dialog (more standard, one more dependency); the native `<dialog>` element (rejected: jsdom does not implement it, so the component tests would need a polyfill).

### D8. Error messages
New Spanish entries in `errors.byCode` for `PAYLOAD_TOO_LARGE`, `UNSUPPORTED_MEDIA_TYPE`, `DOCUMENT_QUOTA_EXCEEDED`, `INGESTION_QUEUE_FULL` and `REQUEST_TIMEOUT`, a table for the five 422 reasons, and the existing 429 handling with the wait in seconds. `409` on subject creation uses the existing conflict message unless the form shows a more specific "name already used" text. All in `strings.es.ts`; `tests/copy.test.ts` keeps forbidding inline text.

### D9. Notice about the material
The upload area states the accepted formats and, in one proportionate sentence, that this version is an MVP for tests: only fictitious documents must be uploaded, without personal data or confidential content (owner decision). Copy: "Formatos admitidos: PDF, texto (.txt) y Markdown (.md). Esta versión es un MVP de pruebas: suba únicamente documentos ficticios, sin datos personales ni contenido confidencial." It claims nothing about legal status and is removed or reworded by the change that prepares the pilot.

### D10. Security and privacy of the screens
File names and subject texts are rendered as React text (never as HTML) and wrap; no file content is read in the browser; diagnostics log method, path without query and status only (the file name is never logged); the UI hides teacher screens from students but the backend stays the authority; no token, file name or server message in the URL or in storage. No new personal data is collected.

## Dependencies

- `privacy-consent-ui` is merged (`12bc127`); nothing in this change alters its decisions or its open tasks, TD-003, TD-063 or TD-064.
- Backend endpoints exist and are unchanged. For the real-backend verification the existing stack is used as it is (the stack is not rebuilt or recreated by this change): the `worker` already ingests documents to `ready`; the frontend container serves the source in development mode.
- No new npm package (see D7 for the alternative that would add one).
- `student-chat-ui` depends on this change only for convenience (material uploaded from the interface); it needs an enrolled student (see Open decisions).

## Risks / Trade-offs

- **A document stays `pending` forever if the worker is down.** The UI keeps polling every 3 s while the tab is visible. Mitigation: the manual refresh control, and the text of `pending` says processing can take a while; a hint after several minutes is a possible addition (Open decision 5).
- **The 202 is a promise, the list is eventually consistent.** The row shows `pending` from the upload response; a refresh that races with it must not drop the row (the upload updates the cache and the poll reconciles).
- **Large files** are sent in full before a 413 when the file is just over the limit; accepted (D4).
- **Rate limits** (upload 429) are shown with the wait; the interface does not retry on its own.
- **Name collisions** (409) are per teacher and case-sensitive; the form keeps the values.
- **Filename tricks** (direction characters, long names, markup): the API cleans them and the UI renders text only and wraps it.
- **Testing the real flow** needs the worker and the local embedder, which the mocked suites cannot prove; covered by the gated real-backend spec and the agent's manual run.
- **Scope pressure:** enrollment, subject deletion and a progress bar are the usual requests; they are listed as non-goals so this change stays proportional.

## Decisions taken by the owner (previously open)

1. **Enrollment of students:** out of this change; a later change `teacher-enrollment-ui` covers it. Until then enrol through the API documentation (`POST /subjects/{id}/enrollments`).
2. **Document deletion with confirmation:** in scope (a failed or wrong file would otherwise block its quota).
3. **Subject edit and delete:** not in this change (deleting a subject also erases the students' conversations, a personal-data action that deserves its own confirmation design).
4. **Confirmation component (D7):** inline panel, no new dependency.
5. **Hint when a document is pending for a long time:** deferred; the manual refresh is enough for the MVP.
6. **Material notice (D9):** a proportionate warning that the MVP accepts only fictitious documents.
