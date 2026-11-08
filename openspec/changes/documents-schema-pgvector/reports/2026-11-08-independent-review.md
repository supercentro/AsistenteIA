# Independent adversarial review (task 11.1)

Date: 2026-11-08. Skill: `adversarial-review`. Reviewer: a separate subagent (type `Explore`, model `opus`, clean context, no edit tools; instructed to be read-only on the repository, to probe only `asistenteia_test`, its own scratch `*_test` database, or read the catalog of `asistenteia`, and not to touch ports 8000 and 5173). The implementing session gave it the scope, the focus areas and the constraints, and none of its own conclusions. The reviewer's database list, repository state and scratch files were checked by itself after the run; the working tree was not changed by it.

Scope: `git diff main...HEAD` of PR #7 (26 commits at the time), the whole OpenSpec change, migration `0004`, models, repository, validation helper, tests, docs and the live catalog.

## Review 1 (HEAD `01f7dd9`): verdict FAIL (one major)
What the reviewer ran: the full backend suite once (668 passed), read-only catalog queries on `asistenteia`, and probes on a scratch database created from `pg_dump -s` (integrity, float32 edges, Unicode blanks, plans on 20,000 chunks in 200 subjects), plus Python probes of the validator and the compiled SQL. It did not run `alembic check`, CI, the frontend suites, `docker compose up --build` or pgvector above 20,000 rows.

Clean areas (with how it tried to break them): isolation SQL for both roles (EXISTS bound to the same parameters, nothing correlated to the wrong table, unknown role returns before any SQL, no other public method), composite FK and cascades (moving a document's or chunk's subject, teacher RESTRICT, 0 orphans), ordering and `top_k` handling, validation of NaN, infinity, bool, complex, Fraction, Decimal, float subclasses and negative zero, error and log paths, concurrency (one read-committed statement per search), and agreement of models, migration, `data-model.md`, backend standards and the live catalog.

| ID | Severity | Finding | Disposition |
|---|---|---|---|
| F1 | **MAJOR** | `design.md` I2 and the dependency row said `find_similar` translates integrity and data errors; the code propagates them and a test asserts that. Safety is in the handlers and the middleware. Not reported as a deviation. | **Fixed** (artifact): I2, dependency row and divergence 6 corrected; deviation recorded in the TDD evidence. The alternative (implement the translation) was not taken because it would add a new error contract; see decision 1 below |
| F2 | MINOR | The statement-log leak test could not see the embedding (it searched `1.0, 0.0` while pgvector writes `[1.0,0.0,`); it passed with parameters exposed | **Fixed** (test): real serialisation forbidden, `hidden` asserted; mutation `hide_parameters=False` now killed |
| F3 | MINOR | An integer component such as `10**400` raised `OverflowError` instead of the controlled error | **Fixed** (code, tests first: red 5 failures, then green) |
| F4 | MINOR | A sequence whose `__len__` says 384 but yields another number of items reached the database | **Fixed** (code, tests first) |
| F5 | MINOR | The helper measures the norm in double precision, the database check in float32: vectors at the extreme edges (about `1e6` and `1e-6`) pass the helper and fail the CHECK on insert | **Fixed on 2026-11-08** by user decision (tests first, mutations, focused review PASS): see `2026-11-08-focused-review-f5-f7-f8.md` |
| F6 | MINOR | `content ~ '\S'` accepts content made only of U+00A0 or U+0085 (database locale), while the spec says whitespace-only is rejected | **Accepted** by user decision: registered as TD-027; migration `0004` and the applied constraints are unchanged |
| F7 | ACCEPTABLE RISK / QUESTION | `find_similar` trusts `actor.role`; the SQL does not join `users`, and the database does not force enrollees to be students or owners to be teachers (the services do) | **Fixed on 2026-11-08** by user decision: the stored role is checked inside the SQL of both branches (tests with false roles, mutations, focused review PASS) |
| F8 | MINOR / QUESTION | The scenario title says "malformed access" but a non-UUID `subject_id` raises a `DataError` (echoing the value in its message) instead of an empty list | **Fixed on 2026-11-08** by user decision: a non-UUID `subject_id` (and `actor.user_id`) raises the controlled error before any statement; an unknown well-formed UUID still returns an empty list |
| F9 | MINOR | `checkfirst=True` on the enum could adopt a stale type with other labels | **Accepted** by user decision (2026-11-08) as a low residual risk: TD-028; detection query in `docs/development_guide.md`; `0004` unchanged and no `0005` |
| F10 | MINOR | A throwaway password literal in the committed experiment script | **Fixed**: read from `SPIKE_DSN` |
| F11 | MINOR | Tasks 0.1 to 0.4 unticked | **Open**: see `2026-11-08-group-0-survey.md` (plan awaiting approval) |
| F12 | ACCEPTABLE RISK | The pre-migration dump is still inside the container `/tmp` | **Closed** by user decision: a persistent copy was made outside the repository and the temporary directories (see below); no copy deleted |
| F13 | ACCEPTABLE RISK | The hnsw index is unused by construction (tie-break); removing `, id` would bring back the D3 risk | Documented as TD-022; see test gap below |

Test gaps named by the reviewer: the recall test cannot detect filtered-ANN loss at its size (only `test_ties_are_broken_by_chunk_id` kills the "remove tie-break" mutation); an `EXPLAIN` assertion that the plan never uses `ix_document_chunks_embedding` is missing; the database-failure test simulates the failure by raising an INSERT violation from `session.execute`; missing cases for a malformed subject id (F8), a teacher enrolled as a student (F7), float32 edge vectors on insert (F5) and Unicode blanks (F6), and for a document moving from `ready` to `failed`.

## Review 2 (HEAD `ed5be99`): verdict PASS WITH GAPS
The same reviewer verified the corrections of F1, F2, F3/F4 and F10 independently (`git diff HEAD~3 HEAD`, one pytest run: 674 passed) and tried to break them: `10**400`, two components of `1e308` (overflow of the norm), generators, a `list` subclass with a lying length, lying `__iter__` (0, 383, 385, 5000 items). All four items: **PASS**. No blocker and no major remain.

New findings of review 2:
| ID | Severity | Finding | Disposition |
|---|---|---|---|
| N1 | MINOR | Duplicate number 4 in the divergence list of `design.md`, and the cited report did not exist | **Fixed**: renumbered as item 6; this report is the cited file |
| N2 | MINOR | An `int` subclass whose `__float__` raises `ValueError` or `TypeError` escaped as an uncontrolled exception (nothing reached the database, nothing leaked) | **Fixed** (tests first: red 2 failures, then green) by catching them too |
| N3 | ACCEPTABLE RISK | The throwaway password of the experiment container (`spikepw`) remains in git history (`f61ce6d`) | Accepted: scratch container, no longer in any file; history is not rewritten |
| N4 | MINOR (process) | The correction of F1 was not recorded as a deviation | **Fixed**: TDD evidence, AI usage notes and lesson L17 |

The reviewer also noticed ` M backend/app/core/database.py` in the working tree during its run. It was a line-ending-only difference left by a temporary mutation check (the content was restored and compared identical before its run; `git diff --ignore-cr-at-eol` is empty). It was normalised with `git checkout` and the suite of the final commit was run again by the implementing session.

## TD-022 to TD-025: assessment and proposed classification
| ID | Reviewer assessment | Proposed classification (for the user's decision) |
|---|---|---|
| TD-022 hnsw unused | Accurate; verified independently (not chosen even with seqscan, bitmapscan and sort disabled) | **Accept for the MVP**, revisit in change 12. Add one line: dropping the tie-break brings back the incomplete-filtered-results risk (D3) |
| TD-023 no quota | Accurate but incomplete: no `statement_timeout` or work bound on the exact sort | **Later (change 6 and 12)**: caps on chunks per document or subject, plus a statement timeout |
| TD-024 fixed dimension, version-dependent range | Accurate; add the float32-versus-double edge (F5) | **Accept** |
| TD-025 hnsw parameters, filtered ANN | Accurate but largely duplicates TD-022 | **Later**; could be merged into TD-022 |
| New (not yet registered) | F7 role trusted, not checked in SQL; F6 NBSP-only content (next to TD-018); F12 lifecycle of the backup dump (a process note, not a code debt) | Register TD-026 and TD-027 if the user accepts F7 and F6 instead of fixing them |

## Decisions needed from the user (task 11.2 stays open until then)
1. F1 was fixed by correcting the design artifact (smallest change, no new contract). The alternative is to implement the translation in `find_similar` (new controlled error type, possible 503 mapping in change 9). Confirm or ask for the alternative.
2. F5, F6, F7, F8, F9: fix now (each needs a spec, contract or migration change), accept as technical debt, or defer.
3. Whether to add an `EXPLAIN` guard test that fails if the plan starts using the hnsw index, so that removing the tie-break cannot go unnoticed (suggested for change 12 instead, with TD-022).
4. The classification of TD-022 to TD-025 above and the registration of the new items.

## Final verdict of this review
**PASS WITH GAPS.** No blocker and no major is open; the gaps are minors and risks listed above, each with a disposition. The change is not closed for archive until the user decides items 1 to 4 (task 11.2).


## Resolution of the user's decisions (2026-11-08)
- **F1:** the design artifact correction is kept; no new error type; the response and log protection tests are kept.
- **F5, F7, F8:** corrected with tests first, mutations and a focused independent review (verdict PASS, `2026-11-08-focused-review-f5-f7-f8.md`). The review found that the first F5 fix was incomplete (midpoint rounding and summation order) and that `actor.user_id` also needed the UUID guard; both were corrected.
- **F6:** accepted; TD-027 registered.
- **F9:** accepted as a low residual risk (TD-028); see the final decisions below.
- **TD-022 to TD-025:** kept with the review precisions (TD-022: dropping the tie-break brings back the D3 risk; TD-023: evaluate `statement_timeout` before any bulk load; TD-024: single-precision norm and the margin assumptions). TD-026 (no automated guard for the HNSW plan or the tie-break) and TD-027 (F6) registered. No debt was merged or deleted.
- **Not done on purpose:** the `EXPLAIN` guard test (kept as TD-026 for change 12), deleting any backup.
- **Task 11.2:** closed on 2026-11-08 after the final decisions below were carried out and verified.

## F9 in full (original text and alternatives; the user chose alternative 1 on 2026-11-08)
**Finding (review 1, MINOR):** in `backend/alembic/versions/0004_create_documents_and_chunks.py`, `upgrade()` creates the `document_status` type with `document_status.create(op.get_bind(), checkfirst=True)` (the type object is declared with `create_type=False` so that the table does not create it again) and `downgrade()` drops it with `checkfirst=True`. `checkfirst=True` only tests whether a type with that name exists. If a type named `document_status` already exists with other labels (for example left by a failed manual attempt or a different branch), the migration skips creating it and then creates `documents.status` on top of the stale type, so the labels `pending`, `processing`, `ready`, `failed` might not exist; the failure would appear later as an insert error, not as a migration error. On a clean database, in CI and in the development database (already migrated) this does not occur.
**Alternatives:**
1. Leave as is and register it as a low technical debt (no change to `0004`; the development database is already at `0004`).
2. Add a new migration `0005` with a check that fails if the type exists with other labels (never edit a migration already applied).
3. Edit `0004` to create the type without `checkfirst` (fails fast on any existing type). It would change a migration already applied in development, so it needs the user's explicit approval and a reset or stamp of that database.
**Recommendation:** alternative 1 (or 2 if a stale type is judged plausible); alternative 3 only with a rebuild of the development database.

## Final decisions of 2026-11-08 and their verification
### F9, accepted as a low residual risk (TD-028)
- No change to `0004` and no `0005`. TD-028 is specific to the enum; it does not duplicate TD-018 or TD-027.
- Detection: the catalog query in `docs/development_guide.md` (migrations section) lists any `document_status` type and its labels before the migration. Check made on the development database: the type exists with the labels `pending, processing, ready, failed`, in that order.

### F12, persistent backup of the pre-`0004` dump
- Location: `%USERPROFILE%\Backups\AsistenteIA\asistenteia_pre_0004.dump` (a folder in the user profile on a fixed local disk, outside the repository, outside every temporary directory and not synchronised with a cloud folder).
- Permissions: inheritance removed; full control only for the current Windows user (checked with `icacls`).
- Integrity: size 8,261 bytes at the source and the copy; SHA-256 identical (prefix `f1bf54e5dc15a567`, full hash `f1bf54e5dc15a567a186f06e5dd1831630c57e6d26915a6aeba19e914a1ebe97`); `pg_restore --list` reads the copy (the archive header and its 9 table and type entries). The earlier restore into an isolated database (group 8) used this same file content.
- Contents: schema only (the development database held no application rows), no credentials.
- Retention: kept until change 5 is merged and archived and the owner agrees; nothing was deleted (the temporary copy of the session and the copy in the container's `/tmp` remain; neither counts as storage).
- Owner of the risk: the project owner; follow-up when archiving change 5.

### N3, spike credential
- The string belonged to the throwaway container used for the compatibility spike (a container `spike-pgvector-g1`, now removed: no container or volume with `spike` in its name exists).
- It is not a credential of the project: the working tree has no file that uses it (the only mention is this report's note by name); no tracked file outside `openspec/` mentions it; `docker-compose.yml` and the CI workflow do not use it; the local `backend/.env` has no match; the project database container does not use it as its password (compared without printing); the project database has only the role `asistente`, no spike role.
- Commit `f61ce6d` holds it in the script `2026-10-28-magnitude-experiment.py`; the script now reads the DSN from the environment. History was not rewritten.
- Not checked: containers of other applications on the machine (out of the project scope; not inspected).
- Accepted by user decision; owner: the project owner. Revisit if the password is ever reused.

### Classification of accepted risks
| Risk | Severity | Owner / follow-up |
|---|---|---|
| F9 stale enum | Low | TD-028, whoever applies `0004` to a foreign database |
| F6 blank-looking content | Low | TD-027, change 6 |
| F7 role trusted by services (now also checked in SQL) | Closed | none |
| F12 backup lifecycle | Low | project owner, review at archive time of change 5 |
| N3 spike password in history | Low | project owner |
| F13 no plan guard | Low | TD-026, change 12 |
| TD-022, TD-023, TD-024, TD-025 | Low | change 12 (TD-023 also change 6) |
