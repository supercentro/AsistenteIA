# Mutation checks of A2 + A2b

Date: 2026-11-23. Each mutant changes production code temporarily, the named tests run, and the file is restored from a copy (the working tree has no residue). A mutant counts as detected when a test fails (pytest exit 1).

| # | Mutant | Detected by | Result |
|---|---|---|---|
| M1 | no filter by the marker (`_after_marker` returns the first week) | the window rule tests and the random worlds (25 seeds) | detected |
| M2 | the open week is let through (the last ended Sunday becomes the Sunday of this week) | the temporal property, the default window, the clamp | detected |
| M3 | the marker is written after the deletion (the draft order) | the order test of the statements and the static test | detected |
| M4 | the marker never advances (`LEAST` instead of `GREATEST`) | the monotonic test over three removals | detected |
| M5 | a removal that deletes nothing keeps the marker (the savepoint is committed) | the repository test that commits whatever happened | **survived the first time**: at API level the request handler also rolls back the 404, so the first test could not tell; the repository-level test was added and the mutant is now detected |
| M6 | the read is not one snapshot (the isolation level is removed from the dependency) | the dependency test (`repeatable read`, read only) | detected |
| M7 | a second place deletes an enrolment | the static single-path test | detected |
| M8 | the backfill marks every subject | the migration test | detected |
| M9 | the application role loses the column grant | the privilege matrix test | detected |
| F1 | the window line is shown with no weeks | the page test with no whole week | detected |
| F2 | the limit note is always shown | the page tests (full window, no weeks) | detected |
| F3 | the whole-weeks note is removed | the page tests (3 failed) | detected |

Second round, after the independent review (each of these survived the first round of tests, which is why the tests were added):

| # | Mutant | Detected by | Result |
|---|---|---|---|
| M10 | `now()` instead of `clock_timestamp()` for the marker | a turn that commits after the removal's transaction began (marker later than the turn) | detected |
| M11 | the marker is read without converting to UTC | a marker at UTC-5 near midnight | detected |
| M12 | the shared session keeps its connection while the snapshot opens (review M-1) | the route on a pool of one connection | detected |
| M13 | no margin of one hour after the Sunday | the boundary tests of `ended_weeks_today` | detected |

Not covered by a mutant: the choice of `REPEATABLE READ` against the race itself is shown by the control test (the same read without the snapshot returns the mixed answer), not by removing the option from the test's own session.
