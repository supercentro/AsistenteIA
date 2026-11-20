# teacher-enrollment-ui: TDD and mutation evidence (sections 1 and 2)

Date: 2026-11-19. Branch `feature/teacher-enrollment-ui` (from `main` `f8020ec`). Frontend only.

## Failing run before the implementation (task 1.8)

Command (from `frontend/`): `npx vitest run src/lib/enrollmentSchema.test.ts src/services/enrollmentService.test.ts src/components/ConfirmPanel.test.tsx src/pages/TeacherEnrollments.test.tsx`

Result: **4 test files failed; 48 tests failed, 1 passed (49)**. Failure summary: `enrollmentSchema`, `enrollmentService` and `ConfirmPanel` did not exist, `strings.enrollments` did not exist, and the subject page had no "Estudiantes inscritos" section.

## Passing run after the implementation (tasks 2.1 to 2.4)

The four files and the whole suite passed: 34 files, 487 passed, 1 skipped, with `typecheck` and `lint` clean. The document-deletion tests of `teacher-material-ui` passed unchanged after `DocumentRow` was moved onto the shared `ConfirmPanel`.

## Mutation checks (task 2.5)

Each change was applied to the production code, the test files of the change were run, and the code was restored (`mutate_en.py`, scratchpad of the session). Every mutation is detected:

| Mutation | Result |
|---|---|
| a student reaches the section (route guard widened) | 1 failed |
| the confirmation is skipped | 14 failed |
| the 404 message mentions teachers | 1 failed |
| enroll without `cancelQueries` | 1 failed (after lengthening the delay of the race test: the first version did not detect it, because typing could outlast the delayed answer) |
| remove without `cancelQueries` | 1 failed |
| the e-mail rule stricter than the registration | 3 failed |
| no subject re-check after an enroll 404 | 2 failed |
| the removal text says "irreversible" | 1 failed |
| the 409 is not explained | 1 failed |
| other confirm controls stay enabled | 1 failed |
| the e-mail is sent lowercased | 2 failed |
| no focus on the heading after a removal | 1 failed |

## Review round (task 3.6)

The independent review gave FAIL (two Major findings). Failing run before the corrections: `npx vitest run src/pages/TeacherEnrollmentsReview.test.tsx`: **4 failed, 5 passed** (a removal 404 with the subject gone; enrolling while the list had failed and while it was loading; a stale enrollment error). After the corrections the whole suite passes: 35 files, **497 passed, 1 skipped**; coverage 97.54 % statements, 93.11 % branches, `src/hooks` 100 %, `src/components` 96.15 %. Three more mutations of the corrections were detected: the removal 404 without the subject re-check (1 failed); enrolling with an unloaded list writing a one-row list (2 failed); the enrollment error kept after editing the field (1 failed). Weak assertions pointed out by the review were replaced by assertions on the rendered DOM (the neutral 404 message, the hint) and a second double-submit test (Enter twice).

## Deviations

- The `isPending` guard of the enroll form is redundant with the disabled submit control (browsers do not submit implicitly through a disabled default button), so no mutation of it is detected; the Enter-twice test still proves that a single request is sent.
- 320 px, keyboard use and real timing are verified in the browser (`2026-11-19-step-3-4-e2e-verification.md`): jsdom has no layout. The open confirmation at 320 px is covered by the shared component's `max-w-full` and `overflow-wrap` classes (unit test) and by the same classes in the closed state (browser).
