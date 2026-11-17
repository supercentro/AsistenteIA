# Step 13: HTTP testing against a real server process

**Change**: chat-rag-endpoint
**Runs**: 2026-11-16 (manual curl), 2026-11-17 (committed real-server tests)
**Isolation**: `asistenteia_test` database only (`127.0.0.1:5442`, name checked before every connection); fake LLM and fake embedder (`APP_ENV=test`, `LLM_BACKEND=fake`, `EMBEDDER_BACKEND=fake`); Gemini never called; persistent database `asistenteia` and the compose containers untouched.

## A. Manual curl run (2026-11-16) — partial, kept for traceability

Server: `uvicorn app.main:app_factory --factory` on `127.0.0.1:8099` against the test database. Student without material (no chunks seeded):

| Check | Expected | Observed |
|---|---|---|
| `POST /chat` enrolled and consented, no material | 200, `no_material=true` | 200, `no_material=true`, `sources=[]` |
| No token | 401 | 401 |
| Teacher token | 403 | 403 |
| Empty message | 422 | 422 |
| 2001-character message | 422 | 422 |
| `GET /conversations` and `?subject_id=` | 200 | 200 |
| `GET /conversations/{id}/messages` | 200 | 200, sources empty (no material) |
| `DELETE /conversations/{id}`, `DELETE /users/me/conversations` | 204 | 204, list empty afterwards |

This run did **not** cover consent, enrolment, isolation between students or messages with sources. Those are covered by section B.

## B. Real-server tests (2026-11-17) — `backend/tests/integration/test_chat_real_server.py`

The tests start a real Uvicorn process with the production arguments (`--factory --no-proxy-headers`) on a free port and talk to it over a raw socket. Seed data: one subject, one chunk embedded with the fake embedder.

| Test | Result |
|---|---|
| No token → 401 | pass |
| Teacher → 403 | pass |
| No consent → 403 `CONSENT_REQUIRED` | pass |
| Outdated consent (`2025-01-v0`) after a successful chat → 403 `CONSENT_REQUIRED` | pass |
| Not enrolled → 404 (superseded 2026-11-17: now 403, unknown subject 404; see the round-2 matrix) | pass at the time |
| Answer has sources (`document_filename`, `page_number`) and the history endpoint returns the same sources | pass |
| Another student: read messages 404, continue conversation 404, delete 404, own list empty; owner still reads 200 | pass |

Command: `backend/.venv/Scripts/python.exe -m pytest tests/integration/test_chat_real_server.py -q` → 7 passed.

Mutation checks (TDD deviation compensation: tests written after the code). Each mutation made at least one of these tests fail and was reverted: consent gate removed, enrolment gate removed, conversation ownership check removed.

## C. Environment notes

- `tests/server_support.py` now keeps `SYSTEMROOT` in the child environment and kills the process tree on Windows teardown (the venv launcher left a child holding the log file). No other test-support behaviour changed.
- The database restore step (13.7) needs no action: the test database is rebuilt and truncated by the fixtures, and it holds no tables at rest (see step-12 report).
