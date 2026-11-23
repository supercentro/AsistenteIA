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


### 1b. Candidate finding found while specifying A2 (needs its own authorisation, D-P11)
- [ ] 1.7 (the arithmetic was observed with a throwaway probe on 2026-11-23: a cell 10 -> 11 in the same week and `active_students` 5 -> 6 after a newcomer asked; the repository test is pending) Demonstrate the candidate V5 (two reads in the same week differ by what was asked in between; an added student's questions appear in the current week) with an in-memory test, record it in `reports/`, and decide A2b (complete weeks only) separately

### 2. Result
- [x] 2.1 Reports in `reports/` with the table of vectors: reproduced, not reproduced or characterised, and which figures leak
- [x] 2.2 A mutation check of each test: change the aggregate so that the vector disappears and show that the test passes, then restore it
- [x] 2.3 (done, F8 confirmed end to end; see `reports/2026-11-23-demonstration-results.md`) With the owner's authorisation (D-P2): an end-to-end test on a disposable test database with `TEACHER_ACTIVITY_ENABLED=true` for the test only, fictitious data: register accounts, enrol them by email, ask, read; record F8 as confirmed or refuted
- [x] 2.4 `docs/technical-debt.md`, authorised by the owner: F8 recorded as TD-071 (Major, confirmed end to end, open) and TD-069 pointing to the evidence of V1 and V3; the roadmap is not changed

## B. Mitigation (blocked until the owner approves each option)

### 3. Tests first, per approved package (each package waits for its own approval)
- [ ] 3.1 P1 (D-P4, D-P5): the figures of V4 bounded (C) and the window-wide figures removed or computed on fixed blocks (F2a or F2b), `start` and `end` restricted (F); the property tests of V3 and V4 now pass unchanged and their `xfail` markers are removed in the same change; the contract, the generated types and the dashboard copy
- [ ] 3.2a P2 (D-P9a to D-P9f, D-P12), tests first: replace the xfail of the V1 property by the two-world non-interference test with fixed seeds (service, in memory) and the edge cases of the design; run them before the rule and record the failing run
- [ ] 3.2b P2: migration `0008` (the nullable column `subjects.last_unenrolment_at`, the backfill with the migration time, a working `downgrade`), the `Subject` model, `alembic check` clean, migration tests
- [ ] 3.2c P2: `EnrollmentRepository.delete_for_teacher_subject` sets the marker (`GREATEST` with the database clock) in the same transaction **before** deleting the enrolment (advisory lock, subject row, enrolment row); a removal that deletes nothing raises 404 and rolls back; tests of an inactive student, rollback, a failing update, 404, two removals, re-enrolment, account and conversation deletion, and the static test of the single path
- [ ] 3.2d P2: `ActivityService` and the repository compute the effective weeks; the response window and the shape of 0 weeks; the existing activity tests reviewed; the V1 end-to-end test of `test_activity_inference_f8.py` flipped to the non-interference expectation; the F8 end-to-end tests unchanged
- [ ] 3.2e P2: concurrency tests (the pattern of `test_chat_enrollment_lock.py`: the turn first, the removal first, two removals, the lock order against the document upload and against the deletion of the subject, with no deadlock)
- [ ] 3.2e2 P2: the activity read in one `REPEATABLE READ` read-only snapshot, set before its first statement, and a deterministic race test (a separate session commits the removal between two statements of the read); the mutation check that splits the read
- [ ] 3.2f P2: `backend/app/db_privileges.py`, the inventory and the matrix tests, the role-bound suites, the exposure test; the grant reaches an existing environment through `db-migrate` then `db-verify` (never by hand), rehearsed by the CI job `privileges`; the procedure is written in `docs/development_guide.md`; the development database is not touched without the owner's authorisation
- [ ] 3.2g P2: `docs/api-spec.yml` (`weeks` minimum 0, the descriptions of the effective window, no new field), the generated types, the contract tests; `docs/data-model.md`; one bullet of `docs/backend-standards.md` section 9
- [ ] 3.2h P2: dashboard states (limited and no weeks) with the copy approved in D-P9e, the strings, the judgement-word scan, the component tests, the mocked Playwright spec and the Playwright MCP run
- [ ] 3.2i P2: mutation checks (remove the filter, a conditional marker, a decreasing marker, the write after the commit, another deletion path) and the independent adversarial review; then, and only then, TD-069 records the unenrolment form of F1 as mitigated
- [ ] 3.3 P3 (D-P7, D-P10): the written decision on F8 recorded in `docs/technical-debt.md`; only the mechanisms the owner approves (I2, I6, or later I3 or I8); a test of each approved mechanism against the end-to-end F8 scenario; F8 stays open until the strong option exists
- [ ] 3.4 P4 (D-P6): a persistent record with its retention, its reviewer and an erasure rule; a test that the record holds no figure and no text
- [ ] 3.5 P5 (D-P8): a limit of reads, only as approved
- [ ] 3.6 A2b (D-P11, only after the demonstration 1.7 and the owner's decision): show only ended weeks; the effective weeks are those with `c(M) <= w <= L`, the default `end` is the last Sunday and an `end` inside the open week is clamped; the temporal non-interference test (two states that differ only in messages or enrolments of the current week give identical responses, and the answer changes by exactly one week between Sunday 23:59:59 and Monday 00:00:00); the mutation checks (let the open week through, clamp to the wrong day); the dashboard notice «Se muestran solo semanas completas.» if approved; the contract and the dashboard states edited together with 3.2g and 3.2h

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
