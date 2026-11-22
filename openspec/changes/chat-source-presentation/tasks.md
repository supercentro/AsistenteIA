# Tasks

> Approved by the owner on 2026-11-22 (D-S1 to D-S6 and the two labels) and implemented in the working tree (not committed). No commit, push, pull request or merge without a new authorisation; no real Gemini call; no change of Actions, database, secrets or architecture. Follows `docs/openspec-tasks-mandatory-steps.md`.

## 0. Branch

- [x] 0.1 Step 0: create the branch `feature/chat-source-presentation` from `main` (f8f28b0) before any code change. Merge only through a Pull Request.

## 1. Tests first

- [x] 1.1 Backend unit: the pure helper `attribution_of(content, ranks)` (cited, retrieved, no sources, a rank gap, an answer that only the new reader recognises, an invalid marker); a property test that the live decision of `select_cited` and the derivation from the stored data agree for generated answers and chunk counts
- [x] 1.2 Backend integration against PostgreSQL: the chat answer and the history carry the same `attribution`; a "no material" answer and a question have none; the sources and their order are unchanged
- [x] 1.3 Contract: `api-spec.yml` documents the optional nullable field; the contract tests and `check:api-types` stay green
- [x] 1.4 Frontend component tests: cited sources show their marker number and the cited label; retrieved sources are inside a collapsed detail with its label and no number; a response without the field is shown as retrieved; neutral wording; text-only rendering; axe without serious violations
- [x] 1.5 Playwright mocked test of the chat: cited and retrieved answers in one thread; keyboard opening of the collapsed detail
- [x] 1.6 Run the new tests before any implementation and record the failing run in `reports/`

## 2. Implementation

- [x] 2.1 Backend: the helper next to `select_cited`; `attribution` in `ChatResponse` and `MessageResponse` and in both endpoints; no model, repository, migration or grant change
- [x] 2.2 `docs/api-spec.yml` and `frontend/src/types/api.generated.ts` (regenerated, same commit)
- [x] 2.3 Frontend: `SourcesBlock.tsx`, `MessageBubble.tsx`, `strings.es.ts` (approved copy only)
- [x] 2.4 Mutation checks: flag always `cited`, always `retrieved`, derivation ignores gaps, marker numbers shown for retrieved, detail not collapsed
- [x] 2.5 `ruff check --no-cache`, `ruff format --check`, `mypy --strict`, `npm run typecheck`, `lint`, `format:check`, `check:api-types`

## 3. Verification

- [x] 3.1 Step N: review and update the existing chat tests (backend and frontend) and the e2e specs
- [x] 3.2 Step N+1: run the unit and integration suites and the frontend suites; the database state: the test database `asistenteia_test` holds 0 users, 0 subjects and 0 messages afterwards and the development database is not touched (nothing is written by this change)
- [x] 3.3 Step N+2: manual endpoint test with the fake model only (no real Gemini call); record it
- [x] 3.4 Step N+3: Playwright MCP run by the agent on the chat with the mocked API
- [x] 3.5 Step N+4: documentation: `docs/api-spec.yml`, `docs/technical-debt.md` (TD-062: what this slice covers, still open), `docs/roadmap.md`, `docs/development_guide.md` if needed
- [x] 3.6 Independent review (`adversarial-review` skill): contract compatibility, the derivation rule, wording that could imply a guarantee, accessibility
- [ ] 3.7 Final gates of `docs/base-standards.md` section 9 re-run after the last change; `openspec validate --all --strict`; CI on Linux after the pull request

> Notes (2026-11-22): approved by the owner (D-S1 to D-S6 and the two labels). 3.3: no endpoint call to a real model was made; the integration tests drive `/chat` and the history with a scripted model against PostgreSQL. 3.4: the committed Playwright suite (real Chromium, mocked API) covers the cited and the retrieved blocks, the keyboard opening and 320 px; no Playwright MCP run. 3.6: independent review PASS WITH GAPS (no Blocker or Major; the minors are in `reports/2026-11-22-verification-and-review.md`). Open: **3.7**, CI on Linux after the pull request, which needs a push (not authorised yet). Open outside this change: the quantitative target and the real-model comparison (baseline 3.3b of `rag-golden-set-evaluation`), the markers as links (D-S5), TD-062 and TD-068.
