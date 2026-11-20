# teacher-material-ui: TDD and mutation evidence (sections 1 and 2)

Date: 2026-11-18. Branch `feature/teacher-material-ui` (from `main` `12bc127`). Frontend only.

## Failing run before the implementation (task 1.9)

Command (from `frontend/`): `npx vitest run src/lib/apiError.test.ts src/lib/subjectSchema.test.ts src/services/materialServices.test.ts src/hooks/useDocuments.test.ts src/pages/SubjectsPage.test.tsx src/pages/CreateSubject.test.tsx src/pages/TeacherSubjectPage.test.tsx src/pages/TeacherUpload.test.tsx src/pages/TeacherDocuments.test.tsx`

Result: **9 test files failed; 35 tests failed, 57 passed (92)** (files whose modules did not exist, such as `documentService`, `useDocuments` and the new pages, failed to load, so their tests are not counted among the 35). Failure summary: `subjectSchema` and `strings.subjects.create` / `strings.materials` did not exist, `ApiError.reason` was undefined, `/subjects/:id` rendered the not-found page, the teacher list had no form and no link. The 57 that passed are existing tests and negative cases that hold without the feature.

## Passing run after the implementation (tasks 2.1 to 2.6)

The same files: all passed. Full suite with coverage: 29 files, 413 passed, 1 skipped (the on-demand policy release check); coverage 97.46 % statements, 93.14 % branches, 98.85 % functions; `src/components` 96.94 %, `src/hooks` 98.78 % (thresholds of 70 %).

Two test-environment findings fixed during the implementation, not production defects: `request.formData()` of the MSW handler cannot parse a jsdom `File` (undici asserts its own `File` class), so the tests read the raw multipart body (`tests/materials.ts`, `readMultipart`); and `userEvent.upload` honours the `accept` filter, so the upload tests use `applyAccept: false` to choose unsupported files like a user would.

## Mutation checks (task 2.7)

Each change was applied to the production code, the seven touched test files were run, and the code was restored (`mutate_tm.py`, scratchpad of the session). Every mutation is detected:

| Mutation | Result |
|---|---|
| polling stops early (`processing` treated as final) | 2 failed |
| polling continues when all documents are final | 6 failed |
| the server `error_message` is shown | 13 failed |
| the confirmation is skipped (the button deletes at once) | 8 failed |
| the create form is shown to students | 2 failed |
| an unlisted 422 reason is accepted by `ApiError` | 4 failed |
| a blank description is sent | 1 failed |
| the ready announcement is not produced | 1 failed |

## Review round (task 3.6)

The independent review gave FAIL (two Major findings). Failing run before the corrections: `npx vitest run src/pages/TeacherReviewFixes.test.tsx src/lib/apiError.test.ts`: **12 failed, 61 passed** (a 503 `Retry-After`, the upload time limit and message, the cache races of upload and delete, the bidirectional isolate, the refresh error of the subject, the announcement of several documents, the focus after a deletion, the other confirm controls). After the corrections the full suite passes: 30 files, **429 passed, 1 skipped**; coverage 97.69 % statements, 93.46 % branches, 100 % hooks, 97.08 % components. Ten more mutations of the corrections were each detected (1 to 3 failing tests): 503 `Retry-After` ignored; upload without its longer limit; delete and upload without `cancelQueries`; no `bdi` around the name; no key per subject; a refresh error of the subject hiding the page; only the last announcement kept; no focus after deletion; other confirm controls left enabled.

## Deviations

- The "keep polling after unmount" and "hidden tab" cases are covered by tests with fake timers, but only the first seven mutations above were run; their guards (React Query defaults and the hook lifecycle) are not code of this change.
- 320 px, keyboard use and real timing are verified in the browser (`2026-11-18-step-3-4-e2e-verification.md`): jsdom has no layout.
