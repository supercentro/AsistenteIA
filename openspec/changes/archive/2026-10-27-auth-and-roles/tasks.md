# Tasks

Reports required by `docs/openspec-tasks-mandatory-steps.md` are saved in `openspec/changes/auth-and-roles/reports/` (same convention as `project-scaffold`). Every group writes its failing tests first and lands its own tests and documentation. Backend only: no frontend code changes.

## 0. Setup: Create Feature Branch (MANDATORY - FIRST STEP)

- [x] 0.1 Verify the current branch is `feature/auth-and-roles` (created from `main` during planning; `git branch --show-current`) and that `main` contains the archived `project-scaffold`
- [x] 0.2 Confirm `origin/main` contains the archive commit `d63efd5` (published on 2026-10-27 by the user's approval) so this branch's base is the published `main`
- [x] 0.3 Start the stack (`docker compose up -d db`) and confirm `uv run pytest -q` is green on the starting point

## 1. Dependencies and Settings (TDD)

- [x] 1.1 Write failing unit tests for settings (spec `user-authentication` startup requirement and `privacy-consent`): `JWT_SECRET` missing/short/placeholder/low-variety rejected in every environment without printing the value; `JWT_EXPIRE_MINUTES` range; issuer/audience defaults; `PRIVACY_POLICY_VERSION` empty or > 20 chars rejected; `LOGIN_RATE_LIMIT` unparsable rejected; defaults applied
- [x] 1.2 Add `PyJWT`, `argon2-cffi`, `pydantic[email]` and `limits` with `uv add`, commit `uv.lock`; verify `uv sync --frozen`, `pip-audit` clean
- [x] 1.3 Implement the settings in `core/config.py` (`SecretStr` secret); verify 1.1 passes
- [x] 1.4 Update existing tests/fixtures that build `Settings` (add a valid test secret), `.env.example` (placeholders only, generation command in a comment), local `backend/.env`, compose, and the CI workflow (random secret generated at job start); verify the full existing suite still passes

## 2. Security Primitives (TDD)

- [x] 2.1 Write failing unit tests for password hashing: Argon2id hash differs from password, verify true/false, dummy-hash verification path, no plaintext in exceptions
- [x] 2.2 Write failing unit tests for tokens: encode contains exactly `sub, iat, exp, iss, aud` and HS256; decode accepts valid; rejects expired, tampered signature, wrong secret, wrong audience, wrong issuer, `alg=none`, HS384, missing each required claim, non-UUID `sub`, malformed, extra `role` claim ignored; explicit `now` used
- [x] 2.3 Implement `core/security.py` (hasher with injectable cost, `encode_access_token`, `decode_access_token`); verify 2.1 and 2.2 pass and `mypy --strict` is clean

## 3. Users Persistence and Migration (TDD)

- [x] 3.1 Extend the migration test: after `upgrade head` table `users` and type `user_role` exist, email check and unique constraint present; after `downgrade base` both are gone; upgrade again works (guarded test database)
- [x] 3.2 Write failing repository integration tests: add/get by id/get by lowercase email, duplicate email raises the domain conflict (also differing only by case), role enum round-trip, `created_at` set
- [x] 3.3 Implement `models/user.py`, Alembic `0002` with a working `downgrade`, and `repositories/user_repository.py`; verify 3.1 and 3.2 pass
- [x] 3.4 Add a guarded `TRUNCATE users` fixture between integration tests; verify tests are isolated

## 4. Register, Login, Profile and Rate Limiting (TDD)

- [x] 4.1 Write failing integration tests for `POST /auth/register`: 201 student, lowercase email, no password/hash in body, role in payload ignored, duplicate (any case) 409 with a single row, 422 for password 9 and 129 chars, bad email, blank/over-long name, no submitted values echoed, stored value is an Argon2id hash
- [x] 4.2 Write failing integration tests for `POST /auth/login`: success 200 with `expires_in` = minutes × 60 and case-insensitive email; wrong password and unknown email produce identical 401 `INVALID_CREDENTIALS` bodies; 422 on missing fields; token validates against `GET /users/me`
- [x] 4.3 Write failing integration tests for rate limiting with a small limit and injectable clock: N+1th attempt 429 `RATE_LIMITED` with `Retry-After` even with correct credentials, window elapsed succeeds, other endpoints not limited, limit applied before hashing (no DB/hash call on 429), rotating forged `X-Forwarded-For` / `Forwarded` / `X-Real-IP` headers share one bucket (default `10/minute` verified in settings)
- [x] 4.4 Write failing integration tests for `GET /users/me`: own profile 200, no header / wrong scheme / malformed / expired / tampered / wrong secret / wrong audience / wrong issuer / `alg=none` / HS384 / missing claim / non-UUID `sub` → 401 with `WWW-Authenticate: Bearer` and identical generic body; valid token of a deleted user → 401
- [x] 4.5 Implement schemas, `AuthService`, rate limiter (`core/rate_limit.py`), new domain errors with handler support for `Retry-After`, `get_current_user`, and the `auth`/`users` endpoints and router wiring; verify 4.1-4.4 pass
- [x] 4.6 Write and pass a log-leak test: after register, login success/failure and invalid-token calls the captured logs contain no submitted password, issued token or the JWT secret, and user references are ids only

- [x] 4.7 Review follow-up (TDD): write failing tests for `POST /auth/register` rate limiting (`REGISTER_RATE_LIMIT`, default 5/minute): 429 + `Retry-After`, no Argon2id call and no stored account when rejected, forged forwarding headers ignored, independent from login, invalid payloads count, settings validation; then implement the generic `RateLimiter`, the second limiter and the dependency

## 5. Role Guards (TDD)

- [x] 5.1 Write failing integration tests with test-only routes: teacher-only (teacher 200, student 403, anonymous 401) and student-only (student 200, teacher 403, anonymous 401); role changed in the database after login is applied to the same token; forged token with a `role` claim does not change the applied role; OpenAPI has no endpoint that creates teachers or changes roles
- [x] 5.2 Implement `require_teacher` and `require_student` reading the database role; verify 5.1 passes

## 6. Privacy Consent (TDD)

- [x] 6.1 Write failing integration tests for `POST /users/me/consent`: current version 200 with version and timestamp set (teacher and student); other version 422 `INVALID_CONSENT_VERSION` with `details.current_version` and unchanged data; empty and 21-char values 422 `VALIDATION_ERROR`; re-acceptance updates timestamp and version; changed configured version then accepting it; no token 401; consent of user A does not alter user B
- [x] 6.2 Write failing unit tests for `has_current_consent` (null, outdated, current) and a consistency test that reads `frontend/src/lib/privacyPolicy.ts`, extracts `PRIVACY_POLICY_VERSION` and asserts it equals the backend default and is 1-20 characters (failure message names both values); add a Vitest test for the constant's format
- [x] 6.3 Implement `ConsentService`, endpoint, helper and the constant `frontend/src/lib/privacyPolicy.ts` (constant only, no screens); verify 6.1 and 6.2 pass, that a deliberately changed constant makes the consistency test fail (then restore), and that no chat enforcement was added

## 7. Administrative CLI (TDD)

- [x] 7.1 Write failing tests for `create-teacher`: creates a teacher with Argon2id hash; password only from prompt/stdin (no `--password` option accepted); < 10 chars rejected; existing email (student or teacher) untouched and non-zero exit; output has no password/hash; HTTP surface unchanged
- [x] 7.2 Write failing tests for `seed`: creates exactly one teacher and one student (no other rows); second run changes nothing and exits 0; refuses in `production`; missing/weak variables exit non-zero and create nothing; no default credentials in code or `.env.example`; never prints passwords
- [x] 7.3 Implement `app/cli.py` with the shared service/repository code; verify 7.1 and 7.2 pass and run both commands by hand against the development database (cleanup afterwards)

- [x] 7.4 Review follow-up: run `create-teacher` and `seed` as a real process (`python -m app.cli`, including `main()`) in tests: production rejection, absent credentials, duplicate email, idempotent seed, no password in output, password options refused

## 8. Review and Update Existing Unit Tests (MANDATORY)

- [x] 8.1 Re-read every spec scenario of `user-authentication`, `role-based-access` and `privacy-consent` and confirm each has an automated test (add missing ones); confirm the scaffold tests still pass unchanged in intent

## 9. Run Unit Tests and Verify Database State (MANDATORY)

- [x] 9.1 Capture the pre-test baseline of `asistenteia` and `asistenteia_test` (extensions, tables, `alembic_version`, row counts)
- [x] 9.2 Run targeted tests per module, then the full suite with coverage (`services/` and `repositories/` ≥ 80 %)
- [x] 9.3 Re-check the same indicators; restore if tests left residue
- [x] 9.4 Create report `openspec/changes/auth-and-roles/reports/YYYY-MM-DD-step-9-unit-test-and-db-verification.md`

## 10. Manual Endpoint Testing with curl (MANDATORY - AGENT MUST EXECUTE)

- [x] 10.1 Apply `alembic upgrade head` on the development database and start the backend with a valid `JWT_SECRET`
- [x] 10.2 Register a student (201), duplicate (409), invalid payloads (422), role injection attempt
- [x] 10.3 Login success, wrong password and unknown email (identical 401), repeated attempts until 429 with `Retry-After`
- [x] 10.4 `GET /users/me` with valid, expired (crafted), tampered and missing tokens
- [x] 10.5 Consent: current version 200, other version 422 with `current_version`, re-acceptance, no token 401
- [x] 10.6 Create a teacher with the CLI, log in with it, and run `seed` twice (second is a no-op); confirm `seed` refuses with `APP_ENV=production`
- [x] 10.7 Delete every account created for the test, verify the database equals the pre-test state, and document all commands and responses in `reports/YYYY-MM-DD-step-10-curl-verification.md`

## 11. E2E Verification (not applicable to UI; regression only)

- [x] 11.1 Record in a report that no frontend or user workflow changes in this change, so the Playwright MCP interactive flow is not applicable; run `npm run test:e2e` (smoke suite) and the frontend gates to prove no regression; browser sessions closed

## 12. Update Technical Documentation (MANDATORY)

- [x] 12.1 Update `docs/api-spec.yml` (login 429 + `Retry-After`, consent 422, password `maxLength` 128, name `minLength` 1, new error codes) and verify the YAML parses and matches the implemented OpenAPI
- [x] 12.2 Update `docs/data-model.md` (`user_role` type, lowercase-email check, migration `0002`)
- [x] 12.3 Update `docs/development_guide.md` (new variables with secret generation command, CLI usage for `create-teacher` and `seed`, rate-limit limitations including forwarded-header trust and `--forwarded-allow-ips` behind proxies, policy-version mirroring with the UI constant, breaking note for existing `.env` files) and verify every documented command was executed as written (the interactive hidden-prompt variant of `create-teacher` is covered by tests with an injected prompt and was not run in a TTY)
- [x] 12.4 Update `docs/backend-standards.md` only where the implementation differs (e.g. `limits` instead of `slowapi`); run the `update-docs` skill checklist; confirm `readme.md` and `prompts.md` are untouched (`git diff --stat -- readme.md prompts.md` is empty)

## 13. Adversarial Review (required for authentication, authorization and personal data)

- [x] 13.1 Run the `adversarial-review` skill (independent pass) against this change, covering token validation, enumeration and timing, rate-limit bypass, role escalation paths, CLI misuse, logging and consent; save `reports/YYYY-MM-DD-adversarial-review.md`
- [x] 13.2 Fix findings related to this change (tests first) or record accepted risks with the user's agreement; re-run affected tests
- [x] 13.3 Review follow-ups landed: control characters in `name` (500 fixed), strict `aud`/`sub`/time claims, spec wording, concurrency and odd-input probes (`test_adversarial_probes.py`); tracked items (registration rate limit, `APP_ENV` default, docs exposure) are recorded in the review report for the user's decision

## 14. Final Verification of MUST Quality Gates (`docs/base-standards.md` §9)

- [x] 14.1 §9.1 Typing and validation: `uv run mypy --strict app tests`; Pydantic schemas on every request/response; no raw `dict` crossing the API layer
- [x] 14.2 §9.2 Testing: unit + integration green; every authorization rule has a negative test (no token, invalid token, wrong role, role changed); no external services called
- [x] 14.3 §9.3 Secrets and security: Argon2id, JWT with expiry, secret only through `core/config.py`, no secrets in repo or logs, dependencies pinned and `pip-audit` clean, `.env.example` placeholders only
- [x] 14.4 §9.6 Lint/format: `ruff check`, `ruff format --check`; frontend lint/format/typecheck/tests still green
- [x] 14.5 §9.7 Migrations: `0002` upgrade/downgrade on a clean database; `docker compose up --build` still starts the stack following the guide
- [x] 14.6 §9.8 Documentation updated in this change; conventional commits prepared (commits, push and Pull Request only when the user asks); `/chat` consent enforcement NOT implemented (change 9)
- [x] 14.7 Run `openspec validate auth-and-roles --strict` and tick this change's tasks only after all items above pass

## 15. Independent Review Follow-ups (TDD; findings of the second adversarial review)

- [x] 15.1 Write failing tests, then fix F1: the engine hides SQL parameters (API and CLI), an outermost middleware keeps unexpected exceptions and their data out of the server log (no traceback propagates, only type/method/path are logged), and a statement error does not expose the password hash or email in its text
- [x] 15.2 Write failing tests, then fix F7: database-unreachable errors on login/register (and any endpoint) return 503 `SERVICE_UNAVAILABLE` with a generic body
- [x] 15.3 Write failing tests, then fix F2: start the real Uvicorn with the Dockerfile's flags and show rotating `X-Forwarded-For` / `Forwarded` / `X-Real-IP` cannot bypass the login and registration limits; add `--no-proxy-headers` to the Dockerfile and the compose command and a test that guards the flag
- [x] 15.4 Write failing tests, then fix F3 and F4: names reject Unicode line/paragraph separators and bidirectional overrides (API and CLI `--name`); remove dead helper code
- [x] 15.5 Write failing tests, then fix F5: unsupported CLI arguments are rejected without echoing their values
- [x] 15.6 F6: add `maxLength` 128 and `minLength` 1 to the login password in `docs/api-spec.yml`; document the proxy-header requirement, the 503 behaviour and the log hardening in the development guide
- [x] 15.7 Re-run all quality gates, `openspec validate auth-and-roles --strict`, update the reports, push the fixes to the same branch and re-check GitHub Actions

## 16. Email Normalization Decision (review F8; TDD)

- [x] 16.1 Write failing tests, then restrict emails to ASCII (lowercased) in registration, login and the CLI (`create-teacher`, `seed`): accented, full-width, Greek/Cyrillic look-alike and Unicode-domain emails are rejected (422 / non-zero exit), uppercase ASCII is normalised, duplicates in any case return 409, punycode domains are accepted
- [x] 16.2 Add the database check `ck_users_email_ascii` to migration `0002` with a test (non-ASCII insert fails; constraint present after upgrade and gone after downgrade); verify compatibility: no non-ASCII rows exist in the development database and `0002` was never merged or applied elsewhere; re-run downgrade/upgrade locally
- [x] 16.3 Run the `update-docs` skill (no earlier evidence that the skill itself was invoked; only its checklist was applied manually) and update `docs/api-spec.yml`, `docs/data-model.md`, `docs/backend-standards.md` and `docs/development_guide.md` consistently with the artifacts
- [x] 16.4 Re-verify review findings F1-F8, run all quality gates and audits, `openspec validate auth-and-roles --strict`, push, update the PR and wait for green CI

## Workflow follow-up

- Open the Pull Request from `feature/auth-and-roles` to `main` when the user requests it and confirm the CI run is green.
- Archive with `/opsx:archive` after review and merge (the adversarial review in group 13 is a prerequisite).
- Ask the user whether to record notable AI usage in `prompts.md`.
