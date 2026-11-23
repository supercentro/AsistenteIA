# Tasks

> Proposal prepared after Explore (2026-11-23); incorporated into the roadmap as a future feature by the owner on 2026-11-23 with provisional rules (N = 5, weekly, 90 days, aggregate-only, no new storage, disabled until the privacy and consent conditions are met); **not approved for implementation and not implemented**. R-D1 is approved for the aggregate metrics (2026-11-23) and `base-standards.md` §8 and `openspec/config.yaml` carry the minimal wording; the §9.4 sentence and the `backend-standards.md` section are tasks 2.2 of this change. The remaining decisions are in `design.md` (policy, consent version, legal review). Individual analytics, profiling, migrations, stored events and any dashboard are out of scope. No commit, push, pull request or merge without a new authorisation; no real Gemini call. Follows `docs/openspec-tasks-mandatory-steps.md`.

## 0. Branch

- [ ] 0.1 Step 0: create the branch `feature/activity-events-and-metrics` from `main` before any code change. Merge only through a Pull Request.

## 1. Tests first

- [ ] 1.1 Repository aggregates on a fixture database: questions per period, distinct active students, no-material share, share without cited source (with the derived `attribution`), appearances of cited sources per document and documents with none; unenrolled students and other subjects are not counted
- [ ] 1.2 Suppression: N-1, N and N+1 students per cell, per period and per document; rates with a denominator below N; a subject below N active students shows only the enrolled count
- [ ] 1.3 Privacy by shape: a test that walks the response schema and fails if any field can hold message text, a student id, a name or an e-mail; the window is limited to 90 days and the granularity to the allowed values
- [ ] 1.4 Authorisation: the owner reads; another teacher gets the same answer as for an unknown subject; a student and an anonymous caller are refused; the aggregate query takes the teacher and joins `subjects.teacher_id`
- [ ] 1.5 Erasure: deleting a conversation, all conversations of a student, and unenrolling lowers the next result; nothing is stored by the call
- [ ] 1.6 Run the new tests before any implementation and record the failing run in `reports/`

## 2. Implementation (backend, no migration)

- [ ] 2.1 Aggregate repository and service with the suppression rules; one route in the teacher area, switched off by a setting until D-M2 is met; schemas without free text
- [ ] 2.2 `docs/api-spec.yml` (additive path and schemas), the role-bound scenario required by `test_least_privilege_coverage.py`, and, reserved for this change by the owner, the sentence of `docs/base-standards.md` §9.4 and the section of `docs/backend-standards.md` §9 (the diffs proposed in the design, applied with the owner's approval)
- [ ] 2.3 Mutation checks: suppression threshold off by one, enrolled filter removed, owner check removed, text field added to the schema, window limit removed
- [ ] 2.4 `ruff check --no-cache`, `ruff format --check`, `mypy --strict`

## 3. Verification

- [ ] 3.1 Step N: review the existing tests that touch the chat tables and the teacher routes
- [ ] 3.2 Step N+1: unit, integration and role-bound suites; database state before and after (the change writes nothing)
- [ ] 3.3 Step N+2: manual endpoint test with a teacher, another teacher and a student on the development stack with fictitious data
- [ ] 3.4 Step N+3: not applicable (no user-facing flow in this change)
- [ ] 3.5 Step N+4: documentation: API contract, data protection section of `docs/data-model.md`, `docs/technical-debt.md` (residual re-identification risk), `docs/roadmap.md`
- [ ] 3.6 Independent adversarial review with a privacy focus: re-identification, differencing, authorisation, the shape of the response, erasure
- [ ] 3.7 Final gates of `docs/base-standards.md` section 9 re-run after the last change; `openspec validate --all --strict`; CI on Linux after the pull request

> Open decisions: R-D1, D-M1 (N), D-M2 (policy, legal review, consent version, switched off until then), D-M3, D-M5, D-M6, D-M7, R-D7 (no new storage in this slice).
