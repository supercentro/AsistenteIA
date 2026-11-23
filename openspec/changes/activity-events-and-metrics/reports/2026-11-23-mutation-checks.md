# Mutation checks (task 2.3)

Date: 2026-11-23. Each row changes one line of the implementation, runs the three activity test modules (`tests/unit/test_activity_service.py`, `tests/unit/test_activity_schema_shape.py`, `tests/integration/test_activity_endpoint.py`, stopping at the first failure) and then restores the file. The script checks a digest of the four mutated sources before and after, so the final tree equals the tested one. Fictitious data only.

| # | Mutation | Result | First failing test |
|---|---|---|---|
| 1 | cell threshold off by one (`>` instead of `>=` the minimum group) | killed | `test_a_period_is_shown_only_when_at_least_n_distinct_students_asked[N]` |
| 2 | cell threshold removed (every cell shown) | killed | `...[N-1]` |
| 3 | subject threshold off by one | killed | `test_exactly_n_active_students_are_shown` |
| 4 | subject threshold removed | killed | `test_a_subject_with_fewer_than_n_active_students_shows_only_the_enrolled_count` |
| 5 | rates shown below the minimum group | killed | `test_a_rate_whose_denominator_has_fewer_than_n_students_is_null` |
| 6 | enrolment join removed from the repository | killed | `test_only_conversations_of_the_subject_and_enrolled_students_are_counted` |
| 7 | owner check removed from the service | killed | `test_a_subject_of_another_teacher_is_not_found` |
| 8 | `Subject.teacher_id` condition removed from the repository | killed | `test_the_aggregate_queries_take_the_teacher_and_join_the_subject_owner` |
| 9 | a free text field added to the response schema | killed | `test_the_response_has_only_reviewed_fields` |
| 10 | window limit removed | killed | `test_the_window_has_at_most_twelve_weeks_which_is_within_ninety_days` |
| 11 | switched-off guard removed | killed | `test_the_capability_is_switched_off_by_default` |
| 12 | answers that only retrieved their sources counted as appearances | killed | `test_only_cited_answers_count_as_appearances` |

Twelve of twelve killed, none survived.
