# Step 12 Report - Independent Adversarial Review and Final Verification

- Date: 2026-11-28
- Change: frequent-questions-and-topics
- Reviewer: a separate subagent with a clean context, read-only on the repository (checksums of the 85 changed files were identical before and after), disposable databases only, no external model. Authorised by the owner.
- Corrections and final verification: the implementing session.

## Reviewer verdict

**FAIL** for closing or archiving the change, because of TD-073 and TD-074, two Major findings already registered and open. **No new Blocker or Major** in the implementation. Pull Request: GO to prepare one with both switches false, fictitious data only and both risks stated as open and not accepted. Enabling for real students: NO-GO.

## Findings and what was done

| # | Severity | Finding | Outcome |
|---|---|---|---|
| 1 | Major (known) | TD-073: controlled accounts reveal what one student's answers cited | Open, not mitigated, not accepted |
| 2 | Major (known) | TD-074: inference from one cut and from combined figures | Open, not mitigated, not accepted |
| 3 | Minor | A write overlapping a deletion answered 409 `no_pages` instead of 404 | Fixed |
| 4 | Minor | No test of the read-only repeatable-read snapshot of the ranking | Test added; fails by mutation |
| 5 | Minor | Teacher scope of the repository, `ready` filter and minimum of active students untested | Tests added; fail by mutation |
| 6 | Minor | A downgrade of `0009` loses the privacy marker | Documented (design, data model) |
| 7 | Minor | The subtraction against the document figure is not limited to the retroactive cut | TD-074 widened |
| 8 | Minor | A failed reload discarded the typed rows and showed nothing | Fixed |
| 9 | Minor | Rows editable while a save was in flight, then discarded | Fixed (read-only while saving). Leaving the page with unsaved rows still loses them (not changed) |
| 10 | Minor | Focus dropped to the document body | Fixed for cancel, for a successful save and (after the incremental review) for a successful reload. A refused save after confirming is not handled |
| 11 | Minor | Title length counted in UTF-16 units in the client | Fixed |
| 12 | Minor | Invisible titles accepted | Fixed: a title needs one visible character (spec, API description) |
| 13 | Minor | Ranking cost at large volumes; messages read with no topic defined | Early return added; measurements recorded in TD-076. The cost itself is not changed (owner decision) |
| 14 | Question | The warning says figures are not shown "until" the week named; they appear after that week ends | Corrected after the owner approved new wording: the figures "se mostrarán cuando esa semana termine" |
| 15 | Question | JSON bodies have no size limit and validation echoes extra keys (API-wide, earlier than this change) | Registered as TD-077 (owner decision); not corrected |
| 16 | Minor | The development guide overstated the effect of a missing `0009` | Corrected |

## Performance measured by the reviewer

Method and numbers are in TD-076. In short: the ranking costs 1.2 to 1.4 times the activity read; 0.7 s at 10,000 cited answers, 3.6 s at 50,000, 14.9 s at 200,000; eight concurrent rankings took up to 37.6 s at 50,000 with about 2 GB of memory. Seven statements, no N+1. The bookmark run adds 0.2 s to a 300-page file and up to 3.2 s with hostile outlines. Not measured: many subjects, mixed load, the real pilot size.

## Incremental adversarial review of the corrections

The same reviewer, again read-only (checksums of the 88 changed and untracked files identical before and after), reviewed what changed after the first review. Findings 3, 4, 5, 8, 11, 12 and 16 resolved; 6, 7 documented; 9 resolved with a test gap; 10 resolved on the paths named; 13 resolved as decided. It reran lint, `mypy`, the unit suite, 234 targeted topic tests, the frontend checks on a copy and `openspec validate`, and 19 of 20 mutations were caught. **No new Blocker or Major.** Verdict: **FAIL** for closing or archiving only (TD-073, TD-074); opening the Pull Request GO after C1; merge with both switches false GO with conditions and only with the owner's authorisation.

| # | Severity | Finding | Outcome |
|---|---|---|---|
| C1 | Minor | This report was stale | Corrected; gates repeated after the last edit |
| C2 | Minor | TD-076 said 100 students for every row | Corrected |
| C3 | Minor | TD-077 suggested that an anonymous body is not processed | Corrected |
| C4 | Minor | The roadmap said the review was pending | Corrected |
| C5 | Minor | No test that the page fields are read-only while saving | Test extended; fails by mutation |
| C6 | Minor | Focus dropped after a successful reload and after a refused confirmed save | Reload fixed (test first). The refused confirmed save is not handled |
| C7 | Note | A title made only of private-use or very new code points is refused | Recorded in TD-075 |
| C8 | Question | Playwright reuses `localhost:5173` and a unit test can reach port 8000 (both earlier than this change) | Not registered: for the owner |

**The switches do not make a merge inert.** Reading bookmarks and migration `0009` are not behind them: if a working tree mounted by running containers is updated to this code, `docker compose up` applies `0009` to its volume, and a worker restarted without `0009` fails every PDF that has bookmark topics.

The changes made after the incremental review (C1 to C7) were verified by the implementing session only.

## Final verification after the last change

Run after the last change of code, tests and technical documentation (only this report was completed afterwards):

| Command | Result |
|---|---|
| `mypy --strict app tests` (Linux) | no issues |
| `pytest tests/unit` (Linux) | 2062 passed, 11 skipped, 2 xfailed |
| `pytest tests/integration -m "not role_bound and not realmodel"` (Linux) | 1167 passed |
| `privilege_gate.sh` | 1142 tests, no drift, `alembic check` clean |
| `ruff check --no-cache`, `ruff format --check` | clean |
| `npm run lint / typecheck / format:check / check:api-types / build` | all exit 0 |
| `vitest run --coverage` (copy with the API on an unused port) | 712 passed, 1 skipped; 97.1% statements |
| `playwright test` (own server on port 5199) | 36 passed, 9 skipped |
| `npm audit` | 0 vulnerabilities |
| `openspec validate --all --strict` | 29 passed |

The real-server `curl` walkthrough above was run before the incremental review; no backend code changed after it. The remote CI is recorded in the Pull Request.

## Incidents of the verification

- A first Playwright run reused the owner's running frontend on port 5173 (`reuseExistingServer`): 7 tests failed because it does not run this branch. The mocked specs intercept every API route and the owner's API received no request from them. The suite was repeated against the worktree's server on port 5199 (`E2E_BASE_URL`).
- Unit test runs of the frontend let requests reach the owner's API: its log of 6 hours shows four `GET /api/v1/probe` (404) and one `GET /api/v1/subjects` (401), all rejected, nothing written. `/probe` belongs to `App.test.tsx` and `queryClient.test.tsx`, which this change does not modify; the origin of the other request was not established. Later runs used a copy whose API address is an unused port.

## Not verified

Bookmark coverage of real course PDF files; the editor's failed reload and read-only state in a real browser (component tests only); remote CI; the ranking under mixed load.
