# P1, second round: G3, rate sides and the second independent review — 2026-11-25

Branch `feature/activity-privacy-hardening-p1`. Nothing committed. Switches off by default; no migration, model, grant or infrastructure change; no Gemini call; fictitious data and disposable databases only.

## 1. G3 evaluated before implementing it

An exhaustive adversary (`backend/tests/composition_oracle.py`) enumerates every world of answer types consistent with a response. With the first version of its targets, 1 500 small classes, one (two) citations per answer: G2 disclosed in 85 % (87 %) of them, **G3 alone in 47 % (47 %)** (the difference of the two rates, and the total minus a document figure), G3 plus rate sides in 11 % (15 %). So G3 was not sufficient alone.

## 2. Implemented inside the approved scope

- Rule G3 in place of G2.
- Each rate needs both of its sides publishable; with both rates, also the retrieved-only difference. An empty group is not publishable (the approved convention). Dominance on rate sides now fires.
- Revised privacy note, claiming only what is demonstrated and saying what it does not cover.
- No contract shape change; descriptions corrected.

**Cost.** In classes of 8 / 12 / 20 / 40 with 3 documents and 10 % of answers without material, the share of reads keeping `no_material_rate` fell from 100 % to 2 / 11 / 50 / 96 %, and `no_cited_source_rate` from 89 / 64 / 71 / 100 % to 6 / 21 / 64 / 99 %.

## 3. Tests that had not detected the leaks

| Step | Result |
|---|---|
| New tests before the code change | 10 failed, 4 passed, 1 xfailed; the adversary found 225 rate differences, 133 hidden-citing counts and 120 cited counts determined |
| After the change | pass |
| Adversary after the second review: new target (with material, outside documents), determined zeros, a check that at least one world is consistent, a stratified generator with minimum counts of published rates | finds only the open complements and zeros; the three review reproductions are characterisation tests with their strict xfail property |

## 4. Mutation checks

23 mutants of the service, restored and checked by hash: all caught. The adversary alone caught 2 at first and 7 after being strengthened (it still relies on named scenarios for the others).

## 5. Second independent review (new agent, clean context)

Verdict **FAIL**: no Blocker, 3 Major, 4 Minor. 206 passed and 2 xfailed in its run; it did not run integration or frontend suites.

| Id | Finding | State |
|---|---|---|
| M1 | total, `no_material_rate` and a document figure isolate small groups or show there are none (V9); rule D does not fix it | **open**; characterised; D-Q23 |
| M1b | with two-document answers, a rate minus a figure isolates the answers citing only withheld documents (V10) | **open**; characterised; D-Q23 |
| M2 | contract, spec, design and docstring promised more than the code does | corrected; see section 6 |
| M3 | canonical documents still described G2 | corrected; see section 6 |
| m1, m2 | gaps and near-vacuity of the adversary for rate interactions | strengthened (section 3); intersections and bounds are still not targets |
| m3 | "0 % and 100 % are never given" false above ten thousand answers | wording corrected |
| m4 | an answer that loses its chunk ids during generation withholds the uncited rate | open question, availability only |

The review judged the new privacy note true for the implemented behaviour.

## 6. Verification of the corrections

The same reviewer verified them. M3 closed for the canonical documents. M2 not closed at that point, and one **new Major**:

| Id | Finding | State |
|---|---|---|
| N1 (Major) | `active_students` against the two weekly cells isolates students who asked in one week only; the design said it gave nothing exact, and D-Q23 (c) was claimed to close composition | **open**, now V11: reproduced as a test, declared in TD-069, contract and design; D-Q24 |
| Minor | two sentences said "none" is never told from "few"; unmarked superseded text in `design.md` and `tasks.md`; open zeros whitelisted too broadly in the property | corrected: sentences rewritten, superseded sections marked, and the property now requires that rates and cells alone determine nothing |

The reviewer confirmed the counts of the D-Q23 table, not the availability percentages (their simulator is outside the repository). It found that no canonical document still describes G2, and judged the claims about the document figures honest once N1 was declared. The corrections after N1 were **not** reviewed again.

## 7. Status by vector (in the branch)

| Vector | Status |
|---|---|
| V3 | mitigated |
| V6a | mitigated for unchanged data |
| V7 | mitigated |
| V6b | **open**: the uncited-rate channel is closed; V8 to V10 bound or determine withheld figures |
| F6 | **open** (no published cell, rate side or document figure is more than half one student's; complements are not covered) |
| F7, F8 | open |

## 8. Final gates and verification

| Gate | Result |
|---|---|
| `ruff check --no-cache`, `ruff format --check`, `mypy --strict app tests` | clean (305 source files) |
| `pytest tests/unit` (after the last change) | 1858 passed, 110 skipped, 5 xfailed (V2, and the strict properties of V8 to V11), 4 failed (host-only, the same as without this change) |
| `pytest tests/integration -m "not role_bound and not realmodel"` | 1042 passed, 39 skipped, 0 failed |
| Role-bound activity routes, empty disposable cluster | 5 passed, 1 skipped |
| Frontend `vitest`, typecheck, lint, format, API types, build | 681 passed, 1 skipped; clean |
| Playwright mocked and smoke, temporary server | 34 passed; the dashboard spec repeated 15 times: 75 of 75 |
| `openspec validate --all --strict` | 29 of 29 |
| Mutation checks | 23 of 23 caught, source restored by hash |
| Local demo (backend restarted, fictitious data) | three subjects walked, no browser error, no overflow at 320 px |

The integration run finished before the last edits, which changed docstrings, contract descriptions, unit tests and documents, not behaviour. The Linux-only tests were not run and need CI.

A Playwright failure appeared in this round: the sign-in helper of `teacher-activity.mocked.spec.ts` navigated before the redirect after login, which overwrote the navigation under load. The helper now waits for the session.

`docs/backend-standards.md` was not modified. The proposed diff is `reports/backend-standards-proposed.patch`.

## 9. Recommendation

**NO-GO to prepare the pull request with a claim that composition is closed.** V6b and F6 stay open (V8 to V10), and V11 is open. Decisions pending: D-Q23, D-Q24, D-Q22 (wording of the note) and the standards diff. A pull request that records those vectors as open is possible with the owner's explicit acceptance: it would still remove V7 from `main`. Enabling the capability stays NO-GO.
