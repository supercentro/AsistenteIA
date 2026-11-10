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

## Group 4: API contract and generated types

Failing-first runs (the previous contract: 11 failed, 3 passed, 1 xfailed; the real application without the xfail marker: failed on the missing document routes; the stale generated types: `check:api-types` failed), the passing run (14 passed, 1 xfailed) and seven mutations (all detected) are in `2026-11-09-group-4-api-contract.md`. Deviation: the comparison against the real application is `xfail(strict=True)` until group 9, where the routes exist.

## Group 5: embedder, normaliser and chunker

Failing-first runs (three collection errors), the passing runs (134 unit tests and 16 real-model tests in the worker image) and 25 mutation checks are in `2026-11-09-group-5-embedder-normalizer-chunker.md`. Deviation: none; the tests were committed before the modules, and the weak assertions found by the mutations were strengthened.

## Group 6 (loaders and isolated PDF child)
Failing run before the code: 4 collection errors, `ModuleNotFoundError: No module named 'app.rag.loaders'` (commit `71d24ef`). After: 195 passed, 1 skipped in the Linux worker image. 56 mutations, four first-pass survivors resolved (two by new tests, one by removing a redundant branch, one accepted as equivalent). Details: `2026-11-09-group-6-loaders-and-pdf-child.md`.

## Group 7 (repositories and queue)
Failing run before the code: 4 collection errors, `ModuleNotFoundError: No module named 'app.repositories.ingestion_job_repository'` (commit `8723900`). After: 139 passed against PostgreSQL with real concurrency. About 50 mutations; 15 first-pass survivors closed by new tests, the single-check fence redundancy accepted as equivalent. Details: `2026-11-10-group-7-repositories-and-queue.md`.

## Group 8 (ingestion service, heartbeat and worker)
Failing run before the code: 5 collection errors, `ModuleNotFoundError: No module named 'app.services.ingestion_service'` (commit `ca3673e`); the engine option tests failed first with `TypeError: unexpected keyword argument 'statement_timeout_seconds'`. After: 85 tests of the group pass in the Linux image against PostgreSQL. 45 mutations in two passes; 12 first-pass survivors closed with new tests; 2 accepted as equivalent. Details and deviations (including the loss of the host virtual environment to an Application Control policy and the move to the Linux image) are in `2026-11-10-group-8-service-and-worker.md`.

## Group 9: endpoints, upload guard and leak tests
- Failing run before the implementation (commit `cd84041`): `102 failed, 17 passed, 18 errors`; collection errors for `app.services.upload_inspection`, `app.core.upload_guard` and `app.services.document_service`; the contract test failed without its `xfail`.
- After the implementation: 1645 passed, 0 xfailed in the full Linux run. Mutations: 56, all killed except two accepted equivalents. Details in `2026-11-10-group-9-endpoints-and-upload-guard.md`.

## Group 10: real-server and process tests
- Red first: the deterministic UploadSlots interleaving tests failed with TypeError before the seam existed (3 failed), then passed. The real-server and process tests verify behaviour of groups 8 and 9 and are proved by mutation (8 mutations, 2 first-pass survivors closed, all killed). Full Linux run: 1684 passed. See 2026-11-10-step-10-real-server-verification.md.

## Group 11: review of the existing tests
- 6 existing test files were modified by the change (reasons in 2026-11-10-regression-review.md); 11 new tests of the deployment files and 4 of the test seams were added for gaps found in the review. They test existing behaviour (green first run) and are proved by 15 mutations of the files themselves, all killed. Full Linux run: 1702 passed.
