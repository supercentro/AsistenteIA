# Design

Follows `docs/backend-standards.md`. Written after Explore (2026-11-23). Nothing is implemented. Reuses `docs/roadmap.md` (Feature 2, decisions R-D1, R-D3, R-D7), `docs/data-model.md`, the derived `attribution` of `chat-source-presentation`, and the privilege matrix of `database-least-privilege`.

## What the current data can answer

| Metric | Source (existing tables) | Available now? | Notes |
|---|---|---|---|
| Questions per period | `messages` (role `user`) joined to `conversations.subject_id`, `messages.created_at` | **Yes** | Deletions by students lower it (erasure is physical) |
| Active students | distinct `conversations.student_id` with a question in the window | **Yes** | Needs the minimum group size; enrolled count comes from `enrollments` |
| No-material rate | assistant messages with **no** `message_sources` row / all assistant messages | **Yes** | Every answer with material persists its sources and the controlled "no material" answer persists none, so no stored kind is needed |
| Answers with no cited source | the derived `attribution` (`attribution_of`) per assistant message | **Yes** | Includes refusals in words; label it "no cited source", not "wrong" (TD-062) |
| Appearances of cited sources per document | `message_sources` (filename snapshot, `chunk_id`) joined to `documents`; documents with none from `documents` | **Yes** | Count only `cited` answers, or the fallback inflates the counts of every retrieved document |
| Latency | none: the user and assistant messages are written together | **No** | Needs a stored duration (R-D7) |
| Model failures (502/503) | none: a failed turn persists nothing | **No** | Needs an event or counter (R-D7) |
| Per-student or per-question views | the tables could | **Not proposed** | Individual analytics and question text are excluded by default (R-D3, R-D10) |

## Explore findings

| # | Finding | Consequence |
|---|---|---|
| E1 | The application role already has `SELECT` on `conversations`, `messages`, `message_sources` and `documents` (`db_privileges.py`); the worker has none | An on-the-fly aggregate needs **no privilege change**; a new table would need a migration, matrix entries and the privilege gates |
| E2 | `base-standards.md` §9.4: queries that read conversations or messages are scoped by subject **and by the authenticated user**, in the repository | The aggregate repository must take the teacher and the subject and join `subjects.teacher_id`; the standard needs an explicit statement that this aggregate-only read is covered (D-M7) |
| E3 | Erasure is physical (`ON DELETE CASCADE`): deleting a conversation, all conversations or the account removes the rows | Live aggregates are compatible with erasure; any stored event or counter must be anonymous or it conflicts with it |
| E4 | A student's conversations are visible to the student only while enrolled; unenrolment deletes nothing | Aggregates must decide whether unenrolled students count (D-M5) |
| E5 | The policy draft tells students what is stored, where it goes and how it is erased; it says nothing about statistics for teachers | Enabling this needs new policy text, legal review and probably a new consent version (R0, R-D10) |
| E6 | `conversations` has one index, `(student_id, subject_id, created_at)`, student first | A subject-wide window scan is sequential; fine at pilot size, an index is a migration for later (R-D7); bound the window and the granularity |
| E7 | Standards §8 listed advanced teacher analytics as out of scope for the mandatory MVP (should-have) | R-D1 approved (2026-11-23) for the aggregate metrics only; §8 and `openspec/config.yaml` updated with the minimal wording |
| E8 | The `attribution` derivation exists and is tested for agreement with the live decision | Reuse it; no second reader of citation markers |

## Alternatives for the data source

| | Alternative | Pros | Cons |
|---|---|---|---|
| A | **Compute on the fly** from existing tables (chosen) | No migration, no privilege change, compatible with erasure, nothing new to protect | Counts fall when students delete; a scan per request; no latency or failure metrics |
| B | An `activity_events` table with a pseudonymous student id | Stable history, latency and failures possible | A behavioural log per student (profiling risk), conflicts with erasure unless purged, migration and privileges |
| C | A table of daily aggregate counters, no student id | Stable, anonymous, cheap | Small cells are identifying at write time; migration and privileges; needs R-D7 |

Recommendation: **A for the first capability**; B is not proposed; C only when stability or latency is needed, with its own decision.

## Privacy rules proposed (each needs the owner's decision)

- **D-M1 minimum group N (R-D3)**: no figure is shown when fewer than **N = 5** distinct students contribute to it; it is replaced by a suppression marker; a subject with fewer than N active students in the window shows no figure at all, only the enrolled count the teacher already knows.
- **D-M3 granularity**: fixed buckets (week by default, day only when every day of the window reaches N) and a bounded window (at most 90 days), to limit differencing between two requests.
- **D-M4 content**: the response has only numbers and document names; never text of questions or answers, student ids, names or e-mails.
- **D-M5 unenrolled students**: excluded, consistently with the visibility rule of the conversations.
- **D-M6 appearances of cited sources**: a document count is the number of answers whose cited sources include it (answers with `attribution` cited); the others are reported apart. It is **not** presented as semantic support or as proof that the material was used.
- **D-M7 authorisation**: only the teacher who owns the subject; negative tests for another teacher, a student, an anonymous caller and an unknown subject; `base-standards.md` §9.4 gets an explicit sentence for aggregate-only reads.
- **D-M2 what students are told**: policy text and notice about statistics for teachers, legal review and a consent version decision **before** the endpoint is enabled for the pilot; until then the implementation can exist but stay switched off by a setting (default off).
- **D-M8 individual analytics, profiling and the dashboard** are separate changes and are not approved here.

## Sketch of the contract (additive, to be fixed by the owner's decisions)

`GET /subjects/{subject_id}/activity?from=&to=&granularity=week|day` (teacher, owner of the subject) returning `window`, `minimum_group`, `enrolled`, `active_students` (number or `null` when suppressed), `questions` (list of `{period, count|null}`), `no_material_rate`, `no_cited_source_rate`, `documents` (list of `{document_id|null, filename, consultations|null}`) and `suppressed` (flag). Rates are null when their denominator is below N.

## Risks and checks

- Re-identification in small classes (D-M1, D-M3) and differencing between windows; mitigated by the group size, fixed buckets and a bounded window; residual risk stays in the register.
- Students unaware that their activity feeds teacher statistics (E5); the switch-off setting and the policy step.
- Counts that move when students delete data (E3): documented in the response and the dashboard.
- Query cost without a subject-first index (E6): bounded window; measure with the pilot size; index later.
- Misreading "no cited source" as "bad answer": wording in the dashboard change; TD-062 stays open.
- Evidence to produce when implemented: role-bound privilege scenarios for the new route (the coverage test requires one), negative authorisation tests, a test that no response field can carry text or ids, suppression boundary tests (N−1, N, N+1), erasure test (a deleted conversation lowers the count), and an independent privacy review.

## Owner's decisions of 2026-11-23

Approved as **provisional**: the feature is incorporated into the roadmap as a future one; metrics are aggregate-only; **minimum group N = 5** (D-M1); **weekly** granularity and a **window of at most 90 days** (D-M3); no individual analytics, no profiling, no new tables, no migrations (R-D7: no new storage in this slice); the capability stays **disabled** until the privacy and consent conditions are met (D-M2). The artifacts of this Explore are kept and **nothing is implemented**.

Also approved (owner, 2026-11-23, second message): **D-M5** students who are no longer enrolled are excluded from every activity count; **D-M6** the per-document figure counts appearances of cited sources and is not presented as semantic support or demonstrated use; and the part of **D-M7** that says that queries are limited to the subjects of the authenticated teacher and must not allow inferences about individual students. The artifacts are kept and reviewed, **not published and not implemented**. The owner did **not** authorise changes to `base-standards.md`, `backend-standards.md`, `openspec/config.yaml` or `readme.md` for now.

Still pending to enable the implementation: the policy wording, the consent version and the legal review (**D-M2**, row 5), and whether the first capability may be implemented, switched off, before that review. R-D1 is approved (see below) and the sentence for §9.4 and the section of the backend standards are reserved for the implementation change.

## Changes to standards and configuration (status 2026-11-23)

R-D1 was approved by the owner on 2026-11-23 only for the aggregate teacher metrics; individual analytics and profiling stay out of the current scope without being excluded from the future roadmap. Rows 1 and 2 were **applied** in the working tree (not committed) with the minimal wording; rows 3 and 4 are **reserved for the implementation change**; the other rows are untouched.

| 1 | **Applied** `docs/base-standards.md` §8 (line 103) | "Out of scope for the mandatory MVP: Moodle integration; student-services (administrative) assistant; advanced teacher analytics (should-have only)." | Keep the exclusion of individual or profiling analytics; say that aggregate subject-level activity metrics for the owning teacher (minimum group, no storage) are planned and disabled until the privacy conditions are met |
| 2 | **Applied** `openspec/config.yaml` context (line 14) | the same sentence | The same wording as 1 |
| 3 | Reserved for the implementation change: `docs/base-standards.md` §9.4 | "every query that reads chunks, conversations or messages is scoped by `subject_id` and by the authenticated user, enforced in the repository layer" | Add: a teacher may read aggregate-only, suppressed figures over the conversations and messages of a subject they own, through a dedicated repository that joins the teacher; never text, identifiers or per-student figures |
| 4 | Reserved for the implementation change: `docs/backend-standards.md` §9 | no section on aggregate analytics | A short section with the rules of this design (group size, buckets, window, no storage, no free text) |
| 5 | Policy text and notice in the frontend (`strings.es.ts`), `docs/` privacy documents and the consent version (`2026-10-v1`) | no mention of statistics for teachers | New wording, legal review and a consent version decision; owner task |
| 6 | `readme.md` (academic deliverable) | the approved MVP scope | Not modified (owner's decision of 2026-11-23) |
| 7 | `backend/app/core/config.py`, `backend/.env.example` | no such setting | A setting that switches the capability on, default off (implementation change) |

## Implementation notes (2026-11-23)

Implemented switched off by default; no table, no migration, no change of privileges. The contract as built differs from the sketch above in these points, all inside the owner's decisions:

| Sketch | As built | Why |
|---|---|---|
| query `from`, `to` | `start`, `end` (dates) | `from` is a reserved word in the code; the response states the window actually computed |
| `granularity=week\|day` | `week` only | the owner approved weekly aggregation; a daily bucket needs its own decision |
| window of at most 90 days | whole weeks, at most 12 (84 days) | a window of whole weeks keeps the cells fixed, so two requests cannot isolate a few days of one student by shifting the window |
| `suppressed` for the cells | `suppressed` is true when at least one figure is null | a flag that told "one to four" from "none" would leak what the withholding hides, so a figure with no student at all is withheld too |
| `consultations` | `cited_appearances` | the name says what is counted (answers that cite the document) and avoids implying use |
| period `{period, count}` | `{period_start, count}` | the Monday of the week |

`no_cited_source_rate` is the share of answers that cite none of their sources and includes the answers with no material, so it is at least `no_material_rate`; it is not a quality measure (TD-062). Only ready documents are listed; a deleted document that was cited stays listed by its stored name with no identifier. The residual risks are TD-069 (re-identification, to close before enabling) and TD-070 (aggregation in the application process).
