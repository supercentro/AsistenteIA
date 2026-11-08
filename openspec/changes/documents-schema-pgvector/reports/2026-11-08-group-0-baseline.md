# Group 0 closing record (tasks 0.1 to 0.4)

Date: 2026-11-08. The commands below were run on this date against the repository history; the 0.3 values come from records taken earlier, as explained. Nothing was reconstructed from memory.

## 0.1 The branch is `feature/documents-schema-pgvector` and started without code changes
Evidence (Git):
- `git branch --show-current` prints `feature/documents-schema-pgvector`.
- `git log --reverse main..HEAD` starts with `9e46153` (2026-10-28 17:41 -0300, "docs(openspec): plan documents-schema-pgvector"). `git show --stat 9e46153` lists six files, all under `openspec/changes/documents-schema-pgvector/` (`.openspec.yaml`, `design.md`, `proposal.md`, two `spec.md`, `tasks.md`).
- The first commit of the branch that touches `backend/` or `frontend/` is `6e105b4` (2026-10-28 18:41 -0300, group 2, dependency only). The next two commits before it (`e3e33a8`, `5fe11b2`) are OpenSpec reports.
- `git diff --stat 5fe11b2 main -- backend frontend` is empty: until the group 2 commits the code of the branch equals the code of `main`.
Result: the branch started without code changes. 0.1 is satisfied.

## 0.2 The branch is based on the published `main`
- `git merge-base --is-ancestor db06d50 HEAD` exits with success.
- `git merge-base main HEAD` prints `db06d5084d97f1fbf8795ca2c0fc8ff7f85a156c`, the same object as `git rev-parse db06d50`.
Result: 0.2 is satisfied.

## 0.3 Stack, green `pytest` and baseline of the databases
Chronological deviation: the task asked for this to be recorded at the start of the branch (group 0). The baseline was obtained during **group 2** (2026-10-28 21:40 to 21:44 UTC), after the planning and spike commits and before any code change, because group 0 was not executed as a separate step. The values are therefore real and taken on the starting code, but the record is late and was not made under the name of task 0.3.

Evidence of the baseline:
- Report `reports/2026-10-28-group-2-dependency-and-image.md`, section "Data preservation evidence", step 1 ("Before"): `alembic_version` = `0003`; tables `alembic_version, enrollments, subjects, users`; row counts 0/0/0 (`users`, `subjects`, `enrollments`); extension `vector` 0.8.7; PostgreSQL 15.19; databases `postgres, asistenteia, asistenteia_test`. The same report states `pytest`: 494 passed. It also states that `asistenteia_test` is empty between runs by design (its tables are dropped and truncated by the suite), so it has no separate row counts.
- Transcript of the session (the harness file `37b9475e-8000-414a-a563-2a3020e73979.jsonl`): the `uv run pytest -q` command at 2026-10-28 21:40:34 UTC with the result `494 passed, 3 warnings in 60.47s` at 21:41:47 UTC; `docker compose up -d db` at 21:42:09 UTC; the `psql` baseline queries at 21:42:28 and 21:43:06 UTC.
- The `pytest` run (18:40:34 -0300) happened after commit `5fe11b2` (18:40:08) and before `6e105b4` (18:41:53), and the code of `backend/` and `frontend/` is identical to `main` at that point (see 0.1). So the 494 passed result is the result of the starting code.
- Later, independent baselines exist: `reports/2026-11-07-step-7-unit-test-and-db-verification.md` and `reports/2026-11-07-step-8-real-database-verification.md` (revision before migration, databases and counts).

Not available: a separate snapshot of `asistenteia_test` at that moment (it is empty by design). This is stated, not filled in.
Result: 0.3 is satisfied with the recorded chronological deviation.

## 0.4 Notes with the literal user prompts, decisions and AI findings
- `reports/2026-11-08-user-prompts-verbatim.md`: 16 user messages of Feature 5 copied unchanged from the transcript (section A), with timestamps and line numbers; summaries are kept apart (section B). No prompt was completed or reconstructed.
- `reports/2026-11-07-ai-usage-notes.md`: short notes by group (decisions and AI findings), with a pointer to the file above. These notes are summaries.
Result: 0.4 is satisfied. The prompts that precede Feature 5 belong to earlier changes and are outside this task.
