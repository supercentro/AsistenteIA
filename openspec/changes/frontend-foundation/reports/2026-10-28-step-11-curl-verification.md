# Step 11 Report - Manual endpoint testing with curl (real backend)

- Date: 2026-10-28
- Change: frontend-foundation
- Agent: Claude Code (Sonnet 5.5)
- Environment: `docker compose up -d --build` (backend on 8000, frontend on 5173, development database `asistenteia`), executed from the host with `curl`; script kept in the session scratchpad (`curl_suite.sh`). Credentials are random per run and were not printed.

## Baseline and restoration
- Before: `users=0 subjects=0 enrollments=0 alembic=0003`; backend configuration untouched (`JWT_EXPIRE_MINUTES` not set in compose, default 60).
- After (once the whole step 11 and 12 work finished): `delete from enrollments; delete from subjects; delete from users` removed the 4 users, 2 subjects and 2 enrollments created by the checks; result `users=0 subjects=0 enrollments=0 alembic=0003`. The compose backend is running again with its original configuration.

## Results (20 PASS, 0 FAIL)
```
teacher created: 0
--- registration
PASS | register 201 | expected=201 | actual=201
PASS | register duplicate 409 | expected=409 | actual=409
PASS | register short password 422 | expected=422 | actual=422
422 body: {"code":"VALIDATION_ERROR","message":"Request validation failed","details":{"errors":[{"field":"body.password","message":"String should have at least 10 characters"}]}}
--- login
login keys: ['access_token', 'expires_in', 'token_type'] expires_in= 3600 token_type= bearer
PASS | login 200 returns a token | expected=yes | actual=yes
PASS | teacher login returns a token | expected=yes | actual=yes
PASS | login wrong password 401 | expected=401 | actual=401
401 body: {"code":"INVALID_CREDENTIALS","message":"Invalid email or password"}
--- /users/me and Authorization
PASS | me with token 200 | expected=200 | actual=200
me keys: ['consent_accepted_at', 'consent_version', 'email', 'id', 'name', 'role'] student
teacher role: teacher
PASS | me without token 401 | expected=401 | actual=401
401 body: {"code":"UNAUTHORIZED","message":"Invalid or expired token"}
PASS | me with garbage token 401 | expected=401 | actual=401
PASS | me with tampered token 401 | expected=401 | actual=401
PASS | me with wrong scheme 401 | expected=401 | actual=401
PASS | login endpoint ignores a bearer header | expected=401 | actual=401
--- subjects (student and teacher views)
PASS | student list 200 | expected=200 | actual=200
student list: []
PASS | subjects without token 401 | expected=401 | actual=401
PASS | teacher creates subject (setup) | expected=yes | actual=yes
teacher list count: Curl Algebra
PASS | student not enrolled sees none | expected=[] | actual=[]
PASS | enroll student (setup) | expected=201 | actual=201
student list after enrollment: [('Curl Algebra', ['created_at', 'description', 'id', 'name', 'teacher_id'])]
--- CORS
preflight allowed origin:
HTTP/1.1 200 OK
vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers, Access-Control-Request-Private-Network
access-control-allow-methods: DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT, QUERY
access-control-max-age: 600
access-control-allow-credentials: true
access-control-allow-origin: http://localhost:5173
access-control-allow-headers: authorization,content-type
PASS | preflight allowed origin 200 | expected=200 | actual=200
preflight disallowed origin:
HTTP/1.1 400 Bad Request
vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers, Access-Control-Request-Private-Network
access-control-allow-methods: DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT, QUERY
access-control-max-age: 600
access-control-allow-credentials: true
access-control-allow-headers: authorization
PASS | preflight disallowed origin has no allow-origin | expected= | actual=
actual GET with Origin (headers a browser can read):
HTTP/1.1 200 OK
access-control-allow-credentials: true
access-control-allow-origin: http://localhost:5173
--- rate limit (last: it blocks this address for a minute)
429 reached at attempt 6
HTTP/1.1 429 Too Many Requests
retry-after: 51
access-control-allow-credentials: true
access-control-allow-origin: http://localhost:5173
PASS | rate limit returns 429 | expected=HTTP/1.1 429 Too Many Requests | actual=HTTP/1.1 429 Too Many Requests
429 Retry-After present: 1
429 Access-Control-Expose-Headers present: 0

TEACHER_EMAIL=curl-teacher-<ts>@example.com STUDENT_EMAIL=curl-student-<ts>@example.com
RESULT: pass=20 fail=0
```

## Findings
1. **`Retry-After` is not readable by a browser.** The 429 carries `retry-after` but not `access-control-expose-headers`; the backend CORS middleware (`backend/app/main.py`) does not set `expose_headers`. A cross-origin frontend therefore never sees the value and shows the generic rate-limit message (confirmed in the real browser, step 12). The frontend handles the missing header by design (spec scenario "missing header falls back"). Making the wait time visible needs a one-line backend change (`expose_headers=["Retry-After"]`), which is outside this change's scope: **decision requested from the owner**.
2. CORS preflight from the allowed origin returns 200 with `access-control-allow-origin: http://localhost:5173` and `access-control-allow-headers: authorization,content-type`; the disallowed origin gets 400 and no `allow-origin`.
3. Error bodies match `docs/api-spec.yml` (`UNAUTHORIZED`, `INVALID_CREDENTIALS`, `VALIDATION_ERROR` with `details.errors`); the frontend ignores `message` and `details`.
4. `/users/me` returns exactly the six `User` fields and `GET /subjects` the five `Subject` fields, matching the `required` lists added to `docs/api-spec.yml`.

## Token expiry and rotated key (isolated environment)
Per the owner's instruction, JWT settings were changed only in an isolated process: a separate Uvicorn started by a script on port 8000 (the compose backend stopped meanwhile), against the **test database** `asistenteia_test`, with a throwaway secret and `JWT_EXPIRE_MINUTES=1` passed as process environment (no `.env`, compose or repository file edited).
- `POST /auth/login` returned `expires_in=60`; `GET /users/me` with that token: 200 before expiry, 200 at 58 s, **401 `UNAUTHORIZED` at 64 s**.
- A token issued with secret one, after restarting the isolated server with secret two: **401 `UNAUTHORIZED`** (the same token answered 200 before the restart).
- Cleanup: both isolated servers stopped, the test database emptied (`drop_everything`), the compose backend started again and verified (`health=200`, configuration unchanged).

## Addendum: TD-021 resolved (backend rebuilt with `expose_headers=["Retry-After"]`, commit `1d65ac1`)

```
== 429 with allowed Origin
HTTP/1.1 429 Too Many Requests
retry-after: 57
access-control-allow-credentials: true
access-control-expose-headers: Retry-After
access-control-allow-origin: http://localhost:5173

== 429 with disallowed Origin (no access-control-allow-origin, so a browser grants nothing)
HTTP/1.1 429 Too Many Requests
retry-after: 57
access-control-allow-credentials: true
access-control-expose-headers: Retry-After

== preflight allowed (unchanged)
HTTP/1.1 200 OK
access-control-allow-methods: DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT, QUERY
access-control-allow-credentials: true
access-control-allow-origin: http://localhost:5173
access-control-allow-headers: authorization,content-type
```

Finding 1 above is therefore closed. The development database was cleaned again (`users=0 subjects=0 enrollments=0 alembic=0003`).
