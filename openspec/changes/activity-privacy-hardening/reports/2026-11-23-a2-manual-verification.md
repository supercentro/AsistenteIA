# Manual verification of A2 + A2b (tasks 5.3 and 5.4)

Date: 2026-11-23. Fictitious data; throwaway database in its own container; no Gemini call (fake embedder and LLM); the Docker stack of the owner was not touched (private ports 8011 and 5175, stopped afterwards).

## Endpoint, with a real Uvicorn process (`app.main:app_factory`, `--no-proxy-headers`, the switch on for this run only)

One teacher (owner), another teacher, one student enrolled, six students with two ended weeks of activity (12 questions each week) and six questions made minutes ago (in the open week).

| Request | Result |
|---|---|
| owner, default window | 200: 12 weeks ending on the last Sunday (2026-11-22), 2 weeks shown, 6 active, **the open week (2026-11-23) is not in the window** |
| owner, the same read again | identical |
| another teacher / student / anonymous | 404 / 403 / 401 |
| owner, `end=9999-12-31` / 13 weeks / `granularity=day` | 200 (cut at the last ended Sunday) / 422 / 422, never 500 |
| owner removes one student | 204 |
| owner reads again | 200: **0 weeks**, start 2026-11-23, end 2026-11-22, no questions, `active_students` null, 6 enrolled, suppressed |
| the same removal again | 404 |
| the subject read after the removal | no marker field |

Rows before and after the first reads were identical; after the removal only `enrollments` changed (7 to 6). The marker was written by the same route and no other table changed.

## Browser, by the agent (Playwright MCP) against the real backend

Login as the owner, the subject, the **Ver actividad** link, then the page, before and after a removal made through the API (screenshots `a2-before-removal.png` and `a2-after-removal.png`).

- Before: 12 weeks «Semanas del 31/08/2026 al 22/11/2026», the note «Se muestran solo semanas completas.», no limit note, the weekly table, the bars (4), no horizontal overflow.
- After (the run showed the first wording of the note, «Por un cambio reciente…»; the owner changed it to the one below on 2026-11-23): only the enrolled count (6), «Datos insuficientes» in the active card, the note «Por un cambio en las inscripciones, todavía no hay semanas completas para mostrar.», **no window line, no table, no bar**, the focus on the heading, no console warning or error.
- The Playwright Test suites with the mocked API (the page, a withheld week, all withheld, no whole week, fewer weeks, a student refused, the keyboard) pass against a dev server started with the flag.
