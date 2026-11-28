---
description: Development rules and quality gates for AsistenteIA, applicable to all AI agents (Claude, Cursor, Codex, Gemini, etc.).
alwaysApply: true
---

# AsistenteIA — Base Standards

AsistenteIA is an academic RAG assistant organised by subject (teachers upload material, students ask questions and get answers with verifiable sources).

## 0. Documentation hierarchy (who owns what)

| Source | Responsibility |
|---|---|
| Master AI4Devs documents (outside the repo) | Original academic requirements and delivery conditions; they win over any summary |
| `docs/academic-requirements.md` | In-repo summary of those requirements (deliveries, dates, branches, submission, AI log); update it if the originals change |
| `readme.md` | Product-level functional and architectural decisions, delivered to the course |
| `prompts.md` | Record of AI-assisted development (tools, models, key prompts, human adjustments) |
| `docs/` | Technical standards and implementation conventions; **canonical** data model (`data-model.md`) and API contract (`api-spec.yml`) |
| `ai-specs/agents/`, `ai-specs/skills/` | Reusable roles and procedures |
| `openspec/` | Changes, proposals, specs and tasks |

Precedence when sources disagree (highest first): (1) original Master AI4Devs documents; (2) `docs/academic-requirements.md`; (3) `docs/` technical files (`data-model.md`, `api-spec.yml`, standards); (4) `readme.md` sections 3 and 4 (academic summary). Technical contracts are owned by `docs/`, course conditions by (1)-(2). Always report a divergence to the user instead of fixing it silently.

Rules:
- Do not duplicate user stories, API contracts or data models across documents. Link to the owner instead.
- `readme.md` sections 3 and 4 are an academic summary. If they diverge from `docs/data-model.md` / `docs/api-spec.yml`, the `docs/` files win and the divergence must be reported to the user, not silently fixed.
- Never edit `readme.md` or `prompts.md` without explicit user approval. Never invent interactions in `prompts.md`.
- Do not add features beyond the approved MVP (see section 8) without user approval.

## 1. Core Principles

- **Small tasks, one at a time**: work in baby steps; never go forward more than one step.
- **Test-Driven Development**: start with failing tests for any new functionality, according to the task details.
- **Type safety**: all code must be fully typed (Python type hints checked by `mypy --strict`; TypeScript `strict`).
- **Clear naming**: descriptive names for variables, functions and modules.
- **Incremental changes**: prefer small, focused changes.
- **Question assumptions**: always question assumptions and inferences.
- **Pattern detection**: detect and highlight repeated code patterns.

## 2. Language Standards

- **English** for all technical artifacts: code, comments, error and log messages, `docs/`, `ai-specs/`, OpenSpec artifacts, API schemas, database names, configuration, commit messages and test names.
- **Spanish** only for the academic deliverables (`readme.md`, `prompts.md`) and user-facing UI copy (the product serves Spanish-speaking students; keep UI strings in a single i18n/constants location).

## 3. Specific standards

- [Backend Standards](./backend-standards.md) — FastAPI, RAG pipeline, persistence, security, backend testing
- [Frontend Standards](./frontend-standards.md) — React, TypeScript, Tailwind, React Query, frontend testing
- [Documentation Standards](./documentation-standards.md) — documentation structure, ownership and maintenance
- [Data Model](./data-model.md) — canonical database model
- [API Spec](./api-spec.yml) — canonical OpenAPI contract
- [Academic Requirements](./academic-requirements.md) — summary of the LIDR course requirements
- [Development Guide](./development_guide.md) — local setup, commands, reproducibility
- [OpenSpec Tasks Mandatory Steps](./openspec-tasks-mandatory-steps.md) — required checklist when creating or updating OpenSpec `tasks.md`
- [Lessons Learned](./lessons-learned.md) — process lessons with evidence; read before proposing a change
- [Technical Debt](./technical-debt.md) — register of accepted residual risks

## 4. Project Skills

- Skills live in `ai-specs/skills`.
- When a request matches a skill, load and follow the corresponding `SKILL.md` before continuing, including any referenced files in the skill folder.

## 5. Planning Model Recommendation

Planning workflows (`enrich-us`, `openspec-propose`, `openspec-update-change`) **should** run with the strongest reasoning model available. This is a recommendation, not a gate: agents must not edit `.claude/settings.json` or switch models on their own; if the session model seems insufficient, tell the user.

## 6. Multi-Agent Portability (Windows note)

- **Canonical source**: reusable agents and skills live in `ai-specs/`. Agent-specific folders (`.claude/agents`, `.claude/skills`) should reference them through symlinks.
- **Current limitation**: the development machine is Windows without symlink privileges. Therefore:
  - `CLAUDE.md`, `AGENTS.md`, `codex.md`, `GEMINI.md` are tiny pointer files to this document (no rules duplicated).
  - `.claude/agents/*` and `.claude/skills/*` are **copies** of `ai-specs/agents/*` and `ai-specs/skills/*` (except `openspec-*` skills, which are generated by the OpenSpec CLI directly in `.claude/skills` and `.agents/skills`; the `openspec-sync-specs` copy in `ai-specs/skills` is the Specboot variant and is intentionally not copied to avoid overriding the CLI one). After editing an agent or skill in `ai-specs/`, re-copy it in the same change.
  - If symlinks become available (Developer Mode or admin shell), replace the copies with symlinks and update this section.
- The `sync-agent-symlinks` skill assumes symlinks and `.cursor/`; on this machine apply its inventory step only and re-copy manually.
- **Completion gate**: a change is incomplete if it leaves stale copies, broken links, or a duplicated canonical artifact that differs from its source.

## 7. OpenSpec Artifact Updates after Apply

When a new fix/change request appears after `opsx:apply` and before `opsx:archive`, treat it as a spec update first:

1. Update the affected OpenSpec artifacts (scenarios, requirements/specs, `tasks.md`) inside the proper sections — not as ad-hoc "bugfix" tasks.
2. Use `/opsx:update` (skill `openspec-update-change`) to revise and reconcile the artifacts before coding.
3. Implement code only after the artifacts reflect the request.
4. Re-run verification against the updated artifacts before archiving.

## 7.1 Change Workflow (OpenSpec + Specboot)

OpenSpec (`openspec/`) owns changes: proposal, specs, design, tasks and their lifecycle. This document and the other `docs/` files own the implementation standards. Installed commands (OpenSpec CLI 1.15.0, commands in `.claude/commands/opsx/`, skills in `.claude/skills/` and `.agents/skills/`): `/opsx:explore`, `/opsx:propose`, `/opsx:update`, `/opsx:apply`, `/opsx:sync`, `/opsx:archive`; CLI `openspec list|show|validate|archive`.

1. **Define and approve**: refine the story (`enrich-us` skill if needed) and `/opsx:explore` unclear points; get user approval of scope before proposing.
2. **Propose**: `/opsx:propose <change-name>` generates proposal, specs, design and tasks. Check them against the approved MVP scope (§8), `readme.md` and `docs/api-spec.yml` / `docs/data-model.md`.
3. **Validate**: `openspec validate <change-name> --strict`; the user reviews and approves the artifacts. Architecture-affecting decisions need explicit approval.
4. **Implement incrementally**: create the branch `feature/<change-name>` from `main` (task Step 0), then `/opsx:apply`, one task at a time, test first, with the backend or frontend agent from `ai-specs/agents/`. Merge to `main` only through a Pull Request.
5. **Tests and security**: all MUST gates of §9 pass (tests, authorization negatives, isolation, secrets, lint, types).
6. **Review and verify**: run the `adversarial-review` skill on sensitive changes; run the feature for real (manual call or E2E); `update-docs` skill for documentation.
7. **Archive**: `/opsx:archive` (`/opsx:sync` first if specs must be merged without archiving).
8. **Record**: with user approval, add significant AI usage (tools, models, key prompts, human adjustments) to `prompts.md`.

## 8. Product Scope (approved MVP)

In scope: subject and material management by teachers; RAG queries by students with verifiable sources; conversation history; deletion of conversations and personal data; authentication and role-based authorization.

Out of scope for the mandatory MVP: Moodle integration; student-services (administrative) assistant; advanced teacher analytics (individual or profiling; should-have only). Planned and switched off by default until the privacy conditions are met: aggregate activity metrics per subject for its owning teacher (change `activity-events-and-metrics`). Also planned, switched off by default and with fictitious data only (R-D1 extended on 2026-11-28 to this alone): the topics of a subject's PDF material, defined by their bookmarks or by the owning teacher, and the aggregate ranking of the most cited ones (change `frequent-questions-and-topics`).

## 9. Quality Gates

Legend: **MUST** = blocks merge/delivery. **SHOULD** = recommended; deviations need a note in the PR.

### 9.1 Typing and data validation
- MUST: Pydantic v2 schemas on every request/response; no raw `dict` crossing the API layer.
- MUST: `mypy --strict` passes on `backend/app`; TypeScript `strict: true`, no `any` without a justified comment.
- MUST: validate uploads (extension, MIME type, size limit) before processing.
- SHOULD: `NewType`/enums for roles, document status and message roles.

### 9.2 Testing
- MUST: unit tests for services (LLM, embeddings and repositories mocked); integration tests for endpoints against a real PostgreSQL+pgvector test database; at least one automated end-to-end test of the main flow (teacher uploads → student asks → answer with citation) written with **Playwright Test** (`@playwright/test`, committed and run in `npm run test:e2e`) before final delivery. **Playwright MCP** is a different thing: the agent's browser tools for manual verification during `/opsx:apply` (see `openspec-tasks-mandatory-steps.md`); it does not replace the committed suite. Playwright CLI is an accepted alternative to MCP when the MCP server is unavailable.
- MUST: external services (Gemini) are never called in CI; use fakes/recorded fixtures.
- MUST: every authorization rule has a negative test (wrong role, other teacher's subject, non-enrolled student, other student's conversation).
- MUST: TDD evidence per functional group: run the new tests before the implementation and record the failing run (command and failure summary) in the change report or PR. Record every deviation with its justification and compensate it with a mutation check (temporarily remove the guarded code and show a test fails).
- MUST: behaviour that depends on Uvicorn, HTTP headers, proxies, transport or server configuration is tested against a real server process started with the production arguments; `TestClient` alone is not sufficient.
- MUST: negative and extreme-input cases proportional to the change (control characters, oversize, malformed identifiers, duplicates under concurrency) never produce a 500; errors and captured logs of new endpoints never expose passwords, hashes, tokens, emails or SQL parameters (see `backend-standards.md`).
- SHOULD: backend coverage ≥ 80% on `services/` and `repositories/`; frontend ≥ 70% on components/hooks.

### 9.3 Security and secrets
- MUST: no secrets in the repository; `.env` is git-ignored, `.env.example` documents every variable with placeholder values.
- MUST: passwords hashed with argon2; JWT with expiry; secrets read only through `core/config.py`.
- MUST: treat uploaded documents and user messages as untrusted (prompt-injection defences, see backend standards).
- MUST: dependency versions pinned (lock files committed).
- SHOULD: dependency vulnerability scan (`pip-audit`, `npm audit`) in CI.

### 9.4 Authorization and data isolation
- MUST: every query that reads chunks, conversations or messages is scoped by `subject_id` and by the authenticated user, enforced in the repository layer (not only in routers).
- MUST: a student can only access subjects they are enrolled in and their own conversations; a teacher only their own subjects.
- MUST: the only reading of conversations or messages by a teacher is aggregate-only: counts and rates for a subject the teacher owns, through a dedicated repository that takes the teacher and joins `subjects.teacher_id`, with every figure below the minimum group suppressed; never message text, student identifiers or per-student figures (see `backend-standards.md` section 9).

### 9.5 RAG quality
- MUST: answers are generated only from retrieved chunks; if retrieval returns nothing above the relevance threshold, return the controlled "no material" response without calling the LLM.
- MUST: every assistant answer persists its source chunks (traceable citations).
- SHOULD: a small golden set (≥ 15 question/expected-source pairs) evaluated with retrieval hit-rate before final delivery.

### 9.6 Linting and formatting
- MUST: backend `ruff check --no-cache` and `ruff format --check`; frontend ESLint and Prettier; both clean before commit. The local `ruff check` runs without the cache, because a cached verdict computed before new modules existed can hide import-order errors that CI reports.

### 9.7 Migrations and reproducibility
- MUST: every schema change is an Alembic migration with a working `downgrade`; migrations run on a clean database.
- MUST: `alembic check` reports no drift between models and migrations; a migration already merged to `main` is never edited (add a new one).
- MUST: the full stack starts with `docker compose up` following `docs/development_guide.md`.
- MUST: lock files committed (`uv.lock`, `package-lock.json`); runtime versions pinned (Python 3.12, Node LTS, PostgreSQL 15 with pgvector).

### 9.8 Code review and documentation
- MUST: documentation updated in the same change (see documentation standards).
- MUST: conventional commits; one logical change per commit.
- MUST: changes to authentication, authorization, personal data or security get an independent adversarial review (`adversarial-review` skill) by a separate subagent or a clean-context session, not by the implementing session. The report records findings, fixes and a final verdict; a change is not closed with an open blocker or major finding. Other sensitive changes (upload, chat) SHOULD get the same review.
- MUST: traceability before archive: status codes, limits and field rules agree across `docs/api-spec.yml`, the OpenSpec specs, the tests and the implemented behaviour; report any divergence instead of fixing it silently.
- MUST: accepted residual risks are added to `docs/technical-debt.md`; lessons from review findings or process deviations are added to `docs/lessons-learned.md` (see `documentation-standards.md`).

### 9.9 Definition of Done
A task is done when: acceptance criteria met; failing-first tests now pass; all MUST gates above pass, **re-run after the last change (code, tests, scripts or documentation) and before publishing**, since earlier green results do not cover a later edit; docs (`data-model.md`, `api-spec.yml`, standards) updated; OpenSpec `tasks.md` checked off; no TODOs without ticket; and the change was verified running (manual call or E2E), not just by unit tests.
