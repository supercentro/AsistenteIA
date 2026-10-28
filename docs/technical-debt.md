# Technical Debt Register

Central register of residual risks and known limitations accepted when a change was merged. Each item names the change expected to resolve it. This document only **records**; resolving an item happens inside the OpenSpec change listed under "Owner", with the user's approval of scope.

Change numbers refer to the approved 13-change plan (`3` subjects-and-enrollments, `4` frontend-foundation, `5` documents-schema-pgvector, `6` document-ingestion, `7` teacher-material-ui, `8` conversation-persistence, `9` rag-chat, `10` student-chat-ui, `11` personal-data-erasure, `12` e2e-and-quality-closure, `13` deployment-and-delivery-docs). Archived changes are not modified.

## Conventions

- **Priority**: High (blocks a safe release or a mandatory feature), Medium (should be handled before delivery), Low (accept or revisit on evidence).
- **Status**: `open` (not started), `planned` (assigned to an upcoming change's tasks), `accepted` (deliberate trade-off, revisit only on evidence), `resolved` (fixed; keep the row and link the change).
- **Owner**: the change that should resolve it, or `Future feature` when it is outside the approved MVP and needs user approval before being planned (see `docs/base-standards.md` section 8).
- Add a new row (next free ID) whenever a change is merged with a known residual risk; update the status instead of deleting rows.

## Register

| ID | Description | Priority | Impact | Current mitigation | Owner | Status |
|---|---|---|---|---|---|---|
| TD-001 | `APP_ENV` defaults to `development` and the interactive docs (`/docs`) are exposed in every environment | High | A production deployment that forgets `APP_ENV` runs with development behaviour and public API docs | `JWT_SECRET` is required in all environments; production CORS rules and seed restrictions apply once `APP_ENV=production` is set | Change 13 | planned |
| TD-002 | Rate limiting is in memory (`limits`): per process, lost on restart, not shared across workers, and behind a reverse proxy all clients share one bucket until trusted proxies are configured | High | Limits are weaker in a multi-worker or proxied deployment; login and registration can be brute-forced more freely | Per-connection-address limits (login 10/min, register 5/min), forwarding headers never trusted, Uvicorn runs with `--no-proxy-headers`, limits documented in `docs/development_guide.md` | Change 13 (single worker or trusted proxy list); shared store (e.g. Redis) is a Future feature | planned |
| TD-003 | The current privacy-policy consent is recorded but not enforced on `/chat`; `docs/api-spec.yml` still says "recorded consent" instead of "consent for the current policy version" | High | A student with no or outdated consent could use chat once it exists | `has_current_consent` helper and `PRIVACY_POLICY_VERSION` validation already exist; chat does not exist yet | Change 9 (enforcement, align `api-spec.yml`); change 10 (UI re-acceptance flow) | planned |
| TD-004 | Argon2id parameters are the library defaults; they were not measured on the deployment host and there is no rehash-on-login | Medium | Hashing cost may be too low or too slow for the target hardware | Argon2id with 10-128 character passwords; dummy-hash verification keeps login timing uniform | Change 13 (measure on target host) | planned |
| TD-005 | The frontend `PRIVACY_POLICY_VERSION` constant (`frontend/src/lib/privacyPolicy.ts`) must be kept equal to the backend value, including any environment override; no endpoint exposes the version | Medium | A deployment that overrides the backend version without rebuilding the frontend makes registration fail with 422 | Consistency tests in CI; the 422 response includes `current_version` | Changes 10 and 13 (decide on deriving it at build or runtime) | open |
| TD-006 | Access tokens cannot be revoked before they expire (60 minutes by default); there is no logout-everywhere, refresh token or password change | Medium | A stolen token stays valid until expiry | Short lifetime; the user and role are re-read from PostgreSQL on every request, so deleting a user or changing the role takes effect immediately | Future feature (outside the approved MVP) | open |
| TD-007 | The per-address rate limit is weak against IPv6 prefix rotation, shared NAT and distributed attacks | Low | A determined attacker can spread attempts across addresses | Argon2id cost and uniform 401 responses; limits per connection address | Hardening after change 13 | open |
| TD-008 | `POST /auth/register` returns 409 for an existing email, revealing which emails are registered | Low | Account enumeration | Approved contract decision; registration is rate limited | none | accepted |
| TD-009 | Passwords are not normalised in Unicode (NFC/NFKC) | Low | The same visible password typed with different compositions may not match | Length-only validation; hashes are computed over the exact input | Future feature | open |
| TD-010 | A single `JWT_SECRET` with no key rotation (`kid`) | Low | Rotating the secret invalidates every session at once | Secret validation (at least 32 bytes, no placeholders); a rotation is a redeploy | Future feature | open |
| TD-011 | The interactive password prompt of `create-teacher` is covered only by an injected prompt, not by a real terminal | Low | A regression in the real `getpass` path would go unnoticed | Real-process CLI tests cover the non-interactive paths | Change 13 (manual check in the delivery checklist) | planned |
| TD-012 | Local databases that applied an earlier version of migration `0002` need `alembic downgrade -1` then `upgrade head` | Low | Developer confusion on stale local databases | Documented in `docs/development_guide.md`; CI uses clean databases | none | accepted |
| TD-013 | The test-database isolation guard is a naming and environment convention, not a privilege boundary; it does not stop a manual `alembic downgrade` against the development database | Low | Developer mistake can reset development data | Guard rejects unsafe configurations before opening connections; the test database is a separate database | none | accepted |
| TD-014 | The 5 second PostgreSQL connect timeout bounds only connection establishment, not query duration | Low | A slow query can still hold a request | `/health` returns 503 when the database does not answer | Change 12 (revisit with load evidence) | open |
| TD-015 | ESLint is pinned to major version 9 (deprecated) because ESLint 10 conflicts with `eslint-plugin-jsx-a11y`; backend dependencies use `>=` ranges pinned only by `uv.lock` | Low | Future tooling upgrades need a dedicated change | Lock files committed; `pip-audit` and `npm audit` run in CI (non-blocking) | Change 12 (review before delivery) | open |

## Related documents

- Security design and rate-limit limits: `docs/backend-standards.md`, `docs/development_guide.md`.
- Archived origin of each item: `openspec/changes/archive/2026-10-27-project-scaffold/` (TD-013 to TD-015) and `openspec/changes/archive/2026-10-27-auth-and-roles/` (TD-001 to TD-012).
- AI-usage record of both changes: `prompts.md` sections 10 and 11.
