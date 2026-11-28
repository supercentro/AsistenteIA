# Tasks

Tests come first in every group; each records its failing run in `reports/` before the code (`docs/base-standards.md` §9.2). Databases are disposable; no persistent database is migrated or written, and the branch is never started with `docker compose up` against a persistent volume. Gemini is not called. Backend commands that the host blocks (`mypy`, `uvicorn`) run in a container; the block is not worked around.

## 0. Setup: Create Feature Branch (MANDATORY - FIRST STEP)

- [x] 0.1 Create `feature/frequent-questions-and-topics` from `origin/main`; verify with `git status` that no foreign file is included
- [x] 0.2 Record the owner's approval of these artifacts and the answers to Q1 to Q3 of `design.md` in `reports/`; if Q1 is not the recommended option, update the artifacts first (`/opsx:update`)
- [x] 0.3 With Q3 authorised, write the approved R-D1 extension (this feature only, fictitious data, off by default) in `docs/base-standards.md` §8, `docs/backend-standards.md` §9, `openspec/config.yaml` and `docs/roadmap.md`; stop if not authorised

## 1. Data model

- [x] 1.1 Write failing migration, constraint and privilege tests for `document_topic_sets` and `document_topics` (upgrade, downgrade, cascade, composite key, grants per role)
- [x] 1.2 Add the models, migration and `db_privileges.py` entries; `alembic check`, the privilege matrix tests and `db-verify` pass on a disposable database
- [x] 1.3 Update `docs/data-model.md`

## 2. Teacher definition

- [x] 2.1 Write failing unit tests for validation (bounds, overlap, titles, extreme input), rename detection, revision, source and the marker (first set, change, clear, define again, never back)
- [x] 2.2 Write failing integration tests: owner, other teacher, student, anonymous, document of another subject, switches, text file, not ready, concurrent writes, deletion during a write, nothing changed after a refusal, titles absent from logs
- [x] 2.3 Implement repository, service, setting and the `GET`/`PUT` routes; tests pass
- [x] 2.4 Cover the scenarios added after review: delete between the checks of a write, invisible titles, repository scope by teacher

## 3. Ranking

- [x] 3.1 Write failing unit tests for counting once per topic, cited only, five at most, tie order, minimum group by topic and by subject, same title not added, per-document counting start, window rules and no whole week
- [x] 3.2 Write failing integration tests: authorization negatives, other subject's chunks never counted, deleted conversation and document, parameters ignored, switches, the two reasons for a document without topics, no identifying field, nothing stored, one pooled connection (lesson L52)
- [x] 3.3 Write privacy tests with a control on the same data (lesson L51): independence from data before the unenrolment marker; no subtraction across a change of ranges, including clear and define again and a change near midnight on Sunday; passing demonstrations of the open risks (F8 by page, the single retroactive cut, bounding a withheld topic)
- [x] 3.4 Implement the ranking (sharing the window computation) and its route; all tests pass and the activity tests are unchanged and green
- [x] 3.5 Cover after review: no message read without topics, read-only repeatable-read snapshot, subject-level minimum group, non-ready documents left out

## 4. Contract

- [x] 4.1 Add the three routes to `docs/api-spec.yml`, run `npm run generate:api` and `npm run check:api-types`, and add the settings to the example environment files with `false`

## 5. Frontend

- [x] 5.1 Draft the Spanish copy of both views and get the owner's approval (Q4); keep it in the strings file
- [x] 5.2 Write failing component tests for the editor: switches, roles, rows, validation messages, warning only on changed ranges, stale save, no pages, keyboard
- [x] 5.3 Write failing component tests for the ranking: links, one request, bars and table, every state, forbidden words, dashboard and document list unchanged and without topic requests
- [x] 5.4 Implement services, hooks, both views, routes and links; tests, lint, types and format pass
- [x] 5.5 Cover the editor scenarios added after review: failed reload, save in progress, focus, title length in code points

## 6. Bookmarks

- [x] 6.1 Write failing tests: nested, single root, shared page, none, over 100, start after the last page with text, cyclic or broken outline, hostile titles, encrypted file, resource kill and timeout (Linux)
- [x] 6.2 Implement the second run of the isolated child with strict protocol validation, title rules and page ranges
- [x] 6.3 Write failing ingestion tests (stored only with `ready`, none on a lost job, extraction failure keeps the document outcome, none for text, job deadline respected) and implement the write in the fenced final transaction

## 7. Review and Update Existing Unit Tests (MANDATORY)

- [x] 7.1 Review the tests and files this change touches but no test reads (lesson L26), including route and role coverage of the privilege gate; record the review

## 8. Run Unit Tests and Verify Database State (MANDATORY - AGENT MUST EXECUTE)

- [x] 8.1 Capture the disposable database baseline, run targeted and full suites, verify the state afterwards and write `reports/YYYY-MM-DD-step-8-unit-test-and-db-verification.md`

## 9. Manual Endpoint Testing with curl (MANDATORY - AGENT MUST EXECUTE)

- [x] 9.1 Against a real server on a disposable database with fictitious data and fake model: read, define, rename, change and clear topics, validation and stale errors, refusals, switches off, empty and populated ranking; record commands and responses, and restore the state

## 10. E2E Verification (MANDATORY - AGENT MUST EXECUTE)

- [x] 10.1 Playwright MCP run: upload a bookmarked PDF and one without bookmarks, define topics, student answers, both teacher views, keyboard and 320 px checks; record it and clean up
- [x] 10.2 Add the Playwright Test spec with accessibility scans and run `npm run test:e2e`
- [x] 10.3 Read the bookmarks of representative course PDF files if the owner provides them (no personal data, not committed) and record the coverage, or record that it is unmeasured

## 11. Update Technical Documentation (MANDATORY)

- [x] 11.1 Register the new inference risks in `docs/technical-debt.md`, update `docs/roadmap.md` and the development guide; add lessons if any

## 12. Review and Final Verification

- [x] 12.1 Independent adversarial review by a separate session; record findings, fixes and verdict
- [x] 12.2 Re-run every MUST gate of `docs/base-standards.md` §9 after the last change, `openspec validate --all --strict`, and confirm both switches are false by default

## Workflow follow-up

- Commit, push, Pull Request, merge and deployment only with the owner's authorisation.
- Archive only when `docs/base-standards.md` §9.8 allows it.
