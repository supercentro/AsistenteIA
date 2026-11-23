# Demonstration of the inference vectors (part A, tasks 1.1 to 2.3)

Date: 2026-11-23. Fictitious data only. No Gemini call (fake LLM and fake embedder). **No mitigation, no change of production logic, contract, model or default.** Both switches stay off: the integration tests build a test application with `teacher_activity_enabled=True`; nothing else enables it.

## How to read the tests

| Name pattern | Meaning of PASS |
|---|---|
| `test_v*_is_reproduced*` | **The vulnerability is confirmed** (the leak is present) |
| `test_v*_property_holds*` (`xfail(strict=True)`) | The property a mitigation must give. It **fails today** (XFAIL). When a mitigation makes it pass, strict mode raises an error so that the marker and TD-069 are reviewed |
| `test_v4_characterisation*`, `test_v3_the_weekly_cells*`, `test_v1_does_not_leak_below*` | A documented limit or a protection that works today |

Files: `backend/tests/unit/test_activity_inference_vectors.py` (in memory, no database) and `backend/tests/integration/test_activity_inference_f8.py` (public API and real SQL).

## Results

| Vector | Layer | Result | Verdict |
|---|---|---|---|
| **V1** unenrolment differencing (F1) | service, in memory | six students (2, 2, 2, 2, 2, 3): cell 13 and 6 active; after the removal of the last one: cell 10 and 5 active; difference 3 = exactly that student's questions | **Confirmed** |
| V1 | real routes and SQL | the same figures through `DELETE /subjects/{id}/enrollments/{student}` and `GET /activity` | **Confirmed** |
| V1 control | service | a class of exactly 5: removing one student withholds every figure | protection works (no leak below N) |
| **V2 / F8** padding | service, in memory | 4 controlled accounts x 3 questions + 1 real x 2: cell 14, 5 active; 14 - 12 = 2 recovered. A real student with 0 questions: everything withheld; with 1: shown | arithmetic **confirmed** |
| **F8** | end to end, disposable database | public `POST /auth/register` (role student) for 4 accounts, `POST /subjects/{id}/enrollments` by email, consent and 3 `POST /chat` each, plus one real student; `GET /activity` shows cell 14 and `active_students` 5, so 2 recovered; with 0 real questions every figure is null, and one question makes it 5 | **CONFIRMED** end to end (status of F8: confirmed, see below) |
| **V3** window differencing | service and real SQL | windows of weeks 1-12 and 2-13: `active_students` 6 -> 5; `no_material_rate` 0.016 -> 0.0 (the week that left held the only answer without material) | **Confirmed**; both leaking figures are window-wide |
| V3 protection | service | the weekly cells of the 11 weeks both windows contain are identical (5) | protection works (weekly cells do not move) |
| **V4** heavy contributor (F6) | service | 50, 1, 1, 1, 1 questions: shown cell 54; one student is 93 % of it | **Characterised** (a disclosure of dominance, not a recovery) |
| Erasure invariant | real routes and SQL | `DELETE /users/me/conversations` and the deletion of an account (cascade) lower the next result, remove the enrolment and leave no row about the student | **Holds today**; must keep holding |

## Failing run before any mitigation (task 1.6, TDD evidence)

Command: `uv run --no-sync python -m pytest tests/unit/test_activity_inference_vectors.py -q --runxfail`. The three property tests fail:

- V1: `assert (13 - 10) != 3`
- V2: `assert (14 - 12) != 2`
- V3: `assert 6 == 5` (`active_students` of the two windows)

Normal run: 7 passed, 3 xfailed. Integration module on a disposable database: 7 passed.

## Mutation checks (task 2.2)

The service was changed temporarily and restored (`git diff` of `backend/app` is empty).

1. **Every cell withheld**: the leak tests fail (V1, V2, V3 weekly, V4); the property tests keep failing for another reason, so this mutant only shows that the tests depend on the figures.
2. **Counts rounded down to a multiple of 5** (a candidate mitigation, not adopted): `test_v1_property_holds` **XPASS (strict)**, which raises an error as designed, and `test_v1_is_reproduced` fails. So the pair distinguishes a leaking system from a mitigated one.

Not covered: no mutant makes the V2 and V3 properties pass; they need an identity control and a window rule that the owner has not approved.

## F8 verdict (task 2.3, spec requirement "F8 stays unconfirmed...")

**F8 is confirmed end to end** in the test stack: nothing in the application stops a teacher from creating student accounts through public registration, enrolling them by email, making them ask in the teacher's subject and subtracting their questions. Severity proposed: **Major**, open. It is the stronger form of F1 because it needs no unenrolment, and N = 5 does not stop it.

## Limits of this evidence

- **Not shown**: that a real institution lacks an outside control (for example only institutional email domains being allowed to register, or an approval of accounts). The test shows the application, not the policy around it.
- Not shown: real latency, volume or rate limits; the chat rate limit (20 per minute) was not reached with 3 questions per account.
- The teacher account was inserted directly, as in the other integration tests; the vector concerns the accounts the teacher controls, not the teacher's.
- The in-memory repository applies the window and enrolment filters by construction; the SQL layer is shown by the integration tests.
- V3 shows leaks of the window-wide figures when the window moves by one week; with the default window this happens by waiting for Monday, with no parameter.
- Account deletion has no API route; its erasure was exercised by deleting the row (cascade), as stated in the test.
- Isolation: a throwaway `pgvector/pgvector:0.8.7-pg15` container on `127.0.0.1:55433`, with its own database, removed afterwards. The development database and its server were not touched.
- The four failures of `tests/unit` (migration and worker settings) are the known ones of this host; 1709 passed.

## Result for the next step

All of V1, V2 (F8), V3 are confirmed and V4 is characterised. The mitigations of part B stay **blocked** until the owner approves each option (design D-P3 to D-P8).
