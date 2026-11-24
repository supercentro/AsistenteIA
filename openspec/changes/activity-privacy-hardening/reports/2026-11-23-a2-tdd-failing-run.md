# TDD failing run of A2 + A2b (task 3.2a)

Date: 2026-11-23. Fictitious data, in-memory repository, no Gemini call. The spec was corrected first (the property of V1 is independence from the cut-off past, see `design.md`), then the tests were written and run **before** any production change.

Command: `uv run --no-sync python -m pytest tests/unit/test_activity_window_rule.py -q`

Result before the implementation: **61 failed, 29 passed** (90 tests, 10 s).

| Group | Failing | Why |
|---|---|---|
| Independence from the cut-off past, random worlds (25 seeds) | 25 of 25 | the service shows the weeks the removal should hide |
| Independence from the open week (V5), random worlds (25 seeds) | 25 of 25 | the open week is part of the window |
| Rule of the window with a marker (mid-week, Monday 00:00, Sunday night, long ago) | 4 of 4 | the service ignores the marker |
| No whole week remains (marker in the open or the last ended week) | 2 of 2 | idem |
| Ended weeks only (default window, clamp of `end`, start inside the open week) | 3 of 3 | the default window ends today |
| Weeks before the marker not shown even with data; two reads in one week | 2 of 2 | idem |

The 29 that pass before the change are the controls and the rules that must not change: the same random worlds **differ** without the marker (25 of 25), the weaker formulation holds without any mitigation unless the student is re-enrolled (it is why it is not accepted as evidence), the Sunday and Monday windows, the old marker, a null marker, and the existing window errors.
