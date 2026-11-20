# Step 3.4 Report - Browser verification

- Date: 2026-11-20
- Change: student-chat-ui
- Target: the existing local stack (frontend development server on 5173, backend 8000, worker, database, real Gemini on the free tier), not rebuilt or recreated. Fictitious subject and document, existing test accounts.

## Playwright MCP run by the agent
1. Signed in as the student test account (the browser had autofilled another saved login; it was overwritten and never used). The subject list showed the card with the link "Preguntar sobre ..." and the history section.
2. Opened the chat: subject name, the test-version notice with the Gemini disclosure, the link to the privacy draft, the empty list and the empty thread.
3. Asked a question about the material (1 real Gemini call): the question appeared, the answer came in plain text ("... las mitocondrias producen la energía de la célula en forma de ATP [1, 2]."), "Material consultado" listed two sources with their snippets in expandable details, the neutral note was present, the box was empty and had the focus.
4. The vite server reloaded after a source edit and ended the in-memory session; signing in again returned to the same chat page (return target). The conversation list showed the conversation labelled by its date (finding TD-066: the API gives no preview).
5. Asked an off-topic question: the controlled "no material" answer appeared as an ordinary message with no sources block; the list then showed two conversations, newest first.
6. 320 px: `scrollWidth` 305 for an `innerWidth` of 320 (no horizontal scrolling).
7. Keyboard only: focus on the delete action of the older conversation, Enter, the focus moved to the confirmation group ("... Se borran la conversación y todos sus mensajes. No se puede deshacer."), Tab to confirm, Enter: the row disappeared, the other stayed, and the focus went to the "Conversaciones" heading.
8. From the subject list, the history action: the group said that it covers all subjects, also those no longer visible, that it cannot be undone and that the account stays; confirming showed the notice, and the database held 0 conversations of that account.
9. Signed in as a teacher and navigated inside the application to the chat route: "Acceso no permitido", no box, no history action.
10. The only console error came from the agent's own probe run while the login page was shown, not from the application.
11. Restoration: the subject was deleted through the API and the student's history was deleted; no account was created.

## Committed Playwright Test specs
- `e2e/student-chat.mocked.spec.ts` (API stubbed, no backend), four tests: asking, reading the sources, continuing and deleting a conversation with the keyboard; the 429, `LLM_UNAVAILABLE` and `LLM_BLOCKED` messages with the question kept in the box; the whole-history deletion from the subject list; no horizontal scrolling at 320 px with a long answer, preview and file name. `auth-flow.mocked.spec.ts` was updated (the narrow-viewport test names the subject heading, now that the history section adds another level-2 heading).
- `e2e/student-chat.real-backend.spec.ts` (gated by `E2E_REAL_BACKEND=1` and the teacher and student accounts): sets up a subject, a ready document and the enrollment through the API, then the student asks **one** real question through the interface, reads the answer and the sources, deletes the conversation, and the subject is deleted at the end. **Passed three times (6 to 8 s each)**; never run from CI.
- Mocked suites together (`student-chat teacher-enrollments teacher-materials auth-flow consent-flow smoke`): 27 passed; real-backend specs of the three features: 3 passed.

## Findings during the run (fixed)
- A student's subject with a very long name made the new chat link overflow at 320 px: the link wraps now (`break-words`, `overflow-wrap:anywhere`) with a unit test.

## Outcome
Step 3.4 status: PASS.
