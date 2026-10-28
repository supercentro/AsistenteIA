# Tasks

Reports required by `docs/openspec-tasks-mandatory-steps.md` are saved in `openspec/changes/subjects-and-enrollments/reports/` (same convention as the earlier changes). Every group writes its failing tests first and lands its own tests and documentation. Backend only: no frontend code changes. Design decisions are in `design.md` (D1-D9).

## 0. Setup: Create Feature Branch (MANDATORY - FIRST STEP)

- [ ] 0.1 Verify the current branch is `feature/subjects-and-enrollments` (created from the published `main` during planning; `git branch --show-current`) and that it contains no code changes yet
- [ ] 0.2 Confirm `origin/main` contains `93c58da` (technical debt register) so the branch base is the published `main`
- [ ] 0.3 Start the stack (`docker compose up -d db`) and confirm `uv run pytest -q` is green on the starting point

## 1. Shared Validators Extraction (TDD, behaviour-preserving)

- [ ] 1.1 Write unit tests for the new `schemas/validators.py` (control, line-separator and bidi rejection, name trimming and limits, email ASCII/lowercase rules, description rule allowing line breaks) and verify they fail
- [ ] 1.2 Move the validators out of `schemas/auth.py`, keep its public names, and verify the existing auth, CLI and email tests pass unchanged plus the new unit tests; `ruff` and `mypy --strict` clean

## 2. Subjects and Enrollments Persistence and Migration (TDD)

- [ ] 2.1 Write failing migration tests: `0003` upgrade creates both tables, constraints (`unique (teacher_id, name)`, `unique (subject_id, student_id)`), FKs with RESTRICT/CASCADE and the `student_id` index; downgrade removes them; re-upgrade works; the `users` table is untouched
- [ ] 2.2 Write failing repository integration tests for every method in design D2 against PostgreSQL: owner and student scoping, other actor returns nothing, ordering, duplicate name and duplicate enrollment mapped to `ConflictError`, vanished student mapped to not found, delete scoped by owner, cascade of enrollments on subject and student deletion, RESTRICT on teacher deletion
- [ ] 2.3 Add the `Subject` and `Enrollment` models, migration `0003` (with `downgrade`) and `SubjectRepository`/`EnrollmentRepository`; verify 2.1 and 2.2 pass and `alembic upgrade head` / `downgrade -1` work on the development database

## 3. Subject Service and Endpoints (TDD)

- [ ] 3.1 Write failing unit tests for `SubjectService` (repositories mocked: create with trimmed name, list per role, get per role, delete, not-found cases raising one identical `NotFoundError`) and integration tests for every scenario of `subject-management` including 401/403/404/409/422, identical 404 bodies for missing vs inaccessible, and concurrent duplicate creation
- [ ] 3.2 Implement schemas (`SubjectCreate`, `SubjectResponse`), `SubjectService`, dependencies and the `/subjects` routes using `require_teacher` for create/delete and `CurrentUser` for list/get; verify 3.1 passes
- [ ] 3.3 Mutation spot-check the actor filters (remove the owner or enrollment condition in each repository method) and verify a test fails for each; record results in the step 9 report

## 4. Enrollment Service and Endpoints (TDD)

- [ ] 4.1 Write failing unit tests for `EnrollmentService` (unknown email and teacher email raise the same error with no email in message or details, duplicate, vanished student, ownership checked first) and integration tests for every scenario of `subject-enrollments` including role/ownership negatives on all three operations, email case normalisation, 422 without echo, no pre-enrollment, removal of another subject's enrollment, and concurrent duplicate enrollment
- [ ] 4.2 Implement `EnrollmentRequest`/`EnrollmentResponse`, `EnrollmentService` and the enrollment routes (teacher-only, owner-scoped); register the router; verify 4.1 passes
- [ ] 4.3 Add a log test proving emails of rejected enrollments do not reach the application log, and mutation spot-check the owner filter on list and delete

## 5. Review and Update Existing Unit Tests (MANDATORY)

- [ ] 5.1 Re-read every scenario of `subject-management` and `subject-enrollments` and confirm each has an automated test; confirm earlier suites (`user-authentication`, `role-based-access`, `privacy-consent`, health, errors) pass unchanged in intent

## 6. Run Unit Tests and Verify Database State (MANDATORY)

- [ ] 6.1 Capture the pre-test baseline of `asistenteia` and `asistenteia_test` (extensions, tables, `alembic_version`, row counts)
- [ ] 6.2 Run targeted tests per module, then the full suite with coverage (`services/` and `repositories/` at least 80 percent)
- [ ] 6.3 Re-check the same indicators and restore if tests left residue
- [ ] 6.4 Create report `openspec/changes/subjects-and-enrollments/reports/YYYY-MM-DD-step-6-unit-test-and-db-verification.md`

## 7. Manual Endpoint Testing with curl (MANDATORY - AGENT MUST EXECUTE)

- [ ] 7.1 Apply `alembic upgrade head` on the development database, create a teacher with the CLI and register two students, start the backend with a valid `JWT_SECRET`
- [ ] 7.2 Subjects: create (201), duplicate (409), invalid name (422), student create (403), no token (401), list as teacher and as student, get as owner, enrolled student, other teacher (404) and non-enrolled student (404), malformed id (422)
- [ ] 7.3 Enrollments: enroll (201), duplicate (409), unknown email and teacher email (identical 404), invalid email (422), student role (403), other teacher (404), list, remove (204), remove missing (404)
- [ ] 7.4 Delete the subject (204, second delete 404), remove every account and row created for the test, verify the database equals the pre-test state, and document all commands and responses in `reports/YYYY-MM-DD-step-7-curl-verification.md`

## 8. E2E Verification (not applicable to UI; regression only)

- [ ] 8.1 Record in a report that no frontend or user workflow changes in this change, so the Playwright MCP interactive flow is not applicable; run `npm run test:e2e` (smoke suite) and the frontend gates to prove no regression; browser sessions closed

## 9. Update Technical Documentation (MANDATORY)

- [ ] 9.1 Apply the corrections of design D8 to `docs/api-spec.yml` and verify the YAML parses and the implemented OpenAPI matches the documented paths, methods and status codes of subjects and enrollments
- [ ] 9.2 Update `docs/data-model.md` (index on `enrollments.student_id`, listing orders, migration `0003`) and `docs/development_guide.md` only if the migration or command flow changes
- [ ] 9.3 Add TD-016 (listings without pagination) to `docs/technical-debt.md` and mark any resolved item; run the `update-docs` skill checklist; confirm `prompts.md` is untouched and that `readme.md` differs from `main` only by the approved HU-1 correction (403 to 404 in "Intento de carga en asignatura ajena", already applied during planning); other `readme.md` divergences (conversation 403 in HU-4, document endpoints in `docs/api-spec.yml`) stay for changes 6, 7 and 8

## 10. Adversarial Review (required for authorization and data isolation)

- [ ] 10.1 Run the `adversarial-review` skill against this change (isolation between teachers and students, enumeration through status codes, message and log leakage of emails, race conditions on duplicates, cascade and RESTRICT behaviour, validators extraction regressions); save `reports/YYYY-MM-DD-adversarial-review.md`
- [ ] 10.2 Fix findings related to this change (tests first) or record accepted risks in `docs/technical-debt.md` with the user's agreement; re-run affected tests

## 11. Final Verification of MUST Quality Gates (`docs/base-standards.md` section 9)

- [ ] 11.1 Section 9.1 typing and validation: `uv run mypy --strict app tests`; Pydantic schemas on every request and response; no raw `dict` crossing the API layer
- [ ] 11.2 Section 9.2 testing: unit and integration green; every authorization rule has a negative test; no external services called
- [ ] 11.3 Section 9.3 and 9.4 security and isolation: reads scoped by actor in repositories, no secrets in repo or logs, dependencies unchanged, `pip-audit` clean
- [ ] 11.4 Section 9.6 lint and format: `ruff check`, `ruff format --check`; frontend lint, format, typecheck and tests still green
- [ ] 11.5 Section 9.7 migrations: `0003` upgrade and downgrade on a clean database; `docker compose up --build` still starts the stack following the guide
- [ ] 11.6 Section 9.8 documentation updated in this change; conventional commits prepared (commits, push and Pull Request only when the user asks)
- [ ] 11.7 Run `openspec validate subjects-and-enrollments --strict` and tick this change's tasks only after all items above pass

## Workflow follow-up

- Open the Pull Request from `feature/subjects-and-enrollments` to `main` when the user requests it and confirm the CI run is green.
- Archive with `/opsx:archive` after review and merge (the adversarial review in group 10 is a prerequisite).
- Ask the user whether to record notable AI usage in `prompts.md`.
