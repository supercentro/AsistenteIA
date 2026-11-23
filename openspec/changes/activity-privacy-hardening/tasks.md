# Tasks

> Specified after the owner's decisions of 2026-11-23 (D-H1 to D-H7 in `design.md`); **not implemented**. Part A needs the owner's authorisation to start (D-P1, D-P2). Part B is **blocked** until the owner approves each package (D-P4 to D-P10): no migration, change of contract, retention of an enrolment after unenrolment, identity verification or persistent access record is implemented without it. No Gemini call; both switches stay false by default; F1 (Major), F6, F7 and the unconfirmed F8 stay open until their tests pass. Follows `docs/openspec-tasks-mandatory-steps.md`.

## 0. Branch

- [x] 0.1 Step 0: create the branch `feature/activity-privacy-hardening` from `main` before any code change. Merge only through a Pull Request.

## A. Demonstration (needs D-P1 and, for A.7, D-P2)

### 1. Tests first
- [x] 1.1 Test V1 with the in-memory repository: six students with 2, 2, 2, 2, 2 and 3 questions, a read, the removal of the student with 3, a read; assert that the difference is not that student's contribution (it fails today); record the failing run in `reports/`
- [x] 1.2 Test V2 at service level: four controlled accounts with 3 questions each and one real student with 2, and the same with a real student with none; assert that neither the figure nor its presence reveals the real student (it fails today)
- [x] 1.3 Test V3: a student active only in week 1, the windows of weeks 1 to 12 and 2 to 13; assert that no window-wide figure moves by that student's contribution; record which figures leak
- [x] 1.4 Characterise V4: five students with 50, 1, 1, 1 and 1 questions; record the dominance as a documented limit, not as a pass or a fail
- [x] 1.5 (in `test_activity_inference_f8.py`, needs a database) Erasure invariant (passes today and must keep passing): conversations deleted or account deleted, then the next read excludes the student
- [x] 1.6 Run the new tests before any mitigation and record the failing run (command and failure summary) in `reports/`

### 2. Result
- [x] 2.1 Reports in `reports/` with the table of vectors: reproduced, not reproduced or characterised, and which figures leak
- [x] 2.2 A mutation check of each test: change the aggregate so that the vector disappears and show that the test passes, then restore it
- [x] 2.3 (done, F8 confirmed end to end; see `reports/2026-11-23-demonstration-results.md`) With the owner's authorisation (D-P2): an end-to-end test on a disposable test database with `TEACHER_ACTIVITY_ENABLED=true` for the test only, fictitious data: register accounts, enrol them by email, ask, read; record F8 as confirmed or refuted
- [x] 2.4 `docs/technical-debt.md`, authorised by the owner: F8 recorded as TD-071 (Major, confirmed end to end, open) and TD-069 pointing to the evidence of V1 and V3; the roadmap is not changed

## B. Mitigation (blocked until the owner approves each option)

### 3. Tests first, per approved package (each package waits for its own approval)
- [ ] 3.1 P1 (D-P4, D-P5): the figures of V4 bounded (C) and the window-wide figures removed or computed on fixed blocks (F2a or F2b), `start` and `end` restricted (F); the property tests of V3 and V4 now pass unchanged and their `xfail` markers are removed in the same change; the contract, the generated types and the dashboard copy
- [ ] 3.2 P2 (D-P9): a migration with a working `downgrade` for the marker of the last unenrolment on `subjects`; the service computes the figures only over whole weeks after the marker; the V1 property test passes unchanged (service and real SQL); the erasure tests still pass and no row about the student remains; `alembic check` clean
- [ ] 3.3 P3 (D-P7, D-P10): the written decision on F8 recorded in `docs/technical-debt.md`; only the mechanisms the owner approves (I2, I6, or later I3 or I8); a test of each approved mechanism against the end-to-end F8 scenario; F8 stays open until the strong option exists
- [ ] 3.4 P4 (D-P6): a persistent record with its retention, its reviewer and an erasure rule; a test that the record holds no figure and no text
- [ ] 3.5 P5 (D-P8): a limit of reads, only as approved

### 4. Implementation
- [ ] 4.1 Implement only the approved packages, one at a time, test first
- [ ] 4.2 `docs/data-model.md`, `docs/api-spec.yml` and the generated types only for an approved package that changes them; `docs/backend-standards.md` section 9 only if a rule changes

## 5. Verification

- [ ] 5.1 Step N: review and update the existing tests of the aggregate, the dashboard and the enrolments
- [ ] 5.2 Step N+1: run the unit and integration suites; database state before and after
- [ ] 5.3 Step N+2: manual endpoint test with `curl` on the test stack with fictitious data (owner, another teacher, student, anonymous, switch off, the vectors V1 and V3 repeated)
- [ ] 5.4 Step N+3: Playwright MCP run on the dashboard with the mocked API if the page or its copy changed, then the Playwright Test suite
- [ ] 5.5 Step N+4: documentation, with the owner's authorisation
- [ ] 5.6 Independent adversarial review with a privacy focus: each vector, each residual risk, the erasure test, the classification of the controls
- [ ] 5.7 Final gates of `docs/base-standards.md` section 9 re-run after the last change; `openspec validate --all --strict`; CI on Linux after the pull request

> Out of this change and not authorised: enabling either switch, any use with real students, a legal opinion on N, archiving, any change not listed in an approved option.
