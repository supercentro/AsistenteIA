# Lessons Learned

Process lessons from completed changes, with the preventive measure and the evidence behind each one. OpenSpec remains the source of truth for requirements and the SpecBoot skills remain the source of procedures; this document only records what went wrong or right, why, and which rule now prevents a repeat. Rules themselves live in `docs/base-standards.md` (section 9) and the other standards: link to them instead of copying.

Sources: `openspec/changes/archive/2026-10-27-project-scaffold/` and `.../2026-10-27-auth-and-roles/` (proposal, design, tasks, `reports/`), Pull Requests #1 and #2 of `supercentro/AsistenteIA`, `prompts.md` sections 10 and 11, `docs/technical-debt.md` and the Git history (`e0e115a`, `d63efd5`, `2e87864`, `3ca9b6b`).

## How to use and maintain this document

- Read the relevant lessons before proposing a change and when writing `tasks.md`; the standards below make the main ones mandatory.
- Update it when a change finds a defect, a process deviation, or a practice worth repeating (typically at review or archive time). Append the next free ID; change `Status` instead of deleting entries.
- **Ownership (no duplication):** product or code risks accepted at merge live only in `docs/technical-debt.md`; a lesson that concerns one of them cites its `TD-` ID and does not restate it. A lesson with no product risk (process, tooling, test suite) lives only here.
- Status values: `implemented` (a rule, test or document now prevents it), `pending` (measure agreed but not yet applied), `accepted` (deliberate trade-off).
- Evidence paths are relative to the repository root; `AR` = `openspec/changes/archive/2026-10-27-auth-and-roles/reports/`, `PS` = `openspec/changes/archive/2026-10-27-project-scaffold/reports/`.

## Summary

| ID | Lesson | Origin | Status |
|---|---|---|---|
| L01 | Tests must be seen failing before the code exists | project-scaffold, auth-and-roles | implemented (standard) |
| L02 | A review in the implementing session misses major defects | auth-and-roles | implemented (standard) |
| L03 | `TestClient` does not exercise Uvicorn or the transport | auth-and-roles | implemented (standard) |
| L04 | Errors and logs leaked sensitive data | auth-and-roles | implemented (standard) |
| L05 | Extreme and malformed inputs reached 500s or were accepted | auth-and-roles | implemented (standard) |
| L06 | Contracts, specs, tests and code drifted apart | planning, auth-and-roles | pending (automated check) |
| L07 | Migration versus model drift and amended migrations | auth-and-roles | pending (CI step) |
| L08 | AI-usage evidence and documentation skills were applied late | auth-and-roles, project-scaffold | pending |
| L09 | Residual risks were scattered before a register existed | auth-and-roles | implemented |
| L10 | Local environment pitfalls on Windows and Docker | project-scaffold | pending |
| L11 | Template defaults conflicted with the standards | project-scaffold | implemented |
| L12 | Unsafe defaults left for the deployment change | auth-and-roles | pending (change 13) |
| L13 | A rate-limit test depends on a real sleep | auth-and-roles | accepted |
| L14 | Practices that worked and should be repeated | both | implemented |

## Lessons

### L01. Tests must be seen failing before the code exists
- **Origin:** project-scaffold, auth-and-roles.
- **Problem:** the `/health` endpoint (scaffold) and the role guards `require_teacher`/`require_student` (auth) were written together with their surrounding code before their own tests; the tests passed on first run and were never observed failing.
- **Root cause:** infrastructure and endpoint were built in one step with the code they depend on, so the failing-test step was skipped.
- **Impact / repetition risk:** a test that never failed may not detect a regression. High: `tasks.md` says "write failing tests" but did not ask for evidence.
- **Solution applied:** the guard tests were validated afterwards by mutation (5 of 6 failed without the check); `/health` was covered by curl, including a real 503. Both deviations were recorded in the reports and the PR.
- **Preventive measure:** `docs/base-standards.md` section 9.2 requires evidence of the initial failure per functional group, a recorded justification for any deviation and a mutation check when a deviation happens.
- **Evidence:** `PS/2026-10-27-final-review.md` ("Process deviation: TDD on `GET /api/v1/health`"); `AR/2026-10-27-adversarial-review.md` (finding "Process" and attack 15); PR #2 section "TDD deviations (recorded)".

### L02. A review in the implementing session misses major defects
- **Origin:** auth-and-roles.
- **Problem:** the first adversarial review ran in the same session as the implementation (verdict PASS WITH GAPS). A second review by a separate subagent with a clean context found two further majors (F1, F2) and five minors.
- **Root cause:** the implementer shares the assumptions that produced the defects (here, tests that never passed through a real server).
- **Impact / repetition risk:** high for every change touching authentication, authorization or personal data. Both majors were exploitable and would have merged.
- **Solution applied:** independent review requested by the user before merge; F1-F7 fixed with regression tests, F8 resolved by the user's decision.
- **Preventive measure:** section 9.8 makes an independent review mandatory for those changes, with recorded findings, fixes and verdict, and no merge with open blockers or majors.
- **Evidence:** `AR/2026-10-27-adversarial-review.md` ("Follow-up" and header), `AR/2026-10-27-independent-review.md`; PR #2 "Security review"; `prompts.md` section 10.3.

### L03. `TestClient` does not exercise Uvicorn or the transport
- **Origin:** auth-and-roles (finding F2).
- **Problem:** Uvicorn trusts `X-Forwarded-For` from a loopback peer by default, so rotating the header bypassed both rate limiters. The in-process tests could not see it.
- **Root cause:** the tests used a client that does not go through the server, so server options (proxy headers, logging) were outside the test.
- **Impact / repetition risk:** security controls that depend on transport or server configuration are silently untested. Medium now, high for the deployment change.
- **Solution applied:** `--no-proxy-headers` in the Dockerfile and compose command; tests start a real Uvicorn with the Dockerfile's own arguments and a guard test on the flag; mutation (flag removed) failed three tests.
- **Preventive measure:** section 9.2 requires tests against a real server process for behaviour that depends on Uvicorn, headers, proxies, transport or server configuration.
- **Evidence:** `AR/2026-10-27-independent-review.md` (F2); `backend/tests/integration/test_review_hardening.py`; `docs/development_guide.md` (rate limiting section).

### L04. Errors and logs leaked sensitive data
- **Origin:** auth-and-roles (F1, F5).
- **Problem:** a statement-level database error wrote the full traceback, with bound parameters (email, Argon2id hash), to the server log; argparse echoed an unsupported `--password` value to stderr.
- **Root cause:** library defaults (SQLAlchemy parameter display, Starlette re-raise logged by Uvicorn, argparse error text) were not reviewed for data exposure, and no test captured the log of a failing statement.
- **Impact / repetition risk:** exposure of personal data and credentials in logs. High for any endpoint that sends emails or text as SQL parameters.
- **Solution applied:** `hide_parameters=True`, an outermost middleware that logs only exception type, method and path, and a `SafeArgumentParser`.
- **Preventive measure:** section 9.2 requires tests that errors and logs do not expose sensitive data (passwords, hashes, tokens, emails, SQL parameters) for new endpoints; `docs/backend-standards.md` keeps the logging MUSTs.
- **Evidence:** `AR/2026-10-27-independent-review.md` (F1, F5); `backend/tests/unit/test_error_hardening.py`, `backend/tests/integration/test_review_hardening.py`, `backend/tests/integration/test_auth_logging.py`.

### L05. Extreme and malformed inputs reached 500s or were accepted
- **Origin:** auth-and-roles.
- **Problem:** a NUL character in `name` caused a 500; the JWT accepted `aud` as a list, non-canonical `sub` and boolean time claims; names accepted line separators and bidirectional controls (F3); the CLI did not validate `--name` (F4).
- **Root cause:** validation covered normal input; edge cases were found only by probing.
- **Impact / repetition risk:** 500 responses and spoofable data. High: every new text field and identifier is exposed to the same cases.
- **Solution applied:** control-character, line-separator and bidi rejection, strict claim validation, a dead validator removed after a mutation proved it unused, and probes kept as regression tests.
- **Preventive measure:** section 9.2 requires negative and extreme-input cases (control characters, oversize, malformed identifiers, concurrency) that never produce a 500, in proportion to the change's scope.
- **Evidence:** `AR/2026-10-27-adversarial-review.md` (attacks 1, 2, 5, 6, 7 and findings); `AR/2026-10-27-independent-review.md` (F3, F4); `backend/tests/integration/test_adversarial_probes.py`.

### L06. Contracts, specs, tests and code drifted apart
- **Origin:** planning and auth-and-roles.
- **Problem:** the plan found the user story HU-3 using 403 where the contract says 404 and a ticket declaring no dependencies despite one; during auth the login `maxLength` was missing from `docs/api-spec.yml` (F6) and a spec said "repeats a single character" while the code required eight distinct ones. Later, `readme.md` HU-1 said 403 for another teacher's subject while the decision was 404.
- **Root cause:** decisions and constants were copied by hand across `readme.md`, `docs/api-spec.yml`, specs, tests and code, and verification was manual.
- **Impact / repetition risk:** high; each new endpoint multiplies the places that must agree.
- **Solution applied:** manual reconciliation at planning and before archive; the HU-1 wording is corrected on the change branch `feature/subjects-and-enrollments` (`db676a5`).
- **Preventive measure:** section 9.8 requires traceability between specs, contract, tests and behaviour before archive. Pending: an automated test comparing the app's OpenAPI with `docs/api-spec.yml` (paths, methods, status codes).
- **Evidence:** `prompts.md` section 11.1; `AR/2026-10-27-adversarial-review.md` (Spec finding); `AR/2026-10-27-independent-review.md` (F6).

### L07. Migration versus model drift and amended migrations
- **Origin:** auth-and-roles (F8).
- **Problem:** the ASCII-only email decision required a database check that was added to migration `0002` before it was merged, leaving local databases with an earlier `0002`. `alembic check` was run manually and is not a CI step.
- **Root cause:** the decision came late in the review and the pipeline has no drift gate.
- **Impact / repetition risk:** medium; a merged migration must never be edited, and drift between models and migrations could reach `main` unnoticed.
- **Solution applied:** local databases re-run `downgrade -1` and `upgrade head` (documented); `alembic check` was clean on the final run.
- **Preventive measure:** section 9.7 requires `alembic check` to be clean for every schema change and forbids editing a merged migration. Pending: run it in CI.
- **Evidence:** `AR/2026-10-27-step-9-unit-test-and-db-verification.md` (final run); `AR/2026-10-27-independent-review.md` (F8); `docs/development_guide.md` (note on local databases); `.github/workflows/ci.yml` (no `alembic check` step).

### L08. AI-usage evidence and documentation skills were applied late
- **Origin:** auth-and-roles, project-scaffold.
- **Problem:** the `update-docs` skill was applied as a manual checklist during auth and invoked itself only at the end, at the user's request; the `prompts.md` records for both changes were written after the fact, the scaffold one only after the auth record, from reports, Git history and the session.
- **Root cause:** the evidence of prompts and decisions lived only in the conversation, which is lost when the context is compacted.
- **Impact / repetition risk:** medium to high; incomplete or reconstructed AI-usage records weaken the academic deliverable.
- **Solution applied:** both records were completed with explicit labels for literal fragments versus summaries.
- **Preventive measure (pending):** keep a short AI-usage notes file in the change's `reports/` folder while applying, invoke `update-docs` in the documentation group, and propose the `prompts.md` entry at archive time (with the user's approval).
- **Evidence:** `prompts.md` sections 10 and 11; commits `ae7cbae` and `a32296e`; PR #2 ("`update-docs` was run").

### L09. Residual risks were scattered before a register existed
- **Origin:** auth-and-roles.
- **Problem:** residual risks lived in the PR body, review reports and the development guide, with no single list or owner.
- **Root cause:** no register or rule requiring one.
- **Impact / repetition risk:** medium; accepted risks get forgotten before the deployment change.
- **Solution applied:** `docs/technical-debt.md` (TD-001 to TD-015) and an ownership row in `docs/documentation-standards.md`.
- **Preventive measure:** the closing tasks of each change add a row per accepted risk; no risk is recorded in two places (see "How to use").
- **Evidence:** commit `93c58da`; `docs/technical-debt.md`.

### L10. Local environment pitfalls on Windows and Docker
- **Origin:** project-scaffold.
- **Problem:** port 5432 was taken by other local containers; `localhost` resolved to IPv6 first and connections hung; line endings differ on Windows (Prettier is configured with `endOfLine: auto`); `pip-audit` timed out reaching the network in the final auth runs.
- **Root cause:** assumptions about a clean machine.
- **Impact / repetition risk:** high but low severity; each costs time.
- **Solution applied:** database published on `127.0.0.1:5442`, hosts written as `127.0.0.1`, Prettier `endOfLine: auto`, CI used as the audit confirmation.
- **Preventive measure (pending):** a short "known environment issues" section in `docs/development_guide.md`.
- **Evidence:** `prompts.md` section 11.4; `docs/development_guide.md`; `frontend/.prettierrc.json`; `AR/2026-10-27-step-9-unit-test-and-db-verification.md`.

### L11. Template defaults conflicted with the standards
- **Origin:** project-scaffold.
- **Problem:** the Vite template brought React 19, TypeScript 7 and oxlint, against the standards (React 18, TypeScript strict 5.x, ESLint); ESLint 10 conflicted with `eslint-plugin-jsx-a11y`.
- **Root cause:** generated defaults were not compared with the documented stack.
- **Impact / repetition risk:** low now (no dependency is added in the next change), recurring with every new tool.
- **Solution applied:** versions pinned to the standards, lock files committed, leftover template file removed.
- **Preventive measure:** section 9.3 already requires pinned versions; compare any generated or added dependency with `docs/*-standards.md` before committing.
- **Evidence:** `prompts.md` section 11.4; `PS/2026-10-27-final-review.md` (cleanups).

### L12. Unsafe defaults left for the deployment change
- **Origin:** auth-and-roles.
- **Problem:** `APP_ENV` defaults to `development` and the OpenAPI docs are open in every environment; the in-memory rate limit has deployment limits.
- **Root cause:** development-friendly defaults chosen first, with the production decision deferred.
- **Impact / repetition risk:** a deployment that forgets configuration runs with development behaviour.
- **Solution applied:** deferred and tracked; no code change.
- **Preventive measure:** tracked as TD-001 and TD-002 (owner: change 13); not restated here.
- **Evidence:** `AR/2026-10-27-adversarial-review.md` (Question rows); `docs/technical-debt.md`.

### L13. A rate-limit test depends on a real sleep
- **Origin:** auth-and-roles.
- **Problem:** the rate-limit window test sleeps 1.2 seconds because the `limits` library has no injectable clock, instead of the injected clock planned in the design.
- **Root cause:** library limitation.
- **Impact / repetition risk:** low; slightly slower and potentially timing-sensitive suite.
- **Solution applied:** none; recorded as a deviation.
- **Preventive measure:** prefer injectable clocks when choosing libraries; no technical-debt row because there is no product risk.
- **Evidence:** `backend/tests/integration/test_auth_rate_limit.py`; PR #2 "TDD deviations (recorded)"; `AR/2026-10-27-adversarial-review.md` (Tests row).

### L14. Practices that worked and should be repeated
- **Origin:** both changes.
- **Practices, each with evidence:**
  - Race tests for unique constraints: six concurrent registrations produced exactly one 201 and five 409 (`AR/2026-10-27-adversarial-review.md`, attack 3).
  - Mutation checks: removing a check made the guard tests fail (attack 15) and exposed a dead validator that was removed; the scaffold guard re-check was mutation-verified (`openspec/changes/archive/2026-10-27-project-scaffold/tasks.md`, task 4.0c).
  - Verification on the real stack with curl and cleanup of the created data (`AR/2026-10-27-step-10-curl-verification.md`, `PS/2026-10-27-step-11-curl-verification.md`).
  - Real-process tests of the CLI and of Uvicorn (`backend/tests/integration/test_cli_process.py`, `test_review_hardening.py`).
  - Design decisions approved by the user before implementation and artifacts updated when the review changed the scope (`prompts.md` sections 10 and 11).
  - Squash-merge Pull Requests with green CI and a separate archive commit (`e0e115a`, `d63efd5`, `2e87864`, `3ca9b6b`).
- **Status:** implemented; concurrency and mutation checks are part of the section 9.2 requirements.
