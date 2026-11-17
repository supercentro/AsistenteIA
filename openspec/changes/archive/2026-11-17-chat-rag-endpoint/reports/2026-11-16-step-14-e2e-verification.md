# Step 14: Browser verification

**Change**: chat-rag-endpoint (backend-only; no frontend file was modified: `git status --short frontend` is empty)
**Run**: 2026-11-17, Playwright MCP (real Chromium)

## Executed

Isolated stack: Vite dev server on `http://localhost:5180` (`VITE_API_URL=http://localhost:8099/api/v1`) and the API on port 8099 against `asistenteia_test`, with fake LLM and embedder. The persistent frontend (5173) and backend (8000) were not used. A test teacher, student and subject were seeded in the test database only.

| Step | Observed |
|---|---|
| Open `/` | redirected to `/login`, form rendered |
| Log in as the test student | `POST /auth/login` 200, `GET /users/me` 200, redirected to `/subjects` |
| Subjects page | "Mis asignaturas" lists the seeded subject; `GET /subjects` 200 |
| Console errors after login | 0 |
| New endpoints called with `fetch` from the page origin (CORS and preflight exercised) | chat without consent → 403 `CONSENT_REQUIRED`; consent → 200; chat → 200 (`no_material=true`, no chunks seeded); list conversations → 200 (1); `DELETE /conversations/{id}` → 204; list → 0 |
| Console after the `fetch` calls | 1 error entry: the browser's log of the expected 403 response |

## Not executed (pending, not claimed)

- There is no chat UI in this change, so no chat screen was exercised in the browser.
- The committed Playwright suite (`npm run test:e2e`, required by base-standards 9.2 before final delivery) was not run.
- The teacher flows (subjects, documents) were not exercised in the browser.
- A screenshot was not saved (the screenshot tool rejected the scratchpad path).

## Cleanup

Vite and the API were stopped (ports 5180 and 8099 no longer listening); the persistent containers kept their uptimes.
