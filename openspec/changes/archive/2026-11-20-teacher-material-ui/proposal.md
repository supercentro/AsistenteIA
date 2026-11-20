# Proposal

## Why

The backend already lets a teacher create subjects, upload material and follow its processing (`subjects-and-enrollments`, `document-ingestion`), but the interface only lists subjects: a teacher cannot create one, upload a file or see whether it was processed, so the first half of the main flow (teacher uploads, student asks) can only be exercised through the API documentation. This change adds that half to the web interface. It is change 7 of the approved plan and the next milestone after `privacy-consent-ui`; the chat screen (`student-chat-ui`) follows as a separate change.

## What Changes

- A **create-subject form** on the teacher's subject list (name and optional description, the limits of `POST /subjects`).
- A **teacher subject page** (`/subjects/{subject_id}`, teachers only) that shows the subject and its documents with name, type, size, chunk count and **processing status** (`pending`, `processing`, `ready`, `failed`).
- **Document upload** on that page (one `.pdf`, `.txt` or `.md` file at a time, `POST /subjects/{id}/documents`) with a Spanish message for every documented failure (type, size, quota, rate limit, full queue, timeout).
- **Status follow-up**: the list refreshes by itself while a document is `pending` or `processing` and stops when all are final; a `failed` document shows a Spanish explanation chosen by its `error_code`; a manual refresh control is always available.
- **Document deletion** with an explicit confirmation that states it is irreversible (`DELETE /subjects/{id}/documents/{document_id}`), so a failed or wrong file can be removed and the per-subject quota recovered.
- The subject list of a teacher links each subject to its page. Students are unchanged (still read-only, no detail page).
- Documentation: `docs/frontend-standards.md` (pages, structure), `docs/development_guide.md` (the local test circuit now has screens for steps 2 and 3).

**Out of scope (not added):** enrolling or removing students (see Open decisions), editing or deleting a subject, the chat screen, document preview or download (the original file is not kept), several files at once, drag and drop, an upload progress bar, search or sorting of documents, any backend, contract or migration change.

## Capabilities

### New Capabilities
- `frontend-teacher-materials`: subject creation, the teacher subject page, document upload, processing status follow-up and document deletion for teachers.

### Modified Capabilities
- `frontend-app-shell`: the requirement "Read-only subject list" changes for teachers only (a create form and a link to each subject page appear); the student list stays read-only.

## Impact

- **Authorization / isolation:** none changed; the backend stays the authority (owner teacher only; another teacher's subject answers 404, a student 403). The UI hides teacher screens from students (`RequireRole`) and shows the API's refusal when it happens. No new data of other users is fetched.
- **Personal data (Ley 25.326):** no new personal data is collected. Teacher material is processed locally and its fragments are sent to Gemini when a student asks; in the MVP only fictitious material is used. A short notice in the upload area states that this MVP is for tests and that only fictitious documents must be uploaded, without personal data or confidential content (approved by the owner). `privacy-consent-ui` decisions and TD-003, TD-063 and TD-064 are not touched; teachers are still not asked for the chat consent.
- **External services:** none called from the interface; the worker's embedder is local (no Gemini call is added).
- **Contracts:** `docs/api-spec.yml` and `docs/data-model.md` do not change (every endpoint and field used already exists: `Subject`, `Document`, `error_code`). `src/types/api.generated.ts` is expected to need no regeneration; `npm run check:api-types` confirms it.
- **Code:** frontend only (services, hooks, one page, small components, copy module, tests). No new runtime dependency (the confirmation is an inline panel, see design D7). No backend, infrastructure or secret change.

### Decisions approved by the owner (see design, Decisions taken)
1. Enrollment of students stays out of this change.
2. Deleting a document is in scope; deleting or editing a subject is not.
3. No client-side file type or size check beyond "a file was chosen": the API decides.
4. The upload notice says the MVP accepts only fictitious documents (approved by the owner).
