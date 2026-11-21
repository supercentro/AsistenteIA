# Proposal

## Why

Every later feature of the roadmap (`docs/roadmap.md`) trusts the answers and the citations of the RAG pipeline, and none of that trust is measured today. TD-033 records that retrieval was validated on 45 questions written by one author; TD-062 records that the share of answers that fall back to "all retrieved chunks", that replay stale `[n]` markers or that repeat a marker from a document is unmeasured at scale. The spike of `document-ingestion` also measured that irrelevant passages of the same subject reach a median similarity of 0.285 (p90 0.438), close to the default `CHAT_RELEVANCE_THRESHOLD` of 0.3, so the "no material" decision is probably weak. Changing the prompt, the retrieval or the model without a baseline would make any improvement a guess. A repeatable, offline evaluation harness is the smallest change that makes the next quality changes testable.

## What Changes

- A **golden set** of fictitious documents and cases, seeded from the already validated spike material (60 passages in 3 subjects, 45 questions, in the archived `document-ingestion` reports) and extended with unanswerable, follow-up, prompt-injection, wrong-marker and cross-subject cases. Each case states the acceptable sources (file, page, passage) or the expected "no material" outcome.
- An **evaluation harness** (tooling, not product code) that loads the corpus into the isolated test database through the existing ingestion code and measures the production code path (the chat service read phase, prompt builder and citation selection), reporting:
  - retrieval metrics (Hit@1, Hit@3, Hit@5, MRR), with follow-ups reported apart, and a sweep of `CHAT_TOP_K` and `CHAT_RELEVANCE_THRESHOLD`;
  - the "no material" decision (answerable questions wrongly refused, unanswerable ones that pass the threshold);
  - **attribution metrics** (answers mode with the real model): valid marker, fallback to all retrieved chunks, wrong citation against the accepted passages, stale or repeated markers; unanswerable cases that reach the model are listed for human review, not auto-graded.
- Modes: `retrieval` (no model), `answers` with the fake model (what the automated suite runs on a small fixture, with the fake embedder, to prove the mechanics) and `answers` with the real Gemini model on the free tier (manual, fictitious data, bounded, never CI). Runs with the real embedder happen in the container that holds the model, like the existing `realmodel` tests.
- A baseline report under `reports/` and new evidence for TD-033 and TD-062 (both stay open).

## Capabilities

### New Capabilities

- `rag-evaluation`: offline, repeatable measurement of retrieval, refusal and attribution quality of the chat pipeline on a fictitious golden set, without any product behaviour change.

### Modified Capabilities

_None._ `rag-chat`, `chunk-retrieval` and `document-ingestion` are consumed unchanged.

## Impact

- **Product behaviour, API contract (`docs/api-spec.yml`), data model (`docs/data-model.md`), migrations, application package `app/`, dependencies, infrastructure and Docker/compose files**: none.
- **Regression risk for the MVP**: nil by construction (no file of `app/` changes); the only shared surface is one new integration test in the existing backend job and a few seconds of its time. The harness must not become a second implementation of the pipeline (it calls the production functions).
- **Authorization and data isolation**: the harness uses the real repository authorization (a synthetic student enrolled in synthetic subjects) and includes denied cases (not enrolled, other subject) so that a retrieval change cannot leak across subjects unnoticed.
- **Personal data**: none. Corpus and questions are fictitious; no real student, no real course material (decision D5 for the future use of real material).
- **External services**: Gemini only in the manual real-model mode, free tier, fictitious data, bounded calls; CI never calls Gemini and never loads the embedding model.
- **Security**: the set contains prompt-injection traps as inputs; reports never contain secrets; the harness refuses to run against any database other than the isolated test database (TD-013 notes that this guard is a convention, so the harness adds its own check).
- **Cost**: the real-model mode makes one model call per answered case (about 50 in the proposed size); retrieval mode and CI make none.

### Out of scope

- Any change to the prompt, retrieval, thresholds, model, sources shown or API (they belong to `rag-source-attribution` and `rag-retrieval-quality`).
- Real course material or real students' questions (needs approval, D5).
- Automatic LLM-as-judge scoring.
- A frontend or dashboard; the output is a Markdown/JSON report.
- Closing TD-033 or TD-062: the baseline gives evidence; closing them is decided with the owner after the improvements.
