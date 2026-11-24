# AsistenteIA — Evolution roadmap (planning, not approved for implementation)

Status: **proposal** of 2026-11-20 for the owner's approval. It does not change the approved MVP scope of `docs/base-standards.md` §8 nor `openspec/config.yaml` until the owner approves decision R-D1 below. Change names are proposals; each becomes an OpenSpec change (`/opsx:propose`) only when its turn comes and its blocking decisions are closed. Residual risks stay in `docs/technical-debt.md`; this file links them and does not restate them.

Reference products: the analysis of Aprendiz and MIA is not in the repository. The nine features below are taken from the owner's roadmap; any expectation taken from those products that is not written here must be provided (R-D11).

## 1. Starting point (what can be reused)

| Capability | State | Reused by |
|---|---|---|
| Subjects, enrollments, teacher/student roles, JWT | Done, least-privilege database roles | everything |
| Ingestion (PDF/txt/md) → chunks → local 384-d embeddings in pgvector | Done, async worker | 1, 3, 5, 6, 9 |
| RAG chat: subject-scoped retrieval, threshold, grounded prompt, `[n]` sources, no-material answer, history (last 10), prompt-injection defences | Done; model `gemini-3.1-flash-lite` (free tier, fictitious data only) | 1, 5, 6, 9 |
| Conversations, messages (`created_at`), `message_sources` (rank, score, filename snapshot) | Done; student-only access; delete one / all | 2, 3, 4 |
| Student chat UI, teacher material and enrollment UI, consent gate, in-memory session | Done | 2, 5, 6, 7 |
| Quality gates, mutation/adversarial review practice, CI (backend, frontend, privileges) | Done | all |

Known limits that shape the order: retrieval ignores the conversation (a follow-up like "and why?" retrieves poorly); sources can list chunks the model did not use (TD-062); retrieval quality measured on 45 questions by one author (TD-033); `last_message_preview` never filled (TD-066); no token or cost accounting; no consent withdrawal or account erasure (TD-064); free tier not usable with real students (TD-003, TD-063); single API process rate limit (TD-007); no deployment yet.

## 2. Principles

1. **Measure before changing**: no AI behaviour change without the golden-set baseline (change R1). Status 2026-11-23: the retrieval baseline is complete; the **answers** baseline with the real model is blocked by the availability of the provider (task 3.3b, below). A feature that does not change what the assistant answers (for example the teacher activity dashboard) does not wait for it; a change that does (`rag-retrieval-quality`, a new prompt or model) needs a comparison against the retrieval baseline and states what it could not measure about the answers.
2. **Teachers see patterns, not people, by default**: analytics are aggregated with a minimum group size; identifying a student needs an explicit owner decision, a stated purpose in the policy and a legal review (R-D3, R-D10).
3. **The AI advises, people decide**: difficulty signals and recommendations are explainable, show their evidence, never grade, never reach the student as a label, and carry a visible reliability statement.
4. **Grounded or silent**: generated content (answers, exercises, recommendations) is traceable to the subject's material or says it cannot be.
5. **Real students only after the pilot conditions** (TD-003, TD-063, TD-064): until then all new work runs on fictitious data.
6. **One increment, one reviewable change**: backend and frontend of a feature can be separate changes; every change has its own failing-first tests, review and evidence.
7. **Explore before every feature** (owner decision of 2026-11-20): run `/opsx:explore` on the change before proposing or adjusting it, to find reusable capabilities, dependencies, alternatives, risks and regressions; implementation, tests, adversarial review and evidence then follow the OpenSpec + SpecBoot workflow unchanged. The nine features stay in the roadmap and the current MVP is the functional baseline: every change is incremental and backwards compatible unless the owner approves otherwise.
8. **Cost is a requirement**: every feature that calls a model states calls per use and the monitoring that detects a runaway.

## 3. Roadmap

Priority follows the owner's order where dependencies allow; two changes are advanced (R0, R1a) because they unblock everything else, and LMS (8) is a parallel track that waits for deployment.

| Phase | Changes (proposed names) | Roadmap feature |
|---|---|---|
| 0 Foundations for real users | `personal-data-erasure` + consent withdrawal, `llm-usage-metering`, `e2e-and-quality-closure`, `deployment-and-delivery-docs` (the last three already in the 13-change plan) | prerequisites |
| 1 Answer quality | `rag-golden-set-evaluation` → `rag-source-attribution` → `rag-retrieval-quality` | **1** |
| 2 Teacher visibility | `activity-events-and-metrics` → `teacher-activity-dashboard` | **2** |
| 3 Insight | `frequent-questions-and-topics` → `learning-difficulty-signals` → `teacher-pedagogical-recommendations` | **3, 4, 7** |
| 4 Personalisation | `student-learning-profile` → `personalised-study-support` → `adaptive-exercises` | **5, 6** |
| 5 Integration and institution | `lms-integration-foundation` (parallel track), `institutional-assistant` | **8, 9** |

### R0. Foundations (prerequisites, not new features)
- `personal-data-erasure` + consent withdrawal (TD-064): every later feature stores more personal data, so erasure must exist first. `DELETE /users/me` is in the contract and not implemented.
- `llm-usage-metering`: record model, tokens in/out, latency and failures per call (no content) and a budget alarm. Needed to price features 3–7 and 9. Needs a table (migration) → approval.
- `e2e-and-quality-closure` and `deployment-and-delivery-docs` (plan items 12 and 13): CI-level main-flow E2E and a deployable stack; LMS integration (8) cannot start without a public HTTPS deployment.
- Paid-tier or alternative provider decision for real students (TD-063, R-D2). Not code, but gates the pilot.

### Feature 1 — Answer quality and source attribution (TD-062, TD-033)
Split into three changes, in this order:
1. **`rag-golden-set-evaluation`** (drafted and explored in `openspec/changes/rag-golden-set-evaluation/`; harness in `backend/tests/evaluation/`, no change to `app/`): fictitious golden set seeded from the spike corpus (~75 cases), offline harness, retrieval/refusal/attribution metrics, baseline. No product change. Size: M.
2. **`rag-source-attribution`** (second slice `chat-source-presentation` merged on 2026-11-22 (PR #25): derived `attribution`, cited sources with their marker number and retrieved fragments collapsed; first slice merged; explored 2026-11-21; slice 1 approved and implemented on `feature/rag-source-attribution`: history, document and filename markers neutralised, `[n, m]` accepted, no contract change; slice 2, the flag and the numbering of sources, is a second change; the quantitative target waits for the real-model baseline): numbering that cannot collide across turns (strip or renumber markers of replayed history), validate markers against the turn's chunks, stop trusting markers copied from documents, decide what to show when no marker is valid (R-D4: drop sources, or keep them flagged `attribution=retrieved`). May touch `docs/api-spec.yml` (new field) and the frontend sources block. Size: M. Closes TD-062 only if the baseline shows the target is met.
3. **`rag-retrieval-quality`**: history-aware retrieval (follow-ups), top-k/threshold from the sweep, optional hybrid lexical search, optional reranker or query rewriting (extra model call and latency/cost; R-D6). Embedding model change is excluded unless the baseline justifies it (schema `vector(384)`, TD-024; needs approval). Size: M–L.
- **Baseline (2026-11-20, `rag-golden-set-evaluation`, golden set v0.1-draft, real embedder, top-k 5, threshold 0.3)**: self-contained questions Hit@1 69 %, Hit@3 93 %, MRR 0.793; follow-ups Hit@5 75 % (retrieval ignores the conversation); 60 % of the unanswerable questions pass the threshold (40 % at 0.4, 10 % at 0.5, at the cost of refusing 4 % / 27 % of the answerable ones); no isolation violation. The attribution baseline with the real model is partial and waits for the owner's confirmation of the remaining free-tier budget (TD-067).
- **Answers baseline, status 2026-11-23 (task 3.3b, still open)**: two real runs (18 requests, golden set `v0.2-draft`, `gemini-3.1-flash-lite`) answered 10 of the 45 cases that reach the model (all answerable; 8 with a valid marker, 2 fell back to every retrieved chunk, no wrong citation); 8 requests failed with `503` and `504` of the provider and each run stopped by the rule of two failures in a row. Nothing is presented as a baseline. The ledger says `authorised_total` 206 and `spent` 172 (154 historical estimate, never confirmed, plus 18 real requests). A new attempt needs the owner's decision and a new authorisation; see `reports/2026-11-23-answers-runs-1-and-2.md` of the change.
- Risks: overfitting to a self-authored set (hold-out part, real material later, R-D5); latency/cost of rewriting; prompt changes shifting behaviour (every change compared against the baseline).

### Feature 2 — Teacher activity dashboard
- **Status 2026-11-23 (owner decision)**: `activity-events-and-metrics` is incorporated as a **future** feature, explored in `openspec/changes/activity-events-and-metrics/` (not implemented). Provisional rules approved by the owner: aggregate-only metrics per subject, **minimum group of 5 students**, **weekly granularity**, **window of at most 90 days**; no individual analytics, no profiling, no new tables, no migrations (R-D7: no new storage in this slice); the capability stays **disabled** until the privacy and consent conditions are met (policy text, legal review, consent version). R-D1 was **approved on 2026-11-23 only for these aggregate metrics**: `docs/base-standards.md` §8 and `openspec/config.yaml` carry the minimal wording. **Implemented (backend only, no dashboard) in the branch `feature/activity-events-and-metrics`, switched off by default** (`TEACHER_ACTIVITY_ENABLED=false`): `GET /subjects/{subject_id}/activity`, the sentence of §9.4 and the section of `docs/backend-standards.md` §9 are in the same change; the window is whole weeks, at most 12 (84 days). It must not be enabled for real students: the policy text, the legal review, the consent version and TD-069 stay pending. **The visual teacher page `/subjects/:id/activity` (change `teacher-activity-dashboard`) is implemented behind `VITE_TEACHER_ACTIVITY_ENABLED` (default false) and does not reduce F1; both switches stay off.** **Privacy hardening (change `activity-privacy-hardening`, A2 + A2b, implemented in a branch, pending merge): the unenrolment and open-week forms of TD-069 are mitigated at the price of availability after a removal; F8 (TD-071), V3, F6 and F7 stay open and the capability must not be enabled for real students.**
1. **`activity-events-and-metrics`** (backend): aggregate-only endpoints per subject (questions per day, active students count, no-material rate, answers without valid source, documents most/least consulted, response latency) computed from existing `messages`/`message_sources`; a stored answer kind (`answered|no_material`) and the model failures need a small schema addition (R-D7). Minimum group size to avoid identifying a single student (R-D3).
2. **`teacher-activity-dashboard`** (frontend): read-only dashboard in the teacher subject page; accessible tables first, simple charts after (chart library = dependency approval, R-D8).
- Dependencies: 1 (so "answer quality" metrics mean something), R0 consent/purpose wording. Risks: de-anonymisation in small classes; students unaware that their questions feed teacher statistics (policy text and notice change → legal review).

### Feature 3 — Frequent questions and recurring topics
- **`frequent-questions-and-topics`**: group questions of a subject by meaning using the existing local embedder (no external call) and label groups (labels by the model would send questions to Gemini, already the case for the chat; templated labels avoid it); show topic, count, trend, and the material coverage gap (questions with no material). Output aggregated; example questions shown only when anonymised and above the group size.
- Dependencies: 2 (events, aggregation rules), stored question embeddings or recomputation (R-D7), clustering without a new dependency if possible (R-D8). Risks: noisy clusters on small classes; labels that expose personal text; recomputation cost.

### Feature 4 — Possible learning difficulties
- **`learning-difficulty-signals`**: transparent rules first (repeated reformulation of the same topic, repeated no-material on a topic the material covers, sequence of follow-ups on one concept), shown to the teacher per topic and, only if R-D3/R-D10 allow it, per student with the evidence. Not a score, not a grade, not shown to the student.
- Dependencies: 3, 1 (a "difficulty" caused by a retrieval failure is a false positive). Risks: **profiling of students** (legal review; Ley 25.326 purpose and information duties), false positives, teacher over-trust, bias by writing style. Needs the owner's decision and a lawyer's opinion before any per-student view.

### Feature 5 — Personalised support per subject and student
- **`student-learning-profile`** (backend): what is remembered per student and subject (topics asked, confirmed understanding, preferences such as brevity), under the student's control: visible, editable, deletable, off by default or opt-in (R-D10). Depends on `personal-data-erasure` and consent withdrawal.
- **`personalised-study-support`**: use the profile in the prompt (suggestions, "you asked about X last week", review reminders) without leaving the subject's material. Cost: longer prompts. Risks: memory leaking across subjects (isolation scenarios), prompt-injection through stored memory, creepiness, data growth.

### Feature 6 — Adaptive content, explanations and exercises
- **`adaptive-exercises`**: generate practice questions and graded explanations from the subject's chunks, adjusting difficulty by the profile; each exercise stores its source chunks; the student's attempts are personal data. Teacher can review/disable generated sets. Depends on 1 (grounding) and 5 (profile), plus new entities (exercises, attempts → migration). Risks: wrong answers presented as correct (needs source-bound answer keys and a "report this" path), cost per generation, cheating/assessment misuse (explicitly practice only, never grades).

### Feature 7 — Pedagogical recommendations for teachers
- **`teacher-pedagogical-recommendations`**: from the aggregated outputs of 3 and 4 (not from raw conversations), suggest actions ("topic X: many unanswered questions — add material / clarify in class"), each with its evidence and a reliability note. Depends on 3 and 4. Risks: generic or wrong advice, over-trust, one more model call per report (cost; generate on demand, cache).

### Feature 8 — Moodle and other LMS
- **`lms-integration-foundation`** (parallel track): decide the mechanism first (LTI 1.3 launch with signed JWT and deep link vs. REST/webservice sync of courses and enrolments vs. both), identity mapping/SSO (a new way to authenticate — architecture-affecting), course ↔ subject mapping, enrolment sync, grade passback excluded. Depends on deployment (HTTPS, stable URLs), institution agreement and the identity decision (R-D9). Risks: tenant/institution model absent today, key management, data contracts of each LMS, support burden. Proposed first slice: LTI launch + roster sync read-only for Moodle.

### Feature 9 — Institutional academic and administrative assistant
- **`institutional-assistant`**: a knowledge base that belongs to the institution (calendar, regulations, procedures), not to a subject; new role(s) to manage it and a new retrieval scope; clear hand-off to a human for anything that is not documented. This is the "student-services assistant" the MVP excluded. Depends on 1, deployment, a role/permission model extension and probably an institution entity (R-D9). Risks: administrative answers carry institutional liability, outdated documents, sensitive procedures, scope creep into transactions (read-only information only).

## 4. Dependency map

```
R0 (erasure, consent withdrawal, metering, e2e, deploy)
   |
   v
1a golden set --> 1b attribution --> 1c retrieval quality
                                         |
                                         v
                    2 events/metrics --> 2 dashboard
                                         |
                                         v
                    3 topics --> 4 difficulty signals --> 7 recommendations
                      |
                      v (profile needs erasure + consent)
                    5 learning profile --> 5 personalised support --> 6 adaptive exercises
   deploy --> 8 LMS foundation (parallel)        1c + role model --> 9 institutional assistant
```

## 5. Cross-cutting requirements (apply to every change)

- **Privacy and legal (Ley 25.326, Decreto 1558/2001)**: each feature states purpose, data kept, retention and who sees it; the policy and the consent text are versioned and re-accepted when the purpose changes; analytics and profiling are listed purposes; erasure and withdrawal cover every new store. TD-003, TD-063, TD-064 stay conditions for any real-student use.
- **Security**: authorization and subject/student isolation scenarios with denied cases for every new endpoint; model inputs treated as untrusted, including stored memory and generated exercises; no secrets or content in logs; adversarial review for every change touching chat/RAG or personal data (`docs/base-standards.md` §9.8).
- **AI reliability**: golden-set regression before and after any AI change; refusal over invention; human-in-the-loop for anything about people; labelled reliability and a way to report a wrong output.
- **Cost and capacity**: metering per call, per feature and per subject; budgets and alarms; caching of derived results; free tier is for fictitious data only (TD-063); capacity of a single process and in-memory rate limits (TD-007, TD-035).
- **Data**: migrations with downgrade, least-privilege grants, `docs/data-model.md` and `docs/api-spec.yml` updated in the same change, retention defined for events and embeddings of questions.
- **Process**: one OpenSpec change per row of §3, branch `feature/<name>`, evidence reports, independent review, and the accepted risks in `docs/technical-debt.md`.

## 6. Decisions that need the owner (blocking marked)

| ID | Decision | Blocks |
|---|---|---|
| R-D1 | Approve moving the excluded items (advanced teacher analytics, LMS integration, institutional assistant) into scope; then update `docs/base-standards.md` §8, `openspec/config.yaml` context and, with approval, `readme.md` (academic deliverable) **Approved on 2026-11-23 only for aggregate teacher activity metrics (switched off by default); `base-standards.md` §8 and `openspec/config.yaml` updated; individual analytics and profiling stay out of the current scope without being excluded from the future roadmap; LMS integration and the institutional assistant are still pending; `readme.md` untouched** | all of phases 2–5 (not phase 0–1) |
| R-D2 | Provider and tier for real students (paid Gemini with data processing terms, another provider, institution-hosted model) and who signs the terms (TD-063) | pilot, not development |
| R-D3 | Teacher visibility: aggregate only with minimum group size N, or identifiable students; value of N. **Provisional (owner, 2026-11-23): aggregate only, N = 5, weekly, 90 days; identifiable students are not approved** | 2, 3, 4, 7 |
| R-D4 | Source attribution policy when no valid marker: drop the sources, or keep them flagged (contract change) | 1b |
| R-D5 | Golden set: authorship, size, when to add real teacher material and who consents | 1a (size), 1c (real material) |
| R-D6 | Retrieval techniques allowed: query rewriting with the model, hybrid search, reranker, embedding model change (cost, latency, schema) | 1c |
| R-D7 | Data-model additions: stored answer kind, event/metric tables, question embeddings, retention periods | 2, 3, 5, 6 |
| R-D8 | New dependencies: chart library (frontend), clustering (backend) | 2, 3 |
| R-D9 | Architecture: institution/tenant entity, admin/institution roles, SSO or LTI identity | 8, 9 |
| R-D10 | Legal opinion on student profiling, learning memory and automated signals; whether memory is opt-in and whether per-student views exist | 4, 5, 6 |
| R-D11 | Provide or confirm the Aprendiz/MIA analysis the roadmap is based on | prioritisation |

## 7. Recommendation

**GO** to start `rag-golden-set-evaluation`: no contract, schema, dependency or architecture change, fictitious data only, no Gemini in CI, and it is the evidence every other row depends on. Needs only the owner's approval of its artifacts (size and authorship of the set, R-D5; the `backend/evaluation/` location).
**NO-GO (until decided)** for `rag-source-attribution` (R-D4), phases 2–5 except the first aggregate teacher metrics (R-D1 approved for them on 2026-11-23; R-D3 provisional; R-D7 no new storage in that slice) and any use with real students (R-D2, TD-003, TD-063, TD-064).
