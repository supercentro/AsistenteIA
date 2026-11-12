# Lessons Learned

Process lessons from completed changes, with the preventive measure and the evidence behind each one. OpenSpec remains the source of truth for requirements and the SpecBoot skills remain the source of procedures; this document only records what went wrong or right, why, and which rule now prevents a repeat. Rules themselves live in `docs/base-standards.md` (section 9) and the other standards: link to them instead of copying.

Sources: `openspec/changes/archive/2026-10-27-project-scaffold/` and `.../2026-10-27-auth-and-roles/` (proposal, design, tasks, `reports/`), Pull Requests #1 and #2 of `supercentro/AsistenteIA`, `prompts.md` sections 10 and 11, `docs/technical-debt.md` and the Git history (`e0e115a`, `d63efd5`, `2e87864`, `3ca9b6b`). L18 to L27 come from the reports of the change `document-ingestion` (groups 5 to 14, branch `feature/document-ingestion`, Pull Request #8).

## How to use and maintain this document

- Read the relevant lessons before proposing a change and when writing `tasks.md`; the standards below make the main ones mandatory.
- Update it when a change finds a defect, a process deviation, or a practice worth repeating (typically at review or archive time). Append the next free ID; change `Status` instead of deleting entries.
- **Ownership (no duplication):** product or code risks accepted at merge live only in `docs/technical-debt.md`; a lesson that concerns one of them cites its `TD-` ID and does not restate it. A lesson with no product risk (process, tooling, test suite) lives only here.
- Status values: `implemented` (a rule, test or document now prevents it), `pending` (measure agreed but not yet applied), `accepted` (deliberate trade-off).
- Evidence paths are relative to the repository root; `AR` = `openspec/changes/archive/2026-10-27-auth-and-roles/reports/`, `PS` = `openspec/changes/archive/2026-10-27-project-scaffold/reports/`, `DI` = `openspec/changes/document-ingestion/reports/` (the change is not archived yet; if the path moves at archive time, update it then).

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
| L15 | Editing tools collapsed backslash escapes; the dev container did not see a new migration | subjects-and-enrollments | implemented (guide), pending (tooling note) |
| L16 | Mocks hid a server header and a layout defect; dependency changes need a new container volume | frontend-foundation | implemented (standard) |
| L17 | A design promise and a test can claim a control that does not exist | documents-schema-pgvector | implemented (practice) |
| L18 | A cached lint result gave a local green that CI refuted | document-ingestion (group 5) | implemented (rule in base-standards 9.6) |
| L19 | Windows and Linux test runs are not equivalent | document-ingestion (group 6) | implemented (practice; the Linux image and CI run the isolation tests) |
| L20 | Lock order must be designed from every path that locks, including cascades | document-ingestion (group 7) | implemented (repositories, service, worker and endpoints) |
| L21 | A lease only fences if the clock and the token are checked at write time | document-ingestion (group 7) | implemented (fence and heartbeat) |
| L22 | Erased `bytea` stays in dead tuples, WAL and backups | document-ingestion (design, group 7) | accepted (TD-029; operations guide written) |
| L23 | Mutation testing found real gaps and has known limits | document-ingestion (group 7) | implemented (practice) |
| L24 | The response leaves before a `yield` dependency exits, so a durable promise needs an explicit commit | document-ingestion (groups 9 and 10) | implemented (code, real-server test, standard) |
| L25 | A late edit after the last green gate broke CI | document-ingestion (group 9) | implemented (rule in base-standards 9.9) |
| L26 | Files that a change modifies but no test reads, and test seams in production code | document-ingestion (groups 10 and 11) | implemented (tests) |
| L27 | A verification task must not depend on writing to the development database | document-ingestion (group 13) | implemented (tasks.md, development guide) |

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
- **Solution applied:** manual reconciliation at planning and before archive; the HU-1 wording was corrected in `readme.md` with the planning of the `subjects-and-enrollments` change (see its proposal).
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

### L15. Editing tools collapsed backslash escapes; the dev container did not see a new migration
- **Origin:** subjects-and-enrollments.
- **Problem:** Unicode and newline escapes (`U+2028`, `\n`) written through the file-editing tools or shell heredocs reached the files as real invisible characters or real newlines (a bidi control inside a test file, `SyntaxError` at collection); heredocs containing an apostrophe failed to parse. Separately, `alembic check` run inside the compose backend container reported `0002 (head)` because only `backend/app` is mounted, and a `downgrade -1` there reverted `0002` on the development database (no data lost: 0 users).
- **Root cause:** escape handling of the tooling layer and an assumption that the container mirrors the working tree.
- **Impact / repetition risk:** invisible characters in source files (trojan-source style) and migrations run against the wrong revision. Medium.
- **Solution applied:** files with such literals were scanned for non-ASCII characters and rebuilt with `chr()`/explicit code points; the migration was applied from the host and the container image was rebuilt; `docs/development_guide.md` now says a new migration needs a rebuild or a host run.
- **Preventive measure (pending):** when a test needs special characters, build them with `chr()`, then assert the file is ASCII-only; check `alembic current` before any `downgrade`.
- **Evidence:** `openspec/changes/subjects-and-enrollments/reports/2026-10-28-ai-usage-notes.md`; `docs/development_guide.md` (database section).

### L16. Mocks hid a server header and a layout defect; dependency changes need a new container volume
- **Origin:** frontend-foundation.
- **Problem:** (1) the mocked browser suite was first written with a readable `Retry-After`, but the real backend does not expose it through CORS, so a real browser never saw it (found by the first mocked E2E run and confirmed with curl and Playwright MCP; resolved afterwards with `expose_headers`, TD-021); (2) a 140-character unbroken subject name widened the list grid and caused horizontal scrolling at 320 px, invisible in jsdom (found by the browser test); (3) after adding npm packages the compose frontend kept its anonymous `node_modules` volume and failed with `Failed to resolve import`.
- **Root cause:** component tests cannot see CORS exposure or real layout; the container reuses its anonymous volume on recreation.
- **Impact / repetition risk:** behaviour that works in tests and fails in the browser. Medium.
- **Solution applied:** the UI degrades gracefully when the header is unreadable, the owner approved the one-line CORS fix (commit `1d65ac1`, test `backend/tests/integration/test_cors_retry_after.py`) and the mocks and the gated real-backend spec now assert the seconds; the list grid is a single explicit column and a 320 px browser test guards it; the guide documents `docker compose up -d --build -V frontend`.
- **Preventive measure:** verify headers, CORS and layout in a real browser against the running stack for every change that adds a screen (now in `docs/frontend-standards.md` section 6); derive mocks from observed responses, not from the contract text alone.
- **Evidence:** `openspec/changes/frontend-foundation/reports/` (`tdd-evidence`, `step-11`, `step-12`).

### L17. A design promise and a test can claim a control that does not exist
- **Origin:** documents-schema-pgvector (independent review, findings F1 and F2).
- **Problem:** (1) `design.md` said the repository translates database errors into controlled errors; the code propagates them and a test asserts that, so the written control was never implemented and the difference was not reported as a deviation. (2) A log test searched for a text format that the library does not produce, so it passed even with SQL parameters exposed.
- **Root cause:** the design text was written before the implementation and not re-read against it; the mutation table checked the guarded line against a different test than the one that claimed to cover it.
- **Impact / repetition risk:** a later change copies a pattern that does not exist, or a leak guard silently stops guarding. Medium for a security-sensitive change.
- **Solution applied:** `design.md` corrected; the log test now forbids the real serialisation and asserts the "hidden" marker; the mutation `hide_parameters=False` is killed.
- **Preventive measure:** when a design or spec sentence names a control, grep the code and a test for it before the group closes; for every leak or isolation test, print what the leak looks like once (a probe with the control removed) and assert on that real text, not on an assumed one.
- **Evidence:** `openspec/changes/archive/2026-11-08-documents-schema-pgvector/reports/2026-11-08-independent-review.md`, `reports/2026-10-28-tdd-evidence.md` (group 11).

### L18. A cached lint result gave a local green that CI refuted
- **Origin:** document-ingestion (group 5).
- **Problem:** `ruff check` passed locally and the CI `backend` job failed at the lint step with `I001` (import order) in three test files.
- **Root cause:** the Ruff cache held the result computed before the modules `app.rag.*` existed; once they were created, those imports changed from third-party to first-party and the cached verdict was stale.
- **Impact / repetition risk:** a false green before a push; any change that creates a new top-level package or module can repeat it. Low severity, recurring.
- **Solution applied:** `ruff check --fix` (import order only, no behaviour change) in a new commit; every later local gate runs `ruff check --no-cache`.
- **Preventive measure:** run `ruff check --no-cache` (and `ruff format --check`) as the local gate, especially after adding modules. It is now a rule in `docs/base-standards.md` section 9.6.
- **Evidence:** `DI/2026-11-09-group-5-embedder-normalizer-chunker.md` (CI failure paragraph); the quality-gate lines of `DI/2026-11-09-group-6-loaders-and-pdf-child.md` and `DI/2026-11-10-group-7-repositories-and-queue.md`.

### L19. Windows and Linux test runs are not equivalent
- **Origin:** document-ingestion (group 6).
- **Problem:** the PDF child process uses POSIX-only calls (`resource` limits, process groups, `SIGXCPU`). On the Windows development host those tests are skipped (107 skipped, including AES) and coverage reads lower (92 % against the Linux figure); `mypy` rejected the POSIX calls there; a test parametrised on `signal.SIGXCPU` failed at collection on Windows.
- **Root cause:** the platform of the code under test (Linux worker image and CI) differs from the platform of the developer host.
- **Impact / repetition risk:** a green Windows run does not prove the isolation tests passed, and a local coverage figure can understate or hide what Linux runs. High for any code that depends on the operating system.
- **Solution applied:** `[tool.mypy] platform = "linux"`; the signal is resolved by name (`signal.Signals[name]`); skips carry an explicit reason; the isolation tests were run in the worker image (195 passed, 1 skipped for AES) and the CI job runs them on Linux.
- **Preventive measure:** record every skip with its reason and the platform that runs it, and take the Linux image or CI result as the evidence for OS-dependent behaviour (the same idea as L03 for transport). The Linux image ran the whole suite in groups 8 to 14 and the CI `backend` job runs it on Linux (green at the published head of the change).
- **Evidence:** `DI/2026-11-09-group-6-loaders-and-pdf-child.md` (components, TDD evidence and full-run paragraphs); `backend/pyproject.toml`.

### L20. Lock order must be designed from every path that locks, including cascades
- **Origin:** document-ingestion (group 7).
- **Problem:** the first design of the fenced worker write locked the job row first and then the document row. `DELETE FROM documents` locks the document and then cascades to the job, so a deletion and a worker write could each hold one row and wait for the other (deadlock).
- **Root cause:** the order was chosen from the worker's point of view only; the cascade of the foreign key is an implicit second locking path.
- **Impact / repetition risk:** intermittent deadlocks that only appear under concurrency. High for any table with several writers.
- **Solution applied:** the order was fixed before writing code: document row, then job row, the same as the delete cascade; admission takes the subject row, then the quota check, then the global advisory lock. Renewals touch only the job row and cannot close the cycle. Tests use real concurrent sessions: 72 uploads from 6 subjects over 4 rounds and mixed uploads and deletions produce no deadlock, and a lock on one subject delays only that subject.
- **Preventive measure:** before coding a multi-row write, list every statement that locks the same rows (cascades, sweeps, deletes) and write the order in the design; test it with concurrent sessions released at the same instant (extends L14). The service and worker of group 8 and the endpoints of group 9 keep this order (document, then job), proved by the concurrent tests of groups 8 to 10.
- **Evidence:** `DI/2026-11-10-group-7-repositories-and-queue.md` ("Lock order document then job" and TDD evidence); `backend/tests/integration/test_document_repository.py`, `test_ingestion_lease_fencing.py`.

### L21. A lease only fences if the clock and the token are checked at write time
- **Origin:** document-ingestion (group 7).
- **Problem:** with `now()` (constant inside a transaction) a long transaction could keep using a lease that had already expired, and a worker whose job was reclaimed could still write over the new owner's result.
- **Root cause:** a lease and a claim token are only meaningful if they are verified by the same statement or transaction that writes, against a clock that advances.
- **Impact / repetition risk:** double processing and a terminal document overwritten by a stale worker. High for any queue with leases.
- **Solution applied (implemented, group 7):** the fence is the claim token plus `locked_until > clock_timestamp()` on every write; multi-statement writes lock the document and the job and check again under the lock; a terminal document is never updated; a stale token, a deleted job or an expired lease writes nothing and returns `False`. A renewal is one fenced `UPDATE` that leaves no lock or open transaction (tested).
- **Preventive measure:** the repository provides `renew`, but the **operational heartbeat belongs to group 8** (the service and worker): it must call `renew` in its own session, commit at once, and stop quietly when `renew` or any fenced write returns `False`. That behaviour is pending and must be proved with the worker's tests; until then this lesson is only half implemented.
- **Evidence:** `DI/2026-11-10-group-7-repositories-and-queue.md` ("Fence", deviations 2 and 5); `backend/tests/integration/test_ingestion_lease_fencing.py`.

### L22. Erased `bytea` stays in dead tuples, WAL and backups
- **Origin:** document-ingestion (design and spike H8, group 7 implementation).
- **Problem:** the uploaded file lives temporarily in `ingestion_jobs.payload`. Setting it to `NULL` or deleting the row does not remove the bytes from dead tuples, table files, the write-ahead log, or any backup, dump or replica made while the job existed: about 21 MB of WAL per job of 10 MB (10.7 MB on insert and 10.5 MB on clearing, measured on 2026-11-08).
- **Root cause:** how PostgreSQL stores and logs row versions; autovacuum removes dead tuples but does not overwrite free pages.
- **Impact / repetition risk:** teachers' files outlive their erasure in backups for the retention period. A design that says "the original is never kept" is only true for the live table.
- **Solution applied:** the decision is documented in the data model: the bytes are erased on every terminal path, the sweep erases the bytes of terminal documents with ordinary statements (batches, `SKIP LOCKED`, never `VACUUM FULL`, never a table lock), and `VACUUM FULL ingestion_jobs` stays a manual operator action. The residual risk is to be registered in `docs/technical-debt.md` in task 15.1 of the change (not copied here); until that row exists, treat backups as containing the files.
- **Preventive measure:** when a design stores sensitive bytes in the database, measure the WAL and say in the data model and the operations guide how long copies survive; do not describe erasure as complete. The operational queries and the retention wording are now in `docs/development_guide.md` ("Document ingestion") and the residual risk is TD-029.
- **Evidence:** `docs/data-model.md` (`ingestion_jobs`, temporary bytes paragraph); `DI/2026-11-08-spike-h8-h9-bytea-and-http.md`; `DI/2026-11-10-group-7-repositories-and-queue.md` (`sweep`); `openspec/changes/document-ingestion/design.md` (debts paragraph).

### L23. Mutation testing found real gaps and has known limits
- **Origin:** document-ingestion (groups 6 and 7).
- **Problem:** after the first test pass of group 7, about 50 mutations of the two repositories left 15 survivors that the green suite did not reveal: an orphaned, locked or exhausted job hiding a claimable one, availability order, the re-check of the claim `UPDATE`, the sweep waiting for locked documents, and invalid input to `complete` issuing statements. The run also found a redundant filter in `delete_for_teacher`. In group 6 survivors exposed untested branches (data after the end marker, killing the process group).
- **Root cause:** tests written from the happy path and the limits that were already in mind; no test relaxed or removed the guarded line.
- **Impact / repetition risk:** a guard that no test needs can be deleted unnoticed. Medium to high for security and concurrency code.
- **Solution applied:** targeted tests for each survivor (including a deterministic test that relaxes the candidate query through a cursor event); the redundant filter removed; one equivalent group accepted and written down.
- **Limits recorded:** (1) removing the token or the lease condition from only **one** of the two fence checks is equivalent, because each covers the other by design; removing both is detected (tested). (2) A mutation that waits for a lock hangs the test, so the harness needs a timeout and, on Windows, `taskkill /T` (one stray `pytest` process of an earlier run had to be stopped by hand; no file was left mutated). (3) The scripted mutations use exact text, so a replacement can silently not apply (CRLF, escapes; the harness counts it as a skip, not a kill). (4) Mutation shows that a line is guarded, not that the behaviour is complete.
- **Preventive measure:** keep the mutation list per group in the TDD evidence, list accepted equivalents with their justification, and test the joint mutation of redundant checks. The requirement itself is in `docs/base-standards.md` section 9.2; this lesson adds the limits.
- **Evidence:** `DI/2026-11-10-group-7-repositories-and-queue.md` (mutation checks and deviation 6); `DI/2026-11-09-group-6-loaders-and-pdf-child.md` (mutation paragraph); `DI/2026-11-08-tdd-evidence.md`.

### L24. The response leaves before a `yield` dependency exits, so a durable promise needs an explicit commit
- **Origin:** document-ingestion (groups 9 and 10).
- **Problem:** the standard says one transaction per request, committed by the dependency that provides the session. With FastAPI 0.162 the response is sent **before** the exit code of a `yield` dependency runs, so a client could receive `202` or `204` and a failure (or a kill of the process) could still happen before the commit.
- **Root cause:** the order of response and dependency exit is a framework detail that `TestClient` hides and that the written standard did not mention.
- **Impact / repetition risk:** a promise that is not durable (an upload acknowledged but lost, a deletion acknowledged but not applied). High for every endpoint that promises durability.
- **Solution applied:** the upload and the delete call `commit()` before building the response, and any database error on that path is `503`; a real-server test pins the framework order and another test kills the process between stages.
- **Preventive measure:** a documented exception in `docs/backend-standards.md` section 3 (explicit commit before a durable `2xx`), and the rule of `docs/base-standards.md` section 9.2 that behaviour depending on the server is tested against a real process. Re-run the pinning test when FastAPI or Starlette is upgraded.
- **Evidence:** `DI/2026-11-10-group-9-endpoints-and-upload-guard.md` ("Commit before `202`"); `backend/tests/integration/test_real_server.py::test_the_response_leaves_before_the_dependency_exit_so_the_delete_commits_first`; `DI/2026-11-10-step-10-real-server-verification.md`.

### L25. A late edit after the last green gate broke CI
- **Origin:** document-ingestion (group 9).
- **Problem:** after the local gates were green, a test file was edited again (a scripted client typed with `list`) and pushed without repeating the gates; the CI `backend` job failed in `mypy --strict` (an invariant `list` type where a `Sequence` was needed).
- **Root cause:** the gates were run before the last edit, not after it, and test files were treated as outside the typing gate.
- **Impact / repetition risk:** a red CI on a published branch; the same slip is likely whenever a small edit follows a green run. Low severity, recurring (see L18).
- **Solution applied:** the test was typed with a covariant `Sequence` (commit `e0355d6`) and all gates were repeated.
- **Preventive measure:** every group repeats `ruff check --no-cache`, `ruff format --check`, `mypy --strict app tests` and `pip-audit` **after the last change, including tests and documentation scripts**, and the report says so. It is now part of the Definition of Done in `docs/base-standards.md` section 9.9.
- **Evidence:** commit `e0355d6`; the "Results" lines of `DI/2026-11-10-group-9-endpoints-and-upload-guard.md` and of every later group report.

### L26. Files that a change modifies but no test reads, and test seams in production code
- **Origin:** document-ingestion (groups 10 and 11).
- **Problem:** the review of existing tests found four files changed by this change that no test read: `.env.example`, the `Dockerfile`, `docker-compose.yml` and the CI workflow. Separately, a keyword-only argument of `UploadSlots` exists only so tests can force an interleaving; nothing proved it stayed inert in production.
- **Root cause:** tests were written for behaviour of the application, not for the files that configure how it is built and run; a seam is easy to leave reachable.
- **Impact / repetition risk:** the API image could silently gain `torch`, the worker lose its command or its offline flag, an undocumented variable appear, or a seam be wired to a setting. Medium.
- **Solution applied:** `tests/unit/test_deployment_files.py` (settings documented and equal to the defaults, placeholders only, image targets, worker service, CI steps) and `tests/unit/test_test_seams.py` (the seam is keyword-only, `None` by default, mentioned by one module and not wired in `create_app`); 15 mutations of those files, all killed.
- **Preventive measure:** when a change touches a configuration or build file, list it in the regression review and give it a test that reads it; when production code accepts a test seam, add a test that it is off by default and unreachable from requests, headers, the environment and settings.
- **Evidence:** `DI/2026-11-10-regression-review.md`; `backend/tests/unit/test_deployment_files.py`, `test_test_seams.py`.

### L27. A verification task must not depend on writing to the development database
- **Origin:** document-ingestion (group 13).
- **Problem:** tasks 13.1 and 13.2 were written to back up the development database, migrate it and restore it; the authorisation of the group forbade touching that database. The tasks had to be reworded through `/opsx:update` before they could be ticked, and `design.md` kept a stale migration plan until group 15.
- **Root cause:** the task text was fixed at planning time, before the decision about which environments an agent may change; verification and operation of the shared database were mixed in one task.
- **Impact / repetition risk:** a task that cannot be completed as written, or pressure to run a risky operation to satisfy the text. Medium for any change that adds a migration.
- **Solution applied:** the verification ran on a disposable PostgreSQL container on an internal network (migration, real API and worker, real model, HTTP, search, cleanup) and the development database was checked unchanged; the tasks record the substitution, its authorisation and its evidence, and no backup or restore is claimed.
- **Preventive measure:** write verification tasks against an isolated disposable database and keep applying a migration to a shared database as a separate, explicitly approved operation with a verified backup and a recovery procedure (`docs/development_guide.md`, section 3). When a restriction changes a task, update the artifacts first (`docs/base-standards.md` section 7) and record what was substituted.
- **Evidence:** `openspec/changes/document-ingestion/tasks.md` (substitution record under group 13); `DI/2026-11-10-step-13-manual-verification.md`; `openspec/changes/document-ingestion/design.md` (Migration Plan).
