# TDD Evidence - subjects-and-enrollments

Failing run of each functional group before its implementation (`docs/base-standards.md` section 9.2). Commands run from `backend/`.

## Group 1 - shared validators (`schemas/validators.py`)
- Command: `uv run pytest tests/unit/test_validators.py -q`
- Result before the implementation: `ModuleNotFoundError: No module named 'app.schemas.validators'` (collection error, 1 error, 0 tests run).
- Result after the implementation: `26 passed`. Existing suites unchanged in intent (full backend suite: 370 passed).

## Group 2 - persistence and repositories
- Command: `uv run pytest tests/integration/test_migrations_subjects.py -q`
- Result before the implementation: `4 failed` (`psycopg.errors.UndefinedTable: relation "public.subjects" does not exist`).
- Command: `uv run pytest tests/integration/test_subject_repositories.py -q`
- Result before the implementation: collection error `ModuleNotFoundError: No module named 'app.models.subject'` (0 tests run).
- Test adjusted in the same step: `test_users_migration_downgrades_one_step_to_the_vector_revision` in `test_migrations.py` now downgrades to revision `0001` explicitly (its intent, the `0002` downgrade, is unchanged; `-1` would now only remove `0003`).

## Group 3 - subject service and endpoints
- Command: `uv run pytest tests/unit/test_subject_service.py -q`
- Result before the implementation: collection error `ModuleNotFoundError` for `app.schemas.subject` / `app.services.subject_service` (0 tests run).
- Command: `uv run pytest tests/integration/test_subjects_api.py -q`
- Result before the implementation: `43 failed, 2 passed` (the routes did not exist). The 2 passing tests (`test_inaccessible_subjects_answer_the_same_404_as_missing_ones`, `test_another_teacher_cannot_delete_the_subject`) expect a 404 and pass only because the route is missing; they are covered by the owner-success tests of the same group and by the mutation checks of task 3.3.
- Result of the subject tests after the implementation: `441 passed` for the whole backend suite at the end of group 3.

## Group 4 - enrollment service and endpoints
- Command: `uv run pytest tests/unit/test_enrollment_service.py -q`
- Result before the implementation: collection error (`app.services.enrollment_service` does not exist).
- Command: `uv run pytest tests/integration/test_enrollments_api.py -q`
- Result before the implementation: `22 failed, 7 passed`. The 7 passing tests expect a 404 or an absent log entry and pass only because the routes do not exist yet (`test_another_teacher_gets_the_same_404_as_for_a_missing_subject`, `test_unknown_and_teacher_emails_get_the_identical_404_without_the_email`, `test_removing_a_missing_enrollment_is_404_and_leaves_the_others`, `test_removing_a_student_who_is_enrolled_only_in_another_subject_is_404`, `test_deleting_the_subject_removes_enrollments_visible_through_the_api`, `test_emails_of_rejected_enrollments_do_not_reach_the_log`, `test_a_database_error_during_subject_creation_never_logs_the_name`); they are backed by the success-path tests of the same group and by the mutation checks (4.3).

## Deviations from test-first order (task 5.1)
None. In every group the tests were written and run (failing) before the implementation. Two caveats, both recorded above: a few tests that expect a 404 or an absent log entry pass before the routes exist (they are backed by success-path tests and mutation checks), and the tests of group 3 for lone surrogates first failed because of the HTTP client (it cannot UTF-8 encode them), which was fixed in the test helper, not in the application.

## Review follow-ups (task 10.2)
- Tests added before the fixes: `uv run pytest tests/unit/test_validators.py tests/unit/test_enrollment_service.py tests/integration/test_subjects_api.py -q` gave `3 failed, 77 passed` (`test_subject_create_turns_a_blank_description_into_none`, `test_vanished_student_race_gets_the_same_not_found_as_an_unknown_email`, `test_description_is_trimmed_and_a_blank_description_becomes_null`). After the fixes the full suite gives `479 passed`.
- Caveat: the first version of these tests was written through a tool that collapsed `\n` escapes into real newlines (SyntaxError at collection); the escapes were rebuilt with explicit characters before the failing run above.
