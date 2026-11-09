# TDD evidence

One section per group. Each records the failing run before the implementation, the passing run after it, the deviations and the mutation checks.

## Group 2: configuration, dependencies and images

### 2.1 Settings (`app/core/config.py`, `app/core/cpu_quota.py`)

Tests written first: `backend/tests/unit/test_ingestion_settings.py` (69 cases) and `backend/tests/unit/test_cpu_quota.py` (14 cases).

- **Failing run before the implementation** (`uv run --frozen pytest tests/unit/test_ingestion_settings.py tests/unit/test_cpu_quota.py -q`):
  - `test_cpu_quota.py`: collection error, `ImportError: cannot import name 'cpu_quota' from 'app.core'`.
  - `test_ingestion_settings.py`: **69 failed** (the settings and variables did not exist, and invalid values were not rejected).
- **Passing run after the implementation**: 83 passed. One test of mine was wrong (a deadline of 30 s is below the default lease of 120 s, which the new cross-field rule rightly rejects); I corrected the test value (300 s), not the rule.
- **Mutation checks** (temporary edits of `config.py`, reverted afterwards; final run 69 passed):
  - disabling the fake-embedder rule: 3 tests failed (the rejection tests for development and production, and `test_fake_embedder_is_never_accepted_in_production_even_with_the_flag`);
  - disabling the "deadline greater than lease" rule: 1 test failed (`test_inconsistent_combinations_are_rejected[INGESTION_JOB_DEADLINE_SECONDS-...]`).
- **Not mutation-checked**: the numeric bounds (each has a rejected-value test, which fails if the bound is removed) and the quota arithmetic (14 tests cover cgroup v2 and v1, "max", fractions, caps and invalid content).

### 2.2 and 2.3 Dependencies, lock, images and CI

Configuration and build files with no unit-test surface; the evidence is the verification run recorded in `2026-11-08-group-2-dependencies-and-images.md`. **Deviation**: no failing-first test exists for these tasks, compensated by the checks listed there (the lock diff is additive, the lock holds no CUDA packages, the `api` image does not contain `torch`, `pypdf` or the model, the `worker` image loads the model offline as a non-root user and detects the container CPU quota, and the full suite passes).

## Group 3: migration 0005 and models

Failing-first runs, the passing runs and eight mutation checks of the migration are recorded in `2026-11-09-group-3-migration-0005.md`. Summary: the catalogue and integrity tests failed at collection (`ModuleNotFoundError: app.models.ingestion`), the catalog tests failed 8 of 12 before the migration, and every mutation of the migration (lease check, attempts check, uniqueness, cascade, error code check, partial index, downgrade, column width) was detected. Deviation: none.
