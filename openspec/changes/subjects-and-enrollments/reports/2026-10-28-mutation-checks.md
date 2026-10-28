# Mutation Spot-Checks - subjects-and-enrollments

Method: for each actor filter, the condition is temporarily replaced by a tautology (for example `Subject.teacher_id == Subject.teacher_id`), the repository and API tests are run (`pytest -x`), and the file is restored. A mutation is KILLED when at least one test fails. Script kept in the session scratchpad; the repository files were restored after every run (`git diff` empty).

## Subject repository (task 3.3)
| # | Method | Removed condition | Result | First failing test |
|---|---|---|---|---|
| 0 | `list_for_teacher` | `teacher_id == teacher_id` | KILLED | `test_list_for_teacher_returns_only_own_subjects_ordered_by_name_then_id` |
| 1 | `list_for_student` | `Enrollment.student_id == student_id` | KILLED | `test_list_for_student_returns_only_enrolled_subjects` |
| 2 | `get_for_teacher` | `teacher_id == teacher_id` | KILLED | `test_get_for_teacher_requires_ownership` |
| 3 | `get_for_student` | `Enrollment.student_id == student_id` | KILLED | `test_get_for_student_requires_enrollment` |
| 4 | `delete_for_teacher` | `teacher_id == teacher_id` | KILLED | `test_delete_for_teacher_only_deletes_owned_subjects` |

## Enrollment repository and service (task 4.3)
| # | Target | Mutation | Result | First failing test |
|---|---|---|---|---|
| 5 | `EnrollmentRepository.list_for_teacher_subject` | owner condition `Subject.teacher_id == teacher_id` made a tautology | KILLED | `test_list_for_teacher_subject_is_scoped_to_the_owner_and_subject` |
| 6 | `list_for_teacher_subject` | subject condition made a tautology | KILLED | same test |
| 7 | `delete_for_teacher_subject` | ownership subquery condition made a tautology | KILLED | `test_delete_for_teacher_subject_is_scoped_to_owner_subject_and_student` |
| 8 | `delete_for_teacher_subject` | student condition made a tautology | KILLED | same test |
| 9 | `EnrollmentService.enroll` | ownership check removed | KILLED | `test_enroll_links_the_registered_student_after_checking_ownership` |
| 10 | `EnrollmentService.enroll` | non-student accounts accepted | KILLED | `test_unknown_and_non_student_emails_raise_the_same_error_without_the_email` |
| 11 | `EnrollmentService.list_for_subject` | ownership check removed | KILLED | `test_list_returns_an_empty_list_for_an_owned_subject_and_not_found_otherwise` |
| 12 | `EnrollmentRepository.add` | owner condition `Subject.teacher_id == teacher_id` removed from the `INSERT ... SELECT` (F6) | KILLED | 4 tests: `test_enrollment_add_refuses_a_teacher_who_does_not_own_the_subject`, `test_enrollment_add_refuses_a_missing_subject_and_a_student_account_as_actor`, `test_a_refused_enrollment_leaves_the_session_usable`, `test_concurrent_enrollments_by_owner_and_strangers_create_exactly_one_row` |

## Log protection (task 4.3)
- Forcing a real PostgreSQL error on the lookup by email (`FROM users` renamed) and on `INSERT INTO subjects` returns the generic 500 and the captured log contains no email, name or description.
- Mutation A: `UnhandledErrorMiddleware` logging with `logger.exception` (traceback) alone: the tests still pass because the engine hides parameters (`hide_parameters=True`).
- Mutation B: `hide_parameters=False` alone: the tests still pass because the middleware logs only the exception type, method and path.
- Mutations A and B together: both log tests FAIL (leak detected). The two existing defences are independent layers, and the new tests detect the loss of both.
