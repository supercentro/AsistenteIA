# Academic Requirements (LIDR AI4Devs Final Project)

Faithful summary of the course requirements that constrain AsistenteIA. It exists so that the repository is self-contained: the original Master AI4Devs documents live outside the repo and are **not** copied here.

> Status: summary written from the four course documents listed in "Sources". If a statement here diverges from the originals, the **originals win** and the divergence must be reported to the user. Everything in this file is a requirement of the course, not a product decision; product decisions live in `readme.md` and `docs/`.

## Sources (outside the repository)

| Document | Used for |
|---|---|
| Proyecto Final Master AI4Devs | Overview, the 3 deliveries, dates, repository and branch rules, submission form |
| Lección 1 — Todo lo que necesitás saber para arrancar tu Proyecto Final | MVP scope, content of each delivery, AI log, FAQ |
| Lección 2 — Resuelve tus bloqueos y avanza hacia la entrega final | Deployment expectations, where documentation lives, stories vs tickets, AI log, delivery 2 checklist |
| Ejemplo_Proyectos Finales Reales | Two reference projects (inspiration only, never features of this product) |

## 1. What the course asks for

- A software product built end to end with AI integrated in every phase (idea, documentation, code, testing, deployment). Free domain and stack.
- An MVP robust enough to have **at least one complete end-to-end flow** (backend, frontend and database, or the equivalent for the stack).
- Evaluation has three axes: the product idea and architecture, code quality, and how AI was used throughout the process.
- Recommended MVP scope: **3–5 must-have user stories** and **1–2 should-have**. Do not try to include everything learned in the master.
- Estimated effort: 30 hours in total (in practice many students spend more).

## 2. The three deliveries

| # | Delivery | Content | Date |
|---|---|---|---|
| 1 | Technical documentation (no code) | Project card (name, description, repo URL or ZIP), product overview (goal, features), system architecture, data model, user stories, work tickets, chosen stack | Friday 2026-09-25 |
| 2 | Functional code | Scaffolds of the architecture connected (frontend, backend, database), main flow (almost) complete, first operational features. Tests are not mandatory yet | Friday 2026-10-23 |
| Final | Final delivery | Deliveries 1 + 2, **3–5 complete and functional features**, test suite (unit, integration, **at least one end-to-end test of the main flow**), deployment evidence (public URL, screenshots or video), complete `prompts.md` | Tuesday 2026-11-10 |

- Deliveries 1 and 2 get automated review; only the final delivery gets personalised human feedback.
- A delivery may be submitted before its date (e.g. delivering 1, 2 and final together). Partial dates exist so work is not left to the end.
- Extension: up to 2 weeks after the **final** date, requested to the TA in advance and evaluated case by case. Partial deliveries have flexibility handled case by case with the TA.

## 3. Repository, branches and submission

- Work happens in the student's **own repository** (new or existing). The official `LIDR-academy/AI4Devs-finalproject` repository is only a template to copy `README.md` and `prompts.md` into the root; it is not used for work or Pull Requests.
- One branch per delivery, **initials mandatory** (without them the delivery cannot be identified):
  - Delivery 1: `feature/entrega-1-<INITIALS>`
  - Delivery 2: `feature/entrega-2-<INITIALS>`
  - Final: `final-project-<INITIALS>`
- After each delivery, complete the Typeform submission form with full name, email, delivery type (1, 2 or final) and the **link to the branch** (`https://github.com/<user>/<repo>/tree/<branch>`). Pull Request URLs are not accepted. Without the form, the delivery does not formally exist.
- Private repository: invite the institutional GitHub account **LIDR-AI4Devs** (not an individual TA) and submit as usual. If code cannot be shared: complete the README and record a 2–3 minute video of the product working. In every case `prompts.md` is mandatory.
- Project documentation lives in the repository root (`README.md`, `prompts.md`), not in Confluence, Notion or an external wiki. The README must include the project card, architecture, instructions to run/test the MVP and **test login credentials** if the MVP requires login.

## 4. Documentation expectations

- `README.md` (course template): project card, description, architecture, data model, API, user stories, tickets, stack.
- User story vs ticket: a **story** is a business-language description of what the user needs (readable by the client); a **ticket** is the technical task (what to do, how, acceptance criteria). One story can generate several tickets; tickets are what enters the board.
- For delivery 1, start from the 3–5 most important features: one story per feature, and technical tickets per story. Documentation grows with the project.
- Any ticket tool is valid (Jira, Linear, GitHub Issues, Azure DevOps, Notion) as long as tickets exist and are referenced in the documentation.
- Reference examples (Example1: PHP/React booking system; Example2: Python/FastAPI/React RAG chatbot with Gemini and pgvector) are for inspiration; copy decisions, not structure.

## 5. AI usage log (`prompts.md`)

The log documents the **AI workflow**, not the whole chat history:

- Tools used (Claude, Cursor, ChatGPT, etc.) and for which phase.
- Models used and why (e.g. Opus for specifications, Sonnet for coding).
- Skills, subagents, rules or custom commands, and how context was structured (CLAUDE.md, rules, system prompts).
- The 3–5 most representative prompts or workflows (reconstructed ones are acceptable if labelled as such).
- The human adjustments made when the AI got something wrong.

Prompts relevant to each phase should be saved as the work progresses. This is one of the three evaluation axes of the final delivery.

## 6. Deployment expectations

- **Mandatory minimum**: the system can be verified as working — a public URL, a 2–3 minute video of the main flow, or repository access for the LIDR-AI4Devs account to review locally.
- **Not mandatory**: production deployment with a custom domain, full CI/CD, infrastructure as code. They do not block approval.
- Typical web project: any cloud platform (Railway, Render, Vercel + Supabase, etc.).

## 7. Testing expectations

- Delivery 2: tests not mandatory.
- Final delivery: unit tests, integration tests and at least one end-to-end test of the main flow.
- Not implementing advanced CI/CD or testing is not a problem; the focus is a working product and visible use of AI.

## 8. Delivery 2 checklist (from the course)

README up to date and based on the template; instructions and test credentials; connected scaffolds; main flow at least partially functional and verifiable; branch with correct name and initials; repository access granted to LIDR-AI4Devs if private; form submitted with the branch link.

## 9. How this repository maps to the course

- AsistenteIA is developed in its own product repository. Implementation work uses `feature/<change-name>` branches merged to `main` through Pull Requests (see `docs/development_guide.md` §5).
- Course delivery branches (`feature/entrega-N-<INITIALS>`, `final-project-<INITIALS>`) are a submission concern and are cut from `main` when a delivery is made. Their naming comes from section 3 above, not from the implementation workflow.
- `readme.md` and `prompts.md` are the course deliverables and follow the template; see `docs/base-standards.md` §0 for who owns what.
