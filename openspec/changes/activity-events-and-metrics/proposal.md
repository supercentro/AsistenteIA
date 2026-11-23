# Proposal

## Why

Teachers have no view of how their subject is used: how many students ask, which material is consulted, how often the assistant finds nothing. Feature 2 of the roadmap (`docs/roadmap.md`) proposes a backend capability first, then a dashboard. Explore (2026-11-23) found that most of the useful, **non-identifying** numbers can be computed from data the application already stores, with no migration and no new privilege, and that the real blockers are decisions about privacy (minimum group size, what students are told, erasure) and one scope decision (R-D1: the standards list advanced teacher analytics as out of scope for the mandatory MVP).

## What Changes

Planning only; nothing is implemented. Proposed first capability, **aggregate-only, per subject, read-only, for the owning teacher** (decisions D-M1 to D-M8 in `design.md`):

- One new endpoint (additive contract) that returns counts for a window: questions per period, active students, share of answers with no material, share of answers with no cited source, and appearances of cited sources per document (including documents with none). Every figure that comes from fewer than N distinct students is replaced by a suppression marker (N is decision R-D3).
- Computed on the fly from `conversations`, `messages`, `message_sources`, `documents` and `enrollments`; no stored event, no new table, no migration, no new database privilege.
- Never returned: question or answer text, student ids, names or e-mails, any per-student figure.
- Out of scope: the dashboard (`teacher-activity-dashboard`), individual analytics, student profiling, topic clustering, latency and failure metrics (they need new storage, R-D7), any migration.

## Capabilities

### New Capabilities
- `teacher-activity-metrics`: the aggregate metrics of a subject for its teacher, with minimum group size and suppression.

### Modified Capabilities
<!-- None in this slice. The privacy wording of the policy changes in a separate, legally reviewed step (D-M2). -->

## Impact

- Backend (when implemented): a repository of aggregate queries, a service with the suppression rules, one route in the teacher area, schemas, tests. `docs/api-spec.yml` (additive path and schemas).
- Not touched: the privilege matrix (the application role already reads the tables), migrations, models, the worker, the frontend (second change).
- Standards: R-D1 was approved by the owner on 2026-11-23 **only for the aggregate teacher metrics**, and the minimal wording was applied to `docs/base-standards.md` section 8 and `openspec/config.yaml` (individual and profiling analytics stay out of scope, without being excluded from the future roadmap). The sentence of section 9.4 and the section of `docs/backend-standards.md` are reserved for the implementation change.
