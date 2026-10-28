---
description: Standards for technical documentation and AI specs in AsistenteIA, including ownership, update process and language rules.
alwaysApply: true
---

# Documentation Standards

## Ownership map (no duplication)

| Content | Single owner |
|---|---|
| Academic requirements, delivery dates | Master AI4Devs documents (outside the repo, they win); in-repo summary in `docs/academic-requirements.md` |
| Product description, user stories (academic summary), tickets (academic summary), architecture overview | `readme.md` |
| AI usage log (tools, models, key prompts, human adjustments) | `prompts.md` |
| Database model | `docs/data-model.md` |
| REST contract | `docs/api-spec.yml` |
| Coding, security, testing conventions and quality gates | `docs/base-standards.md`, `docs/backend-standards.md`, `docs/frontend-standards.md` |
| Setup and commands | `docs/development_guide.md` |
| Change proposals, specs, tasks | `openspec/` |
| Residual risks and accepted technical debt | `docs/technical-debt.md` |
| Process lessons learned (problem, root cause, preventive measure, evidence) | `docs/lessons-learned.md` |

Rules:
- Link instead of copying. If information must appear in two places (e.g. the course requires it in `readme.md`), the `docs/` file is canonical and the copy is labelled as a summary.
- Reference examples from the course (Example1/Example2 repositories) are inspiration, never features of this product.

## Language

- `docs/`, `ai-specs/`, OpenSpec artifacts, code comments, commit messages: **English**.
- `readme.md` and `prompts.md` (course deliverables): **Spanish**.

## When to update what

Before any commit or push, review which documentation changes:

| Change | Update |
|---|---|
| Entity, column, index, migration | `docs/data-model.md` |
| Endpoint, schema, status code | `docs/api-spec.yml` |
| Library, tooling, env var, install step | `docs/*-standards.md`, `docs/development_guide.md`, `.env.example` |
| Architecture or stack decision | `readme.md` (needs user approval) and the relevant standards |
| Residual risk or known limitation accepted at merge | `docs/technical-debt.md` (add a row; update the status when resolved) |
| Review finding, process deviation or practice worth repeating | `docs/lessons-learned.md` (append the next ID at review or archive time; the preventive rule goes to the owning standard, linked, not copied) |
| Significant use of AI (new agent, skill, workflow, notable correction) | `prompts.md` (needs user approval; only real interactions) |

Update in the same change as the code, in English (except the two Spanish files), keeping the existing structure.

One home per item: a product or code risk accepted at merge lives only in `docs/technical-debt.md`; a process or tooling lesson lives only in `docs/lessons-learned.md`, which cites `TD-` IDs instead of restating them.

## `prompts.md` rules

- Record only interactions that really happened; never fabricate or embellish prompts.
- Per the course: tools used, models and the phase they served, skills/subagents/rules used, the most representative prompts or workflows (max 3 per section), and the human adjustments made to AI output.
- Reconstructed prompts must be labelled as reconstructed.

## AI specs (agents, skills, rules)

- Agents and skills live in `ai-specs/` (canonical). See `base-standards.md` §6 for the Windows copy limitation.
- Learn from user feedback: when the user corrects or states a preference, propose a precise change to the affected rule, get explicit approval, then apply it and confirm.
- Avoid: applying rule changes without approval, unlinked proposals, touching unrelated rules, and changing rules without a triggering piece of feedback.

## Documentation quality checks

- MUST: every relative link resolves; every code/command example has been run or is marked as planned.
- MUST: no secrets or real credentials in any document, including examples.
- SHOULD: mark status explicitly (`confirmed`, `proposed`, `pending`) whenever a decision is not final.
