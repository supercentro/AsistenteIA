# Independent adversarial review (task 3.6)

Date: 2026-11-23. Reviewer: a separate subagent with a clean context and no write access, privacy focus (re-identification, differencing, authorisation, shape of the response, erasure). It ran the three unit modules (46 passed) and read the rest; it did not run the integration suites. Fictitious data only.

Verdict of the reviewer on the first pass: **FAIL for enabling, PASS WITH GAPS for merging it switched off**, with two blocking items (F2, F3) and one owner decision (F1).

| # | Sev | Finding | Disposition |
|---|---|---|---|
| F1 | Major | The teacher controls enrolment and unenrolment deletes nothing, so reading, unenrolling a student, reading again and re-enrolling reveals that student's contribution to the shown figures for any class of 6 or more | **Open, needs the owner's decision.** Registered in TD-069 with the options (a minimum number of enrolled students, counting unenrolled students, an access record). The capability stays off; it must not be enabled before the decision |
| F2 | Major | Dates next to the calendar limits (`end=9999-12-31`, `end=0001-01-05`) raised an uncaught `OverflowError`, a 500 against the spec | **Fixed**: the arithmetic is guarded and answers 422; unit tests (4 cases), HTTP tests (`limit`, `calendar`, `datetime`) and the real-server test |
| F3 | Major | Two descriptions in `docs/api-spec.yml` were unquoted flow mappings; a comma split them and created bogus keys, also in the generated frontend types | **Fixed**: quoted, types regenerated, and a contract test fails on any unexpected key of the activity schemas |
| F4 | Minor | Window-wide totals (`active_students`, rates, document figures) differ between windows that differ by whole weeks; the docstring overstated the protection | **Fixed the wording** (service docstring); the risk is in TD-069 |
| F5 | Minor | A deleted document that was cited was listed even when its figure was withheld, so its presence disclosed a citation | **Fixed**: listed only when its figure is shown; tests for N-1, N and a suppressed subject |
| F6 | Minor | A shown cell counts all the questions of its 5 or more students, so one heavy user can dominate it | **Accepted**, in TD-069 |
| F7 | Minor | Rows and answer text of 12 weeks are held in memory; no rate limit | **Accepted**, TD-070 |
| F8 | Minor | Missing tests: extreme dates, future windows, datetime strings, a deleted document below N | **Added** |
| F9 | Minor | `tasks.md` not updated | **Done**; 3.2 and 3.7 stay open until the CI of the pull request |

Not found by the reviewer: IDOR through `subject_id`, a way to distinguish another teacher's subject from an unknown one, SQL injection, writes, a privilege gap for the application role, free text or identifiers in the schema.

Final verdict after the fixes: **PASS WITH GAPS for a pull request with the capability switched off**; F1 is an open decision of the owner and a condition to enable the capability, not a condition to merge it switched off.
