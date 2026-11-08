# Group 6 - review of existing tests and scenario coverage (task 6.1)

Date: 2026-11-07. Scope: confirm that every scenario of `document-storage` and `chunk-retrieval` has an automated test, that earlier suites pass unchanged in intent, that no test depends on a fixed migration head, and that tests are isolated.

## Scenario to test map

### `document-storage`
| Scenario | Test |
|---|---|
| Upgrade on a database at 0003 | `test_migrations_documents::test_upgrade_from_0003_leaves_existing_rows_unchanged` |
| Upgrade on an empty database | `test_migrations.py` and the `migrated_db` fixture (`drop_everything` then `upgrade head`) |
| Downgrade and re-upgrade | `test_migrations_documents::test_downgrade_removes_tables_and_enum_but_keeps_the_extension` |
| Valid / wrong dimension / missing embedding | `test_document_storage_integrity::test_valid_embedding_is_stored_and_read_back`, `test_wrong_dimension_is_rejected`, `test_missing_embedding_is_rejected` |
| Zero vector / non-finite / magnitude outside the range | `test_zero_vector_is_rejected_by_the_norm_check`, `test_non_finite_values_are_rejected`, `test_magnitude_outside_the_reliable_range_is_rejected_on_insert`, `test_update_to_zero_or_out_of_range_is_rejected` |
| Normalised and unnormalised outputs | `test_magnitude_inside_the_reliable_range_is_accepted` |
| Consistent chunk / other subject / missing document / subject cannot change | `test_consistent_chunk_is_stored`, `test_chunk_with_another_subject_than_its_document_is_rejected`, `test_chunk_of_a_missing_document_is_rejected`, `test_document_subject_cannot_change_while_chunks_exist` (+ `..._can_change_when_it_has_no_chunks`) |
| Delete a document / a subject / teacher stays protected | `test_deleting_a_document_deletes_only_its_chunks`, `test_deleting_a_subject_deletes_documents_and_chunks_only_of_that_subject`, `test_teacher_who_owns_subjects_with_documents_stays_protected` |
| Negative or blank values / duplicate chunk position / invalid status / defaults | `test_negative_document_numbers_are_rejected`, `test_negative_chunk_index_is_rejected`, `test_page_number_below_one_is_rejected_and_null_is_allowed`, `test_blank_content_is_rejected`, `test_duplicate_chunk_index_in_one_document_is_rejected_but_not_across_documents`, `test_invalid_status_is_rejected`, `test_every_status_value_is_accepted`, `test_defaults_are_applied_by_the_database` |
| Indexes exist with the required definition | `test_hnsw_index_uses_cosine_operator_class_and_default_parameters`, `test_btree_indexes_on_subject_columns` |
| Statement error on a chunk insert / integrity violations carry row data | `test_error_text_exposure` (precondition + 6 parametrised violations) |
| Catalog assertions | `test_migrations_documents` (enum, columns, constraints, FK, hnsw, indexes, `command.check`); the group 3 mutations show that a wrong operator class or `m` is detected |

### `chunk-retrieval`
| Scenario | Test |
|---|---|
| Enrolled student / owning teacher / not enrolled / another teacher / enrollment removed / unknown subject / other subjects never returned | `test_chunk_retrieval` (enrolled, owning, parametrised unauthorized cases, swapped role, unknown role, unknown subject and actor, removed enrollment, other subjects, fewer chunks than `top_k`) |
| Ranking / limit / only ready / complete results with many subjects | ranking, `top_k`, ready-only, and the recall test against an exact Python ranking over 1,060 chunks and 40 subjects |
| Wrong dimension, zero, NaN/infinity, magnitude, edges, normalised, invalid limit | `test_vector_validation` (45 cases) and `test_chunk_retrieval` (edge norms `1e-6` and `1e6` against known similarities; uneven components; no statement executed for 11 invalid inputs) |
| Values are not leaked | unit test of error text and the log-spy test with statement logging on |
| Parallel searches / statement-level error / real database error text | `test_parallel_searches_by_different_actors_stay_isolated`, `test_a_database_failure_in_the_search_path_surfaces_without_row_data`, `test_the_repository_does_not_swallow_or_rewrite_database_errors` |

Result: every scenario has at least one test; no gap was found.

## Earlier suites
- Existing test files modified by this change: `test_migrations_subjects.py` (`downgrade -1` to `downgrade 0002`, group 3). Authentication, roles, consent, subjects, enrollments, CLI, health and error tests are untouched and pass.
- Full suite: **668 passed**, also when the files run in reverse alphabetical order (no order dependence); coverage of `app` 98 %.

## Dependence on a fixed head
- All tests were searched for `0003`, `head`, `-1` and `alembic_version`. Tests that name a revision do so on purpose (`0001`, `0002`, `0003`) to test one step; those that use `head` follow the latest revision.
- One real fragility found and fixed: `test_downgrade_removes_tables_and_enum_but_keeps_the_extension` (a test of this change) used `downgrade -1`, relative to the head. Once change 6 adds a migration it would undo that one instead of `0004`. It now downgrades to `0003`. It passed before and after (robustness fix, no behaviour change), so there is no failing run to record.

## Isolation and cleanup
- `truncate_all` empties every public table except `alembic_version`, so the new tables are covered automatically (confirmed by the suite passing in reverse order and by the catalog test that rebuilds the dataset twice).
- Tests that migrate use only the guarded `*_test` database; the development database stays at `0003` (checked read-only).
- The mixed dataset, the parallel test and the catalog insert their own rows after `clean_db`.

## Deviations from test-first order (all groups of the change) and compensation
1. Group 3: one existing test edited (`downgrade -1` to `0002`); the I2 leak tests passed once the tables existed. Compensation: log-leak mutation (6/6 killed).
2. Groups 3 to 5: my own wrong expectations, corrected against evidence.
3. Group 4: the pinned fingerprint derives from the implementation. Compensation: 7/7 fixture mutations.
4. Group 5: the tie-break test was too weak, the mutation survived, the test was strengthened (13/13 killed in the end).
5. Group 6: the relative downgrade fix above (no behaviour change).
Details are in `2026-10-28-tdd-evidence.md`. There are no other deviations.
