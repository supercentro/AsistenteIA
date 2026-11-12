# Group 0 closing record (tasks 0.1 to 0.3)

Date: 2026-11-09. Group 0 was not executed when the branch was created (the planning and the spike came first) and was authorised on 2026-11-09, together with group 3. Every value below comes from a command run on that date against the Git history and the databases, or from an original record that is named. Nothing was reconstructed from memory, and where an original record does not exist this is said.

## 0.1 The branch started from `main` and contains only OpenSpec files
Evidence (Git):
- `git branch --show-current` prints `feature/document-ingestion`.
- `git merge-base main HEAD` prints `3960132`, the tip of `main` and of `origin/main` when the branch was created (session record of 2026-11-08 18:15 UTC: `main HEAD 3960132 origin/main 3960132`).
- `git log --reverse main..HEAD` starts with `67f950c` (2026-11-08 18:27 -0300, "docs(openspec): plan document-ingestion"). `git show --stat 67f950c` lists 8 files, all under `openspec/changes/document-ingestion/` (`.openspec.yaml`, `design.md`, `proposal.md`, four `spec.md`, `tasks.md`; 915 insertions).
- Commits after it: `918e52c` (spike reports, only under that folder), `a43dd64` (artifact update, six files in that folder), then the group 2 commits `e61ce9e`, `2652724` and `8343890` that change `backend/` and the CI and Compose files, and `a98f7f3` (reports). The first commit that touches code is `e61ce9e`.
- `git diff --stat main...HEAD` at the start of this group: 44 files, 4,111 insertions, 8 deletions (planning, spike reports, group 2).
Result: the branch started from the published `main` and held only OpenSpec planning files until group 2. 0.1 is satisfied. Chronological deviation: the check is made after groups 1 and 2, not before; Git history proves the content of the first commit.

## 0.2 `main` is the published one
- `git merge-base --is-ancestor 3960132 HEAD` exits with success.
- `main` and `origin/main` are both `3960132` (record above).
Result: 0.2 (first half) is satisfied.

## 0.3 Stack, green `pytest` and baseline of the databases
Chronological deviation (stated, not hidden): the task asks for the baseline at the start of the branch. No baseline report was written then, because the planning phase did not run tests or touch the databases, and the spike came next. What exists:

1. **Original records of the starting point** (taken when `main` was `3960132`, before this change touched anything):
   - Archived Feature 5 report `openspec/changes/archive/2026-11-08-documents-schema-pgvector/reports/2026-11-08-final-verification.md`: full backend suite **712 passed** on PostgreSQL 15.19 with pgvector 0.8.7, coverage of `app` 98 %; development database at revision `0004`, tables `alembic_version, document_chunks, documents, enrollments, subjects, users`, 0 rows in the application tables, extension 0.8.7; `asistenteia_test` has no tables after the suite (only `plpgsql`); databases `asistenteia`, `asistenteia_test`, `postgres`.
   - Session record of the spike cleanup (2026-11-08 22:29 UTC, transcript line 15482): the development database was compared with the Feature 5 verification snapshot and found identical (revision, tables, row counts, column and constraint hashes) after the spike.
2. **Measurements taken on 2026-11-09 for this record** (read-only queries inside the `asistenteia-db-1` container; nothing was written):
   - `docker compose` stack: `asistenteia-db-1` up and healthy (the only Compose container of the project; ports 8000 and 5173 not used by this work).
   - PostgreSQL 15.19; extensions `plpgsql 1.0` and `vector 0.8.7`; databases `asistenteia`, `asistenteia_test`, `postgres`.
   - Development database `asistenteia`: `alembic_version` = `0004`; tables `alembic_version, document_chunks, documents, enrollments, subjects, users`; row counts `users` 0, `subjects` 0, `enrollments` 0, `documents` 0, `document_chunks` 0; md5 of the column list `11ea5ce4039d0ae55a8f93ea48649395`; md5 of the constraint definitions `406f11d19decea83878ab535b1dbd648`.
   - Test database `asistenteia_test`: no tables and only the extension `plpgsql`, as designed (the suite builds it and drops it at the end).
   - Test baseline of the code that existed before this change, run on the current checkout with the two test files added by group 2 excluded (`uv run --frozen pytest -q --ignore=tests/unit/test_ingestion_settings.py --ignore=tests/unit/test_cpu_quota.py`): **712 passed**, 2 warnings, 150.9 s. This reproduces the 712 of the Feature 5 record on the current code.
   - Current full suite (group 2 included): 795 passed (712 plus 83 new).
3. **Not available**: a snapshot of the databases taken on 2026-11-08 18:15 UTC at the exact moment the branch was created. It is not filled in; the Feature 5 record and the spike-cleanup comparison are the nearest original evidence, and the 2026-11-09 values agree with them.

Result: 0.2 (second half) and 0.3 (baseline) are satisfied with the recorded deviation.

## 0.3 (second part) Literal prompts and notes
- `reports/2026-11-09-user-prompts-verbatim.md`: literal transcriptions A1 to A9 of the user's messages of Feature 6, copied mechanically from the harness transcript by a script with the transcript line and UTC timestamp of each; a second pass found every block identical to the transcript. Summaries are in a separate section B. The record was created on 2026-11-09, after groups 1 and 2 (stated in its header).
- `reports/2026-11-09-ai-usage-notes.md`: summaries and AI findings, not quotations.
- Verification "A1..An match the transcript": done by the second pass (9 of 9 identical).
- The condition "the record exists before group 1 starts" was not met (deviation above); it exists before group 3 starts.
