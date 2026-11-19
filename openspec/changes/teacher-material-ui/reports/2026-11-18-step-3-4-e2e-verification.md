# Step 3.4 Report - Browser verification

- Date: 2026-11-18
- Change: teacher-material-ui
- Target: the existing local stack (frontend development server on 5173, backend 8000, worker, database), not rebuilt or recreated.

## Playwright MCP run by the agent (real stack, test accounts, fictitious files)
1. Signed in as a teacher test account. The browser had autofilled another saved login; it was overwritten with the test account and never used.
2. Created a subject named `MCP Fisica <b>ficticia</b>` with a description: it appeared in the list with the name shown literally, the form cleared, and the name is a link to `/subjects/{id}`.
3. Opened the subject page: heading, description, upload area with the formats and the MVP notice (fictitious documents only), empty-state text.
4. Uploaded a `.txt`: the row appeared as pending and turned to **Listo** with "1 fragmento" by itself, with no reload; the live region said "El documento ... está listo."
5. Uploaded an executable: the Spanish message for an unsupported type was shown (415); the console showed only `[api] POST /api/v1/subjects/{id}/documents -> 415` (no file name, no server text).
6. Uploaded a markdown file with only blanks: it was accepted and ended **Con error** with the sentence for `NO_EXTRACTABLE_TEXT`.
7. Viewport 320 px: `scrollWidth` 305 for a `innerWidth` 320 (no horizontal scrolling); the tab order was Asignaturas, Cerrar sesión, Volver, Archivo, Subir documento, Actualizar lista, the delete buttons.
8. Keyboard only: focus on a delete button, Enter, the focus moved to the confirmation group ("¿Eliminar «...»? Esta acción no se puede deshacer"), Tab to the confirm button, Enter: the row disappeared.
9. Signed out and in as a student test account: held at `/consent` as designed; after accepting, navigating inside the application to `/subjects/{id}` showed "Acceso no permitido" with no upload form.
10. Restoration: the subject (and its remaining document) was deleted through the API.

## Committed Playwright Test specs
- `e2e/teacher-materials.mocked.spec.ts` (API stubbed, no backend): four tests: create subject, upload, pending to ready by polling, delete with confirmation; upload refusal and failed-document explanation, with no server text; no horizontal scrolling at 320 px and keyboard order; a student cannot open the page. `e2e/auth-flow.mocked.spec.ts` was updated (the teacher now sees the create form and a link; still no delete or enrol control).
- `e2e/teacher-materials.real-backend.spec.ts` (gated by `E2E_REAL_BACKEND=1`, `E2E_TEACHER_EMAIL`, `E2E_TEACHER_PASSWORD`): creates a subject, uploads a text document, waits for ready (worker running), deletes the document and removes the subject through the API. **Passed against the existing stack in 4.8 s.**
- Mocked suites together (`teacher-materials auth-flow consent-flow smoke`): 20 passed.

## Outcome
Step 3.4 status: PASS. Findings: none open. Note for the record: the in-memory session means a page reload ends it, so the specs navigate inside the application when they need a different route.
