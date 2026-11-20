# Proposal

## Why

A student can only ask about a subject they are enrolled in, and only the subject's teacher can enroll them. The backend already offers that (`subjects-and-enrollments`), but the web interface has no way to do it: after `teacher-material-ui` a teacher can create a subject and upload material, yet the next step of the main flow (enroll a student) can still only be done through the API documentation, and the future `student-chat-ui` needs an enrolled student to be demonstrable from the interface. This change adds that step. It is the follow-up decided when `teacher-material-ui` was scoped.

## What Changes

- A new **"Estudiantes inscritos" section on the teacher's subject page** (`/subjects/{subject_id}`): the list of enrolled students (email, as the API returns it), an **enrollment form** (one student email) and a **remove** action per student.
- **Enrolling** by email (`POST /subjects/{id}/enrollments`): the student must already have an account; the form says so. Every documented outcome has its own Spanish message: unknown or non-student email (one neutral message, because the API deliberately answers both the same), already enrolled, invalid email, rate limit, server failure.
- **Removing** an enrollment (`DELETE /subjects/{id}/enrollments/{student_id}`) after an inline confirmation that says what happens: the student stops seeing the subject and its conversations, nothing is deleted, and the teacher can enroll the student again.
- The inline confirmation of the document row is **extracted into a shared component** and used by both lists (a repeated pattern; the existing tests of the document deletion keep passing).
- Documentation: `docs/frontend-standards.md` (page structure, shared confirmation), `docs/development_guide.md` (the local test circuit: enrolling now has a screen; the chat still uses the API documentation).

**Out of scope (not added):** student self-enrollment, enrollment by invitation or in bulk (file or list), pre-enrollment of unregistered emails (the backend forbids it), searching or listing all students, showing names or any other data than the email, a student-side view of subjects beyond the existing list, notifications, the chat, editing or deleting subjects, and any backend, contract or migration change.

## Capabilities

### New Capabilities
- `frontend-teacher-enrollments`: list, enroll and remove the students of a subject from the teacher's subject page.

### Modified Capabilities
<!-- None: the new section is added to the subject page of `frontend-teacher-materials` (still an active change, not yet a main spec) without changing any of its requirements, and the subject list of `frontend-app-shell` keeps "no enrol control" because the controls live on the subject page. -->

## Impact

- **Authorization / isolation:** none changed; the backend stays the authority (owner teacher only; another teacher's subject answers 404, a student 403). The section exists only on the teacher-only route, so a student never reaches it or triggers a request. The UI does not tell an unregistered email from a teacher's email, as the API does not.
- **Personal data (Ley 25.326):** the list shows the e-mail of each enrolled student to the owner teacher; that is what the existing endpoint returns and no other personal data is added. The email typed in the form is sent once to the API and is not stored, logged or shown back in error messages. The privacy policy draft does not say that the teacher of a subject sees the e-mail of its enrolled students: recorded for the owner (TD-064 already holds the open point about teachers' data); the policy text is not changed here. MVP: fictitious accounts only.
- **External services:** none. No Gemini call, no worker.
- **Contracts:** `docs/api-spec.yml` and `docs/data-model.md` do not change (the three endpoints, the `Enrollment` schema and the error codes exist). `src/types/api.generated.ts` already holds `Enrollment`; `npm run check:api-types` confirms no regeneration is needed.
- **Code:** frontend only (service, hooks, one section component, a shared confirmation component, copy module, tests). No new runtime dependency. No backend, infrastructure or secret change.

### Decisions to confirm (see design, Open decisions)
1. The section lives on the existing subject page, below the documents.
2. The removal is confirmed inline, with wording that says it is reversible.
3. A 404 on enrolling is explained as "no registered student with that e-mail" and the page re-checks the subject, because the API uses 404 for both the e-mail and the subject.
4. The privacy policy is not changed in this change; the teacher's visibility of student e-mails is recorded for the pilot.
