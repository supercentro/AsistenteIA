# Step 3.3 Report - Manual endpoint testing against the local stack

- Date: 2026-11-19
- Change: teacher-enrollment-ui
- Target: local development stack `http://127.0.0.1:8000/api/v1` (backend and worker as they were running; not rebuilt or recreated). The two teacher test accounts and the student test account that already existed (no account was created); fictitious subject.
- The script is not part of the repository (scratchpad of the session); no password was printed.

| Call | Expected | Result |
|---|---|---|
| enroll with the student's e-mail in capitals | 201, lowercase e-mail in the answer | 201, lowercase |
| enroll an unregistered e-mail | 404 | 404 |
| enroll a teacher's e-mail | 404, body identical to the previous one | 404, identical body |
| the 404 bodies | do not repeat the e-mail | they do not |
| enroll the same student again | 409 | 409 |
| non-ASCII e-mail / malformed e-mail | 422 | 422 / 422 |
| another teacher enrolls | 404 | 404 |
| a student enrolls | 403 | 403 |
| list as owner | 200, only `id`, `subject_id`, `student_id`, `student_email`, `created_at` | 200, exactly those fields |
| list as another teacher / as a student | 404 / 403 | 404 / 403 |
| the enrolled student lists their subjects | contains the subject | contains it |
| remove the enrollment | 204 | 204 |
| remove it again / remove as another teacher | 404 / 404 | 404 / 404 |
| the student lists their subjects / reads the subject | no longer / 404 | no longer / 404 |
| enroll again | 201 | 201 |
| delete the subject (cleanup, cascades the enrollments) | 204 | 204 |

Not exercised here: the restoration of the student's conversations after enrolling again (covered by the backend suite, `conversation-history`, and stated in the confirmation text); 429 and 5xx (covered by the interface tests with stubbed answers).

## Restoration
The subject and its enrollments were deleted through the API. No account was created.

## Outcome
Step 3.3 status: PASS (21 of 21 checks). The 404 of an unregistered e-mail and of a teacher's e-mail are indistinguishable, as the interface assumes.
