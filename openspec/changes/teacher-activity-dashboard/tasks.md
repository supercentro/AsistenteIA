# Tasks

> Specified after the owner's decisions of 2026-11-23 (D-D1 to D-D9 in `design.md`); **not implemented**. The implementation needs a new authorisation, and so do the edits to the standards listed in `design.md`, the approved Spanish copy, and every commit, push, pull request and merge. No change of backend, contract, database, privileges, GitHub Actions or OpenSpec/SpecBoot components; no real Gemini call. **Both switches stay off by default, F1 (Major, TD-069), F6 and F7 stay open, and the capability must not be enabled for real students** until F1 is decided and the policy text, the legal review and the consent version exist: this change does not do that. Follows `docs/openspec-tasks-mandatory-steps.md`.

## 0. Branch

- [x] 0.1 Step 0: create the branch `feature/teacher-activity-dashboard` from `main` before any code change. Merge only through a Pull Request.

## 1. Tests first

- [x] 1.1 Service and hook: one `GET` per load with no query parameters; no refetch on focus, reconnection or interval; the response is not retained after leaving (`gcTime: 0`); the key holds no window
- [x] 1.2 Page states: loading, loaded, error with retry, 403 (forbidden page), 404 and 422 (not-found view, the same for another teacher's and an unknown subject), 401 (session ends as elsewhere), all figures suppressed
- [x] 1.3 Suppression: a null week, `active_students`, rate or document figure reads «Datos insuficientes», has no bar and is never zero; a rate of 0% is shown as 0%; a count is never rendered as zero
- [x] 1.4 Switches and authorisation: flag off means no route, no link and no request; student and anonymous caller get the forbidden page and the login page without a request; flag on with the backend answering 404 shows the not-found view
- [x] 1.5 Placement: the link is outside `EnrollmentsSection`; the activity page shows no enrolment control; an enrolment change sends no activity request
- [x] 1.6 Neutral labels: a scan of every label and heading fails on a judgement word (quality, error, wrong, good, bad, useful, learning, understood and the Spanish forms); the note on document figures and the note on «sin fuente citada» are present
- [x] 1.7 Accessibility with `vitest-axe` in the loaded, suppressed, empty and error states; every bar has a table equivalent and is hidden from assistive technology; no information by colour alone; keyboard order and focus
- [x] 1.8 Playwright mocked test (build flag on, fictitious responses): the page, a suppressed week, the all-suppressed state, a student refused, keyboard navigation
- [x] 1.9 Run the new tests before any implementation and record the failing run in `reports/`

## 2. Implementation (frontend only)

- [x] 2.1 `activityService`, `useActivity` and the typed flag helper (`lib/features.ts`, `vite-env.d.ts`); the types come from `api.generated.ts`
- [x] 2.2 Components `ActivityDashboard`, `MetricCard`, `WeeklyQuestions`, `ShareBar`, `CitedDocumentsTable`, `PrivacyNote`, `InsufficientData`; plain text, CSS bars, no new dependency
- [x] 2.3 `TeacherActivityPage`, the guarded route registered only with the flag on, and the link in the header area of `TeacherSubjectPage`
- [x] 2.4 `strings.es.ts` with the copy approved by the owner (the table of `design.md`)
- [x] 2.5 `frontend/.env.example` with `VITE_TEACHER_ACTIVITY_ENABLED=false`
- [x] 2.6 Mutation checks: a null shown as zero, a parameter added to the request, a refetch on focus, a response retained, the link inside the enrolments, a visible bar, a judgement word, the route registered with the flag off
- [x] 2.7 `npm run typecheck`, `lint`, `format:check`, `check:api-types`, unit and component suites; no backend file changes

## 3. Verification

- [x] 3.1 Step N: review and update the existing frontend tests that touch the teacher subject page, the routes and the strings
- [x] 3.2 Step N+1: run the unit, component and accessibility suites; database state before and after (the change writes nothing and touches no backend)
- [x] 3.3 Step N+2: manual endpoint test with `curl` of the existing endpoint on the test stack with the backend switch on and fictitious data (owner, another teacher, student, anonymous, switch off); the frontend sends no other call
- [x] 3.4 Step N+3: Playwright MCP run by the agent on the page with the mocked API and the build flag on, then the Playwright Test suite
- [x] 3.5 Step N+4: documentation, with the owner's authorisation (frontend standards exception, development guide, `.env.example`, TD-069 note, roadmap): `docs/frontend-standards.md` (the second public variable and the dashboard rules), `docs/development_guide.md`, `docs/technical-debt.md` (interface notes under TD-069; F1 unchanged), `docs/roadmap.md`
- [x] 3.6 Independent adversarial review with a privacy and accessibility focus: inference by comparison, F1 not presented as mitigated, wording that attributes quality or use, flag behaviour, states, keyboard and screen reader (report: `reports/2026-11-23-adversarial-review.md`; no Blocker or Major; the minor findings were fixed or registered)
- [x] 3.7 Final gates of `docs/base-standards.md` section 9 re-run after the last change; `openspec validate --all --strict`; CI on Linux after the pull request (evidence: local gates re-run before the commit; PR #32 CI green on the head 339e891 with backend, frontend and privileges, Playwright mocked suite 32 passed; CI of main green on the squash merge f1a117e; `openspec validate --all --strict` 28/28)

> Out of this change and not authorised: enabling either switch for real students, a date selector, comparison, export, polling, any change of aggregation or of D-M5, any resolution of F1, a charting library, archiving.
