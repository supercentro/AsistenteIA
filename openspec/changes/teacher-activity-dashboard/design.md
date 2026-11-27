# Design

Follows `docs/frontend-standards.md`. Written after Explore (2026-11-23) and the owner's decisions of the same day. Nothing is implemented. Reuses the endpoint and the rules of `activity-events-and-metrics` (spec `teacher-activity-metrics`, design D-M1 to D-M8, TD-069, TD-070) and the generated types of `frontend/src/types/api.generated.ts`.

## Decisions of the owner (2026-11-23)

| # | Decision |
|---|---|
| D-D1 | A separate page `/subjects/:subjectId/activity`, only for teachers |
| D-D2 | The existing endpoint and types; no change of contract or backend |
| D-D3 | A frontend switch `VITE_TEACHER_ACTIVITY_ENABLED`, false by default; the backend switch stays mandatory |
| D-D4 | Cards, CSS bars and accessible tables; no charting library |
| D-D5 | One request per load; no date selector, polling, export or comparison between periods |
| D-D6 | Suppressed figures read «Datos insuficientes», never zero |
| D-D7 | Neutral labels: no pedagogical quality, no demonstrated use of a document |
| D-D8 | Tests of accessibility, authorisation and interface states with fictitious data |
| D-D9 | F1 (Major), F6 and F7 stay open; D-M5 and the aggregation rules are not changed; the interface adds no mechanism that eases inference about individuals; both switches stay off; no use with real students until F1 is resolved and the legal and consent conditions are met |

## What the contract gives the screen

| Element | Response field | Rendering | When null |
|---|---|---|---|
| Enrolled students | `enrolled_students` | card | never null |
| Active students | `active_students` | card | «Datos insuficientes» |
| Window | `window.start`, `window.end`, `window.weeks` | text under the title | never null |
| Questions per week | `questions[].period_start`, `.count` | table with a CSS bar per row | row reads «Datos insuficientes», no bar |
| Answers without material found | `no_material_rate` | percentage and one bar | «Datos insuficientes» |
| Answers without a cited source | `no_cited_source_rate` | percentage and one bar, with the note that it includes the answers without material | «Datos insuficientes» |
| Documents | `documents[]` (`filename`, `cited_appearances`, `document_id` not shown) | table | «Datos insuficientes» |
| Note | `minimum_group`, `suppressed` | fixed text | n/a |

Not possible with this contract, and not proposed: daily detail, latency, model failures, topics, anything per student, trends beyond the 12 weeks of one window, a comparison between windows.

## Structure (frontend standards: service, hook, components, page)

- `services/activityService.ts`: `get(subjectId)` over the shared client, one call, no parameters; typed with `components['schemas']['ActivityResponse']`.
- `hooks/useActivity.ts`: `useQuery` with `retry: false`, `refetchOnWindowFocus: false`, `refetchOnReconnect: false`, `refetchInterval: false`, `staleTime: Infinity` during the visit and `gcTime: 0` so the response is not retained after leaving. The key has the user id and the subject id and never a window.
- Components (presentational, plain text, no HTML from data): `ActivityDashboard` (composition), `MetricCard`, `WeeklyQuestions` (table with bars), `ShareBar`, `CitedDocumentsTable`, `PrivacyNote`, `InsufficientData`.
- `pages/TeacherActivityPage.tsx`: reads the subject id, applies the states of the spec, maps 403 to the forbidden page and 404 or 422 to the not-found view.
- Route: inside `RequireConsent` and `RequireRole roles={['teacher']}`, and only registered when the flag is true; with the flag false the catch-all not-found page applies. One link in the header area of `TeacherSubjectPage`, rendered only with the flag on and **not** inside `EnrollmentsSection`.
- Copy: only in `lib/strings.es.ts`.
- Flag: `frontend/src/vite-env.d.ts` typing, read through one helper (`lib/features.ts`) so tests can set it; `frontend/.env.example` documents it with the value `false`.

## Proposed Spanish copy (the owner approves it before implementation)

| Place | Text |
|---|---|
| Title | «Actividad de la asignatura» |
| Cards | «Estudiantes inscriptos», «Estudiantes activos» |
| Window | «Semanas del {inicio} al {fin}» |
| Weekly table | caption «Preguntas por semana»; columns «Semana» and «Preguntas» |
| Shares | «Respuestas sin material encontrado», «Respuestas sin fuente citada» with the helper «Incluye las respuestas sin material encontrado» |
| Documents | caption «Documentos citados en las respuestas»; column «Veces que una respuesta citó el documento»; note «Cuenta citas; no mide comprensión ni uso del material» |
| Suppressed | «Datos insuficientes» |
| Privacy note | «Solo se muestran cifras agregadas de al menos {n} estudiantes. Cuando hay menos, se indica «Datos insuficientes». Las cifras pueden cambiar entre consultas.» (superseded by change `activity-privacy-hardening`: the note now says that anonymity is not guaranteed; the current text is in `frontend/src/lib/strings.es.ts`) |
| All suppressed | «Todavía no hay datos suficientes para mostrar la actividad de esta asignatura.» |
| Link on the subject page | «Ver actividad» |

A test scans the labels and headings for judgement words (quality, error, wrong, good, bad, useful, learning, understood and their Spanish forms) so the wording cannot drift.

## Privacy analysis of the interface

| Risk | What the interface does | What it cannot do |
|---|---|---|
| **F1** (enrolment differencing) | The page is separate from the enrolments screen, has no link next to the enrol or unenrol controls, does not refresh with them and keeps no earlier response | It cannot close F1: the endpoint recomputes from the live enrolment, so a teacher who reads, unenrols, reads and re-enrols still sees the difference. Only a decision on the endpoint closes it (D-M5 or another rule, owner's decision). **F1 stays open and blocks any real use** |
| Comparison between periods | One request, default window, no selector, no polling, no export, no week-over-week change, `gcTime: 0` | The default window moves one week each week, so totals differ between visits made in different weeks (TD-069); this exists at the API |
| Misreading | Neutral labels, the note on document figures, the note that «sin fuente citada» includes the answers without material (TD-062) | It cannot stop a reader from drawing a pedagogical conclusion |
| Small classes | A clear all-suppressed state that shows the enrolled count and no bar | It does not hide that the class is small (the teacher already knows it) |
| Screenshots or copies | Nothing is stored by the page; no export | A teacher can copy what they see |
| F6 and F7 | Documented, unchanged | One heavy user can dominate a shown week; the aggregation is in memory (TD-070) |

## The two switches

| Switch | Where | Default | Effect when off |
|---|---|---|---|
| `TEACHER_ACTIVITY_ENABLED` | backend setting | false | the endpoint answers 404 to a teacher |
| `VITE_TEACHER_ACTIVITY_ENABLED` | frontend build (public, not a secret) | false | no route, no link, no request |

The frontend switch is a build-time convenience to hide the entry point, **not** a security control: the backend decides. With the frontend switch on and the backend one off, the page shows the not-found view, which is the intended behaviour. Neither switch may be turned on for real students while F1 is open.

## Alternatives considered

| Alternative | Why not |
|---|---|
| A tab inside the subject page | It would sit next to the enrol and unenrol controls and share their refresh, which makes F1 easy to use |
| A charting library | A new dependency for four figures; bars and a table are enough and are accessible by construction |
| A window selector or a comparison | It would give the teacher the differencing the endpoint tries to limit; a separate decision and a separate change |
| Polling | It would produce many consecutive responses of the same window |
| Hiding the page through the backend response only | The frontend then needs to guess why a 404 happened; the build-time flag avoids showing a dead link |

## Dependencies and standards that need authorisation when implemented

| # | File | Why |
|---|---|---|
| 1 | `docs/frontend-standards.md` (the rule «only `VITE_API_URL` is configured») | A second public variable is introduced; the rule needs the exception and the dashboard rules (no polling, no comparison, neutral labels) |
| 2 | `frontend/.env.example`, `docs/development_guide.md` | Document the new variable with the value `false` |
| 3 | `docs/technical-debt.md`, `docs/roadmap.md` | Interface notes under TD-069 (F1 unchanged) and the status of feature 2 |
| 4 | `frontend/src/lib/strings.es.ts` | The approved copy |

No change of `docs/api-spec.yml`, `docs/data-model.md`, backend code, privileges or GitHub Actions. This change does not edit the standards: the table is the request the owner decides on at implementation.

## Risks and open points

- **F1 stays open** and is the condition that matters for real use; the dashboard does not reduce it and must not be presented as a mitigation.
- With the backend off and the frontend on, the page shows «not found»; a teacher may not understand why. Acceptable while the capability is not enabled.
- Coverage of the all-suppressed state will be the common state in pilot classes of fewer than 5 active students.
- The default window changes weekly (TD-069); the page says only that figures can change between consultations.

## Evidence to produce when implemented

Failing run first; unit tests of the service and the hook (one request, no parameters, no refetch, `gcTime`); component tests of every state; accessibility scans (`vitest-axe`) in the loaded, empty, suppressed and error states; authorisation tests (student, anonymous, flag off, 404, 403); a test that the link is not inside the enrolments section and that an enrolment change sends no activity request; a scan of the labels for judgement words; mutation checks (a null shown as zero, a parameter added to the request, a refetch on focus, the link inside the enrolments, a visible bar, a judgement word); Playwright with a mocked API and the build-time flag on, including the keyboard; an independent review with a privacy and accessibility focus; CI on Linux.
