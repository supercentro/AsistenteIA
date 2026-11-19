# Step 3.3 Report - Manual endpoint testing against the local stack

- Date: 2026-11-18
- Change: teacher-material-ui
- Target: local development stack `http://127.0.0.1:8000/api/v1` (backend and worker as they were running; not rebuilt or recreated). Two teacher test accounts (created with the administrative command), one student test account (registered through the API) and fictitious files.
- The script is not part of the repository (scratchpad of the session); the passwords were generated at random and never printed.

| Call | Expected | Result |
|---|---|---|
| `POST /subjects` | 201 | 201 |
| same name again | 409 | 409 |
| blank name | 422 | 422 |
| student creates a subject | 403 | 403 |
| `GET /subjects/{id}` as owner | 200 | 200 |
| same, another teacher | 404 | 404 |
| documents of the subject, another teacher | 404 | 404 |
| subject, student not enrolled | 404 | 404 |
| malformed id | 422 | 422 |
| upload `.txt` | 202, `pending` | 202, `pending` |
| until the worker finishes | `ready` with chunks | `ready`, 3 chunks |
| empty file | 422 `details.reason` `EMPTY_FILE` | 422, `EMPTY_FILE` |
| executable content | 415 | 415 |
| 11 MB file | 413 | 413 |
| wrong field name | 422 | 422, `FILE_PART_MISSING` |
| upload by a student / by another teacher | 403 or 404 / 404 | refused / 404 |
| a markdown file with only blanks | accepted, then `failed` | 202, then `failed` with `NO_EXTRACTABLE_TEXT` |
| delete the document | 204 | 204 |
| delete it again | 404 | 404 |
| delete by another teacher | 404 | 404 |
| delete the subject (cleanup, cascades its documents) | 204 | 204 |

Not reproduced: 409 `DOCUMENT_QUOTA_EXCEEDED` (needs 50 documents; covered by the backend suite and by a UI test with a stubbed answer), 408, 429 and 503 (covered by UI tests with stubbed answers).

## Restoration
The subject and documents created by the checks were deleted through the API. The three test accounts remain (no account deletion endpoint yet, TD-064); see the database comparison in `2026-11-18-step-3-2-unit-test-and-db-verification.md`.

## Outcome
Step 3.3 status: PASS. The error bodies carry only `code`, `message` and `details`; the interface chooses its own Spanish text by code and, for 422, by the documented reason.
