# Independent adversarial review (task 3.6)

Date: 2026-11-23. Reviewer: a separate subagent with a clean context and no write access, privacy and accessibility focus. It ran the five test files (42 of 42), `npm run typecheck` and `npm run lint`, and a throwaway script for the wording scan; the rest is by reading. Fictitious data only. No backend, contract, data model, workflow or dependency change (checked by the reviewer with `git diff`).

Verdict of the reviewer: **PASS WITH GAPS**, no Blocker, no Major.

| # | Sev | Finding | Disposition |
|---|---|---|---|
| F1 | Minor | No test checked a bar width or the formatters; `barWidth` could return a constant and every test passed | **Fixed**: `activityFormat.test.ts` (clamping, zero maximum, no NaN) and a page test that asserts the width of each bar |
| F2 | Minor | The judgement-word regex missed most Spanish forms (correctas, erróneas, comprensión, aprenden, más usados...) and scanned only 13 labels | **Fixed**: stems, a scan of every string of the copy with the functions called on sample arguments, an explicit allowance only for the note «no mide comprensión ni uso del material», and tests that the scan catches 13 forms and lets four normal phrases through |
| F3 | Minor | The note said that only aggregates of at least N students are shown, but the enrolled count is always shown | **Fixed** (copy): «Las cifras de actividad solo se muestran cuando provienen de al menos N estudiantes...» |
| F4 | Minor | «Estudiantes activos» was not defined | **Fixed** (copy): «Estudiantes que hicieron al menos una pregunta en estas semanas.» The owner reviews the final texts |
| F5 | Minor | No focus management: after the link the focus stayed on `body` | **Fixed**: the heading takes the focus once the figures appear (`useFocusOnMount`), with a test |
| F6 | Minor | A hostile or right-to-left file name could be visually reordered | **Fixed**: the name is wrapped in `<bdi>`; a test with HTML and a bidirectional override, duplicated and deleted names and a 300-character name |
| F7 | Minor | Untested: strict mode double mount, duplicate or null-id rows, the key by subject, the 401 branch, a flagged dev server for the e2e spec | **Partly fixed**: strict mode test (one request), duplicates and null ids; the key by subject, the 401 branch (it relies on the session ending as in the rest of the app) and the flagged server (documented in the development guide and the spec header) stay as noted limits |
| F8 | Question | Does the interface worsen F1? | **No worsening found**: separate page, link outside the enrolments, no window parameter, polling, export, timestamp or kept response. The read, unenrol, read, re-enrol loop is F1 itself and stays open in TD-069 |

Not found: any write to browser storage, URL state or copy or print affordance, an `any`, an invalid `dl` structure, missing captions or headers, a way for a student or an anonymous caller to reach the page or trigger the request, a way for the flag to flip at runtime or reach a production build, server text shown to the user.

Final verdict after the fixes: **PASS WITH GAPS, advisable to prepare the pull request** with both switches off. F1, F6 and F7 of the backend capability (TD-069, TD-070) stay open and are the conditions to enable it for real students.
