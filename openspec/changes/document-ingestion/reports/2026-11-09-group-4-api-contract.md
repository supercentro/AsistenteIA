# Group 4: API contract and generated types

Date: 2026-11-09. Branch `feature/document-ingestion`. Tasks 4.1 and 4.2. No router, service, migration or UI file was changed; the only application-adjacent artefacts are the contract, the generated frontend types and tests.

## 4.1 `docs/api-spec.yml`, `docs/data-model.md` and generated types

Changes to `docs/api-spec.yml` (additive; nothing removed or renamed):
- `GET /subjects/{subject_id}/documents` and `DELETE .../{document_id}`: add `401`; `DELETE` states it is valid while the document is being processed.
- `POST /subjects/{subject_id}/documents`: responses `202`, `401`, `403`, `404`, `408`, `409`, `413`, `415`, `422`, `429`, `503`.
  - `408` `REQUEST_TIMEOUT`: only for a client that stays connected; nothing is stored.
  - `409` `DOCUMENT_QUOTA_EXCEEDED`; `413` `PAYLOAD_TOO_LARGE`; `415` `UNSUPPORTED_MEDIA_TYPE`; `429` `RATE_LIMITED` with `Retry-After`; `503` `INGESTION_QUEUE_FULL` or `SERVICE_UNAVAILABLE` with `Retry-After`.
  - `422` keeps the generic `VALIDATION_ERROR` and documents the fixed `details.reason` values `MALFORMED_MULTIPART`, `FILE_PART_MISSING`, `UNEXPECTED_FIELDS`, `EMPTY_FILE`, `INVALID_FILENAME`, so the `Error` schema itself does not change.
  - Multipart body: exactly one non-empty `file` part, `additionalProperties: false`; the description states durability before `202`, type decided from content, filename cleaning, the order of checks (authentication and ownership before the body) and that the original file is not kept.
- `Document`: new `required` list (`id`, `subject_id`, `filename`, `content_type`, `size_bytes`, `status`, `chunks_count`, `created_at`; closes divergence 5 of change 5), new nullable `error_code` with the closed enum of the 12 codes (and `null`, as OpenAPI 3.0 requires), descriptions of `status`, `error_code` and `error_message`.
- `Error.code` description lists the new codes.

`docs/data-model.md`: `ingestion_jobs` (diagram, section, referential action), `documents.error_code` (columns, check, catalogue of 12 codes, the service rule that a failed document has a code), migration `0005`, the persistence of deleted bytes in dead tuples, WAL and backups with the measured numbers, and item 7 in "Changes vs readme.md". The statement that the original file is not stored in the database was corrected: it lives temporarily in `ingestion_jobs.payload`.

Compatibility with the implemented models: `Document.error_code` and the ORM column match (`varchar(40)`, nullable); the enum equals `DocumentErrorCode` (a test compares them); no existing endpoint changed. Existing clients keep working: only optional fields and error responses were added, and the new `required` list names fields that every response has always carried.

Verification (red, then green):
- Red: after editing the spec, `npm run check:api-types` failed ("src/types/api.generated.ts is missing or out of date").
- `npm run generate:api` regenerated `frontend/src/types/api.generated.ts` (111 insertions, 18 deletions: the new responses, `error_code`, the required list and descriptions; no hand edit). `npm run check:api-types`: up to date.
- `npm run typecheck`, `npm run lint`, `npm run format:check`: clean. `npm test`: **236 passed** (16 files). `npm run build`: succeeds. No UI file changed.
- OpenAPI validity: the generator (`openapi-typescript`) parsed the document without errors and the YAML loads with `yaml.safe_load`; no separate OpenAPI linter exists in the repository tooling, so none was added.

## 4.2 Contract test in the backend

Files: `backend/tests/contract_support.py` (comparison helper) and `backend/tests/unit/test_api_contract.py` (15 tests). The helper compares, for given paths, the methods, the response status codes, the multipart field names and the property names and `required` list of the `Document` schema, following local `$ref`.

- **Failing run first.** Two records:
  1. Against the previous contract (`docs/api-spec.yml` at `HEAD`, stashed temporarily): **11 failed, 3 passed, 1 xfailed** (the status code set, the required list and the error code enum did not match the design).
  2. The real application document with the xfail marker ignored (`--runxfail`): the test fails with `/subjects/{subject_id}/documents: methods [] differ from the contract ['get', 'post']` and the other missing paths and status codes, because the document routes do not exist until group 9.
- After the contract update: **14 passed, 1 xfailed** (the xfail is the real-application comparison).
- **Deviation (needs the reviewer's attention).** The task asks for a test comparing the real OpenAPI document of the application with the contract. The routes (and the `responses=` declarations that FastAPI needs to publish error statuses) are implemented in group 9, so that comparison cannot pass in group 4. The test is therefore `xfail(strict=True)` with the reason "implemented in group 9"; strict means it will fail (XPASS) the moment the routes appear, forcing group 9 to remove the marker. Task 9.1 now says so. In the meantime the comparison mechanism is verified on synthetic documents (eight kinds of drift, a `$ref` case) and the contract is checked against the code (the 12 codes of `DocumentErrorCode`, the status code sets, the required fields). The existing endpoints were not compared: the application does not declare their error responses in its OpenAPI document (a pre-existing gap: for example `GET /subjects` publishes only `200`), which is outside the three paths named by the task.
- **Mutation checks** (temporary edits, restored byte-identical): renaming the `408` response in the contract (2 failed), changing a code of the enum (1 failed), dropping `status` from `required` (2 failed); in the helper, disabling the status code comparison (2 failed), the form field comparison (1 failed), the required comparison (1 failed) and the method comparison (3 failed). All detected.
- A bug of mine found by the tests: the helper fixture aliased the shared contract (a mutation leaked into later tests); fixed by deep-copying before re-keying the paths.
- `pyyaml` is used by the helper; it is already installed as a dependency of `uvicorn[standard]`. It has no type stubs, so `pyproject.toml` ignores missing stubs for `yaml` in `mypy` (no new dependency was added).

## Quality gates
- `ruff check`, `ruff format --check`, `mypy --strict app tests`: clean (116 files).
- `pip-audit`: no known vulnerabilities (no dependency change).
- Full backend suite and coverage: see the end of this file.
- OpenSpec: `openspec validate document-ingestion --strict` and `--all --strict` pass.

## Databases and restrictions
Migration `0005` was not applied to the development database (`asistenteia` stays at `0004`). The suite uses only the isolated `asistenteia_test`. Migrations `0001` to `0004`, `prompts.md`, `readme.md`, archived specs and the OpenSpec and SpecBoot configuration were not touched. The closed catalogue stays at 12 codes.

## Full run
Backend suite on the isolated test database: **846 passed, 1 xfailed** (the strict xfail of the real-application contract test), 2 warnings, 163 s; 832 before this group plus 14 new passing tests. Coverage of `app`: **98 %** (unchanged; the group adds only tests and documentation). `asistenteia_test` has no tables afterwards; the development database `asistenteia` is still at revision `0004` with 0 rows.
