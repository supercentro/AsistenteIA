# Design

## Context

State after changes 1 and 2: `users` table and `User`/`UserRole` model, `CurrentUser`, `require_teacher`/`require_student` guards (`api/deps.py`), `AppError` hierarchy (`NotFoundError`, `ConflictError`, `ForbiddenError` already exist), one transaction per request in `get_db`, `UserRepository.add` using a savepoint to turn unique violations into `ConflictError`, shared `Name`/`Email` validators currently living in `schemas/auth.py`, Alembic head `0002`. The canonical contract is `docs/api-spec.yml` (subjects and enrollments paths already drafted) and `docs/data-model.md` (`subjects`, `enrollments`). See `proposal.md` for motivation and the user-approved decisions D1-D12 summarised there. Layering and security rules: `docs/backend-standards.md`, quality gates `docs/base-standards.md` section 9 (isolation enforced in repositories).

## Goals / Non-Goals

**Goals:**
- Persist subjects and enrollments with database-level integrity (uniqueness, cascades, RESTRICT).
- Enforce actor scoping inside the repository layer so a router bug cannot leak another user's subject.
- Keep existence indistinguishable from inaccessibility (identical 404 body) and keep emails out of error messages.

**Non-Goals:**
- Pagination, rename, self-enrollment, bulk or pre-enrollment, user deletion, documents, conversations, chat gating, frontend, new rate limits.
- Enforcing the student/teacher role of `subjects.teacher_id` and `enrollments.student_id` in the database (the data model assigns that to the service layer).

## Decisions

### D1. Check order: role first (403), then ownership/visibility (404)
Routes restricted to teachers depend on `require_teacher`, so a student always gets 403 whether or not the subject exists (no existence signal). `GET /subjects` and `GET /subjects/{id}` accept both roles and branch on `user.role` in the service. Alternative (404 for everything unauthorised, including wrong role) rejected: it contradicts the approved "403 for wrong role" and the existing `role-based-access` spec.

### D2. Repository API takes the actor; there is no unscoped read for request paths
`SubjectRepository`: `add(subject)`, `list_for_teacher(teacher_id)`, `list_for_student(student_id)` (join `enrollments`), `get_for_teacher(subject_id, teacher_id)`, `get_for_student(subject_id, student_id)`, `delete_for_teacher(subject_id, teacher_id) -> bool` (a single `DELETE ... WHERE id = :id AND teacher_id = :teacher` and `rowcount`). `EnrollmentRepository`: `list_for_teacher_subject(subject_id, teacher_id)` joins `subjects` on `teacher_id` and `users` for the email, `add(subject_id, student_id)`, `delete_for_teacher_subject(subject_id, teacher_id, student_id) -> bool` (via a subquery on `subjects.teacher_id`). A service never receives rows it did not obtain through an actor-scoped method. Alternative (load by id, compare owner in the service) rejected: it makes isolation depend on every caller remembering the comparison (docs/base-standards.md section 9.4).

### D3. Enrollment flow
`EnrollmentService.enroll(teacher, subject_id, email)`: (1) `get_for_teacher` or 404; (2) `UserRepository.get_by_email`; if missing or `role != student` raise the same `NotFoundError("Student not found")` with no `details`; (3) insert inside a savepoint: `UniqueViolation` becomes `ConflictError("Student is already enrolled")`, `ForeignKeyViolation` (student removed concurrently) becomes the same 404 as step 2. The success response carries `student_email` from the already loaded user. The submitted email never appears in a message, log line or `details`. Identical status, code and message for unknown and non-student emails keeps the two cases indistinguishable; timing differences are negligible and accepted.

### D4. Migration `0003` and models
`subjects`: `id uuid` default `gen_random_uuid()`, `name varchar(150) not null`, `description text null`, `teacher_id uuid not null` FK to `users` `ON DELETE RESTRICT`, `created_at timestamptz` default `now()`, unique `(teacher_id, name)`. `enrollments`: `id`, `subject_id` FK `ON DELETE CASCADE`, `student_id` FK `ON DELETE CASCADE`, `created_at`, unique `(subject_id, student_id)`, plus an index on `student_id` for the student listing and for erasure (change 11). Constraint names follow the existing `NAMING_CONVENTION`. `downgrade` drops `enrollments` then `subjects`. The unique `(teacher_id, name)` index also serves the teacher listing. Deletes rely on database cascades (`passive_deletes`), so later tables (`documents`, `conversations`) add their own `ON DELETE CASCADE` FKs in changes 5 and 8 without changing this code. This is a data-model change inside the already approved model, so it is not flagged as architecture-affecting.

### D5. Shared validators in a neutral module
Move `ensure_no_control_characters`, the bidi set, the name type factory and `Email` from `schemas/auth.py` to `schemas/validators.py`; `schemas/auth.py` imports them and keeps its public names. Subject name is `Name` with a 150 limit; the description uses a separate control-character check that allows `\n`, `\r` and `\t`. No behaviour of registration or login changes; the existing tests are the safety net. Alternative (subject schemas import from `schemas/auth.py`) rejected as indebted coupling, as requested.

### D6. Responses and schemas
`SubjectResponse` (`id`, `name`, `description` nullable, `teacher_id`, `created_at`) and `EnrollmentResponse` (`id`, `subject_id`, `student_id`, `student_email`, `created_at`) are explicit Pydantic models; no user fields beyond id and email are exposed, and the student's own `GET /subjects/{id}` returns the same `SubjectResponse` (the teacher id is already public in the contract). Path ids are `uuid.UUID`, so malformed ids produce the standard 422.

### D7. Listings are plain, ordered arrays
Subjects ordered by `name, id`; enrollments by `created_at, id`; no `limit/offset`. Volumes in the MVP are small and the contract returns arrays. Registered as TD-016 so pagination can be added with a contract change later.

### D8. Contract corrections (docs/api-spec.yml, docs/data-model.md)
- Subjects: `POST` gains 409; `DELETE` keeps 403 (role) and 404 (not owner); `GET` documents 404 for another teacher's or a non-enrolled subject.
- Enrollments: add 401 to all three operations, 422 to `POST` and to the path ids, 409 stays, 403 means wrong role only, 404 covers: subject not owned or missing, unknown or non-student email, missing enrollment.
- `student_email` gains `maxLength: 255` and the ASCII note; `SubjectCreate.name` gets `minLength: 1`; `description` is nullable.
- Shared response descriptions: `Forbidden` becomes "wrong role (and, for chat, not enrolled or consent missing)"; `NotFound` mentions other users' resources.
- `docs/data-model.md`: add the `enrollments.student_id` index and the listing orders; no new error codes.

### D9. Tests
Integration tests (real PostgreSQL) cover every spec scenario, including a negative test per authorization rule (student on teacher routes, other teacher on get/delete/list/enroll/unenroll, non-enrolled student), identical 404 bodies for missing vs inaccessible, cascade and RESTRICT behaviour, and concurrent duplicate creation and enrollment (N parallel identical requests against separate sessions: exactly one 201, the rest 409, never 500, exactly one row, and the 409 body is the standard `CONFLICT` error). Unit tests cover the service branches with repository doubles and the shared validators. Mutation spot-checks on the actor filters, as done in change 2. Log tests force a statement-level database error on subject creation and enrollment and assert the captured log holds no email, name or parameter value (the engine already hides parameters; this proves it for the new endpoints). Parametrized never-500 probes cover odd text and malformed ids.

### D10. Verification controls from the lessons learned
Applied through `tasks.md`, not through new code: TDD evidence report with the failing run of each group and any deviation (L01, `docs/base-standards.md` 9.2); an independent adversarial review by a separate subagent or clean-context session with no closure while a blocker or major is open (L02, 9.8); `alembic check` after `0003` and no edits to it once committed (L07, 9.7); a contract reconciliation report across specs, `docs/api-spec.yml`, `docs/data-model.md`, schemas, migration and generated OpenAPI (L06, 9.8); explicit `update-docs` invocation, AI usage notes and register updates (L08, L09). Real-server tests (L03) do not apply because this change adds no behaviour that depends on Uvicorn, headers, proxies or transport; the final report states that.

## Risks / Trade-offs

- [A teacher can learn whether an email is a registered student: 201 vs 404] → accepted residual risk of the MVP (user decision, registered as TD-017), inherent to enrollment by email (approved D3/D4); teachers are created only by an administrator; the response shows nothing else about the account and a rate limit would be a separate change if abuse appears.
- [Case-sensitive subject names allow "Algebra" and "algebra" for the same teacher] → matches `docs/data-model.md` (`unique (teacher_id, name)`); a case-insensitive rule would be a contract change and is not proposed.
- [Unpaginated lists grow without bound] → bounded by MVP scale; registered as TD-016.
- [Deleting a subject only cascades to enrollments today] → later FKs declare `ON DELETE CASCADE` in their own migrations and add a cascade test each (changes 5 and 8); this change leaves nothing to rework.
- [Role of `teacher_id`/`student_id` not enforced by the database] → services only link a teacher id from `CurrentUser` and a student found with `role = student`; tests assert both.
- [Local databases without `0003`] → `alembic upgrade head`; documented in `docs/development_guide.md` if the procedure changes.

## Migration Plan

`alembic upgrade head` creates both tables; rollback with `alembic downgrade -1`. No data backfill. The test database is migrated by the existing session fixture and the migration test is extended (upgrade, downgrade, re-upgrade).

## Open Questions

None blocking. Deferred without effect on specs or tasks: whether `GET /subjects` should later accept filters, and the `readme.md` HU-1 wording (needs the user's approval, reported in `proposal.md`).
