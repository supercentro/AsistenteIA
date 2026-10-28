# Independent Adversarial Review - subjects-and-enrollments

- Date: 2026-10-28
- Reviewer: a separate Claude subagent (general-purpose, `model=opus`) started with a clean context, with no access to the implementing conversation. Read-only on the repository; probes ran only against the isolated `asistenteia_test` database, from scratch scripts outside the repository. This report summarises its final report; the resolution column is written by the implementing session.
- Scope: `git diff origin/main..HEAD` of `feature/subjects-and-enrollments` at the time of the review (backend code, migration `0003`, tests, docs, the `readme.md` HU-1 line).
- Verdict of the reviewer: **PASS WITH GAPS**, no blocker and no major.

## What the reviewer tried (summary)
Cross-teacher and cross-student access on every endpoint (identical 404 bodies and headers for missing and inaccessible subjects; 403 before 404 on teacher-only routes; enrollment id versus student id mix-ups; removal through another teacher's subject path); identical 404 for unknown and teacher emails; null, list, number, object and bool values for every field; duplicate JSON keys; extra fields (`teacher_id`, `id`, `student_id`); lone surrogates (escaped and raw), invalid UTF-8, 5000-level nesting, a 2 MB name; malformed and odd path ids; 15 rounds of enrollment racing subject deletion; a forced foreign-key race; migration round trips with `alembic check`; regression of the extracted validators; emails and names in logs and database errors. The full suite (476 tests), `ruff` and `mypy --strict` were run.

## Findings and resolution
| # | Severity | Finding | Resolution |
|---|---|---|---|
| 1 | Minor | A student or subject deleted between the lookup and the insert produced a 404 with the message "Resource not found", not the "Student not found" of design D3 | **Fixed** (tests first): `EnrollmentService.enroll` maps that case to `STUDENT_NOT_FOUND_MESSAGE`; unit test `test_vanished_student_race_gets_the_same_not_found_as_an_unknown_email` |
| 2 | Minor | `Description` is trimmed and a blank description was stored as `""`; the spec scenario promised the text "unchanged" and the unit test name overpromised | **Fixed** (tests first): blank description becomes null; spec scenarios reworded ("Description with line breaks" keeps inner breaks, new "Description whitespace" scenario); `api-spec.yml` states trimming and null; tests `test_subject_create_turns_a_blank_description_into_none`, `test_description_is_trimmed_at_both_ends_but_keeps_inner_line_breaks`, `test_description_is_trimmed_and_a_blank_description_becomes_null`; the misleading test was renamed |
| 3 | Minor | The shared email validator strips Unicode whitespace before the ASCII check, so `"s@example.com"` padded with U+2028 or U+00A0 is accepted as its plain form (registration and login already behave this way); the docs say non-ASCII is rejected | **Recorded as TD-018** (open): tightening the shared validator changes registration and login behaviour of an earlier change and needs the user's approval; not exploitable (normalises to an existing ASCII address) |
| 4 | Minor | The bidi block list omits U+061C (Arabic letter mark) and zero-width characters are allowed, so a teacher can create two names that look identical | **Recorded in TD-018** (same shared code as the user `Name`; affects only the teacher's own subjects) |
| 5 | Minor | Dead code in a test (`if ...: pass`) | **Fixed**: removed |
| 6 | Question | `EnrollmentRepository.add` takes no actor; write authorisation depends on the service calling `get_for_teacher` first | **Accepted for now, flagged for the user**: design D2 documents it; `EnrollmentService` is the only caller and mutation checks (ownership removed from `enroll`) are killed by the tests (`2026-10-28-mutation-checks.md`, #9). An `INSERT ... SELECT` guarded by the owner would remove the dependency on the caller if the user prefers it |

## Verified as sound (by the reviewer)
Actor-scoped repositories on every request path; role check before ownership on all teacher-only routes; identical 404s (bodies and headers) and no echo of emails or names; one 201 and the rest 409 under concurrency; savepoints keep the session usable; migration `0003` (FK actions, names, downgrade order, `alembic check` clean, round trips); no 5xx for any odd input tried; the validator extraction left registration, login and CLI behaviour unchanged; responses expose only ids and the student email; `readme.md` differs from `main` only by the approved HU-1 line.

## Verification after the fixes
Full backend suite **479 passed** (3 new tests), `ruff`, `ruff format --check` and `mypy --strict` clean. The failing run of the new tests before the fixes is recorded in `2026-10-28-tdd-evidence.md`.

## Final verdict
**PASS WITH GAPS.** No open blocker or major. Open items: TD-018 (open, needs approval) and the question of item 6 (accepted, flagged).
