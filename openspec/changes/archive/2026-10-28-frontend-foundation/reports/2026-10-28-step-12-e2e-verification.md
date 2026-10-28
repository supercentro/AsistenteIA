# Step 12 Report - E2E verification (real backend)

- Date: 2026-10-28
- Change: frontend-foundation
- Agent: Claude Code (Sonnet 5.5)
- Tools: **Playwright MCP** (interactive, real Chrome against `http://localhost:5173` and the compose backend) for 12.1 and 12.2; **Playwright Test** for 12.3 (mocked suite and the gated real-backend spec).
- Environment: `docker compose up -d --build`; after the dependency change the frontend container needed `docker compose up -d --build -V frontend` because the anonymous `node_modules` volume kept the old packages (documented in the development guide, extends L15).

## 12.1 Interactive run with Playwright MCP (development database, baseline users=0)
| Step | Observed |
|---|---|
| Open `/` as an anonymous visitor | Redirected to `/login` |
| Register a student on `/register` | `POST /auth/register` 201, redirected to `/login` with the status "La cuenta se creó correctamente" |
| Sign in | `POST /auth/login` 200 without `Authorization`, `GET /users/me` 200, `GET /subjects` 200 **with** `Authorization: Bearer ...`; page `/subjects`, heading "Mis asignaturas", empty message |
| Sign out | Back on `/login` with "La sesión se cerró correctamente" |
| Wrong password | Alert "Correo o contraseña incorrectos."; console: one browser line for the 401 and one `[api] POST /api/v1/auth/login -> 401` (method, path, status only) |
| Subject created by the teacher through `curl` (name containing `<b>`, two-line description) and student enrolled | Student list shows the name literally (`Mcp <b>Algebra</b>`) and both description lines |
| 320 px viewport | `scrollWidth 320 = clientWidth 320`, no horizontal scroll |
| Full navigation to `/subjects` | Redirected to `/login` (a reload ends the session) |
| Teacher sign-in (account created with the CLI) | Heading "Asignaturas a mi cargo", only the button "Cerrar sesión" and the link "Asignaturas", the teacher's subject listed |
| 12 wrong logins from `curl` to reach the limit, then a UI sign-in | 429 answered; the UI shows "Se realizaron demasiados intentos. Espere un momento e inténtelo de nuevo." (**without seconds**: `Retry-After` is not exposed by the CORS configuration, see step 11 finding 1) |

## 12.2 Storage, console and network
- `localStorage` 0 items, `sessionStorage` 0 items, `document.cookie` empty after signing in.
- Console: no error produced by the application; the only application line is `[api] METHOD path -> status`; no token, password or email in any message.
- Network: login and register requests carry no `Authorization`; the `/users/me` and `/subjects` requests carry the bearer token; the only origin contacted besides the frontend is the API.

## 12.3 Playwright Test
- `npm run test:e2e` (mocked suite): **11 passed** (register to login, teacher view, token only on protected calls, wrong credentials, rate limit, reload ends the session, 401 mid-session, sign-out notice, 320 px, smoke).
- `E2E_REAL_BACKEND=1 E2E_SHORT_TOKEN=1 npx playwright test real-backend` against the isolated backend (test database, `JWT_EXPIRE_MINUTES=1`): **5 passed** in 1.1 min: register/sign in/list/reload/sign out; wrong credentials; **real 401** (the request reaches the server with a tampered `Authorization` header and the UI ends the session once); CORS preflight and anonymous 401; **token expiry** (the UI returns to the login screen with "La sesión expiró" by itself and the server answers 401 to the old token).
- Rotated key: covered at API level in the step 11 report (a token of the previous secret is answered 401 after restarting the isolated server with another secret); the browser-level real 401 is the tampered-header case above.

## Restoration
- Isolated Uvicorn processes stopped, test database emptied, compose backend started with its original configuration (`health=200`), development database cleaned to `users=0 subjects=0 enrollments=0`, `alembic=0003`.
- Playwright MCP browser session closed.

## Deviations and notes
- Task 8.1 listed a "wrong-role view" browser case: no role-exclusive production route exists in this change, so that behaviour is covered by the component tests with a role-exclusive test route (`App.test.tsx`).
- The generic (secondless) rate-limit message in a real browser is a finding for the owner, not a defect of the frontend.

## Addendum: TD-021 verification in a real browser
- With the rebuilt backend, after reaching the login limit, signing in through the UI showed `Se realizaron demasiados intentos. Espere 47 segundos e inténtelo de nuevo.` (Playwright MCP, Chrome).
- A `fetch` executed in the page context to the API read `Retry-After` = `38` (status 429), which was `null`/unreadable before the fix.
- The gated spec `E2E_REAL_BACKEND=1 npx playwright test real-backend` against the compose stack: 5 passed, 1 skipped (token expiry needs `E2E_SHORT_TOKEN=1` and was verified earlier in the isolated environment), including the new `a real 429 states the wait` case. The mocked suite now mirrors the real header and expects `Espere 17 segundos` (11 passed).
- Cleanup: the user created by the gated spec was deleted; development database `users=0 subjects=0 enrollments=0`.
