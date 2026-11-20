# Design

## Context

See `proposal.md` (Why). State verified in the repository on `main` (`88a56f3`):

- Backend, unchanged: `POST /chat` (`{subject_id, conversation_id?, message 1..2000}` answers `{conversation_id, message_id, answer, no_material, sources[]}`; 403 not enrolled or consent missing or lost during generation, 404 unknown subject or conversation, 422, 429 with `Retry-After` (per client address, shared by users of one connection), 502 `LLM_UNAVAILABLE` or `LLM_BLOCKED`, 503; **a failed question stores nothing**, so a retry never duplicates); `GET /conversations?subject_id=` (newest first, `last_message_preview`), `GET /conversations/{id}/messages` (oldest first, each with `sources`; 404 when it is not the student's or its subject is no longer visible), `DELETE /conversations/{id}`, `DELETE /users/me/conversations` (all, irreversible, also the hidden ones). `Source`: `filename`, `page_number` (nullable), `rank`, `snippet` (at most 300 characters), `chunk_id` and `document_id` nullable (a deleted document keeps its snapshot). A source is a chunk whose `[n]` marker the answer contains, or **every retrieved chunk** when the answer has no valid marker (TD-062). Retrieval uses only the current message, so a follow-up that does not repeat the topic can answer "no material". The model's limit is `CHAT_LLM_TIMEOUT_SECONDS` (default 30).
- Frontend (after `teacher-enrollment-ui`): routes under `RequireAuth` > `RequireConsent` > `AppShell`, `RequireRole` per area; `SubjectsPage` shows a read-only card list to students; shared `Button`, `FormField`, `TextAreaField`, `Alert`, `ConfirmPanel`, `EmptyState`, `ErrorState`, `LoadingState`; `ApiError` keeps status, code, `Retry-After` and the closed 422 reasons, never server text; `messageFor` chooses text by code then status; the 403 `CONSENT_REQUIRED` handler of `apiClient` already sends a student back to the consent gate; all requests have a 15 s client limit unless overridden (uploads use 120 s); hooks follow one pattern (key with user id; `cancelQueries` before `setQueryData`); pages that depend on a route parameter are keyed by it.
- Standards: `docs/frontend-standards.md` (chat rules: send disabled while pending, typing indicator, "no material" as a normal message, source chips as text, plain text or sanitised Markdown, `aria-live`, deletion confirmations) and `docs/openspec-tasks-mandatory-steps.md`.

## Goals / Non-Goals

**Goals:** a student can ask, read, continue and delete their conversations of a subject from the browser, with every documented failure explained and no claim that sources guarantee anything.

**Non-Goals:** everything listed as out of scope in the proposal; any change of the privacy draft or of TD-003, TD-062, TD-063, TD-064, TD-065; enabling real students.

## Decisions

### D1. Routes
`/subjects/:subjectId/chat` is added under `RequireRole roles={['student']}`, lazy-loaded and keyed by `subjectId` (the state of a previous subject is dropped when the route changes). The student's cards link to it. No navigation item is added (the nav stays "Asignaturas"). *Alternative:* a global `/chat` with a subject selector (rejected: the API scopes every question to one subject and the history is listed per subject).

### D2. Layers and cache
`services/chatService.ts` (`ask`) and `services/conversationService.ts` (`list(subjectId)`, `messages(id)`, `remove(id)`, `removeAll()`); hooks `useConversations`, `useMessages`, `useAskQuestion`, `useDeleteConversation`, `useDeleteHistory`. Keys: `['conversations', userId, subjectId]` and `['messages', userId, conversationId]`. On a successful question the hook appends two messages to the cache (the question as typed, with a local id, and the answer with its `message_id` and sources) when the thread is known to be complete (a new conversation, or one already loaded), and then invalidates the conversation list and the messages: invalidating an active query cancels the request still on its way, so an older answer cannot undo the change (a separate `cancelQueries` was redundant and its mutation was not detectable). Deleting a conversation cancels, removes it from the list and drops its messages; deleting the history cancels and empties every `['conversations', userId, *]` list.

### D3. The thread and the box
A thread (`role="log"`, polite live region) of plain-text bubbles (`whitespace-pre-wrap`, wrapping, never HTML), and a `TextAreaField` with a counter near 2000. Zod: trimmed length 1 to 2000, the same as the API. **Send with the button only**; Enter inserts a line break (no accidental sends, no shortcut to document). While a question is pending the button and the box are disabled, the question is shown as sent, and a `role="status"` says that the assistant is answering. The box keeps the focus after sending. The selected conversation is local state (null means "new").

### D4. Plain text, no dependency
Answers and questions are rendered as text. If the model writes Markdown syntax it is shown as written; the `[n]` markers of the answer are left as they are. This avoids a Markdown parser and its sanitising surface (no new package); a rich rendering would be its own change.

### D5. Sources without guarantees
Each assistant message with sources shows a block "Material consultado": for each source the file name (text, wrapped, bidirectionally isolated), the page when it is not null, and a native `<details>` that shows the snippet as text. One neutral note under the block: "Fragmentos del material asociados a esta respuesta. Compruebe la información en el documento original." No wording says that a source proves, supports or confirms; the ranks are not shown. A source without `chunk_id` or `document_id` (document deleted) looks the same. This matches the contract's own description of `Source` and TD-062.

### D6. Time limit and the doubtful timeout
`chatService.ask` uses a 60-second client limit (the model's own default is 30 s and the retrieval takes a few more seconds; the ordinary 15 s would cut valid answers). A timeout does not tell whether the server saved the turn (the backend commits before answering), so the message says the answer may have been saved, the conversation and the list are requested again, and the student reviews them before asking again; the question stays in the box. Any other failure stores nothing (backend rule), so the question stays in the box and can be sent again as it is.

### D7. Messages by cause
New Spanish entries chosen by code: `LLM_UNAVAILABLE` ("El asistente no está disponible ahora. Inténtelo de nuevo."), `LLM_BLOCKED` ("No se pudo dar una respuesta a esa pregunta. Reformúlela."), and a chat 429 text that adds that the limit can be shared by users of one connection (`messageFor` already adds the wait). 403 and 404 on a question or on the data of the subject or conversation show the "not available to this account" view with a link back (the same neutral sentence for both, the API already treats them differently by design, TD-061); `CONSENT_REQUIRED` is left to the existing gate, which also means the draft in the box is lost (the screen unmounts): accepted for the MVP.

### D8. Deleting
One conversation: the shared `ConfirmPanel` in the list row ("¿Eliminar esta conversación? Se borran también sus mensajes. No se puede deshacer."), 404 treated as already gone with a notice, focus to the list heading afterwards. The whole history: a section on the student's subject list with `ConfirmPanel` whose body says it deletes every conversation of the account in every subject, including subjects the student no longer sees, that it cannot be undone and that the account stays. It lives on the list, not in the chat page, because it is not about the open subject. Both honest, irreversible wordings (unlike the enrollment removal).

### D9. Notice and privacy
A short notice beside the box: "Versión de prueba: las preguntas y los fragmentos del material se envían a Gemini (Google) para generar la respuesta. Use solo datos ficticios." with a link "Política de privacidad (borrador)" that opens in a new tab with `noopener` (a full page load would end the memory-only session). Nothing about legal status is claimed. The interface logs only method, path and status; question, answer, snippet and file names are never logged or stored outside the React Query cache (cleared at the end of the session).

### D10. Findings of the implementation (deviations from the first draft)
- **The API gives no conversation preview.** `last_message_preview` is declared in the contract and in `conversation-history`, but the backend never fills it (always `null`; checked against the running stack). The list would show the same label for every conversation, so a conversation without a preview is labelled by its date and time (`Conversación del 19/11/26, 7:26 p. m.`); with a preview, the preview is used. Recorded as TD-066; the contract and the backend are not changed here.
- **The generated types do not mark the fields of `Source`, `Conversation`, `Message` and `ChatResponse` as required**, although the API always sends them. `types/api.ts` states what the backend guarantees with `Required`, with a comment.
- `react-hook-form` `reset()` unregisters the fields, so the focus could not return to the box right after sending; `resetField('message')` keeps it registered.
- The student's subject link and the history action made the subject list page taller: the long-name wrapping rule of the card now also applies to the chat link.

### D11. Findings of the independent review (corrected)
- **Switching conversation while a question is pending** could attach the answer to the wrong thread. The conversation list, the new-conversation action and every confirm control are locked while a question is pending, so the open conversation cannot change until the answer arrives.
- **A 404 on a question that carried a conversation id** is the conversation, not the subject (a conversation deleted elsewhere): the page keeps the subject, refreshes the list, keeps the question and the next one starts a new conversation. A 404 or 403 on a question of a new conversation still means that the subject is not available.
- The timeout message now also points at the list of conversations (a new conversation that timed out may be there).
- The testing library's asynchronous wait limit is raised to 3 seconds in `tests/setup.ts`: one run of the coverage suite failed once under load; waiting is cheap and the change does not alter what a test proves.

### D12. Tests
Vitest + RTL + MSW as in the previous features (no Gemini, ever, in CI). The gated real-backend spec uses the existing stack with a fictitious document and a few real questions by hand, with the free-tier Gemini (fictitious data only, a handful of calls); the mocked Playwright suite covers the screens and every failure. Ordering tests use delayed answers, as before.

## Dependencies

- `privacy-consent-ui`, `teacher-material-ui` and `teacher-enrollment-ui` are merged. For the real-backend run a teacher, a ready document and an enrolled student exist (the existing test accounts and the gated specs of the previous features create them).
- Backend endpoints unchanged. No new npm package.
- **Archive order:** the delta of `frontend-app-shell` is written on top of `teacher-material-ui`'s; archive `teacher-material-ui` before this change.

## Risks / Trade-offs

- **Duplicate turn after a timeout:** the server may have saved it. Mitigation in D6; the cost is a longer limit and a refresh.
- **Shared rate budget:** 20 questions per minute per client address, shared by a classroom behind one address; the message says so. Nothing in the interface can prevent it.
- **Sources read as proof:** the main honesty risk (TD-062). Wording and note in D5; the label says "consulted", not "cited".
- **Elliptic follow-ups answer "no material":** a product limit of the backend; the interface does not hide it. A short hint under the box ("Mencione el tema en cada pregunta") is cheap; it is part of the notice copy (Open decision 6).
- **Hidden conversations after leaving a subject:** opening one answers 404; handled as not available. Delete-all still removes them (said in the confirmation).
- **Long threads:** the API returns every message and every conversation (no pagination); acceptable for the MVP.
- **Draft lost on the consent gate:** accepted (D7).
- **Gemini free tier:** the notice and fictitious data only; TD-063 keeps the production conditions open.
- **Scope pressure:** Markdown, streaming, editing and regenerating are the usual requests; they are non-goals.

## Open decisions for the owner (recommendation first)

1. **Route and entry.** Recommended: `/subjects/{id}/chat` from the student's cards. *Alternative:* a navigation item with a subject selector.
2. **Delete the whole history.** Recommended: on the student's subject list. *Alternative:* inside the chat page.
3. **Sending.** Recommended: button only; Enter makes a line break. *Alternative:* Enter sends, Shift+Enter breaks the line (faster, easier to send by accident).
4. **Time limit.** Recommended: 60 s, with the refresh after a timeout. *Alternative:* 45 s, or the same 15 s as the rest (would cut valid answers).
5. **Sources.** Recommended: "Material consultado", expandable snippet, neutral note. *Alternative:* chips with file and page only, no snippet.
6. **Notice copy.** Recommended: the test-version notice with the Gemini disclosure, the fictitious-data warning, the tip about naming the topic, and the link to the draft policy.
