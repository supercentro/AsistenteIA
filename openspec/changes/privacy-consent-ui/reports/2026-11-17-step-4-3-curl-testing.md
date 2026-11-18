# Step 4.3 Report - Manual endpoint testing with curl

- Date: 2026-11-17
- Change: privacy-consent-ui
- Target: local development stack, `http://127.0.0.1:8000/api/v1` (backend rebuilt on `main` at `f327be6`, revision `0007`, simulated LLM). The backend is not changed by this change; the calls prove the contract the new screens rely on.
- Account: `consent-curl-1117204901@example.com` (new student, random password never printed or stored).

| Call | Expected | Result |
|---|---|---|
| `GET /users/me` (new student) | 200, `consent_version` null | 200, `{"consent_version": null, "role": "student"}` |
| `POST /chat` without consent | 403 `CONSENT_REQUIRED` | 403 `{"code": "CONSENT_REQUIRED"}` |
| `POST /users/me/consent` without token | 401 | 401 `UNAUTHORIZED` |
| `POST /users/me/consent` with `"2099-x"` | 422 `INVALID_CONSENT_VERSION` and `details.current_version` | 422, `details: {"current_version": "2026-10-v1"}` |
| `POST /users/me/consent` with `""` | 422 `VALIDATION_ERROR` | 422, field `body.consent_version`, "String should have at least 1 character" |
| `GET /users/me` after the failures | still no consent | 200, `consent_version` null |
| `POST /users/me/consent` with `"2026-10-v1"` | 200, version stored | 200, `{"consent_version": "2026-10-v1"}` |
| `POST /chat` with consent, unknown subject | 404, not 403 (a 200 answer needs an enrolled subject and was not exercised here; it is covered by the chat change) | 404 `NOT_FOUND` |

The same sequence ran once before with status codes only (an account `consent-curl-1117204849@example.com`), with identical codes.

## Restoration
The consent of a test account cannot be removed through the API and the accounts cannot be deleted (no endpoint). The rows belong to test accounts created for this check; see the database comparison in `2026-11-17-step-4-2-unit-test-and-db-verification.md`.

## Outcome
Step 4.3 status: PASS. The error bodies carry only `code`, `message` and `details` (the new screens show their own Spanish text and never the server message).
