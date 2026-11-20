# Step 3.4 Report - Browser verification

- Date: 2026-11-19
- Change: teacher-enrollment-ui
- Target: the existing local stack (frontend development server on 5173, backend 8000, database), not rebuilt or recreated.

## Playwright MCP run by the agent (real stack, existing test accounts, fictitious subject)
1. Signed in as a teacher test account (the browser had autofilled another saved login; it was overwritten with the test account and never used).
2. Created a subject and opened its page: the section "Estudiantes inscritos" appeared below the documents with the empty state, the e-mail field, the hint that the account must already exist, and the button.
3. Enrolled an unregistered e-mail: the single neutral message "No se encontró un estudiante registrado con ese correo." appeared, the typed value stayed in the field, and the console showed only `[api] POST /api/v1/subjects/{id}/enrollments -> 404` (no e-mail, no server text).
4. Enrolled the student's e-mail typed with capitals: the list showed it in lowercase and the field was cleared.
5. Enrolled the same e-mail again: "Ese estudiante ya está inscrito en la asignatura." and the list unchanged.
6. At 320 px: `scrollWidth` 305 for an `innerWidth` of 320 (no horizontal scrolling).
7. Keyboard only: focus on "Quitar a ...", Enter, the focus moved to the confirmation group whose text says the student will stop seeing the subject and its conversations and that nothing is deleted; Tab to the confirm button, Enter: the row disappeared, the empty state came back and the focus was on the section heading.
8. Enrolled the student again, signed out and signed in as the student: "Mis asignaturas" listed the subject, read-only, with no link.
9. Restoration: the subject (and its enrollment) was deleted through the API. No account was created.

## Committed Playwright Test specs
- `e2e/teacher-enrollments.mocked.spec.ts` (API stubbed, no backend), three tests: enrolling and removing with the keyboard, the 404 / 409 / invalid e-mail messages, no horizontal scrolling at 320 px with a very long e-mail. The existing `teacher-materials.mocked.spec.ts` got the enrollment list handler its pages now need.
- `e2e/teacher-enrollments.real-backend.spec.ts` (gated by `E2E_REAL_BACKEND=1`, teacher and student accounts given by the environment): creates a subject, checks that an unregistered e-mail gets the neutral message, enrolls the student, checks with the student's own session that the subject appears, the duplicate message, removes, checks that it disappears, and deletes the subject. **Passed against the existing stack (2.3 s)**, together with the gated spec of `teacher-material-ui`.
- Mocked suites together (`teacher-enrollments teacher-materials auth-flow consent-flow smoke`): 23 passed.

## Finding fixed during the run
The mocked spec at 320 px with a very long e-mail without separators showed horizontal scrolling: the label of the remove button ("Quitar a <e-mail>") could not wrap. Fixed in the shared `ConfirmPanel` trigger (`max-w-full`, `text-left`, `[overflow-wrap:anywhere]`) with a unit test; this also protects the document deletion button with a long file name.

## Outcome
Step 3.4 status: PASS.
