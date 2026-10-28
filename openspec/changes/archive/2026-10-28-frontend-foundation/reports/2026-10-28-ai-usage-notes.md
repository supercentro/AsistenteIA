# AI Usage Notes - frontend-foundation

Working notes for a later `prompts.md` proposal (needs the user's approval). Literal fragments are marked; the rest are summaries. Tool: Claude Code (Sonnet 5.5), OpenSpec workflow (`/opsx:explore`, `/opsx:propose`, `/opsx:apply`).

## User decisions and prompts (literal fragments)
- Scope and decisions D1-D9: "Documentar que este alcance se define mediante las decisiones actuales del proyecto y no mediante una especificacion preexistente." and "D2: sesion exclusivamente en memoria. Recargar la pagina requiere volver a iniciar sesion. Gestionar expiracion automatica del token."
- Refinement: "Registrar TD-019 diferenciando la perdida de sesion al recargar del riesgo de exposicion ante XSS." and "Corregir los campos `required` unicamente cuando la evidencia confirme que son obligatorios."
- Implementation authorization: "Apruebo la planificacion OpenSpec y autorizo la implementacion de `frontend-foundation`." with the restriction "Realizar modificaciones temporales de JWT exclusivamente en un entorno aislado de pruebas."

## AI findings and corrections (summaries)
- Planning: the 13-change plan is not written in the repo; the scope of change 4 was proposed by the AI and approved by the user.
- Group 1: `vitest-axe` 0.1.0 works with Vitest 5 and jsdom 30 (probe test); colour-contrast cannot run in jsdom.
- Contract: the backend OpenAPI confirmed `required` for the six `User` fields and for `Subject.description`; both were added to `docs/api-spec.yml`.
- Group 3: the first run of the client tests failed because jsdom performed CORS preflights against MSW; the test environment now uses the API origin, and CORS is left to the real-backend verification.
- Tooling: the shell tool rejected some heredocs containing apostrophes or special characters; files were written with the file-writing tool instead (same issue as L15).
- lesson (again, L15): the shell tool collapsed a double backslash in a test string; the file-writing tool plus String.fromCharCode fixed it
- finding: after adding dependencies the frontend container kept the old anonymous node_modules volume; needed docker compose up -d --build -V frontend (to document in development_guide, extends L15)
