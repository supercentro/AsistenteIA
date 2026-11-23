# Manual verification (tasks 3.3 and 3.4)

Date: 2026-11-23. Fictitious data only; no real Gemini call; the Docker stack of the owner was not touched.

## 3.3 Manual endpoint test with curl (the existing endpoint, a real Uvicorn process)
A real server (production arguments) against the guarded test database `asistenteia_test`, migrated to head for the run and dropped afterwards, with one teacher, another teacher, one student enrolled, six more students with six conversations (24 messages). Result:

| Backend switch | Caller | Status |
|---|---|---|
| on | owner | 200 (6 active of 7 enrolled, figures as seeded) |
| on | another teacher | 404 `Subject not found` |
| on | student | 403 |
| on | anonymous | 401 |
| on | owner, `granularity=day` / 13 weeks / `end=9999-12-31` | 422 / 422 / 422 (never 500) |
| off (default) | owner and another teacher | 404 `Resource not found` |
| off | student / anonymous | 403 / 401 |

Rows of users, subjects, enrollments, documents, conversations, messages and message_sources were identical before and after (the endpoint writes nothing). The frontend adds no backend call besides this one.

## 3.4 Browser run by the agent (Playwright MCP)
A private Vite dev server with `VITE_TEACHER_ACTIVITY_ENABLED=true` and a throwaway mock API with fictitious data (ports 5175 and 8010, stopped afterwards). Login, the subject, the **Ver actividad** link in the header, then the page: cards, the weekly table with one withheld week reading «Datos insuficientes» and no bar, the two shares, the documents table with a deleted document and a withheld figure, the privacy note. **One** request to `/activity` and none with a query string; no console error or warning; at 320 px the page has no horizontal scrolling (305 px of 320); every bar has `aria-hidden="true"`. Screenshot: `activity-desktop.png`. The committed Playwright Test spec (`e2e/teacher-activity.mocked.spec.ts`) passes, and the five mocked suites (30 tests) pass with the flag on.
