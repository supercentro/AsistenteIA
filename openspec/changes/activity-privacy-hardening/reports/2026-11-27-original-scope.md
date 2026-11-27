# Restored original scope of the teacher dashboard (2026-11-26 and 27)

Branch `feature/activity-privacy-hardening-p1`, pull request #37, not merged. Base: `main` at `55bc6da`. Both switches stay false by default. Fictitious data and throwaway databases only; no Gemini call; no change of consent rules, persistent databases, infrastructure, secrets, workflows or OpenSpec/SpecBoot components.

## Owner decisions applied

- Keep the five metrics (weekly questions, active students, share without material, share without cited source, citations per document) over the original window of 12 weeks; remove the four rules of P1 before any merge.
- Keep one correction: deleted documents are not listed (V7).
- Record the processing of earlier activity (TD-072); change no consent rule; the legal evaluation of real data is an activation condition of its own, and consent is not assumed to be the only legal basis.

- (2026-11-27) The new wording of the privacy note is approved; a rate of 0 or 1 and `enrolled_students` minus `active_students` join the candidates for acceptance, not accepted for production.

## Test-first evidence

| Step | Command | Failing run before the change | After |
|---|---|---|---|
| Restored scope (backend) | `pytest` on the activity unit tests | 11 failed, 5 passed | pass |
| Note that anonymity is not guaranteed | `vitest run src/pages/TeacherActivityPage.test.tsx` | 1 failed, 53 passed | pass |
| Note reaches the whole class (review finding 4) | same | 1 failed, 53 passed (`/sobre una persona, sobre pocas o sobre toda la clase/` did not match) | pass |

**Deviation, justified:** the characterisations (V6a to V12, the rate of 0 or 1, enrolled minus active, TD-072) describe behaviour that exists, so they pass when written and have no failing run. Compensation: mutation checks.

## Mutation checks (sources restored by hash)

- Aggregate: 14 of 14 caught (V7 merge, group of 4 and strict comparison, subject and denominator thresholds for rates and documents, one appearance per document, retrieved answers as citations, unenrolment marker, open week, teacher scope, enrolment scope, documents not ready). The first pass left 3 alive; tests were added.
- TD-072: 2 of 2 caught (a filter by the current policy; a filter by messages after the acceptance).

## Independent adversarial review

By a separate agent (base standards 9.8).

**First pass: FAIL, no Blocker, 2 Major.** It found no undue access, no direct exposure and no regression.

| # | Severity | Finding | Fix | Verification |
|---|---|---|---|---|
| 1 | Major | The spec and a test said the withheld figure of a deleted document could not be computed; it still follows through V8 and V9 | Wording, scenario "limit of the correction", test names, TD-069 | fixed |
| 2 | Major | The read does not consider what a student accepted; enabling would process earlier history | Recorded: TD-072, spec requirement, contract, data model, two characterisations. No code change (owner decision) | fixed as a record; **the condition stays open for activation** |
| 3 | Minor | No test of V8 or V9 | Added | fixed |
| 4 | Minor | Rate of 0 or 1 and enrolled minus active missing; the note understated | Added and reworded | fixed |
| 5 | Minor | Contradictions in the contract, spec, proposal, earlier design and TD-069 | Corrected | fixed after the second round of minors |
| 6 | Question | The new wording of the note is not approved | Recorded in the design | approved by the owner on 2026-11-27 |
| 7 | Minor | Fixtures still modelled deleted documents | Updated | fixed |
| 8 | Minor | The Gemini ledger and foreign files must not be staged | Nothing staged | applies at commit time |

Context for finding 2: the chat requires consent for the policy in force when a message is written (`rag_service`), so history was written under earlier texts, not without consent.

**Second pass: PASS WITH GAPS, no open Blocker or Major** for a technical merge with both switches false. New, all Minor: N1 evidence not recorded (this report); N2 stale proposal (corrected); N3 status of the two further inferences, a contract sentence that suggested one could name the student, withdrawn consent missing from TD-072 (corrected). The N1 to N3 corrections were made after that pass and were not re-reviewed.

The reviewer's first activity run shared the throwaway database with a full integration run of the implementing session. That run (156 failed, 428 errors) is discarded and was repeated alone.

## Gates

| Gate | Result |
|---|---|
| Backend unit | 1829 passed, 110 skipped, 2 xfailed, 4 failed (`test_migration_settings`, `test_worker_health`, 2 of `test_worker_settings`: failures of this host seen before this change, in files it does not touch) |
| Backend integration (`-m "not role_bound and not realmodel"`) | 1045 passed, 39 skipped, 0 failed (run alone on a throwaway database) |
| Role-bound API routes | 5 passed, 1 skipped (Linux only) |
| `ruff check --no-cache`, `ruff format --check` | clean |
| `mypy --strict app tests` | blocked on the local host by Application Control (not worked around); on CI: no issues in 305 source files |
| Frontend `vitest` | 674 passed, 1 skipped |
| Frontend typecheck, ESLint, Prettier, API types, build | clean |
| Playwright, mocked and smoke | 34 of 34 |
| `openspec validate --all --strict` | 29 of 29 |
| Local demo, three subjects | five metrics shown, withheld figures as «Datos insuficientes», no browser error, no horizontal overflow at 320 px |
| Other role-bound suites, Linux-only tests, `alembic check` | run on CI, see below |

## CI of pull request #37 (commit `85cfa9b`, Linux)

All jobs green on both triggers (push and pull request). Counts of the pull request run (46037629531): `ruff` clean; `mypy --strict app tests` no issues in 305 source files; unit 1943 passed, 2 xfailed (the 4 local failures do not occur); integration 1084 passed, none skipped; `privileges` job 1140 tests (148 matrix, 453 role-bound, 539 under the production roles), 0 failed, 0 skipped; `alembic check` no new operations; `db-verify` drift check passed; frontend 674 passed, 1 skipped, API types up to date, build, mocked Playwright 34 of 34; `pip-audit` and `npm audit` found no known vulnerability.

## What blocks what

**Technical integration (both switches false):** no open Blocker or Major. The wording of the note is approved (2026-11-27). CI is green on the pull request. Merging needs the owner's authorisation.

**Activation with real data only:** legal evaluation of the earlier history (TD-072: purpose, legal basis without assuming consent is the only one, information to students); recorded acceptance of the inference risks with its institutional scope and legal review of the group size (TD-069); F8 (TD-071) and F7 (TD-070), each with its own treatment; the policy text that tells students what a teacher can learn and the consent version.

## Residual risks (none mitigated)

- Candidates for formal acceptance, none accepted for production: V6b, V8 to V12; V3, V6a, F6 (reopened by the original rules); a rate of 0 or 1; `enrolled_students` minus `active_students`.
- Own treatment: F8 (TD-071), F7 (TD-070), earlier activity (TD-072).
- By design: a student's own erasure can be noticed between reads.
