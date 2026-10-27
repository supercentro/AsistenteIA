# Proposal

## Why

Every remaining MVP feature (subjects, enrollments, documents, chat, GDPR deletion) depends on knowing who the caller is and what role they have. `readme.md` §2.5 requires JWT authentication with expiry, argon2 password hashing, teacher/student roles with no self-assignment of the teacher role, and recorded privacy consent before chat. The scaffold (`project-scaffold`, merged and archived) provides the base but has no users or authentication. This is change 2 of the approved 13-change plan; it is an enabling change (not a user story) confirmed as mandatory MVP scope.

## What Changes

- New `users` table through an Alembic migration (with `downgrade`), as defined in `docs/data-model.md`: `id`, `name`, `email` (unique, stored lowercase), `password_hash` (Argon2id), `role` (`teacher` | `student`), `consent_version`, `consent_accepted_at`, `created_at`.
- `POST /api/v1/auth/register`: public registration that always creates a **student**; duplicate email returns 409; rate limited (initially 5 requests/minute per client address, 429 with `Retry-After`).
- `POST /api/v1/auth/login`: email + password, returns an expiring HS256 JWT (`access_token`, `token_type`, `expires_in`). Unknown email and wrong password return the same 401. Basic per-client rate limiting returns 429.
- `GET /api/v1/users/me`: profile of the authenticated user.
- `POST /api/v1/users/me/consent`: records acceptance of the **currently configured** privacy-policy version (any other version is rejected); re-acceptance updates version and timestamp.
- Authentication dependency (Bearer JWT with strict validation of signature, algorithm, issuer, audience and expiry; role re-read from PostgreSQL on every request) and role guards for teacher-only and student-only endpoints, used by later changes.
- Command-line administration (never HTTP): `python -m app.cli create-teacher` and an explicit, idempotent `python -m app.cli seed` that creates only one teacher and one student (no subjects), refuses to run in production and has no built-in default credentials.
- New settings and `.env.example` entries: JWT secret (minimum 32 bytes, weak values rejected), issuer, audience, expiry, current privacy-policy version, login rate limit, seed variables.
- Documentation: `docs/api-spec.yml` (429 on login, 422 on consent, password and name bounds, new error codes), `docs/data-model.md` (lowercase-email check), `docs/development_guide.md` (variables, CLI, limitations).

**Out of scope** (confirmed inside the approved MVP, handled by other changes): subjects and enrollments (change 3); every frontend screen, including login, registration, the consent screen and in-memory token handling (changes 4 and 10); enforcing consent inside `/chat` (change 9); account deletion `DELETE /users/me` (change 11); refresh tokens, token revocation, logout endpoint, password change/reset, email verification, OAuth/SSO, user-administration endpoints, a public endpoint exposing the policy version, and any role other than teacher/student. No feature beyond the approved MVP is added.

## Capabilities

### New Capabilities
- `user-authentication`: student registration, email/password login with expiring JWT and uniform failures, login rate limiting, strict token validation, the authenticated profile, and credential/secret handling rules.
- `role-based-access`: role model (teacher/student), per-request role re-validation against the database, role guards, and out-of-band teacher creation and seeding.
- `privacy-consent`: recording of acceptance of the configured privacy-policy version (version and timestamp) per user, the evidence later required by chat.

### Modified Capabilities
- `api-error-handling`: database outages answer 503 on every endpoint and unexpected failures never write request data to logs (ADDED requirements).
- `service-health`: the stable-contract requirement no longer claims that `/api/v1/health` is the only API path (obsolete once authentication endpoints exist); the 200/503 contract itself is unchanged.

## Impact

- **Authorization / data isolation:** introduces the authentication and role layer used by every later change. Each guard has denied-case tests (no token, invalid or expired token, wrong role, role changed in the database). Resource-level isolation by subject/user starts in change 3.
- **Personal data (GDPR):** first storage of personal data (name, email, consent evidence). Passwords are stored only as Argon2id hashes and are never returned or logged; tokens, secrets and passwords never appear in logs. Erasure arrives in change 11.
- **External services (Gemini):** none.
- **API contract:** `docs/api-spec.yml` already defines the four endpoints. This change adds, for approval: 429 (with `Retry-After`) on login, 422 on consent for a non-current version, `maxLength` 128 on password, `minLength` 1 on name, and the new error codes `INVALID_CREDENTIALS`, `RATE_LIMITED`, `INVALID_CONSENT_VERSION`.
- **Data model:** `users` as in `docs/data-model.md`, plus a check constraint guaranteeing lowercase emails (documented there).
- **Code:** `backend/` (models, schemas, repositories, services, endpoints, `core/security.py`, rate limiter, `app/cli.py`, migration, tests). Frontend: only the one-line constant `frontend/src/lib/privacyPolicy.ts` and its test; no screens or auth UI.
- **Dependencies:** `PyJWT`, `argon2-cffi`, `email-validator` (via `pydantic[email]`) and `limits` (rate limiting).
- **Architecture-affecting decisions to approve:** listed in `design.md` (D1-D14), notably the `limits` library instead of `slowapi`, in-memory rate-limit storage and its limitations, the consent-versus-current-policy predicate reserved for the chat change, and the choice not to add an endpoint for the policy version.

## Decisions approved by the user (2026-10-27)

1. Seed contains only a teacher and a student, no subjects; explicit, idempotent, no insecure default credentials in production.
2. `consent_version` is validated against the configured current policy version; arbitrary versions are rejected.
3. Basic login rate limiting returning 429, with tests; in-memory limitations documented.
4. Duplicate registration email returns 409; unknown email and wrong password return an identical 401.
5. Passwords: minimum 10 characters, Argon2id, no complexity rules.
6. Re-accepting consent updates version and timestamp.
7. JWT: HS256; claims `sub`, `iat`, `exp`, `iss`, `aud`; configurable expiry; strict validation; secret of at least 32 bytes and no insecure values in production; role re-read from PostgreSQL on every authenticated request; no passwords, tokens or secrets in logs; teacher creation only through administrative commands.

8. Rate limiting uses `limits` with in-memory storage, 10 attempts per minute per address; headers such as `X-Forwarded-For` are never trusted when supplied directly by clients.
9. The backend setting `PRIVACY_POLICY_VERSION` has an equivalent UI constant (`frontend/src/lib/privacyPolicy.ts`, constant only, no screens) with automated consistency checks in CI; no endpoint exposes the version.
10. Valid consent for the **current** version will be required by `/chat`; enforcement belongs to change 9 and is not implemented here.
11. Registration rate limiting (5/minute per address, `limits`, no trust in client-supplied forwarding headers, rejected requests run no Argon2id and persist nothing) approved on 2026-10-27 after the first adversarial review.
12. Independent review (2026-10-27) findings F1 (log leakage on SQL errors), F2 (rate-limit bypass via `X-Forwarded-For` with loopback proxies), F3-F7 (name look-alike characters, CLI name check, argument echo, login `maxLength` in the contract, 503 on outage) are fixed in this change; F8 (email Unicode normalization) is resolved by restricting emails to ASCII (lowercased), enforced in the schemas (registration, login, CLI) and by a database check.
13. Emails are restricted to ASCII and lowercased everywhere (registration, login, CLI); compatibility checked (no existing rows; migration `0002` unmerged).
14. Implementation approved to start (2026-10-27) with mandatory adversarial review; no commits, push, PR, merge or archive of this change without further approval.
