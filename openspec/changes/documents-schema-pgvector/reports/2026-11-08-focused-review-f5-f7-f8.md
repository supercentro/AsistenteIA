# Focused independent review of the corrections F5, F7 and F8

Date: 2026-11-08. Reviewer: the same separate read-only subagent as the group 11 review (type `Explore`, model `opus`, clean of the implementing session's conclusions), resumed for the second pass. It worked on a scratch database `*_test` (dropped afterwards) and on the pytest suite; the development database was only read. It did not edit the repository.

## Pass 1 (HEAD `9c05abb`): PASS WITH GAPS
| ID | Severity | Finding | Disposition |
|---|---|---|---|
| R1 | Major in design, minor in impact today | The helper and the CHECK still disagreed. (a) Values at exact single-precision midpoints: the helper rounded the double itself, but the database rounds the decimal text, so 167 of 3,000 vectors disagreed (84 accepted by the helper and rejected by the database). (b) Summation order: pgvector adds the squares in another order than `math.hypot`; 47 of 240 crafted vectors within about 1e-15 of an edge disagreed. The first test sampled only random doubles and hit neither | **Fixed** (tests first, red): the helper returns the single-precision values it validated and keeps a relative safety margin of `1e-12` at both limits; the guarantee is now one-directional (acceptance implies the CHECK passes). Spec, design (divergence 7), TD-024 and backend standards say so |
| R2 | Minor | `SearchActor.user_id` was not validated and a non-UUID value leaked in a driver error | **Fixed** (tests first, red): same guard and fixed text as `subject_id` |
| R3 | Minor | Weak or misnamed role tests (a "new teacher" test that passed without F7; four tests that pass without F7 because the older checks stop them) | **Fixed**: the new-teacher test now asserts one hit on the own subject and none elsewhere; a teacher-to-student role-change test was added; the regression-only tests remain as regression tests |
| R4 | Acceptable | A `uuid.UUID` subclass with overridden `__str__` is accepted | Accepted: it binds correctly and leaks nothing |

Checked and fine in pass 1: the compiled SQL of both branches (`users` joined inside the EXISTS only, nothing added to the outer FROM, ready-only filter, subject filter, `ORDER BY ..., id` and `LIMIT` unchanged); the plan on 25,012 chunks (student 4.5 to 6.0 ms, teacher 4.1 to 4.4 ms, denied 0.045 ms, the HNSW index still unused as intended); behaviour of legitimate actors; rejection of non-UUID subject ids before any statement; and edge cases of the validator (all `-0.0`, underflow, FLT_MAX overflow, hostile float subclasses).

## Pass 2 (HEAD `a6db5c8`, commits `9e7533b` tests and `a6db5c8` code): PASS
- Fuzzing of the implication "the helper accepts, so the database CHECK accepts the returned vector": 5,000 midpoint vectors (positive and negative, 1 to 384 non-zero components, bands of 3e-12 to 3e-7 around both edges), 3,000 crafted summation-order vectors (1 to 64 large components, exact norm 0 to 2 times the margin inside each edge) and 1,000 denormal mixtures. Database rejections among the vectors accepted by the helper: **0** in every group.
- Mutations (patched in memory by the reviewer): returning the doubles, margin 0 and a missing user id guard are each killed by the expected tests.
- The reviewer's bound for the margin: a sum of 384 exact squares in double precision has a relative error of at most about `383 * 2^-53`, so the margin of `1e-12` leaves about 50 times headroom; the largest error observed was about `1e-15`.
- Remaining minor notes: (1) the guarantee depends on 384 dimensions and on pgvector accumulating in double precision: written down in TD-024; (2) no unit test pins the margin at the lower edge, because no representable single-precision vector has a norm in the margin band above `1e-6` that could be built reliably; the integration summation test covers both edges; accepted. (3) Inputs stored as exactly `1e6` are rejected on the safe side; real embeddings have a norm near 1.

## Verdict
**PASS.** No blocker, major or open minor remains for F5, F7 and F8. Separately, the earlier tests and mutations of this change are listed in `2026-10-28-tdd-evidence.md`.
