# Adversarial Review - auth-and-roles

- Date: 2026-10-27
- Reviewer: Claude Code (Sonnet 5.5), **same session as the implementation** (the skill prefers a different agent or session; this pass is therefore not independent, and a second pass by another session or the user is recommended before archive)
- Scope: change `auth-and-roles` on branch `feature/auth-and-roles` (uncommitted working tree against `main` at `d63efd5`)
- Sources: `openspec/changes/auth-and-roles/{proposal,design,tasks}.md`, specs `user-authentication`, `role-based-access`, `privacy-consent`, delta `service-health`; `docs/api-spec.yml`, `docs/data-model.md`, `docs/backend-standards.md`; full working-tree diff; test suite and manual curl runs (reports of steps 9-11)

## Spec and task alignment
Every scenario of the three new specs and of the `service-health` delta maps to at least one automated test (see step 9 report); the manual curl run (step 10) exercised the running stack for register, login, rate limit, token failures, consent and both CLI commands. `alembic check` reports no drift between models and migration `0002`. Explicit non-goals respected: no frontend screens, no `/chat` consent enforcement, no refresh/revocation/password change, no new endpoint for the policy version.

## Attack attempts and results
| # | Attempt | Result |
|---|---|---|
| 1 | NUL character in `name` (PostgreSQL cannot store it) | **Found: 500.** Fixed: names reject control characters (422). Regression test `test_register_never_answers_500_for_odd_input` |
| 2 | Lone UTF-16 surrogates in name/password/email/login; fullwidth and dotted-capital-I emails; NUL in email/password | 422/201/401, never 500 (a speculative encodability validator was removed after a mutation showed it was dead code) |
| 3 | Six concurrent registrations of one email | exactly one 201, five 409, no 500 (savepoint + unique-violation mapping) |
| 4 | JWT `alg=none`, HS384, wrong secret, tampered signature, swapped payload, missing each claim, wrong iss/aud, expired, issued in the future, malformed | all 401 with one identical generic body |
| 5 | Token with `aud` as a list containing ours | **Found: accepted by PyJWT.** Fixed: audience must equal ours exactly (unit test) |
| 6 | Non-canonical `sub` (uppercase, no hyphens, braces, `urn:uuid:`) | **Found: accepted.** Fixed: subject must be the canonical lowercase hyphenated UUID |
| 7 | `exp`/`iat` as bool or string | **iat as bool was accepted.** Fixed: non-numeric/bool time claims rejected |
| 8 | Forged `role: teacher` / `is_admin` claims | ignored; role comes from PostgreSQL (tests incl. role changed after login) |
| 9 | Login user enumeration by body, status, headers, timing path | identical 401; unknown email still runs a dummy Argon2 verification (test spies on it); timing equality itself is not measured |
| 10 | Brute force / rate-limit bypass with rotating `X-Forwarded-For`, `Forwarded`, `X-Real-IP` | one shared bucket (tested, also against the real stack); 429 happens before hashing and DB access |
| 11 | Secrets in logs: passwords, tokens, secret, emails, hashes, Authorization header | none in captured logs (register, login ok/fail, invalid tokens) |
| 12 | Weak `JWT_SECRET` (short, placeholder, low variety, multibyte) in every environment | startup refuses, value never printed; `.env.example` placeholder itself is rejected |
| 13 | CLI: password as argument or abbreviation (`--pass`), existing email, role promotion, weak password, seed in production, seed without variables, seed twice | all refused or no-op; no password/hash printed |
| 14 | Consent: other/old/padded/uppercase version, empty, 21 chars, no token, cross-user effect | rejected with `current_version`, nothing stored |
| 15 | Mutation checks: removing the role check, removing the consistency of the UI constant | tests fail as expected (5 of 6 guard tests; drift test names both values) |

## Findings
| Severity | Area | Finding | Evidence | Fix |
|---|---|---|---|---|
| Major (fixed) | Input validation | NUL/control characters in `name` caused HTTP 500 | probe failed before the fix | code + tests (done) |
| Minor (fixed) | JWT | `aud` list, non-canonical `sub` and bool time claims were accepted; only forgeable by the secret holder | unit tests failed before the fix | code + tests (done) |
| Minor (fixed) | Spec | spec said "repeats a single character"; implementation requires 8 distinct characters; spec lacked the control-character and strict-claim scenarios | diff | spec text updated (done) |
| Minor (fixed after user approval) | Abuse | Registration was not rate limited and runs an Argon2 hash (about 64 MiB per call by default): an unauthenticated CPU/memory exhaustion and account-spam vector | design D7 limited scope to login | `POST /auth/register` now limited to 5/minute per address with the same `limits` mechanism (independent counters); tests prove 429 + `Retry-After`, no Argon2id call, nothing stored, forged forwarding headers ignored; verified on the live stack |
| Minor (tracked) | Rate limit | IPv6 prefix rotation, shared NAT and multi-worker deployments weaken the per-address limit | documented limitation | accepted; Redis/shared store later |
| Question | Configuration | `APP_ENV` defaults to `development`: a deployment that forgets it runs development defaults (including `seed` being allowed if the SEED variables are present) | `Settings` default | consider requiring `APP_ENV` explicitly in production deployment (change 13) |
| Question | Exposure | OpenAPI docs (`/docs`, `/openapi.json`) are enabled in every environment | scaffold default | decide for production in change 13 |
| Minor (tracked) | Tokens | No revocation or logout before `exp` (60 min default); user existence and role are re-checked on every request | design D4 | accepted, documented |
| Minor (tracked) | Tests | `cli.main()` wiring is covered only by the manual curl run (86 % coverage on `cli.py`); the rate-limit window test uses a 1.2 s real sleep instead of an injected clock | coverage report | accepted |
| Minor (tracked) | Process | Role guards were written together with `get_current_user` (before their dedicated tests); the tests were then validated by mutation | task 5 | recorded |

## Verdict
**PASS WITH GAPS.** No open blockers or majors: the one major (500 on control characters) and the JWT strictness gaps are fixed with regression tests. Open items are tracked minors/questions above, (unlimited registration was fixed after this review). Because this review was done in the implementing session, archiving is advisable only after the user accepts the tracked items (or asks for registration rate limiting) and, ideally, after a second independent pass.

## Recommended next steps (before archive)
- (Done) Rate limiting for `/auth/register`.
- Keep `APP_ENV`/docs exposure on the checklist of change 13 (deployment).
- Optionally run `/code-review` or a fresh-session adversarial pass on the PR.
