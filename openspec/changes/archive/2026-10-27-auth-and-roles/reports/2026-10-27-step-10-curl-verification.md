# Step 10 Report - Manual Endpoint Testing with curl

- Date: 2026-10-27
- Change: auth-and-roles
- Agent: Claude Code (Sonnet 5.5)

Stack: `docker compose up -d --build backend`, then `docker compose exec backend alembic upgrade head` (`0001`, `0002` applied) and `alembic check` ("No new upgrade operations detected": models and migration agree). Base URL `http://127.0.0.1:8000/api/v1`. Passwords were generated per run and are not recorded; tokens are redacted. The script is kept in the session scratchpad only.

## Results (all as expected)

| Step | Request | Expected | Observed |
|---|---|---|---|
| 10.2 | register student (mixed-case email) | 201 student, lowercase email, no credentials | 201, `role: student`, `email: ana.curl@example.com`, consent fields null |
| | register duplicate (other case) | 409 | 409 `CONFLICT` |
| | short password / invalid email | 422 | 422 `VALIDATION_ERROR`, field names only |
| | `"role": "teacher"` injection | 201 as student | 201, `role: student` |
| 10.3 | login (uppercase email) | 200 | 200 `token_type: bearer`, `expires_in: 3600` |
| | wrong password / unknown email | identical 401 | 401 `INVALID_CREDENTIALS`, identical bodies |
| 10.3b | 12 failed attempts, default `10/minute` | 429 after the limit | `401 x5` then `429` with `retry-after: 48`...`47` (earlier logins in the run counted); correct credentials while limited: 429; `/health` while limited: 200; forged `X-Forwarded-For`: still 429 |
| 10.4 | `GET /users/me` valid token | 200 own profile | 200 |
| | tampered token, no header, forged `alg=none` | 401 | 401 `UNAUTHORIZED` + `WWW-Authenticate: Bearer`, same body |
| 10.5 | consent current version / re-accept | 200, timestamp updated | 200; `consent_accepted_at` advanced from `21:55:22.134963Z` to `21:55:22.551636Z` |
| | other version | 422 with current version | 422 `INVALID_CONSENT_VERSION`, `details.current_version: 2026-10-v1` |
| | empty version / no token | 422 / 401 | 422 `VALIDATION_ERROR` / 401 |
| 10.6 | `create-teacher --password-stdin` | created, exit 0, no password in output | `Created teacher id=... email=...` |
| | same email again; weak password; `--password foo` | refused | `already exists; nothing was changed`; `10-128 characters`; `unrecognized arguments: --password foo` (exit 2) |
| | teacher logs in | 200 | 200 |
| | `seed` twice | created then skipped | `Created teacher/student` then `Skipped ... already exists` |
| | `seed` with `APP_ENV=production`; without variables | refused | `seed is disabled when APP_ENV=production`; `Missing seed variables: SEED_...` |

## Addendum: registration rate limit (after the first review)
Backend rebuilt, 7 consecutive registrations from the same client with a different forged `X-Forwarded-For` each: `201 201 201 201 201 429 429` (`retry-after: 60`). Exactly 5 accounts were stored (the 429s created nothing), login with a registered account still returned 200 (separate counters). The 5 accounts were deleted afterwards.

## Migration check on the development database
`alembic downgrade -1` removed table `users` and type `user_role`; `alembic upgrade head` restored them (revision `0002`).

## Database State
- Before: `asistenteia` with `alembic_version` only (after the manual migration).
- Cleanup: the 5 accounts created by this step were deleted (`DELETE 5`, 0 users remain).
- After: tables `alembic_version`, `users` (empty), revision `0002` (the intended result of migrating the development database).

## Outcome
- Step 10 status: PASS
- Blocking issues: none
