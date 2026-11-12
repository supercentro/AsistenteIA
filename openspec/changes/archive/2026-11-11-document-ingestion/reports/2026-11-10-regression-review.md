# Group 11: review of the existing tests

Branch `feature/document-ingestion`. Task 11.1. No later group; migration `0005` was not applied to the development database (`asistenteia` stays at `0004`; `asistenteia_test` ends without tables).

## Method
1. Listed every file of `backend/tests`, `.github`, `docker-compose.yml`, `backend/Dockerfile`, `backend/.env.example` and `backend/pyproject.toml` that this change modified or added (`git diff --name-status main...HEAD`): 43 test files added, 6 existing test files modified.
2. Searched the existing tests for everything the change touches: the new column `documents.error_code`, the table `ingestion_jobs`, revision ids (`0004`, `0005`), settings and `.env.example`, Compose, the Dockerfile and CI.
3. For each match decided: still correct as it is, updated (with the reason), or missing a test (a new test was added).
4. Ran the full backend suite in the Linux image against PostgreSQL after the last change.

## Existing tests modified by the change (6) and why
| File | Change | Reason | Commit |
|---|---|---|---|
| `tests/integration/test_migrations_documents.py` | the expected column list of `documents` gains `error_code`; the expected constraints gain `ck_documents_error_code_only_when_failed` | Migration `0005` adds them. The test checks the catalog of `0004` *plus* what later migrations add; the test of `0005` has its own catalog test. `0004` itself is unchanged (a test pins its hash). | `7648bd8` |
| `tests/integration/helpers.py` (`build_settings`) | `upload_rate_limit` is `1000/minute` | The new limit (10 per minute) would make ordinary tests hit `429`; the rate-limit tests lower it explicitly, like the login and register limits. | group 9 |
| `test_subjects_api.py`, `test_enrollments_api.py`, `test_email_ascii.py`, `test_adversarial_probes.py` | `from httpx import Response` becomes `from httpx2 import Response` | Adding the dependencies updated Starlette, whose `TestClient` now returns `httpx2` responses; the annotation only (no assertion changed). | `2652724` |

No assertion of an existing test was weakened, removed or skipped to make the suite pass.

## Existing tests reviewed and left unchanged
| Area | Tests | Why they stay valid |
|---|---|---|
| Fixtures that insert documents | `tests/sql_support.py` (`insert_document`, `insert_chunk`, `seed_basic`), `tests/catalog.py`, `tests/integration/test_fixture_catalog.py`, `test_document_models.py`, `test_document_repository.py`, `test_document_storage_integrity.py`, `test_chunk_retrieval*.py` | They insert `documents` without `error_code`; the column is nullable and the new CHECK only forbids a code on a document that is not `failed`. The design keeps "a failed document has a code" as a service rule precisely so that fixtures inserting failed rows without a code keep working. Retrieval tests still never see non-`ready` documents. |
| Truncation between tests | `tests/db_support.py` (`truncate_all`) | It lists the tables of the database, so `ingestion_jobs` is emptied with the others (`CASCADE`). The new tests relied on it for hundreds of runs. |
| Migrations | `test_migrations.py`, `test_migrations_subjects.py`, `test_migrations_documents.py`, `test_migrations_ingestion.py` | The chain tests accept the head `0005`; `alembic check` reports no drift; the upgrade/downgrade round trip of `0005` is tested and `0004` is pinned by hash. |
| Settings | `test_config.py`, `test_auth_settings.py`, `test_ingestion_settings.py` | The new settings have defaults, so the old tests need no variable; `test_ingestion_settings.py` covers defaults, environment, invalid values and the fake-embedder rules. |
| Process and transport | `test_review_hardening.py` (real Uvicorn with the Dockerfile arguments, proxy headers, `app_factory`), `test_cli.py`, `test_cli_process.py` | The new middleware sits inside the existing ones; these tests still run and pass. |
| Error exposure | `test_error_text_exposure.py`, `test_auth_logging.py` | The new error classes follow the same handler; the new leak tests extend, not replace, them. |
| Roles and isolation | `test_role_guards.py`, `test_subjects_api.py` | Unchanged routes keep their behaviour. |

## Gaps found and the tests added
The review found four files that change with this change and that no test read:

| File | Gap | New test (`tests/unit/test_deployment_files.py`) |
|---|---|---|
| `backend/.env.example` | no test proved that every setting is documented, that no unknown variable is documented, that the documented values equal the defaults, or that secrets are placeholders | 4 tests (the loop checks 30 or more values) |
| `backend/Dockerfile` | the API image could grow `torch`/`--extra` without a test noticing; the worker could lose its command or the offline model | 2 tests |
| `docker-compose.yml` | the worker service (no `profiles` since group 8) had no test: target, dependency on the healthy database, no ports, resources | 5 tests |
| `.github/workflows/ci.yml` | nothing pinned that CI installs the `ingestion` group only, runs the gates and unit/integration tests, and uses the pgvector image and `APP_ENV=test` | 3 tests |

Also added, from the review of group 10 (`tests/unit/test_test_seams.py`, 4 tests): only `upload_guard.py` mentions the `UploadSlots` pause seam; the application builds its slots without it; the parameter is keyword-only and `None` by default; no production module imports test code. Nothing in a request, a header, an uploaded file, the environment or the settings can reach it (it is a constructor argument that only tests pass).

These tests exercise existing behaviour, so they were green on their first run; their value is shown by mutation: **15 mutations of the files themselves** (a setting removed from the example, a default or a lease changed, an unknown variable, a real-looking secret, the API image installing the embedding group, the worker command lost, the offline flag changed, the worker behind a profile, the worker built from the API target, the memory limit removed, CI installing the embedding group, CI skipping the unit tests, the seam on by default, the seam wired in production), **all killed**.

## Review of the group 10 controls
- **Test seams and HTTP inputs**: the only seam in `app/` is `UploadSlots(pause_between_read_and_write=...)`. It is a keyword argument that only test code passes; `create_app` does not pass it; no module reads the environment, a header or a form for it (tests above). The pause scripts of the real-server tests (`PAUSE_FLAG`, `EXIT_STAMP`) live in the test files and run only in processes the tests start.
- **`UploadSlots` locks**: both critical sections are still under `self._lock`. Removing the lock from `try_acquire` or from `release` is killed by the forced-interleaving tests.
- **Forms and temporary files**: `await form.close()` stays in a `finally`; the tracking tests keep every spooled file referenced, so only an explicit close can close it, and they cover success and every failure path; the real-server tests inspect `/proc/<pid>/fd`.
- **Timing tests**: reviewed every bound. The lower bounds prove the behaviour comes from the right deadline (the idle `408` must arrive before the total deadline; the slow-drip `408` not before about the total deadline); the upper bounds fail if the guard disappears (the drip test then receives no answer at all). Tolerances that remain: the 60-client test accepts one connection more than the slot count to be neither refused nor timed out (a very slow runner), and it also requires that every answered connection is exactly a `503` or a `408`; the "temporary files" test accepts any of `202/413/415/422/503` per request but requires at least one `202` and no file left. No assertion was found that would pass with a wrong behaviour; the margins could need widening on a very slow runner.
- **Recovery and duplicates**: the database forbids two chunks with the same `(document_id, chunk_index)` and two jobs for a document; the tests with a killed worker assert consecutive indexes `0..n-1`, the count equal to `chunks_count`, `attempts = 2` and no leftover bytes.

## Results
- Full backend suite in the Linux worker image against PostgreSQL: **1702 passed, 1 skipped (AES), 16 deselected (`realmodel`)**; coverage of `app` **98 %**.
- `ruff check --no-cache`, `ruff format --check`, `mypy --strict app tests` (169 files) clean; `pip-audit` no known vulnerabilities (no dependency changed); `openspec validate --strict` valid. All repeated after the last change.

## Risks and deviations
- The deployment-file tests read the real files by relative path; they need the repository checkout (CI has it) and are not meant for an installed package.
- The host virtual environment is still blocked by Windows Application Control; everything ran in the Linux image.
- A sixth untracked reference document (`Guia_SDD_OpenSpec_SpecBoot_Revisada.md`) appeared in the repository root; it was not touched or committed.
- Dependabot alert #1 remains open (planned in 15.1 and 17.3).
