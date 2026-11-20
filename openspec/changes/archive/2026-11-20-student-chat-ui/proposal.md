# Proposal

## Why

The product exists to let a student ask questions about the material of a subject and get answers with verifiable sources. The backend already does it (`chat-rag-endpoint`: `POST /chat`, conversations, history, deletion), a teacher can now create subjects, upload material and enroll students from the interface (`teacher-material-ui`, `teacher-enrollment-ui`), and the consent gate holds a student until the privacy draft is accepted (`privacy-consent-ui`). The student, however, still sees only a read-only list of subjects: the main flow (teacher prepares, student asks) cannot be tried from the browser. This change adds the student's chat screen and closes the interface side of the MVP circuit.

## What Changes

- A **chat page per subject** for students (`/subjects/{subject_id}/chat`), reached from a link on each card of the student's subject list.
- **Asking and answering**: a text box (1 to 2000 characters, as the API) and a send action; the question appears at once, a polite "the assistant is answering" status is shown, and the answer is rendered as **plain text**. A "no material" answer is shown like any other assistant message.
- **Sources**: each answer lists the fragments the backend associates with it (file name, page when the format has pages, and the snippet in an expandable detail), labelled as material consulted, **without any claim that they prove each statement** (TD-062).
- **Conversations of the subject**: the list of the student's conversations in that subject (newest first, labelled by the preview when the API gives one and by the date otherwise: today it never does, TD-066), opening one to read its messages and continue it, and starting a new one.
- **Deleting a conversation** with the shared inline confirmation (`ConfirmPanel`) that says it is permanent; and **deleting the whole history** (`DELETE /users/me/conversations`) from the student's subject list, with a confirmation that says it covers every subject, including those the student no longer sees, and cannot be undone.
- **Handling of limits and failures** in Spanish: client time limit longer than the model's, rate limit with the wait, provider unavailable (retry) or blocked (rephrase), lost access (not enrolled any more, subject or conversation gone), consent changed (the existing gate).
- A short **notice** next to the box: this is a test version, questions and fragments go to Gemini (Google), use fictitious data only; with a link to the privacy draft.
- Documentation: `docs/frontend-standards.md`, `docs/development_guide.md` (the local circuit is complete in the interface).

**Out of scope (not added):** Markdown or any rich rendering (plain text only, no dependency), streaming, regenerating or editing a question, feedback buttons, copy or export, search in the history, renaming conversations, a global conversation list across subjects, a teacher view of conversations, attachments, and any backend, contract or migration change.

## Capabilities

### New Capabilities
- `frontend-student-chat`: the student's chat page per subject, answers with sources, conversation list and history, deletion of one conversation and of the whole history, and the handling of limits and lost access.

### Modified Capabilities
- `frontend-app-shell`: the requirement "Read-only subject list" changes for students only (each card links to its chat); the teacher part stays as `teacher-material-ui` defines it. See Impact for the archive order this implies.

## Impact

- **Authorization / isolation:** none changed; the backend stays the authority (role student, enrolled, current consent; a conversation of another student or of a subject the student left answers 404). The chat route is student-only (`RequireRole`), so a teacher never reaches it or triggers a request; query keys carry the user id and the subject or conversation id; the cache is cleared at the end of the session.
- **Personal data (Ley 25.326):** the student's questions and the retrieved fragments are sent to Gemini (Google) by the backend; the interface adds a notice and a link to the draft policy and sends nothing else. Conversations and sources are shown only to their owner. The delete-all action is the right of erasure over conversations; it does not delete the account (TD-064). The policy is still a draft and the chat is **not enabled for real students**: fictitious users and documents only (TD-003, TD-063, TD-064).
- **External services:** none called from the interface; the backend calls Gemini (free tier in the MVP, fictitious data only). Gemini is never called in CI; the gated real-backend run uses it once or twice by hand, with fictitious material.
- **Contracts:** `docs/api-spec.yml` and `docs/data-model.md` do not change (`ChatResponse`, `Source`, `Conversation`, `Message` exist). `src/types/api.generated.ts` already holds them; `npm run check:api-types` confirms it.
- **Code:** frontend only (services, hooks, a chat page, small components, copy module, tests). No new runtime dependency. No backend, infrastructure or secret change.
- **Archive order:** `frontend-app-shell` "Read-only subject list" is also modified by the still-active `teacher-material-ui`. This change's delta is written on top of that one, so `teacher-material-ui` must be archived before this change.

### Decisions to confirm (see design, Open decisions)
1. Route `/subjects/{id}/chat`, reached from the student's subject cards.
2. "Delete all my history" on the student's subject list, not inside the chat page.
3. Send with the button only (Enter inserts a line break).
4. A 60-second client limit for a question, and a refresh of the conversation after a timeout before another question.
5. Sources shown as "Material consultado" with an expandable snippet and a neutral note.
6. The test-version notice with the link to the privacy draft.
