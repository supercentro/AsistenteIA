# Group 4 Report - Deterministic Fixtures (tasks 4.1, 4.2)

- Date: 2026-10-28
- Change: documents-schema-pgvector
- Agent: Claude Code (Sonnet 5.5), main session
- Scope: test helpers only (`backend/tests/`). No production code, no CLI seed change, no migration, no repository (`find_similar` is group 5). No embeddings or document text of real data appear here.

## Preflight
Branch `feature/documents-schema-pgvector`, HEAD `cf01f44`, clean tree; PR #7 open, `MERGEABLE`/`CLEAN`, CI green; `openspec validate --strict` valid, 13 of 13. The exact tasks of group 4 (4.1 and 4.2) are inside the approved scope; nothing had to be reported.

## What was built
- `tests/embeddings.py`: pure functions on 384-dimension vectors (`basis`, `negate`, `scaled`, `at_angle`, `deterministic_vector`, `cosine_similarity`, `to_literal`). Standard library only (a test parses the module imports); no model, network or randomness other than SHA-256 of the seed.
- `tests/catalog.py`: `build_catalog(url)` inserts, by SQL, 2 teachers, 3 students (enrolled in two subjects, in one, in none), 3 subjects (two owned by one teacher), 6 documents covering every status, and 12 chunks with known similarities to the query (axis 0). Ready Algebra chunks sit at 10, 30, 45, 60, 90 and 180 degrees (similarities 0.985, 0.866, 0.707, 0.5, 0.0, -1.0, strictly descending). Algebra also holds `pending`, `processing` and `failed` documents with chunks exactly on the query, and Physics and Chemistry hold chunks strictly nearer to the query than any ready Algebra chunk: the traps for group 5.
- Content is neutral (`fixture chunk <file> <n>`) and the users use `@fixtures.example.com`.

## Verification
- 25 new test cases (12 unit functions, 7 of them parametrised, and 8 integration tests): documented cosine similarity of named vectors (orthogonal 0, identical 1, opposite -1, 45 degrees 0.7071, 30, 60, 90), unit length, 384 finite non-zero components, reproducibility within and across processes (three hash seeds), argument validation, standard-library-only imports; and, against PostgreSQL, the structure of the catalog (counts, enrollments, statuses, subject coupling of every chunk, norm 1 within `1e-6`), the database cosine similarity equal to the Python value within `1e-6` for the ranking of ready Algebra chunks, the traps above, building the catalog twice giving identical embeddings, and neutral content.
- Gates: `ruff check`, `ruff format --check`, `mypy --strict app tests` clean (100 files); `pytest` 587 passed; coverage of `app` 98 %; `pip-audit` clean. Seed tests unchanged and green.
- TDD evidence and mutation checks (7 of 7 killed): `2026-10-28-tdd-evidence.md`.

## Risks and notes
- The pinned fingerprint of `deterministic_vector(7)` guards against accidental changes only (derived from the implementation).
- The catalog is a test aid and is not a seed: demo data for E2E is decided in change 12 or 13.
- Group 5 will add filler subjects for the many-subject recall test using the same helpers.

## Outcome
- Tasks 4.1 and 4.2: PASS. Groups 5 to 12 not started.
