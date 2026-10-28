# Proposal

## Why

Teachers cannot yet organise material and students cannot be linked to a course: every later feature (documents, chat, history) is scoped by subject and authorised by enrollment. This change adds the subject and enrollment foundation on top of the authentication and roles already merged (change 3 of 13 in the approved plan).

## What Changes

- New tables `subjects` and `enrollments` (migration `0003`, with `downgrade`) as defined in `docs/data-model.md`.
- Subject endpoints from `docs/api-spec.yml`: `GET/POST /subjects`, `GET/DELETE /subjects/{subject_id}`.
- Enrollment endpoints from `docs/api-spec.yml`, exclusive to the owning teacher: `GET/POST /subjects/{subject_id}/enrollments`, `DELETE /subjects/{subject_id}/enrollments/{student_id}`.
- Authorization and error semantics approved by the user:
  - Another teacher's subject, or a subject the student is not enrolled in, answers **404**; a wrong role answers **403**.
  - An unknown email and the email of a non-student user answer the same **404**; a duplicate enrollment and a duplicate subject name per teacher answer **409**; removing a missing enrollment answers **404**.
- Contract corrections in `docs/api-spec.yml` (403 for non-owners becomes 404, missing 401/422 responses, field limits, nullable description) and details in `docs/data-model.md`.
- Behaviour-preserving extraction of the shared name and email validators into a neutral schema module, so subject schemas reuse them without importing `schemas/auth.py`.
- Technical debt registered in `docs/technical-debt.md`: TD-016 (unpaginated listings) and TD-017 (accepted risk: enrollment by email lets a teacher tell registered students from other emails).
- Verification controls from `docs/lessons-learned.md` and `docs/base-standards.md` (TDD evidence, independent adversarial review, `alembic check`, contract reconciliation, explicit `update-docs` and AI usage notes); they add tasks and test scenarios only, no functional scope.

Out of scope (not added): pagination, update or rename of subjects, self-enrollment, bulk or pre-enrollment of unregistered emails, student or teacher account deletion, documents, conversations, chat enforcement, any frontend screen (change 4 and later), new rate limits.

**BREAKING**: none for implemented code. The documented status codes of not-yet-implemented subject and enrollment endpoints change in `docs/api-spec.yml`.

## Capabilities

### New Capabilities
- `subject-management`: creation, listing, retrieval and deletion of subjects, with visibility rules per role and per owner.
- `subject-enrollments`: teacher-managed enrollment of students by email in a subject, listing and removal, and the isolation rules around them.

### Modified Capabilities
<!-- None: the existing role guards and error body requirements are reused unchanged. -->

## Impact

- **Authorization / isolation**: new owner-scoped and enrollment-scoped queries enforced in the repository layer (`docs/base-standards.md` section 9.4); every rule has a negative test.
- **Personal data**: a teacher sees the email of students enrolled in their own subjects only; enrollment rows cascade when a user is erased (needed later by change 11).
- **External services**: none.
- **Code**: `backend/app/{models,repositories,services,schemas,api/v1/endpoints}`, `alembic/versions/0003_*`, router registration, test helpers.
- **Docs**: `docs/api-spec.yml`, `docs/data-model.md`, `docs/development_guide.md` (migration note), `docs/technical-debt.md`.
- **`readme.md` correction (approved by the user)**: the HU-1 scenario "Intento de carga en asignatura ajena" said 403 while `readme.md` section 3 and the approved decision say another user's resources answer 404; it was corrected to 404, and nothing else in `readme.md` changes. The document endpoints in `docs/api-spec.yml` and other divergences (e.g. the HU-4 "conversación ajena" 403) are aligned in their own changes (6, 7 and 8).
- **No new permissions**: `GET /subjects` for a student returns only subjects with an enrollment of that student, and `GET /subjects/{id}` follows the same rule; no student route reads other users, enrollments or teachers' data.
