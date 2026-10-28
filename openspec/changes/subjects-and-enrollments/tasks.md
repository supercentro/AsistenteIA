# Tasks

Reports required by `docs/openspec-tasks-mandatory-steps.md` are saved in `openspec/changes/subjects-and-enrollments/reports/` (same convention as the earlier changes). Every group writes its failing tests first and lands its own tests and documentation. Backend only: no frontend code changes. Design decisions are in `design.md` (D1-D10). The lessons in `docs/lessons-learned.md` and the rules of `docs/base-standards.md` sections 9.2, 9.7 and 9.8 apply to this change.

## 0. Setup: Create Feature Branch (MANDATORY - FIRST STEP)

- [x] 0.1 Verify the current branch is `feature/subjects-and-enrollments` (created from the published `main` during planning; `git branch --show-current`) and that it contains no code changes yet
- [x] 0.2 Confirm the branch is rebased on `origin/main` at or after `480201f` (lessons learned and standards, PR #3) so the base is the published `main` (`git merge-base --is-ancestor 480201f HEAD`)
- [x] 0.3 Start the stack (`docker compose up -d db`) and confirm `uv run pytest -q` is green on the starting point
- [x] 0.4 Create `reports/YYYY-MM-DD-ai-usage-notes.md` and keep it updated during the apply with the literal user prompts, decisions and AI findings of this change (source for the later `prompts.md` proposal)

## 1. Shared Validators Extraction (TDD, behaviour-preserving)

- [x] 1.1 Write unit tests for the new `schemas/validators.py` (control, line-separator and bidi rejection, name trimming and limits, email ASCII/lowercase rules, description rule allowing line breaks), run them and record the failing run (command and failure summary) in `reports/YYYY-MM-DD-tdd-evidence.md`
- [x] 1.2 Move the validators out of `schemas/auth.py`, keep its public names, and verify the existing auth, CLI and email tests pass unchanged plus the new unit tests; `ruff` and `mypy --strict` clean

## 2. Subjects and Enrollments Persistence and Migration (TDD)

- [x] 2.1 Write failing migration tests: `0003` upgrade creates both tables, constraints (`unique (teacher_id, name)`, `unique (subject_id, student_id)`), FKs with RESTRICT/CASCADE and the `student_id` index; downgrade removes them; re-upgrade works; the `users` table is untouched; record the failing run in the TDD evidence report
- [x] 2.2 Write failing repository integration tests for every method in design D2 against PostgreSQL: owner and student scoping, other actor returns nothing, ordering, duplicate name and duplicate enrollment mapped to `ConflictError`, vanished student mapped to not found, delete scoped by owner, cascade of enrollments on subject and student deletion, RESTRICT on teacher deletion; record the failing run in the TDD evidence report
- [x] 2.3 Add the `Subject` and `Enrollment` models, migration `0003` (with `downgrade`) and `SubjectRepository`/`EnrollmentRepository`; verify 2.1 and 2.2 pass, `alembic upgrade head` / `downgrade -1` work on the development database, and `alembic check` reports no drift on the development and test databases

## 3. Subject Service and Endpoints (TDD)

- [x] 3.1 Write failing unit tests for `SubjectService` (repositories mocked: create with trimmed name, list per role, get per role, delete, not-found cases raising one identical `NotFoundError`) and integration tests for every scenario of `subject-management` including 401/403/404/409/422, identical 404 bodies for missing vs inaccessible, concurrent duplicate creation (N parallel identical requests, exactly one 201 and the rest 409), and a parametrized never-500 probe over name, description and path ids (NUL, lone surrogates, bidi and line separators, oversize, malformed UUIDs); record the failing run in the TDD evidence report
- [x] 3.2 Implement schemas (`SubjectCreate`, `SubjectResponse`), `SubjectService`, dependencies and the `/subjects` routes using `require_teacher` for create/delete and `CurrentUser` for list/get; verify 3.1 passes
- [x] 3.3 Mutation spot-check the actor filters (remove the owner or enrollment condition in each repository method) and verify a test fails for each; record results in the step 6 report

## 4. Enrollment Service and Endpoints (TDD)

- [x] 4.1 Write failing unit tests for `EnrollmentService` (unknown email and teacher email raise the same error with no email in message or details, duplicate, vanished student, ownership checked first) and integration tests for every scenario of `subject-enrollments` including role/ownership negatives on all three operations, email case normalisation, 422 without echo, odd characters in the email and malformed path ids never producing 500, no pre-enrollment, removal of another subject's enrollment, and concurrent duplicate enrollment (N parallel identical requests, exactly one 201, the rest 409, one row); record the failing run in the TDD evidence report
- [x] 4.2 Implement `EnrollmentRequest`/`EnrollmentResponse`, `EnrollmentService` and the enrollment routes (teacher-only, owner-scoped); register the router; verify 4.1 passes
- [x] 4.3 Add log tests: emails of rejected enrollments do not reach the application log, and a statement-level database error forced during subject creation and during enrollment (the email and name travel as SQL parameters) answers the generic error while the captured log contains no email, name or parameter values; mutation spot-check the owner filter on list and delete

## 5. Review and Update Existing Unit Tests (MANDATORY)

- [x] 5.1 Re-read every scenario of `subject-management` and `subject-enrollments` and confirm each has an automated test; confirm earlier suites (`user-authentication`, `role-based-access`, `privacy-consent`, health, errors) pass unchanged in intent; list in the TDD evidence report every deviation from test-first order with its justification and the mutation check that compensated it (or state that there were none)

## 6. Run Unit Tests and Verify Database State (MANDATORY)

- [x] 6.1 Capture the pre-test baseline of `asistenteia` and `asistenteia_test` (extensions, tables, `alembic_version`, row counts)
- [x] 6.2 Run targeted tests per module, then the full suite with coverage (`services/` and `repositories/` at least 80 percent)
- [x] 6.3 Re-check the same indicators and restore if tests left residue
- [x] 6.4 Create report `openspec/changes/subjects-and-enrollments/reports/YYYY-MM-DD-step-6-unit-test-and-db-verification.md`

## 7. Manual Endpoint Testing with curl (MANDATORY - AGENT MUST EXECUTE)

- [x] 7.1 Apply `alembic upgrade head` on the development database, create a teacher with the CLI and register two students, start the backend with a valid `JWT_SECRET`
- [x] 7.2 Subjects: create (201), duplicate (409), invalid name (422), student create (403), no token (401), list as teacher and as student, get as owner, enrolled student, other teacher (404) and non-enrolled student (404), malformed id (422)
- [x] 7.3 Enrollments: enroll (201), duplicate (409), unknown email and teacher email (identical 404), invalid email (422), student role (403), other teacher (404), list, remove (204), remove missing (404)
- [x] 7.4 Delete the subject (204, second delete 404), remove every account and row created for the test, verify the database equals the pre-test state, and document all commands and responses in `reports/YYYY-MM-DD-step-7-curl-verification.md`

## 8. E2E Verification (not applicable to UI; regression only)

- [x] 8.1 Record in a report that no frontend or user workflow changes in this change, so the Playwright MCP interactive flow is not applicable; run `npm run test:e2e` (smoke suite) and the frontend gates to prove no regression; browser sessions closed

## 9. Update Technical Documentation (MANDATORY)

- [x] 9.1 Apply the corrections of design D8 to `docs/api-spec.yml` and verify the YAML parses
- [x] 9.2 Update `docs/data-model.md` (index on `enrollments.student_id`, listing orders, migration `0003`) and `docs/development_guide.md` only if the migration or command flow changes
- [x] 9.3 Add TD-016 (listings without pagination) and TD-017 (a teacher can tell registered students from other emails; accepted MVP risk) to `docs/technical-debt.md`, mark any resolved item, and keep the design's risk text pointing to those IDs instead of restating them
- [x] 9.4 Invoke the `update-docs` skill itself (not only its checklist), apply what it reports, and note the invocation in the AI usage notes; confirm `prompts.md` is untouched and that `readme.md` differs from `main` only by the approved HU-1 correction (403 to 404 in "Intento de carga en asignatura ajena", applied during planning); other `readme.md` divergences (conversation 403 in HU-4, document endpoints in `docs/api-spec.yml`) stay for changes 6, 7 and 8
- [x] 9.5 Write a reconciliation table in `reports/YYYY-MM-DD-contract-reconciliation.md` comparing limits (name 150, description 2000, email 255), required fields, nullability, listing orders and the status code of every operation across the delta specs, `docs/api-spec.yml`, `docs/data-model.md`, the Pydantic schemas, the migration columns and the OpenAPI generated by the app (`app.openapi()`); fix or report every mismatch

## 10. Adversarial Review (required for authorization and data isolation)

- [ ] 10.1 Run an independent adversarial review with the `adversarial-review` skill, executed by a separate subagent or a clean-context session (not the implementing session), read-only on the repository and probing only the isolated test database or the live stack; cover isolation between teachers and students, enumeration through status codes, message and log leakage of emails, race conditions on duplicates, cascade and RESTRICT behaviour, validators extraction regressions and odd inputs; save `reports/YYYY-MM-DD-independent-review.md` with findings, severity, fixes and a final verdict
- [ ] 10.2 Fix findings related to this change (tests first) and re-run affected tests; the change is not closed while a blocker or major finding is open; record accepted risks as rows in `docs/technical-debt.md` with the user's agreement and, only for relevant findings or process deviations, append a lesson to `docs/lessons-learned.md`

## 11. Final Verification of MUST Quality Gates (`docs/base-standards.md` section 9)

- [ ] 11.1 Section 9.1 typing and validation: `uv run mypy --strict app tests`; Pydantic schemas on every request and response; no raw `dict` crossing the API layer
- [ ] 11.2 Section 9.2 testing: unit and integration green; every authorization rule has a negative test; no external services called; the TDD evidence report is complete; state in the final report why real-server tests do not apply (this change adds no behaviour that depends on Uvicorn, headers, proxies or transport)
- [ ] 11.3 Section 9.3 and 9.4 security and isolation: reads scoped by actor in repositories, no secrets in repo or logs, dependencies unchanged, `pip-audit` clean
- [ ] 11.4 Section 9.6 lint and format: `ruff check`, `ruff format --check`; frontend lint, format, typecheck and tests still green
- [ ] 11.5 Section 9.7 migrations: `0003` upgrade and downgrade on a clean database, `alembic check` clean, `0003` not edited after its first commit; `docker compose up --build` still starts the stack following the guide
- [ ] 11.6 Section 9.8 documentation and traceability updated in this change; conventional commits prepared (commits, push and Pull Request only when the user asks)
- [ ] 11.7 Run `openspec validate subjects-and-enrollments --strict` and tick this change's tasks only after all items above pass

## Workflow follow-up

- Open the Pull Request from `feature/subjects-and-enrollments` to `main` when the user requests it and confirm the CI run is green.
- Archive with `/opsx:archive` after review and merge (the independent adversarial review in group 10 is a prerequisite).
- Propose to the user the `prompts.md` entry for this change, built from the AI usage notes (literal fragments versus summaries); do not edit `prompts.md` without approval.
