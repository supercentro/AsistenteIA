# Validation of rule G (V6b) — 2026-11-25

Analysis and characterisation only. No product code, contract, database or switch was touched; no Gemini call.

## Method and its limits

| Part | What ran | Not covered |
|---|---|---|
| Characterisation of V6a, V6b, V7 and of deletions | The unmodified source of `app/services/activity_service.py` and `app/services/prompt_builder.py`, loaded with the system Python (`python -I -B`), with plain stand-ins for the schemas, repositories and errors; in-memory facts | pydantic validation, SQL, the HTTP layer, the test suite |
| Adversary of rule G | A model of the same arithmetic, seeded random subjects | it is not the service: G is not implemented |

The project interpreter is blocked by an application-control policy on the host and was not circumvented. The throwaway scripts live outside the repository and are not durable; the reproductions below are enough to rewrite them as tests (task 3.1a). The facts that a deleted document leaves a source without identifier come from the model (`message_sources.chunk_id` is `ON DELETE SET NULL`) and the repository query; they were not exercised against a database. No unique constraint or upload check on file names was found; a duplicate upload was not exercised end to end.

## Reproductions on the real service source

| Vector | Setup | Result |
|---|---|---|
| V6a | 12 weeks, six students each, week 5 with four students and 28 questions | cell null; rates 0.138 and 0.331 leave the candidates 13, 28, 49, 107 for the withheld total |
| V6b | `p.pdf` cited 18 times by 6 students, `x.pdf` 3 times by 3 | `x.pdf` null; cited answers from the rate 21, minus 18, gives 3 |
| V7 | two documents named `notes.pdf`: one cited by 6 students (figure 6), one by 3 (null) | after deleting the first: 6; after deleting the second: one entry with 9; withheld figure = 3 |
| V7 against G | same | before: one withheld cited document (G withholds the rate); after the merge: none (G publishes it) |

## Adversary against G (model)

The teacher knows the response, which current documents are new and how many were deleted. A leak is a volume attributed to one document.

| Scenario (about 2 400 reads each) | No rule | G |
|---|---|---|
| several citations per answer | 0.2 % | 0 |
| one citation per answer | 22.5 % | 0 |
| a new document beside the cited withheld one | 0.3 % | 0 |
| one deleted document, distinct names | 0.1 % | 0 |
| a heavy student (dominance) | 1.5 % | 0 |
| 6 old, 2 new, 2 deleted documents | 0 | 0 |

The adversary only uses the direct subtraction. A zero here is not a proof, and it did not use repeated names, which is where G fails (V7).

Mutants of G: ignoring dominance and counting documents without appearances were caught by some scenario; ignoring deleted documents was **not** caught (0 events); `at least one` leaks nothing by construction. Random properties alone are therefore not enough.

## Deletions (real service source, 3 000 random subjects with repeated names)

Share of subjects in which a read after a deletion shows something that the previous read did not: today 61.4 %, G 61.4 %, G2 0 %. The names were drawn from a small set to force collisions, so the percentage measures the defect when names repeat, not how often they do. G and G2 are applied here to the real outputs, not implemented. Dominance is not in `main` and was not part of this run.

## Residuals

- One bit when exactly one withheld current document is listed: the rate status matched "it was cited" in all 1 277 such modelled reads.
- Erasure: one random student erasing flipped the rate from null to published in 577 of 6 000 modelled subjects; the bound on another withheld document was exact in 73 of them.
- Sum of two or more withheld documents, and an estimate from totals under the assumption of one citation per answer (reasoned, not measured).

## Verdict

Rule G as written is insufficient (V7). Recommended: G2 (do not list deleted documents; null uncited rate when a deleted document was cited or exactly one withheld current document was). Pending the owner: D-Q17, D-Q18, D-Q19 in `design.md`. V7 exists in `main`; the capability is switched off and must stay so.
