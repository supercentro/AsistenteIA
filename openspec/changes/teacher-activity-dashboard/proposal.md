# Proposal

## Why

The aggregate activity endpoint `GET /subjects/{subject_id}/activity` (change `activity-events-and-metrics`, merged, switched off by default) has no screen: a teacher can only read raw JSON. Feature 2 of `docs/roadmap.md` plans a dashboard as the second step. Explore (2026-11-23) found that the existing contract supports a small, honest view (weekly questions, active students, two shares, cited appearances per document) and that the main risk is not the drawing but what the screen invites: comparisons between periods, an enrolment control next to the figures (finding F1) and wording that reads as quality or proven use. This change specifies a **minimal, read-only, disabled-by-default** page that adds no access to data.

## What Changes

Planning only; nothing is implemented. Approved by the owner on 2026-11-23:

- A **separate page** `/subjects/:subjectId/activity`, only for a signed-in teacher, with its own role guard.
- It uses the **existing endpoint and the generated types**; no backend, contract, model or database change.
- A frontend switch `VITE_TEACHER_ACTIVITY_ENABLED`, **false by default**; the backend switch `TEACHER_ACTIVITY_ENABLED` stays mandatory and false by default. With the frontend switch off there is no link, no route and no request.
- Cards, **CSS bars and accessible tables**; **no charting library**.
- **One request per page load**, no date selector, no polling, no export, no comparison between periods, nothing kept to compare later.
- A suppressed figure is shown as **«Datos insuficientes»**, never as zero and never as a bar.
- **Neutral labels**: nothing that attributes pedagogical quality or demonstrated use of a document.
- Tests of accessibility, authorisation and every interface state with fictitious data.

Explicitly out of scope: a date or granularity selector, comparison or trend between periods, export or download, automatic refresh, per-student or per-question views, topics, latency or failure metrics, any charting dependency, any change to the aggregation rules (N = 5, whole weeks, at most 12, enrolled only, D-M5), any resolution of F1 (it stays open, see `design.md`), and **any use with real students**.

## Capabilities

### New Capabilities
- `teacher-activity-dashboard`: the teacher's page that shows the aggregate activity of one subject, with its two switches, its states and its privacy limits.

### Modified Capabilities
<!-- None. `teacher-activity-metrics` (the endpoint) is not changed. -->

## Impact

- Frontend (when implemented): one page, one route guard, a service, a hook, a few presentational components, Spanish copy in `strings.es.ts`, a typed environment flag, tests (unit, accessibility with `vitest-axe`, Playwright with a mocked API). One link in the header of the teacher's subject page, outside the enrolments section.
- Not touched: backend, `docs/api-spec.yml`, `docs/data-model.md`, migrations, privileges, the student chat, the RAG pipeline, Gemini, GitHub Actions.
- Authorisation and personal data: the page reads what the endpoint already returns to the owning teacher; it introduces no new access. Standards that need the owner's authorisation when implemented are listed in `design.md` (the frontend standard allows only `VITE_API_URL` today).
- Hard condition: the capability must not be enabled for real students until F1 (TD-069) is decided and the policy text, the legal review and the consent version exist.
