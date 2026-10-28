# Magnitude Experiment Report (incident I3)

- Date: 2026-10-28
- Change: documents-schema-pgvector
- Agent: Claude Code (Sonnet 5.5), main session
- Purpose: define numeric limits for query vectors and stored embeddings only from reproducible evidence (user decision on I3).
- Report rule: no vector values; only scales, norms and error magnitudes.

## Setup and isolation

- Container `pgvector/pgvector:0.8.7-pg15` (PostgreSQL 15.19, pgvector 0.8.7) started with `--rm`, data on `tmpfs`, bound to `127.0.0.1:55439`, scratch database `spike`; throwaway Python 3.12 environment with `psycopg[binary]==3.3.6` in a temporary directory. No project database or container was touched.
- Both resources were destroyed afterwards: no `spike-pgvector*` container, temporary directory removed, nothing listening on 55439.
- Script (committed next to this report as `2026-10-28-magnitude-experiment.py`; it only connects to a scratch database on port 55439): the matrix below is reproduced by generating two seeded Gaussian directions of 384 components normalised to unit length, scaling them, and comparing `a <=> b` computed by PostgreSQL with `1 - dot / (|a| |b|)` computed in double precision on the single-precision-rounded inputs. Seeds 1 and 2.

## Matrix

`norm` is the Euclidean norm of the scaled vector (equal to the scale, as the direction has norm 1). "Single" compares the scaled vector with a unit vector; "both" scales both vectors by the same factor. Error is the absolute difference between PostgreSQL and the double-precision reference.

| norm | `vector_norm` | Single scaled vs unit | Both scaled |
|---|---|---|---|
| 1e-40 | 1.0e-40 | wrong (error 1.0) | `NaN` |
| 1e-38 | 1.0e-38 | wrong (error 1.0) | `NaN` |
| 1e-30 | 1.0e-30 | wrong (error 1.0) | `NaN` |
| 1e-25 | 1.0e-25 | wrong (error 1.0) | `NaN` |
| 1e-22 | 1.0e-22 | wrong (error 1.0) | `NaN` |
| 1e-21 | 1.0e-21 | 3.1e-05 | 9.7e-03 |
| 1e-20 | 1.0e-20 | 4.9e-09 | 1.4e-05 |
| 1e-19 | 1.0e-19 | 2.5e-08 | 4.4e-07 |
| 1e-18 | 1.0e-18 | 1.7e-09 | 1.5e-08 |
| 1e-15 to 1e-3 | exact | below 2e-8 | below 2e-8 |
| 1 | 1.0 | 2.9e-09 | 2.9e-09 |
| 1e3 to 1e18 | exact | below 3e-8 | below 7e-9 |
| 1e19 | 1.0e19 | 9.4e-09 | 4.2e-10 |
| 1e20 | 1.0e20 | 3.2e-03 | `NaN` |
| 1e30 | 1.0e30 | 3.2e-03 | `NaN` |
| 1e38 | 1.0e38 | 3.2e-03 | `NaN` |

Other observations:
- The zero vector gives `NaN` against any vector (no error).
- `vector_norm` itself stays correct for the whole range (it uses double precision); only the cosine distance degrades.
- A single large component keeps working while the norm is below about `1e19` (a vector with one component of `1e19` among `1e-3` ones gave a correct norm).
- With the hnsw index built over rows scaled from `1e-30` to `1e30`, the build succeeds, but a unit query then returns `0` distance for most rows and `1.0` for the `1e30` row, which is wrong (that row's true distance is 0): the extreme rows corrupt ordering silently rather than failing.

## Conclusions (evidence-based limits)

1. Failure is **silent** at both ends: below about `1e-21` the distance is a wrong number (single scaling) or `NaN`; above about `1e19` it is wrong or `NaN`. The earlier spike case (components of `1e-30` and `1e38`) is the same effect.
2. The cosine distance is accurate (error at most `1e-6` in every case, and at most `2e-8` between `1e-18` and `1e19`) for norms from `1e-18` to `1e19`.
3. Proposed limits, defined at the **norm** (all components are bounded by it): accept `1e-6 <= norm <= 1e6`. They keep twelve orders of magnitude of margin against the observed breakdown on the low side and thirteen on the high side, include every realistic embedding (unit-normalised outputs have norm 1; unnormalised sentence-transformer outputs have norms of the order of 1 to 20), and make a float32 overflow of any single component impossible.
4. Apply the same range in three places: the repository validation of the query vector (computed in double precision before any statement); the repository/service validation of embeddings before they are stored (applied by change 6 with the same shared helper); and a database CHECK `vector_norm(embedding) BETWEEN 1e-6 AND 1e6` on `document_chunks`, which also rejects the zero vector. The CHECK replaces the `vector_norm(embedding) > 0` CHECK validated in the spike (task 1.4); `vector_norm` was already verified as usable in a CHECK.
5. Normalised vectors (norm 1, including rounding to single precision) are inside the range with no special handling; no normalisation of inputs is introduced.

## Does this change a contract or the architecture?
No. The API contract is unchanged (no endpoint is added), the data model gains no column, and the CHECK that D8 already specified (zero norm) becomes a stricter range check with the same mechanism; the validation constants live in one module. The change is therefore folded into the artifacts through `/opsx:update` without asking for architecture approval, and the numeric limits are traceable to the matrix above.

## Residual risk
- The range is validated for 384-dimension vectors with Gaussian-like components; a vector inside the range with extremely uneven components (a few large values and very small others) was only checked for its norm (correct), not for cosine accuracy, and is not exhaustively explored; task 5.2 adds such a case. Recorded as a technical-debt candidate together with the HNSW tuning work (task 10.4).
- `pgvector` behaviour belongs to version 0.8.7; a version change must repeat this matrix (it is a short script) and is part of the image-pin documentation (task 2.2).
