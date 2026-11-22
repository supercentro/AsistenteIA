# Lessons Learned

Process lessons from completed changes, with the preventive measure and the evidence behind each one. OpenSpec remains the source of truth for requirements and the SpecBoot skills remain the source of procedures; this document only records what went wrong or right, why, and which rule now prevents a repeat. Rules themselves live in `docs/base-standards.md` (section 9) and the other standards: link to them instead of copying.

Sources: `openspec/changes/archive/2026-10-27-project-scaffold/` and `.../2026-10-27-auth-and-roles/` (proposal, design, tasks, `reports/`), Pull Requests #1 and #2 of `supercentro/AsistenteIA`, `prompts.md` sections 10 and 11, `docs/technical-debt.md` and the Git history (`e0e115a`, `d63efd5`, `2e87864`, `3ca9b6b`). L18 to L27 come from the reports of the change `document-ingestion` (groups 5 to 14, branch `feature/document-ingestion`, Pull Request #8). L30 to L37 and the extension of L24 come from the reports of the change `database-least-privilege` (branch `feature/database-least-privilege`, not merged yet).

## How to use and maintain this document

- Read the relevant lessons before proposing a change and when writing `tasks.md`; the standards below make the main ones mandatory.
- Update it when a change finds a defect, a process deviation, or a practice worth repeating (typically at review or archive time). Append the next free ID; change `Status` instead of deleting entries.
- **Ownership (no duplication):** product or code risks accepted at merge live only in `docs/technical-debt.md`; a lesson that concerns one of them cites its `TD-` ID and does not restate it. A lesson with no product risk (process, tooling, test suite) lives only here.
- Status values: `implemented` (a rule, test or document now prevents it), `pending` (measure agreed but not yet applied), `accepted` (deliberate trade-off).
- Evidence paths are relative to the repository root; `AR` = `openspec/changes/archive/2026-10-27-auth-and-roles/reports/`, `PS` = `openspec/changes/archive/2026-10-27-project-scaffold/reports/`, `DI` = `openspec/changes/archive/2026-11-11-document-ingestion/reports/` (archived on 2026-11-11 with the change), `DL` = `openspec/changes/archive/2026-11-16-database-least-privilege/reports/` (that change was archived on 2026-11-16).

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
| L24 | The response leaves before a `yield` dependency exits, so a durable promise needs an explicit commit | document-ingestion (groups 9 and 10); extended by database-least-privilege (groups 7 and 9) | implemented (code, real-server test, standard) |
| L25 | A late edit after the last green gate broke CI | document-ingestion (group 9) | implemented (rule in base-standards 9.9) |
| L26 | Files that a change modifies but no test reads, and test seams in production code | document-ingestion (groups 10 and 11) | implemented (tests) |
| L27 | A verification task must not depend on writing to the development database | document-ingestion (group 13) | implemented (tasks.md, development guide) |
| L28 | A test probe must look at the system under test, not at the whole shared resource | document-ingestion | implemented (tests) |
| L29 | A container keeps the environment it was created with, and removing a variable is not rotating it | document-ingestion | implemented (development guide) |
| L30 | A contract edit must regenerate the files derived from it in the same change | database-least-privilege (groups 7 and 14) | implemented (backend standards, development guide) |
| L31 | A reviewer must never print the value of a real secret file | database-least-privilege (task 15.1) | implemented (review instructions) |
| L32 | An example file is a default: it must carry the safest identity, and a test must pin that | database-least-privilege (task 15.2) | implemented (tests) |
| L33 | A privilege is proved from the catalog and from the real paths under the real role, not from its declaration | database-least-privilege (groups 5, 6 and 9) | implemented (matrix, `db-verify`, role-bound suites; limits in TD-043 and TD-046) |
| L34 | A finished one-shot service can run again on `up`, and `restart` does not apply a new environment | database-least-privilege (task 1 and H13, group 17A) | implemented (design, development guide); the full flow was not exercised on the real database |
| L35 | A credential rotation is not atomic: the recovery from every intermediate state is written before the point of no return | database-least-privilege (SEC-17B-01, 17B.6) | implemented (procedure and tools, tested on disposable resources); no recovery was needed in the two real rotations |
| L36 | A helper script can print a secret through the exception of its own driver | database-least-privilege (SEC-17B-01, 17B.5) | implemented (tools and practice); no automated guard for ad hoc scripts |
| L37 | A rollback copy needs a proof of completeness before any live file is changed | database-least-privilege (17B.6, independent review) | implemented (tools, tested on disposable resources; the marker was exercised in the real administrator rotation, the rollback never) |
| L38 | A safety check is tested with the default input and against every source of the thing it guards | database-least-privilege (19.3, Codex review of PR #12) | implemented (tests and corrections); the practice is a rule of the reviewers, not yet a standard |
| L39 | State at cluster level leaks between tests of a session-scoped fixture | database-least-privilege (19.3, review of the P1/P2 corrections) | pending (mitigation in two tests; the fixture is TD-056) |
| L40 | Sanitizing an error means handling every exception the parser can raise, at every place it is called | database-least-privilege (19.3, Codex review of PR #12, second P2 finding) | implemented (five sites and 34 tests); the remaining test helper is listed in TD-054 |
| L41 | A `yield` dependency keeps its database connection for the whole request, including slow external calls | chat-rag-endpoint (independent review, finding 7) | implemented (tests); the rule for the owning standard is pending |
| L42 | State checked before a long external call must be revalidated in the transaction that writes | chat-rag-endpoint (round 2) | implemented (tests); the rule for the owning standard is pending |
| L43 | A change's spec text drifted from the canonical contract and from the real privilege matrix | chat-rag-endpoint (rounds 1 and 2) | pending (same automated check as L06) |
| L44 | A task is ticked only when a reproducible run shows the behaviour it names | chat-rag-endpoint (apply, session of 2026-11-16) | pending (agent discipline; no standard owns it yet) |
| L45 | A bind-mounted `--reload` container couples repository edits to a running service; the gate's memory floor is not lowered | chat-rag-endpoint (rounds 4 and 5) | implemented for `--reload` (compose and guide changed, takes effect at the next recreate); pending for the memory rule |
| L46 | A revalidation is a check, not a guarantee: serialise the write with the competing change, with an advisory lock when the privilege matrix forbids row locks | chat-rag-endpoint (M2) | implemented (tests); the rule for the owning standard is pending |
| L47 | A race test must release the transaction it stands for even when it fails, or the suite hangs instead of failing | chat-rag-endpoint (M2 tests) | implemented |
| L48 | A dependency lock regenerated by hand can silently drop a resolution rule of the project (the CPU-only torch index), and no gate notices | chat-rag-endpoint (review of PR #14) | implemented (guard test on the lock) |
| L49 | A contract word ("citation of a chunk used") was implemented as a looser behaviour (every retrieved chunk) and stayed unnoticed until a whole-PR review | chat-rag-endpoint (review of PR #14) | implemented (selection by marker, tests); the share of answers without markers is TD-062 |

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
- **Evidence:** `docs/data-model.md` (`ingestion_jobs`, temporary bytes paragraph); `DI/2026-11-08-spike-h8-h9-bytea-and-http.md`; `DI/2026-11-10-group-7-repositories-and-queue.md` (`sweep`); `openspec/changes/archive/2026-11-11-document-ingestion/design.md` (debts paragraph).

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
- **Extension (database-least-privilege, groups 7 and 9): the same gap hides a database privilege, and what is proved is the persisted state, not the status.**
  - *Historical (found in the spike of 2026-11-12, finding N-1).* `POST /users/me/consent` changed the ORM object and relied on the commit of `get_db`, which runs after the response, so with a role that lacked `UPDATE` on the consent columns the endpoint answered `200`, nothing was stored and the API logged only the type of the unhandled exception; `POST /auth/register`, `POST` and `DELETE` of subjects and of enrollments had the same exposure (TD-039). The consent endpoint was fixed in group 7 and the other handlers in the prerequisites of group 9.
  - *Current behaviour.* Those handlers commit through `commit_or_rollback` before the response; a write refused at commit answers `500` and a lost connection at commit `503` (`docs/backend-standards.md` section 7, TD-039). In the mutations of group 9 that removed a grant from the shipped code the failure was loud (mutations 1 to 3 and 6), so a missing privilege does not always show as a success status.
  - *What the group 9 mutation shows.* Mutation 0 removed the consent `UPDATE` grant and also put the late commit back: the endpoint answered `200`, the status assertion passed, and only the assertion on the persisted state failed. That is why the role-bound tests read the data from another session after the success status.
  - *Preventive measure (added).* A test of a write that depends on a privilege asserts the stored rows from another session; the status code alone is not evidence of the privilege.
  - *Evidence:* `DL/group-9/group-9-report.md` (mutation 0 and the paragraph that follows), `DL/2026-11-12-spike-summary.md` (N-1), `docs/technical-debt.md` (TD-039).
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
- **Evidence:** `openspec/changes/archive/2026-11-11-document-ingestion/tasks.md` (substitution record under group 13); `DI/2026-11-10-step-13-manual-verification.md`; `openspec/changes/archive/2026-11-11-document-ingestion/design.md` (Migration Plan).

### L28. A test probe must look at the system under test, not at the whole shared resource
- **Origin:** document-ingestion (CI run after the archive).
- **Problem:** a test that asserts "the service holds no lock while the PDF child runs" failed once in CI (`[(0, 0, 4, 0)]`) and passed on re-run, although the service held nothing.
- **Root cause:** the probe counted the locks of every backend connected to the test database. Any other session holding a lock at that instant (autovacuum or analyze after the bulk inserts of earlier tests, a leftover connection) was read as a violation; the assertion expressed a property of the service with a measurement of the whole database.
- **Impact / repetition risk:** an intermittent red `main` that trains people to re-run CI; the same shape can hide in any probe of shared state (locks, connections, rows, ports, files). Medium.
- **Solution applied:** the helper records the server process ids of the service's own connections and the probe filters by them (and by client backends); tests show that an unrelated lock is ignored and a lock held by the service is still detected; the old failure was reproduced with a concurrent `VACUUM` (15 of 25 runs) and not reproduced after the fix (25 of 25).
- **Preventive measure:** when a test asserts an absence in shared state, scope the measurement to what the code under test owns and add a negative test that creates the forbidden state; reproduce a suspected flake with a deliberate concurrent actor before and after the fix instead of re-running until green.
- **Evidence:** `backend/tests/service_support.py` (`track_backends`, `activity`), `backend/tests/integration/test_activity_probe.py`, `docs/technical-debt.md` (TD-037).

### L29. A container keeps the environment it was created with, and removing a variable is not rotating it
- **Origin:** document-ingestion (after the archive, validation of the local stack).
- **Problem:** the `.env` files and `docker-compose.yml` had been split so that each service only gets its own variables, and the repository, the tests and the review all said so. The running database container, created before the split, still held `JWT_SECRET`, `DATABASE_URL`, `TEST_DATABASE_URL`, `CORS_ORIGINS`, `APP_ENV` and `LOG_LEVEL` of the API, until a check of the worker's secrets listed the variable names of every container.
- **Root cause:** the declared configuration is not the effective one. A container's environment is fixed when it is created; changing Compose or an `env_file` changes nothing in a container that already exists, and no gate looked at running containers.
- **Impact / repetition risk:** a hardening that is "done" in the repository and absent where it matters; every later change of an environment variable can repeat it. Medium for any change that moves secrets or settings between services.
- **Solution applied:** the effective variable names were compared with the declared ones, `docker compose up -d --no-build --no-deps --dry-run db` showed that only `db` would be recreated, and the container was recreated with the worker stopped; image, volume, port, network, catalog, rows and revision were identical afterwards. The values were not rotated (TD-038); the shared superuser (TD-030) stays open.
- **Preventive measure:** after changing the variables of a service, list the variable **names** of the running container (`docker exec <container> env | cut -d= -f1`) and recreate it when they differ; treat "variable removed from a container" as exposure that already happened and rotate the secret when sharing or deploying. The command and the steps are in the Troubleshooting section of `development_guide.md`, linked here and not copied.
- **Evidence:** `docs/development_guide.md` ("State of the local development environment", Troubleshooting); `docs/technical-debt.md` (TD-038, TD-030).

### L30. A contract edit must regenerate the files derived from it in the same change
- **Origin:** database-least-privilege (task 7.2 added a response to `docs/api-spec.yml`; found in the E2E applicability review of group 14).
- **Problem:** the `500` response of `POST /users/me/consent` was documented in `docs/api-spec.yml` and `frontend/src/types/api.generated.ts` was not regenerated, so the `check:api-types` step of the CI job `frontend` would have failed on the first run, before the Playwright suite. The claim "the frontend is unchanged" was true of the source and false of the gate. The same change had also made five more endpoints answer `500` on a refused write without documenting it.
- **Root cause:** the backend gates (ruff, mypy, pytest, the privilege gate) do not run the frontend checks, the review of group 7 did not include them, and the contract test compares only the document paths, so a missing response elsewhere is invisible to it.
- **Impact / repetition risk:** a red first CI run on the frontend job and a contract that is silent about a real behaviour; any later spec edit can repeat it. Medium.
- **Solution applied:** the contract documents the `500` of all six endpoints that commit before answering (shared `InternalError` response), the types were regenerated with `npm run generate:api` (only the contract's additions changed), and a deliberate contract change without regeneration was shown to fail `check:api-types`.
- **Preventive measure:** whenever `docs/api-spec.yml` changes, run `npm run generate:api` and `npm run check:api-types` in the same change and commit the result; a task that edits the contract lists the derived files; a "no frontend change" statement is verified with `check:api-types`, not only with `git diff -- frontend`.
- **Evidence:** `openspec/changes/archive/2026-11-16-database-least-privilege/reports/2026-11-13-step-14-e2e-applicability.md`, `.../2026-11-13-step-14-closure.md`, `.../group-14/stale-types-detection.txt`.

### L31. A reviewer must never print the value of a real secret file
- **Origin:** database-least-privilege (task 15.1, independent PostgreSQL review).
- **Problem:** to find out which database user the real `backend/.env` files use, a read-only reviewer ran a search whose output included the value of `POSTGRES_PASSWORD`. The value ended in the reviewer's transcript and was reported by the reviewer itself.
- **Root cause:** the review instructions said "read-only" but did not forbid reading the values of real secret files, and the question (which user?) could be answered without them.
- **Impact / repetition risk:** a credential in a transcript that is not under the repository's control; any review or audit of configuration can repeat it. Medium.
- **Solution applied:** incident recorded without the value; the places where the value could be found were searched by pattern and only counts were printed; the review instructions of task 15.2 forbid reading real `.env` values; rotation is prepared (see the incident report).
- **Preventive measure:** to inspect configuration use the examples, `cut -d= -f1` for names, or `sed` that masks values; give every review prompt the line "do not read or print values from real `.env*` files"; search for leaks with `grep -c` or `-l`, never with output.
- **Evidence:** `openspec/changes/archive/2026-11-16-database-least-privilege/reports/2026-11-13-credential-exposure-incident.md`.

### L32. An example file is a default: it must carry the safest identity, and a test must pin that
- **Origin:** database-least-privilege (task 15.2, finding PG-01).
- **Problem:** after the design said the API and the worker must not be the database administrator, `.env.example` and `.env.worker.example` still carried the administrator user and a unit test asserted that they were equal to `POSTGRES_USER`, so copying the examples bypassed the whole model.
- **Root cause:** the tests that pin the example files were written for the previous design and were not revisited when the design changed.
- **Impact / repetition risk:** a new environment silently gets a superuser. High if copied to a real deployment.
- **Solution applied:** the examples carry `asistente_app` and `asistente_worker`, the tests assert the opposite of the old equality, and both services ask the server for their effective identity at start and refuse a superuser.
- **Preventive measure:** when a design changes who may do what, search the tests for assertions of the old arrangement; add a runtime check where a configuration mistake is not recoverable.
- **Evidence:** `backend/tests/unit/test_deployment_files.py`, `backend/tests/unit/test_superuser_refusal.py`, `backend/tests/integration/test_db_roles_startup.py`.


### L33. A privilege is proved from the catalog and from the real paths under the real role, not from its declaration
- **Origin:** database-least-privilege (groups 5, 6 and 9, and the 2026-11-12 spike).
- **Problem:** the privilege inventory assumed that the ORM inserts only the columns passed to the constructor. The first upload under the application role failed with `permission denied for table documents`: SQLAlchemy sends every column without a Python or server default as `NULL`, so the matrix had to be widened by six `INSERT` columns (`documents.error_message` and `error_code`, `users.consent_version` and `consent_accepted_at`, `ingestion_jobs.locked_by` and `locked_until`). The owner authorised narrowing them again in DD-14 (`FetchedValue()` on those columns and `eager_defaults=False` on the job mapper). The spike also showed that a column-level `REVOKE` does not remove a table-level grant, so reading the declared `REVOKE` and `GRANT` statements does not tell what a role can do.
- **Root cause:** the first matrix was derived by reading the code and the declared grants; neither shows what the driver really sends or what PostgreSQL applies once table-level, column-level and `PUBLIC` privileges are combined.
- **Impact / repetition risk:** a matrix that looks right and either breaks a legitimate path or grants more than declared. Medium for any change that touches privileges, the ORM mapping or a migration.
- **Solution applied:** the matrix is declarative (`backend/app/db_privileges.py`) and derived mechanically, but it is checked in three other ways: the effective privileges are read from the catalog (`db-verify`, whose drift cases are tested), the role-bound suites run the routes of the contract, the CLI subcommands and the worker paths under their real roles, and a coverage test fails when a route, a subcommand or a public method of `IngestionJobRepository` has no scenario. The documented privilege table was compared with the code and with the live catalog of the development database on 2026-11-15 (task 18.1).
- **Limits (what is not claimed):** `db-verify` does not check column defaults, column ACLs of roles outside the four, default ACLs of other roles, the ownership of the database, the schema and the extension, or direct `EXECUTE` grants (TD-043); the roles mode covers a hand-kept list of 23 integration modules and about 45 modules run only as the owner (TD-046).
- **Preventive measure:** prove a privilege with the effective catalog and with the real path under the real role, one positive case and one refused case; do not accept the grant text, the inventory or a code reading as proof. The same principle for containers is L29 (declared configuration versus effective environment).
- **Evidence:** `DL/group-5/group-5-report.md` (finding 1), `DL/group-6/orm-insert-columns-analysis.md`, `DL/2026-11-12-spike-summary.md` (H12), `DL/group-9/group-9-report.md` (task 9.2) and `DL/group-9/effective-matrix.txt`, `docs/technical-debt.md` (TD-043, TD-046).

### L34. A finished one-shot service can run again on `up`, and `restart` does not apply a new environment
- **Origin:** database-least-privilege (task 1 and H13, group 17A).
- **Problem:** in the disposable cold start of the planned flow (H13, own Compose project) a second plain `up -d` started the finished `bootstrap` again (round A5: `ALTER` instead of `CREATE`, same catalog fingerprint, `backend` and `worker` not recreated); `docker compose restart worker` kept the old `LOG_LEVEL` while a plain `up -d` recreated the worker with the new one (A6); a failing `migrate` left `backend` and `worker` created and never started (B); a service that depends on one in an inactive profile made the project invalid (C). The report concludes that the one-shots restart on every `up`. In the preparation of the real run, `bootstrap` was also expected to exit 1 on the first run because of the ownership drift of the existing database, which would have stopped `migrate`, `backend` and `worker` (TD-044).
- **Root cause:** Compose starts a finished container of a service again on `up`, and a container keeps the environment it was created with; a restart is not a recreation (L29).
- **Impact / repetition risk:** a privileged command running during an ordinary `up`, or a stack that does not start after a failed one-shot. Medium for any change that adds one-shot services.
- **Solution applied:** the one-shots are idempotent and in the default profile; the rotation of a role password is applied with `up -d`, not with `restart` (A7). On the real database the first `bootstrap` was run as a separate stage (S22) and only `backend` and `worker` were recreated afterwards (S30); on 2026-11-15 only the database container was recreated, keeping its volume. **The complete flow (a plain `docker compose up` with `bootstrap` and `migrate`) has not been exercised on the real database** and the development guide says so (sections 2 and 3).
- **Preventive measure:** make every one-shot idempotent and say what its first run does on an existing database; apply an environment change by recreating the service (`up -d`, or `up -d --no-deps <service>` for one), never with `restart`; before the first full `up` on a database with data, take a verified backup and follow the preconditions of the development guide.
- **Evidence:** `DL/2026-11-12-task-1-h13-cold-start.md` (rounds A5, A6, A7, B and C), `DL/2026-11-13-step-17a-preparation.md` (point 1), `DL/2026-11-14-step-17b-window-closure.md` (S22 and S30), `docs/development_guide.md` (sections 2 and 3), `docs/technical-debt.md` (TD-044).

### L35. A credential rotation is not atomic: write the recovery from every intermediate state before the point of no return
- **Origin:** database-least-privilege (SEC-17B-01 and 17B.6: procedure, independent reviews and rehearsals on disposable resources).
- **Problem:** rotating a database password changes the server, several files and, for a new container, its environment, and the steps cannot be one transaction. The procedures were reviewed by independent reviewers and rehearsed with injected failures before the real runs. They found: a recovery row that offered "revert or forward" in a state where one was refused and the other made it worse; no stated way out of a lock-out; a `bootstrap` run between the change in the database and the update of the files, which would put the old password of the migrator back (it re-sets the working roles from `.env.roles`; for the administrator it fails closed with the old URL); and, after a failed `apply`, backup copies that still hold the live old value. **These are findings of tests and reviews, not incidents:** the two real rotations (migrator on 2026-11-14, administrator on 2026-11-15) ran without any failure and no recovery path was used.
- **Root cause:** the first drafts listed the steps and not the states between them.
- **Impact / repetition risk:** a half-rotated credential with no safe way back, or a recovery that reinstates an exposed password. High for a shared database.
- **Solution applied:** the order proved in the rehearsals and in both real runs is the database first (`ALTER ROLE`, the point of no return), then the files (`apply`), with read-only probes between the steps. `README-17b6.md` has a recovery table by state (before `alter`; `alter` failed or uncertain; `alter` done and a probe unexpected; `alter` done and `apply` failed, with the forward and the revert options; probes after `apply` unexpected, in three database/file combinations; the recreated database container not healthy; lock-out, recoverable through the local socket of the running database container). The alter command refuses a role that is not a superuser, the container scan lists the containers that hold the old value, and a new backup folder is used for every attempt.
- **Preventive measure:** before the first write, write the recovery for every intermediate state and name the point of no return; probe after each step to learn which credential the database accepts; do not run `bootstrap` or `docker compose up` between the steps; check that the new value differs from the passwords of the other roles, since a reused value turns one exposure into two. That check was done by hand in 17B.6 and it stopped the rotation before any write when a first candidate file held the migrator's value; the rotation tool does not enforce it.
- **Evidence:** `DL/2026-11-14-sec-17b-01-migrator-password-exposure.md` (sections 7, 8 and 11), `DL/2026-11-14-td-038-17b6-preparation.md` (sections 6 and 8), `DL/group-17b/rotation/README-17b6.md` (recovery table), `DL/group-17b/recovery-matrix.md`.

### L36. A helper script can print a secret through the exception of its own driver
- **Origin:** database-least-privilege (SEC-17B-01, found during the functional check 17B.5 on 2026-11-14).
- **Problem:** an ad hoc script in a throw-away container opened a database connection with the URL of the environment, which carries an SQLAlchemy dialect prefix that the raw driver does not accept. The driver's error message for an invalid connection string repeats the whole string, and the script had no exception handling, so the uncaught traceback printed the password of the migrator role into the tool output of the session. No data was affected; the password was rotated (TD-050) and the transcript, outside the repository, still holds the old, now invalid value.
- **Root cause:** a one-off script without a handler around the connection, a URL not normalised for the raw driver, and an output filter added only after the first failure. The repository tools (rotation tools, orchestrator) already printed no traceback and redacted their output; the ad hoc script was outside them.
- **Impact / repetition risk:** a credential in a transcript that the repository does not control; the second occurrence of the class after L31. Medium.
- **Solution applied:** rotation of the password and administrative closure (TD-050); every later script catches the exception and prints only its type, and every command that can echo a URL goes through a redaction filter. The independent review of the rotation tool found the same class in the tool itself (a malformed URL makes the URL parser raise an error whose message repeats part of its input) and the tools now catch any exception and print its type only; their tests include hostile files and assert that no password and no traceback appears in any output.
- **Preventive measure:** a script that opens a connection prints `type(e).__name__` and never builds a message from a connection string; apply the redaction filter before the first run, not after the first failure; give secrets to tools through files or standard input and not through arguments. This is separate from L31 (a reviewer reading real secret files) and from L04 (application logs); there is no automated guard for ad hoc scripts, so it stays a practice.
- **Evidence:** `DL/2026-11-14-sec-17b-01-migrator-password-exposure.md` (sections 1, 2, 8 and 11), `docs/technical-debt.md` (TD-050), `DL/2026-11-14-td-038-17b6-preparation.md` (section 6).

### L37. A rollback copy needs a proof of completeness before any live file is changed
- **Origin:** database-least-privilege (17B.6, second independent review, finding N1, and the hardening round that followed).
- **Problem:** in the first scheme of the rotation tools each `<name>.old` copy was written in place and `rollback` restored every `.old` that existed. A hard kill while a copy was being written could leave an empty or partial file, and `rollback` would have restored it over a live environment file. It was found by the review and reproduced in the tests; it did not happen in a real rotation.
- **Root cause:** the rollback trusted the presence of a file, not its completeness, and nothing separated "all copies are safe" from "the live files may now be changed".
- **Impact / repetition risk:** the recovery path destroys the file it should protect. High for credential files, where there is no second source.
- **Solution applied:** each copy is written to a temporary name, flushed and renamed; a `.backup-complete` marker with the name, size and SHA-256 of every copy is written the same way after all copies are verified and **before** the first live file is touched; `rollback` refuses without the marker or when a copy is missing, empty, a link, of another size, of other content with the same size, or when a `.old` exists that the marker does not list, and it writes the bytes it verified; `apply` takes an exclusive lock in the backup folder and refuses a folder that is not empty, so a folder left by a killed run is never reused; `discard` removes the hidden leftovers. The same idea applies to the database dumps (a manifest with the SHA-256 per copy: TD-049).
- **What was validated by tests, and what was exercised on the real environment:** validated on disposable resources (146 checks and 24 mutants for the administrator file tool, 65 checks and 14 mutants for the role tool, end-to-end rehearsals on a disposable PostgreSQL): kills while the copy and while the marker are written, a copy swapped for other content of the same size, a marker that lists fewer copies, two concurrent applies, leftovers of a killed run, hostile files. On the real environment only the administrator rotation of 2026-11-15 used the hardened scheme: `apply` created the marker and the three copies, their size and SHA-256 were verified again before the `discard`, and `discard` removed them (exit 0); `rollback` has never run on the real environment. The migrator rotation of 2026-11-14 ran earlier, with the first scheme and without a marker, and needed no recovery.
- **Limits recorded by the reviews (accepted):** a hard-linked leftover is skipped silently by `discard`; the lock covers the backup folder and not the environment folder, so two runs with different backup folders could interleave (the procedure forbids it and the post-check fails closed); an interruption between taking the lock and the protected block leaves the lock in an otherwise empty folder, to be replaced by a fresh one.
- **Preventive measure:** write rollback copies atomically, record their size and digest in a marker that is written last and before any live change, make the rollback refuse anything the marker does not vouch for, and test the kill between every two steps.
- **Evidence:** `DL/2026-11-14-td-038-17b6-preparation.md` (sections 5, 6 and 8), `DL/group-17b/rotation/README-17b6.md`, `DL/group-17b/rotation/test_rotate_admin_password.py`, `DL/2026-11-14-td-049-backup-hardening.md`.

### L38. A safety check is tested with the default input and against every source of the thing it guards
- **Origin:** database-least-privilege (task 19.3, findings P1 and P2 of the Codex review of PR #12, after two internal adversarial reviews and a green CI).
- **Problem:** (P1) the adoption refused to run while other sessions were connected, but with no exclusion given it replaced the empty list by a list holding the empty string, which skipped every session without an `application_name`, that is, the API and the worker. The test that guarded it opened a session with an explicit name, so it never used the default. (P2) `db-verify` judged the managed roles and the table ACL, but a column privilege granted to a role outside the four or to `PUBLIC` lives in a different catalog column (`pg_attribute.attacl`) and was not read; the limit was written in TD-043 but the example that matters (`users.password_hash`) was not tested.
- **Root cause:** the tests chose the input that the author had in mind (a named session, the roles that exist) instead of the one the production code receives by default; the verifier was built from the list of things the code grants, not from every place where PostgreSQL stores a grant.
- **Impact / repetition risk:** a control that exists, passes its tests and stops nothing in the real flow; the worst kind for a safety prerequisite. Medium here (the adoption is atomic and the services were stopped by procedure; the verifier needs an administrator to create the drift), but it passed two internal reviews.
- **Solution applied:** the exclusions are explicit and an empty list skips nothing (`adopt.py`), and `db-verify` reads the column ACLs of strangers (`verify.py`); twelve regression tests, written first and seen failing (8 failed, 4 controls passed), now pass; removing either fix makes 4 of them fail (mutation on a disposable copy).
- **Preventive measure:** for every check that blocks or reports, (1) test it with the default and the empty input as well as the explicit one, and assert the premise of the test (for example that the session really has an empty name); (2) list every catalog location that can hold the thing it guards (table, column, schema, database, default ACL, `PUBLIC`) and give each one a drift case or a recorded limit; (3) add a control that must stay silent, so a fix cannot trade a false negative for a false positive; (4) ask the reviewer for adversarial cases with the sensitive column or session, not only for a read of the code.
- **Evidence:** `docs/technical-debt.md` (TD-043), `openspec/changes/archive/2026-11-16-database-least-privilege/tasks.md` (19.3.1 and 19.3.2), commits `67ac039` and `bc15b89`, `backend/tests/integration/test_db_admin_adopt.py`, `backend/tests/integration/test_db_admin_verify.py`.

### L39. State at cluster level leaks between tests of a session-scoped fixture
- **Origin:** database-least-privilege (task 19.3, independent review of the P1/P2 corrections, finding R-2).
- **Problem:** a drift case grants `CONNECT` on the `postgres` database to a managed role; the cluster fixture lives for the whole session and cleans only at its start and its end, so the grant survives and a later test that expects a healthy database fails. It was seen when two new controls were placed after the drift cases.
- **Root cause:** the per-test fixture (`scratch_database`) isolates databases, but a grant on a cluster-level object is not inside any of them, and the bootstrap undoes the `PUBLIC` grants only.
- **Impact / repetition risk:** a test result that depends on the order of execution; a new "no findings" test fails for a reason unrelated to what it checks. Low today, because the healthy test is first in its module.
- **Solution applied:** partial: the two new controls call a helper that revokes the leftover grant from the four test roles on a disposable cluster. The fixture itself is not changed (TD-056).
- **Preventive measure:** a test that changes cluster-level state undoes it in the same test (or the fixture does it per test); a test that asserts a clean state either runs first or restores it; run at least one explicit order (polluter first) for tests of this kind.
- **Evidence:** `docs/technical-debt.md` (TD-056), `backend/tests/integration/test_db_admin_verify.py` (`forget_database_grants_of_earlier_drifts`).

### L40. Sanitizing an error means handling every exception the parser can raise, at every place it is called
- **Origin:** database-least-privilege (task 19.3.4, second P2 finding of the Codex review of PR #12 on `6e85470`, after the tests, two internal reviews and a green CI).
- **Problem:** the validator of the database URLs caught SQLAlchemy's `ArgumentError` and replaced it with a message that names the variable and no value. A malformed URL can instead make the parser raise a `ValueError` (an invalid port read from the part of a password after an unescaped `@`); it was not caught, pydantic copied its text into the validation message, and the database commands printed it, with a fragment of the credential. The same single `except` was repeated at four other places that parse a URL.
- **Root cause:** the test of the rejection used one kind of bad URL (unparsable), so only the exception the author expected was exercised; the safe message was written for that exception, not for the operation.
- **Impact / repetition risk:** a fragment of a credential in a terminal or in the logs of a container, from a common configuration mistake (an unescaped `@`). Medium to low; it was found by an external review.
- **Solution applied:** both exceptions give the same fixed message, `from None`, at the five places that parse a URL; 34 regression tests with synthetic values (an unescaped `@`, a malformed port, an unparsable URL) through the loaders, the commands, the connection, the login probe, the test guard and the engine, asserting that the message holds none of the value, no internal text of the parser and no chained exception; each fix is killed by a mutation on a disposable copy.
- **Preventive measure:** when a message is made safe, (1) catch the base of what the operation can raise (or both exceptions of the parser), not the one that was seen; (2) test with at least one input of every kind of malformation (unparsable, wrong port, hostile character) and assert on the final text that a user sees, through the whole path, and on the absence of the chained cause; (3) search every call of the same function (`make_url`, `create_engine`) in the same change; (4) keep a list of residual places (here the test helper and the start-up of the API and the worker) in the debt register.
- **Evidence:** `docs/technical-debt.md` (TD-054), `openspec/changes/archive/2026-11-16-database-least-privilege/tasks.md` (19.3.4), commits `d587ffe` and `152b4d2`, `backend/tests/unit/test_migration_settings.py`, `test_db_admin_connection.py`, `test_db_safety.py`, `test_error_hardening.py`.

### L41. A `yield` dependency keeps its database connection for the whole request, including slow external calls
- **Origin:** chat-rag-endpoint (independent adversarial review of 2026-11-17, finding 7).
- **Problem:** `POST /chat` opened its session in `get_db`, ran authorization and retrieval, then awaited the Gemini call (up to the 30 s timeout) with the connection still checked out and a transaction open; the embedding and every query also ran on the event loop of an `async` handler.
- **Root cause:** the session of a FastAPI dependency with `yield` lives until the handler returns, so anything slow inside the handler holds a pooled connection; synchronous SQLAlchemy and CPU-bound embedding inside `async def` block the loop. Nothing in the unit tests looked at the pool.
- **Impact / repetition risk:** a few concurrent chats could exhaust the pool or stall every request. High for any endpoint that calls a provider.
- **Solution applied:** three phases (read, generate, persist), the session closed before the LLM call, a new transaction to persist, synchronous work in the thread pool (OpenSpec `design.md` D3, requirement "No database connection is held while the LLM generates").
- **Preventive measure:** an endpoint that awaits an external service must prove, from inside the call, that no pooled connection is checked out and no transaction is `idle in transaction` (`ProbeLLM` in `tests/integration/test_chat_phases.py`), and that a concurrent request is served while a CPU-bound step runs. The rule belongs in `docs/backend-standards.md`; it is not written there in this session (standards are not edited), so this lesson stays `pending` for that part.
- **Evidence:** `backend/tests/integration/test_chat_phases.py`, `openspec/changes/archive/2026-11-17-chat-rag-endpoint/reports/2026-11-17-round3-transactions-and-gate.md`.

### L42. State checked before a long external call must be revalidated in the transaction that writes
- **Origin:** chat-rag-endpoint (round 2, decision on finding 7).
- **Problem:** once the connection is released during the LLM call, consent, enrollment, the conversation, the subject and the cited chunks can all change before the answer is stored.
- **Root cause:** authorization was a gate at the start of the request, not a property of the write.
- **Impact / repetition risk:** an answer stored for a student who lost access, orphan messages, or a 500 from a foreign key. Medium to high.
- **Solution applied:** the persist phase revalidates consent, enrollment and conversation ownership in the same transaction that writes; a cited chunk deleted meanwhile is stored with `chunk_id` NULL inside a savepoint; a vanished conversation or subject is a 404.
- **Preventive measure:** write the race as a test with a probe that changes the database at the moment the external call would be running (consent revoked, unenrolment, conversation deleted, subject deleted, document deleted), and check by mutation that each revalidation is needed. Rule for `docs/backend-standards.md`: pending.
- **Evidence:** `backend/tests/integration/test_chat_phases.py`, `backend/tests/unit/test_rag_service.py` (persist tests).

### L43. A change's spec text drifted from the canonical contract and from the real privilege matrix
- **Origin:** chat-rag-endpoint (adversarial review, rounds 1 and 2).
- **Problem:** the OpenSpec scenarios said 404 for a non-enrolled student (the canonical `docs/api-spec.yml` and the readme say 403), the code returned `document_filename`, no `document_id` and an extra `score` (the contract has `filename`, `document_id`, `snippet`), and the privilege requirement described grants that the real matrix does not give. Tasks were ticked against the divergent text.
- **Root cause:** the delta specs were written from the design, not read against `docs/api-spec.yml`, `docs/data-model.md` and `app/db_privileges.py`, which own those facts. Same family as L06.
- **Impact / repetition risk:** a contract break shipped as "done"; found only by an independent reviewer. Medium.
- **Solution applied:** code aligned to the contract without a migration; the two spec requirements corrected through `/opsx:update` after the owner approved the exact text; `openspec validate --strict` passes.
- **Preventive measure:** when writing or checking a delta spec, list every status code, field name and privilege in it and compare each with its owning document; treat a difference as a finding, never as a silent edit. Automating the comparison is the pending measure of L06.
- **Evidence:** `openspec/changes/archive/2026-11-17-chat-rag-endpoint/reports/2026-11-17-round2-findings-matrix.md`.

### L44. A task is ticked only when a reproducible run shows the behaviour it names
- **Origin:** chat-rag-endpoint (apply, 2026-11-16, found by the agent that had ticked them).
- **Problem:** tasks 8.1, 8.2, 9.2, 9.3, 13.3, 13.5 and 14.x were ticked although no test or run covered the 502/503 mapping, the snippet cap, the citation snapshot after deletion, consent and enrollment over real HTTP, or the browser; a report claimed a frontend check that had not run. The 16.4 note said "all tests pass" with a gate gap open.
- **Root cause:** ticking followed the amount of work done, not the evidence for each clause of the task text.
- **Impact / repetition risk:** a false "done" is worse than an open task; it hides the gap from the reviewer. High for reports that feed GO/NO-GO.
- **Solution applied:** the boxes were unticked, the missing tests written (with recorded failing runs and mutation checks) and the reports rewritten to separate what ran from what did not.
- **Preventive measure:** before ticking, quote the command and result that proves each clause; when a clause was not run, say so in the task note. The owning place would be the apply workflow or `docs/openspec-tasks-mandatory-steps.md`; neither is edited in this session, so this stays `pending`.
- **Evidence:** `openspec/changes/archive/2026-11-17-chat-rag-endpoint/tasks.md`, `reports/2026-11-16-step-14-e2e-verification.md`.

### L45. A bind-mounted `--reload` container couples repository edits to a running service; the gate's memory floor is not lowered
- **Origin:** chat-rag-endpoint (rounds 4 and 5, diagnosis authorised by the owner).
- **Problem:** the persistent `asistenteia-backend-1` (created 2026-11-14, `uvicorn --reload`, `./backend/app` bind-mounted) stopped on 2026-11-17 at 14:38:57 UTC with exit code 1 and `_rust_notify.WatchfilesRustInternalError: error in underlying watcher: Cannot allocate memory (os error 12)`. Its log also shows 145 reloads since 2026-11-16 and **127 crashes of the reloaded process** (`GOOGLE_API_KEY is required when LLM_BACKEND=gemini`): the new source ran with the environment and image of November (its environment has no `GOOGLE_API_KEY`, `LLM_BACKEND` or `EMBEDDER_BACKEND`, and the image has no embedding dependencies), so the container said `Up` while its API was down.
- **Root cause of the stop:** not established. Evidence collected: no OOM kill (`OOMKilled=false`), no kill or oom event retained by Docker for that window, 12.6 GB of the 16 GB VM available afterwards, `fs.inotify.max_user_watches` 1048576 and `max_user_instances` 8192 (so not an inotify limit). A memory pressure episode in the shared VM while this session ran disposable clusters, a test runner and image builds coincides in time, but it was **not** demonstrated and must not be stated as the cause. What is established: the watcher is the component that failed, and edits of the repository reached a running container through the mount.
- **Impact / repetition risk:** a development service stops, or silently serves a crashed app, without anyone touching it. Medium.
- **Solution applied:** nothing was restarted or recreated (no safe isolated operation exists, see the round 5 report). `--reload` was removed from the development `backend` command in `docker-compose.yml` and the development guide now says to run `docker compose restart backend` after editing `app/`; it takes effect at the next recreate of the backend, which the owner performs. The mount stays.
- **Preventive measure:** after a change that adds required settings, recreate or rebuild the services that run the mounted code; do not lower a gate's resource guard to make a disposable run fit (the earlier Linux gate run of this change used a scratch copy with the 6 GB floor lowered to 4 GB; that deviation is documented and was not repeated); run disposable workloads one after another. Rule for `docs/development_guide.md` on resource use: pending.
- **Evidence:** `docker inspect` and `docker logs` of `asistenteia-backend-1`; `openspec/changes/archive/2026-11-17-chat-rag-endpoint/reports/2026-11-17-round5-m2-backend.md`.

### L46. A revalidation is a check, not a guarantee: serialise the write with the competing change, with an advisory lock when the privilege matrix forbids row locks
- **Origin:** chat-rag-endpoint (residual risk M2, independent review of round 3; owner-approved correction in round 5).
- **Problem:** the persist phase revalidated consent and enrollment with plain reads and then wrote; an unenrolment that committed between those reads and the commit was not seen and one turn was stored for a student who had just lost access. It was reproduced deterministically.
- **Root cause:** under READ COMMITTED nothing ties a read to a later write. The usual remedy, `SELECT ... FOR SHARE` on the enrollment row, needs an UPDATE privilege that the application role does not and must not have (checked on a disposable PostgreSQL with a role that only has SELECT: `permission denied`).
- **Impact / repetition risk:** low in probability and impact here, but the same shape (check, then act, across a long external call) exists wherever authorization is revalidated.
- **Solution applied:** the persist transaction and the enrollment removal take the same `pg_advisory_xact_lock(space, key)` for the student and subject, before the statements that depend on it, and release it at commit or rollback; no table privilege is needed and no lock is held during embedding or generation (design D3, requirement "Persistence and unenrolment are serialised per student and subject").
- **Preventive measure:** when a write depends on state that another actor can change, decide the serialisation point explicitly, prove both orders with a test that holds the competing transaction open (the waiter is observed in `pg_locks` before the release), and state the lock ordering rule (one lock per transaction, taken before the dependent statements). Rule for `docs/backend-standards.md`: pending.
- **Evidence:** `backend/tests/integration/test_chat_enrollment_lock.py`, `backend/tests/unit/test_enrollment_lock.py`, `openspec/changes/archive/2026-11-17-chat-rag-endpoint/reports/2026-11-17-round5-m2-backend.md`.

### L47. A race test must release the transaction it stands for even when it fails, or the suite hangs instead of failing
- **Origin:** chat-rag-endpoint (M2 tests, found by running the tests under mutation).
- **Problem:** the first version of the race tests held a lock in a separate session; when a mutation made an assertion fail, the session stayed open, the parked request never returned, the thread-pool shutdown waited for it and two mutation runs timed out instead of naming the failing test. A second flaw: one test ran an unenrolment and a turn of the same student at the same time, so it failed intermittently (2 of 8 runs) for a correct reason.
- **Root cause:** cleanup placed after the assertions and outside the executor block; a test that did not separate the operation under test from its competitor.
- **Impact / repetition risk:** a hung or flaky suite hides regressions. Medium.
- **Solution applied:** holders register themselves and an autouse fixture closes them; each test releases its holder before the pool shuts down; the competing operations run in sequence where the order is not the thing under test; the file ran 20 times without a failure and all five mutations are detected by named tests.
- **Preventive measure:** write the failure path of a race test first (what happens when the assertion fails) and run the file repeatedly and under mutation before trusting it.
- **Evidence:** `backend/tests/integration/test_chat_enrollment_lock.py` (`OtherTransaction`, `_release_other_transactions`).

### L48. A dependency lock regenerated by hand can silently drop a resolution rule of the project, and no gate notices
- **Origin:** chat-rag-endpoint (independent whole-PR review of PR #14).
- **Problem:** after the new dependencies were added the lock was regenerated in an environment that did not apply the `[tool.uv.sources]` rule of `pyproject.toml`: `torch` resolved from PyPI with 43 NVIDIA packages instead of the CPU-only build, which would have put CUDA libraries in the API and worker images. All CI jobs were green.
- **Root cause:** `uv sync --frozen` trusts the lock; nothing compared the lock with the rule that `pyproject.toml` declares, and the image size is not measured by any gate.
- **Impact / repetition risk:** images several times larger and slower to build, with no failing check. Medium.
- **Solution applied:** the lock was regenerated with `uv lock` (0 NVIDIA packages, CPU index present) and a unit test fails when the lock contains the CPU index no more or any `nvidia-*` or `triton` package.
- **Preventive measure:** a change that touches `pyproject.toml` or `uv.lock` runs `uv lock --check` and the guard test, and the diff of the lock is read for packages that the change did not ask for.
- **Evidence:** `backend/tests/unit/test_deployment_files.py::test_the_lock_resolves_torch_from_the_cpu_index` (fails on the previous lock, passes on the new one); `reports/2026-11-17-round6-pr14-review.md`.

### L49. A contract word implemented as a looser behaviour stays unnoticed until a whole-change review
- **Origin:** chat-rag-endpoint (owner's review of PR #14).
- **Problem:** `docs/api-spec.yml` defines a `Source` as the citation of a chunk *used* for an answer, but the first implementation returned and stored every retrieved chunk. Four review rounds, written against the spec text of the change (which said "the answer cites retrieved content"), did not see it.
- **Root cause:** the change's spec paraphrased the contract loosely; reviews compared code with the paraphrase, and the one scenario ("3 chunks give 3 sources") described the looser behaviour.
- **Impact / repetition risk:** a student could be shown a source that does not support the answer. Medium.
- **Solution applied:** blocks are numbered, the model is told to cite them, and only the cited chunks are returned and stored; the residual (answers without markers) is TD-062.
- **Preventive measure:** when a spec scenario restates a canonical schema, quote the schema's own wording and check each verb of it (used, owned, current) against the code.
- **Evidence:** `openspec/changes/archive/2026-11-17-chat-rag-endpoint/design.md` D5b; `backend/tests/unit/test_rag_service.py` (citation attribution tests); `reports/2026-11-17-round7-pr14-corrections.md`.

### L50. A focus moved after an asynchronous result must first check where the focus is
- **Origin:** student-chat-ui, found as TD-068 (change `student-chat-focus-stability`).
- **Problem:** a keyboard test of the chat failed in CI in 5 of 8 runs and never locally. It was first read as a flaky test.
- **Root cause:** `QuestionBox` called `setFocus` on every answer. A student (or the test) who had opened the delete confirmation while the answer was pending lost the focus when the answer arrived. The test did not wait for the answer, so the order of the two events depended on the speed of the runner.
- **Impact / repetition risk:** an unexpected focus change for keyboard and screen-reader users, and a red CI that trains people to rerun. Medium; the same unconditional `focus()` exists in four other components after asynchronous results.
- **Solution applied:** the focus returns to the box only when it is on the form or on the body; the late-answer case is a deterministic test with an explicit gate. This fixed a real defect, but the CI failure of the keyboard test persisted afterwards (the group never appeared). A recorder in the test showed the real sequence: the guard was evaluated, then the student focused another control, then react-hook-form's `setFocus`, which defers `focus()` with a timer, took the focus. The second fix decides and moves the focus in the same task.
- **Preventive measure:** a focus move after an asynchronous result checks `document.activeElement` first and moves only if the student has not chosen another control; a flaky test is investigated as a possible product defect before it is given a longer wait; a defect reproduced locally is a cause only if the failure signature of the CI matches it, and a CI that keeps no trace of a failure leaves the cause open (a recorder that prints a timeline on failure found it in one run); a guard on a library call is useless if the library defers the effect, so read what the call really does (`setFocus` uses a timer) and decide and act in the same task; and its race is reproduced with a held response (a gate released by the test), not with a sleep. A new test written for such a fix is itself repeated at least 40 times.
- **Confirmation:** after the second fix the frontend job passed 5 of 5 times in CI (it had failed 5 of 8 before). A CI blocked by billing left the proof pending for a day: the local reproduction with a hook in the window and the mutations were what allowed the fix to be accepted meanwhile.
- **Evidence:** `frontend/src/pages/ChatAsking.test.tsx` ("The focus when an answer arrives"), `frontend/e2e/student-chat.mocked.spec.ts` (the late answer); the review found that the first version of the new e2e test was flaky (its mocked thread lacked the answer) and it was fixed; `openspec/changes/archive/2026-11-22-student-chat-focus-stability/reports/`.
