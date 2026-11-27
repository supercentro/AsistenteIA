# P1 implementation report — 2026-11-25

Branch `feature/activity-privacy-hardening-p1`, from `main` at `55bc6da`. Nothing committed or merged. Both switches stay false by default; no migration, model, identity or audit change; no Gemini call; fictitious data on disposable databases.

## 1. Reproductions before any change (official environment)

The project interpreter ran again on this host, so the characterisations used the real service, pydantic and the test suite. Each one PASSED on unchanged code, which means the leak was confirmed.

| Vector | Where | Result |
|---|---|---|
| V6a | service, in-memory repository | week 5 withheld; rates 0.138 and 0.331 leave the candidates 13, 28, 49, 107 (true 28) |
| V6b | service | cited answers from the rate, minus the published figure, equal the withheld 3 |
| V7 | service | 6 / null, then 6, then one entry of 9: withheld figure 3 |
| V7 | real API, PostgreSQL and the delete route | same sequence, through two `DELETE .../documents/{id}` answering 204 |
| Precondition | real upload route | two documents with the same name are both accepted (202) |

Command: `uv run pytest tests/unit/test_activity_composition.py` (3 passed) and `uv run pytest tests/integration/test_activity_composition_db.py` (2 passed). Those characterisation files were then rewritten as the mitigation tests.

## 2. Test-driven record

| Step | Command | Before implementation |
|---|---|---|
| Service rules | `pytest tests/unit/test_activity_composition.py` | 26 failed, 7 passed (invariants that already held) |
| Dashboard | `vitest run src/pages/TeacherActivityPage.test.tsx` | 7 failed, 54 passed |

Findings during the work: the random "never two versions" property first failed because its generator wrote questions of a removed student, which the system prevents (generator fixed, not the service); the service trusted the repository to return only rows of the block, so a filter and its scenario were added.

## 3. What was implemented

- `activity_service.py`: fixed blocks of two weeks from 2026-01-05; summary over the publishable weeks only (rule F); more than 50 % of one student withholds a weekly cell, the rates and a document figure; a block starting before the marker allows is withheld whole; no deleted document listed; rule G2 for the uncited rate. A request with no whole week shows no summary and reads no fact (clarification of the spec; it only withholds).
- Contract: `summary_window`, `summary_weeks` (additive in shape; the summary figures change their meaning, as the descriptions now say).
- Dashboard: `ActivitySummary` with the approved copy.

## 4. Mutation checks

18 mutants of the service, each applied, tested and restored (verified by hash). 17 were caught at once; "covered weeks not restricted to the block" survived until its deterministic scenario was added. Mutants: overlapping blocks, trimmed block, marker ignored, `end` selects the block, anchor per subject, whole block summarised, weeks outside the block, `>=` for dominance, dominance ignored (cell, rates, document), capped figure, G2 `at least one`, deleted ignored, new documents counted, dominance not counted, `no_material_rate` tied to G2, deleted listed again.

## 5. Independent adversarial review

Separate agent with a clean context, attacking by composition on the real routes and SQL. Initial verdict **FAIL**.

| Id | Severity | Finding | State |
|---|---|---|---|
| M-1 | Major | G2 counts withheld documents, not the students behind them: one answer citing two withheld documents gives both; one controlled account brings a figure back; the same file uploaded twice does it alone | **Open.** Reproduced again in `tests/unit/test_activity_open_composition.py`. Needs D-Q20 |
| m-1 | Minor | rate numerators have no group or dominance rule (older than P1) | open, registered, characterised (D-Q21) |
| m-2 | Minor | dominance on the rates cannot fire with real data | documented in spec and design; not counted as F6 evidence |
| m-3 | Minor | with a controlled account the teacher can change the coverage of a read block | documented, with TD-071 |
| m-4 | Minor | deleting documents probes which withheld one was cited | documented |
| m-5 | Minor | documents behind the code | done, except the bullet of `backend-standards.md` section 9 (below) |
| Q | Question | spec still said the copy needed approval | corrected |
| Q | Question | a chunk deleted while an answer is generated leaves all its sources without id (availability only) | open question, not tested |

The review reported 250 passed and 1 xfailed in its copy, 11 own mutants caught, other-teacher 404, student 403, anonymous 401, switch off 404, extreme dates without 500. The earlier wording that G2 "cannot be split" and that "the teacher cannot trigger" the erasure flip was **wrong**.

**Candidate G3** was evaluated outside the repository (a pytest plugin replacing G2 in memory): it closes the reproductions of M-1 and keeps the deletion property; only the scenario "two withheld documents keep the rate" fails besides the tests that assert the leak. Cost table in `design.md`. Not implemented: it changes an approved scenario.

## 6. Results by vector

| Vector | Status in the branch |
|---|---|
| V3 | mitigated (erasure and document deletion can still change or withhold a block) |
| V6a | mitigated for unchanged data |
| V7 | mitigated |
| F6 | partial: cells and documents; not rate numerators, two students together or padding |
| V6b | **not mitigated** |
| F8, F7 | open |

## 7. Manual verification

Local demo backend restarted with this code (fictitious data, switch on for that process only, `LLM_BACKEND=fake`). A throwaway Playwright script (not the MCP server, to keep the demo password out of the session) walked three subjects: full block with a deleted and a rare document (uncited rate withheld, no entry without id), a class of four (everything withheld), a class with a removal (2-week series). No browser error; no horizontal overflow at 320 px.

## 8. Gates (last run, after the last change of code and tests)

| Gate | Result |
|---|---|
| `ruff check --no-cache`, `ruff format --check`, `mypy --strict app tests` | clean (304 source files) |
| `pytest tests/unit` | 1844 passed, 110 skipped, 3 xfailed (V2 and the two V6b properties), 4 failed (host-only, below) |
| `pytest tests/integration -m "not role_bound and not realmodel"` | 1042 passed, 39 skipped, 0 failed (baseline on `main` before the change: 1040 passed, 39 skipped) |
| Role-bound activity routes on an empty disposable cluster | 5 passed, 1 skipped |
| Frontend `vitest` | 681 passed, 1 skipped |
| Typecheck, lint, format, generated API types, build | clean |
| Playwright mocked and smoke specs, on a temporary server | 34 passed |
| `openspec validate --all --strict` | 29 of 29 |

The full role-bound suite and the CI privileges job were not run: no grant, role or migration changed. Not run on this host: the tests marked Linux-only (`test_activity_real_server.py` among them, updated but never executed here); they need CI. Role-bound tests of the activity route ran on a disposable cluster. The four unit failures of worker and migration settings are host-only and fail the same way without this change.

Not done: the bullet for `docs/backend-standards.md` section 9. The edit was refused by the permission classifier of the session; proposed text: "MUST: the figures that summarise students are never computed over a window the caller chooses: they cover one fixed complete block and only its publishable weeks; a figure that one student concentrates is withheld, never capped or noised; nothing is grouped by a key that a deletion can merge; a new figure must be checked against what the published ones let the reader compute."
