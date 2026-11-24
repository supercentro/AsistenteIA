# Independent adversarial review of A2 + A2b (task 3.2i, 5.6)

Date: 2026-11-23. Reviewer: a separate agent with a clean context, privacy and concurrency focus, read-only (probes only outside the repository, on the throwaway cluster). It read the change, the code, the tests and the reports, ran the activity suites (159 tests passed on the first pass), lint and types, and the role-bound run of the enrolment API. No Gemini call.

Verdict of the reviewer: **PASS WITH GAPS**, no Blocker. It could not build a sequence of teacher actions that recovers a removed student's activity or shows a week that held one (it tried several removals, a student who never asked, re-enrolment, a second removal in the same week, week boundaries, a marker exactly at Monday 00:00, explicit `start` and `end`, a far-future `end`, a `start` inside the open week, a marker later than the window).

## Findings and what was done

| # | Sev | Finding | Disposition |
|---|---|---|---|
| M-1 | **Major** | The activity route held two pooled connections per request (the shared session that authenticates, then the snapshot): 15 concurrent reads on the default pool served none and blocked every route | **Fixed**: the snapshot dependency depends on the authentication and closes the shared session before it opens; test on a pool of one connection (`test_the_activity_read_needs_one_pooled_connection_at_a_time`); mutant M12 detected; lesson L52 |
| m-1 | Minor | A week counted as ended by the application clock at Monday 00:00 UTC, but a chat transaction that began before midnight keeps its `created_at` and can commit after it, so two reads around midnight could differ | **Fixed**: a week counts as ended one hour after its Sunday (`ENDED_GRACE`, `ended_weeks_today`); boundary tests; mutant M13; the contract, the spec and the design say so |
| m-2 | Minor | Two mutants survived: `now()` for `clock_timestamp()` and no conversion to UTC | **Fixed**: a test where a turn commits after the removal's transaction began and a marker at UTC-5 near midnight; mutants M10 and M11 detected |
| m-3 | Minor | Two tests compared the UTC window with the local date; the F8 helper depended on the wall clock | **Fixed**: UTC dates; the helper moves the questions back 14 days so it holds at any hour |
| m-4 | Minor | The static single-path test is a regex tripwire and can be bypassed | **Fixed (honest)**: the docstring says it is best effort and the patterns were widened; a database trigger was not added because it would also fire on the cascade of an erased account, which the owner excluded; the behaviour is shown by the integration tests |
| m-5 | Minor | `spec.md` still called A2b pending, the contract said a read is identical at any moment of a week (false for the enrolled count, deletions and the boundary), the `start` text was wrong with an explicit `end`, the generated types carried it | **Fixed**: spec, contract text and generated types reconciled |
| m-6 | Minor | The working tree holds unrelated changes (the Gemini ledger, `ci-reduce-actions-minutes`, the root guides) | **Handled**: they are not part of this change; the pull request stages only its files |
| q-1 | Question | The deploy order between the migration, the grant and the new code | **Fixed**: the development guide states that `db-migrate` and a clean `db-verify` run before the API takes traffic, and that otherwise a removal fails with 500 and rolls back as one unit |
| q-2 | Question | «reciente» of the approved copy is imprecise (the note can show for up to 13 weeks) | **Fixed on the owner's decision (2026-11-23)**: «Por un cambio en las inscripciones» in both states, without «reciente» |
| q-3 | Question | The backfill has no index on `conversations.subject_id` | **Noted** in the migration docstring (one semi-join scan; adding a column is a catalog change) |

Other observations of the reviewer: a combined run of the integration files that includes the migration tests in the middle makes the others error; the migration tests of this change were changed to leave the database at head, like the others of their family.

## Not found

No path shows the marker, a derived value or a week before it; no cross-teacher write (the update carries `teacher_id` and the delete only runs when it matched); no deadlock between the removal, the chat turn, the document upload, the deletion of the subject or another removal; the isolation level does not leak through the pool; `ActivityRepository` is reachable only through the snapshot session; withheld figures are never shown as zero.

## Final verdict after the fixes

**PASS WITH GAPS**, no open Blocker or Major (M-1 fixed and proven). The remaining gaps are the accepted open risks (F8 TD-071, V3, F6, F7, a student's own erasure). The unenrolment form of F1 (V1) and the open-week form (V5) are recorded in TD-069 as mitigated in this branch, pending merge and CI. **Advisable to prepare the pull request** with both switches off.
