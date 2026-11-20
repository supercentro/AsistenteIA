# Design

## Context

See `proposal.md` (Why). State verified in the repository on `main` (`f8020ec`):

- Backend, unchanged: `GET /subjects/{id}/enrollments` (array of `Enrollment`: `id`, `subject_id`, `student_id`, `student_email`, `created_at`; no names), `POST` with `{student_email}` (201; 404 for an e-mail with no account **or** belonging to a teacher, with the same code and message; 409 already enrolled; 422 invalid e-mail; no pre-enrollment), `DELETE /subjects/{id}/enrollments/{student_id}` (204; 404 when it does not exist). All three are owner-teacher only; another teacher's subject answers 404, a student 403. Unenrolling hides the student's conversations of that subject but deletes nothing, and enrolling again restores them (`docs/data-model.md`, spec `conversation-history`).
- Frontend (after `teacher-material-ui`): the route `/subjects/:subjectId` is teacher-only and keyed per subject; `TeacherSubjectPage` shows the upload form and `DocumentsSection`; `DocumentRow` holds an inline confirmation panel (focus into the panel, back to the trigger on cancel; ready to be shared); hooks follow one pattern (query key with user id and subject id; `cancelQueries` before `setQueryData`); `ApiError` keeps status, code, `Retry-After` and the closed 422 reasons, never server text; `lib/schemas.ts` has an e-mail rule used by login and registration (not exported on its own); `Alert`, `Button` (forwardRef), `FormField`, `EmptyState`, `ErrorState`, `LoadingState` exist; `types/api.generated.ts` already contains `Enrollment`.
- Standards: `docs/frontend-standards.md` (hooks call services, forms mirror API limits, a11y, confirmation for deletions, copy in one module), `docs/openspec-tasks-mandatory-steps.md`.

## Goals / Non-Goals

**Goals:** a teacher enrolls a registered student and removes an enrollment from the interface, with every outcome explained in Spanish, so that the main flow (teacher prepares a subject, student asks) is complete up to the chat screen.

**Non-Goals:** everything listed as out of scope in the proposal. No change of `privacy-consent-ui`, `teacher-material-ui` decisions, or of TD-003, TD-063, TD-064 and TD-065.

## Decisions

### D1. A section on the existing subject page
`EnrollmentsSection` is rendered by `TeacherSubjectPage` below `DocumentsSection`; no new route. The page already guards the role, keys its state per subject and replaces itself by the not-found or forbidden view when a request says so; the enrollment queries join that logic (their 403 and 404 count like the document list's). *Alternative:* a separate `/subjects/:id/students` route or tabs (rejected: another route and navigation for a short list, and the page guard would be duplicated).

### D2. Layers
`services/enrollmentService.ts` (`list`, `create`, `remove`); hooks `useEnrollments(userId, subjectId)` (no polling: enrollment is synchronous), `useEnrollStudent`, `useRemoveEnrollment`; key `['enrollments', userId, subjectId]`. As in `teacher-material-ui`, a successful enroll or remove first calls `cancelQueries` and then updates the cache, so an older list answer cannot undo the change. `types/api.ts` gets an `Enrollment` alias.

### D3. The form
One field `Correo electrónico del estudiante` with a hint ("La cuenta del estudiante ya debe existir: la persona se registra primero."). React Hook Form + Zod with the **same e-mail rule as registration** (ASCII, at most 255, plausible shape), exported from `lib/schemas.ts` as one `enrollmentSchema` so the limits are not copied. The e-mail goes as typed (the API lowercases). The value is kept after a failure and cleared after success; the field keeps the focus path so several students can be added in a row.

### D4. Explaining the outcomes without leaking anything
- 404 on enroll: one message, "No se encontró un estudiante registrado con ese correo.", never saying whether the e-mail is a teacher's (the API refuses to tell). Because the same 404 would also come from a subject that has vanished, the page invalidates the subject and enrollment queries after a 404; if the subject is gone, the existing not-found view replaces the page.
- 409: "Ese estudiante ya está inscrito en la asignatura." Added to the form's `overrides` of `messageFor` by code `CONFLICT`.
- 422 / 429 / 5xx / network: existing messages (`errors.byCode`, `rateLimitedIn`, ...). The submitted e-mail and the server text are never shown or logged (the logger writes only method, path and status; the path has no e-mail).

### D5. Removal: a reversible action, said plainly
The standards ask that deletions say they are irreversible; this one is not, so the text says what is true: "El estudiante dejará de ver la asignatura y sus conversaciones en ella. No se borra nada: si se lo vuelve a inscribir, las recupera." The confirmation is the **shared inline component** extracted from `DocumentRow` (`ConfirmPanel`: group with the question, a body, confirm and cancel, focus into the panel and back to the trigger, busy state), so both lists behave alike and the pattern is not duplicated. After a removal the focus goes to the section heading, as in the documents. A 404 on the deletion means the enrollment no longer existed: the row goes away with a notice. Because the same status also comes from a subject that is gone, the subject and the list are requested again, as after an enroll 404 (found by the independent review). When an enrollment succeeds while the list is not loaded (loading or failed), the list is requested again instead of writing a one-row list into the cache, so the page never shows an incomplete roster as if it were whole.

### D6. Privacy of the screens
The list shows the e-mail of enrolled students to the owner teacher only (the API's own rule). The UI keeps no copy outside the React Query cache (cleared at the end of the session), writes nothing to storage, and renders e-mails as text (with `bdi` and wrapping; the label of the remove button is plain text, which is acceptable because the API accepts ASCII e-mails only). The policy text is not changed in this change: its statement of who sees what is recorded as an open point for the pilot (TD-064 already lists teachers' data); changing the text would also raise the policy version.

## Dependencies

- `teacher-material-ui` is merged (`f8020ec`); `teacher-enrollment-ui` builds on its page, hooks and components but does not change its decisions.
- Backend endpoints exist and are unchanged. For the real-backend verification a **registered student** is needed; the gated spec registers one through the API (fictitious e-mail) and checks the result by signing in as that student. The existing stack is used as it is (not rebuilt or recreated).
- No new npm package.
- `student-chat-ui` follows and will use the enrolled student created here.

## Risks / Trade-offs

- **The 404 of the form is ambiguous by design** (e-mail or subject). Mitigation: the neutral message plus the re-check of the subject (D4); the cost is one extra request after a 404.
- **Typos create no harm but no feedback either:** an e-mail that is not registered is a 404, and the API cannot confirm a near match. Mitigation: the hint says the account must exist and the 404 message names the e-mail's role in the problem without echoing it.
- **Removing hides a student's conversations of the subject** (data effect, reversible). Mitigation: the confirmation says so.
- **No pagination:** the endpoint returns every enrollment. Acceptable for the MVP (one teacher, a handful of fictitious students); noted for later.
- **Visible e-mails:** see D6; only the owner teacher sees them.
- **Test accounts:** the manual and real-backend runs need student accounts; they cannot be deleted through the API (TD-064). Each run creates at most one and removes the enrollments it made.
- **Scope pressure:** invitation, bulk enrollment and names are the usual requests; they are non-goals.

## Open decisions for the owner (recommendation first)

1. **Placement.** Recommended: a section on the subject page, below the documents. *Alternative:* its own page.
2. **Shared confirmation.** Recommended: extract `ConfirmPanel` from the document row and use it for both (a small refactor of existing code with its tests). *Alternative:* a second copy of the panel (faster, repeats the pattern).
3. **Removal wording.** Recommended: say that nothing is deleted and that re-enrolling restores the conversations. *Alternative:* the generic "irreversible" wording of the standards (would be false here).
4. **Privacy policy.** Recommended: leave the text as it is and keep the teacher's visibility of student e-mails as an open point for the pilot (TD-064). *Alternative:* add a sentence now (raises the version; the text is still an unreviewed draft).
