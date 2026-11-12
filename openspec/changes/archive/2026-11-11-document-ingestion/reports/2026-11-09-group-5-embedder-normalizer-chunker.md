# Group 5: embedder, normaliser and chunker

Date: 2026-11-09. Branch `feature/document-ingestion`. Tasks 5.1, 5.2 and 5.3. No database, endpoint, worker or repository code: three modules under `backend/app/rag/` and their tests.

## What was added
- `app/rag/embedder.py` (task 5.1)
  - `Embedder` and `TokenCounter` protocols; `FakeEmbedder` (deterministic hashed bag of words, 384 components, unit norm, so end-to-end tests can check retrieval order without the model); `LocalEmbedder`; `startup_check`; `build_embedder(settings)`.
  - `LocalEmbedder.load` checks the model directory first (nothing is imported when it is missing), imports `torch` lazily, **sets the thread count**, loads `SentenceTransformer` on the CPU, verifies 384 dimensions and `max_seq_length` 128, and finally embeds a probe text through `validate_embedding`.
  - There is **no fallback**: any failure raises `EmbedderStartupError`; the fake embedder is built only when the settings allow it (`APP_ENV=test`, or `ALLOW_FAKE_EMBEDDER=true` outside production), and `build_embedder` repeats that check so a bypassed settings validation cannot put it in production (`EmbedderConfigurationError`).
  - `embed` returns the single-precision values returned by `validate_embedding` (what the database stores). Errors are fixed text raised `from None`: `EmbeddingError` (document `EMBEDDING_FAILED` in group 8) and never the input, a path or the library message. Nothing is logged.
  - `count_tokens(text, include_special=...)` uses the model tokenizer; special tokens add exactly two (verified with the real model).
- `app/rag/normalizer.py` (task 5.2, resolves the content part of TD-027): `normalize_text` and `has_visible_text`. NUL and every other C0/C1 control, DEL and lone surrogates are removed; the twelve bidirectional controls are removed; line and paragraph separators, "next line", vertical tab and form feed become line feeds; `\r\n` and `\r` become `\n`; Unicode space characters become plain spaces; tabs and line feeds are kept; zero width and other format characters (for example the joiner of emoji sequences) are kept but never count as visible; combining marks alone are not visible; surrounding whitespace is trimmed and text without a visible character becomes the empty string. The source uses code points (no raw invisible characters in the repository).
- `app/rag/chunker.py` (task 5.3): `Page`, `Chunk`, `chunk_pages`, `TooManyChunksError`, `ChunkTooLongError`. `RecursiveCharacterTextSplitter` (imported lazily) with the model token count without special tokens as length, size 100, overlap 20, separators paragraph, line, sentence, space, character. Pages are split on their own (a chunk never crosses a page, `page_number` is kept, `None` for text), blank pieces are dropped, indexes are global and consecutive, the cap of 2,000 chunks raises `TooManyChunksError` as soon as it is exceeded, and every chunk is measured again **with special tokens**: above 128 it is re-split (at whitespace near the middle, else by characters) and an unsplittable fragment raises `ChunkTooLongError`.
- `pyproject.toml`: marker `realmodel` registered and excluded by default (`-m 'not realmodel'`).

## TDD evidence
Tests written and committed before the modules (`e73d1fe`):
- `test_normalizer.py` (73 cases), `test_chunker.py` (26), `test_embedder.py` (36), plus `test_embedder_realmodel.py` (5) and `test_chunker_realmodel.py` (11, parametrised by text kind).
- **Failing run before the implementation**: 3 collection errors, `ModuleNotFoundError: No module named 'app.rag.normalizer'`, `... 'app.rag.chunker'` and `ImportError: cannot import name 'embedder' from 'app.rag'`; the real-model files failed the same way.
- **After the implementation**: 134 passed (`test_normalizer`, `test_chunker`, `test_embedder`) and **16 real-model tests passed** inside the `worker` image (below).
- The thread-order test uses fake `torch` and `sentence_transformers` modules injected into `sys.modules` and asserts the event sequence `threads`, `load`, `encode` (the startup probe); another test proves the quota is used (`detect_cpu_quota` patched to 2 gives `("threads", 2)`) and that an explicit `EMBEDDING_THREADS` wins.

### Mutation checks (25 mutations of the three modules)
Each mutation was applied to the source, the three unit test files were run, and the file was restored. All were detected after two test improvements:

| Module | Mutations detected (tests failing) |
|---|---|
| normaliser | keep C0/C1 controls and NUL (12), keep lone surrogates (2), keep bidirectional controls (13), keep Unicode spaces (16), line separators not turned into line breaks (5), carriage returns kept (1), no trimming (1), blank text not emptied (3), combining mark alone counted visible (1) |
| chunker | no runtime guard (2), no chunk cap (3), no overlap (3), indexes from 1 (9), page number lost (8), overlap not validated (1) |
| embedder | threads never set (3), dimension not checked (1), sequence length not checked (2), no startup probe (4), missing files not detected early (3), vectors not validated (6), invalid vector not mapped (1), exception chain kept (1), fake allowed anywhere (1) |

Test improvements that came out of the mutations (not of the implementation): the exception-chaining assertion was too weak (an implicit chain sets `__context__`, not `__cause__`) and now also checks `__suppress_context__`; a model that reports another dimension while its vectors look right, and the message of an invalid vector, are now asserted. One mutation (skipping blank pages at page level) could never be detected because the piece-level check made it redundant; the redundant check was removed instead of tested.

An incident of the process: a first mutation run reported every mutation as "killed" because my strengthened assertion made the unmutated baseline fail on one case; I noticed the pattern (the same single failure for unrelated mutations), fixed the assertion and reran. The numbers above are from the clean run.

### Real model (marker `realmodel`)
Run in the `asistenteia-worker` image (model baked in, hub offline, 4 CPUs, 2 GB) with the current `app` and `tests` mounted read-only and `pytest` installed in a temporary directory inside the container: **16 passed**, also with `FutureWarning` treated as an error after the dimension method was updated.
- Embedder: Spanish and English texts give 384 valid components; the same text gives the same vector (within 1e-5); related text is closer than unrelated text; special tokens add exactly two for Spanish, English, Japanese and emoji; the model needs chunks to fit (a text of more than 128 tokens is detected).
- Chunker with the real tokenizer and **no chunk above 128 tokens with special tokens** for: Spanish prose, one very long word, a run of 6,000 characters, URLs, digits, emoji with joiners, Japanese, Arabic, a mixed text and source code. Ordinary Spanish prose is chunked at no more than 100 tokens (without special) with an average of at least 60.
- `sentence-transformers` 6 renamed `get_sentence_embedding_dimension` to `get_embedding_dimension`; the loader uses the new name when present and the old one otherwise.

## Quality gates
- `ruff check`, `ruff format --check`, `mypy --strict app tests`: clean.
- `pip-audit`: no known vulnerabilities (no dependency change).
- API contract and frontend types: untouched, so the frontend gates were not run again (group 4 ran them).
- Strict xfail of the real-application contract test: still `xfailed`, reason "The document routes are implemented in group 9 (task 9.1)"; the routes do not exist yet (`GET/POST /subjects/{id}/documents` are absent from the application document), as `--runxfail` showed in group 4.
- Full backend suite and coverage: see the end of this file.

## Deviations and notes
1. The fake embedder counts words (not model tokens) so the chunker tests are exact; the real tokenizer is exercised only by the `realmodel` tests, which CI does not run (design D3). They were run in the worker image for this report.
2. `Embedder.embed` does not batch by itself beyond passing `batch_size` to the model; the worker (group 8) decides how many texts it sends per call and renews the lease between calls.
3. `normalize_text` does not apply Unicode normalisation forms (NFC/NFKC): the specs do not ask for it and it would alter stored text.
4. The chunker does not truncate or pad: the re-split pieces after the guard lose the overlap between them (documented in the code).
5. The `Embedder` instance is not thread-safe by contract; the worker uses one.
6. Group 5 touches no database; the development database is still at `0004` and `asistenteia_test` is empty after the suite.

## Full run
Backend suite on the isolated test database: **981 passed, 16 deselected (the `realmodel` tests), 1 xfailed** (the strict xfail of the real-application contract test), 2 warnings, 162 s; 846 before this group plus 135 new passing tests. Coverage of `app`: **98 %**; `rag/normalizer.py` 100 %, `rag/embedder.py` 99 %, `rag/chunker.py` 98 % (one unreachable defensive line each in `embedder` and `chunker`). `asistenteia_test` has no tables afterwards; the development database `asistenteia` is still at revision `0004`.

## CI incident after the first push (`85cdaa7`)
The `backend` job failed at the lint step: three test files (`test_chunker.py`, `test_chunker_realmodel.py`, `test_embedder_realmodel.py`) had an import block that `ruff` (rule `I001`) wanted sorted differently. Locally `ruff check` had passed because its cache held the result from before `app.rag.*` existed (the first-party classification of those imports changed once the modules were created); `ruff check --no-cache` reproduced the failure. Fixed with `ruff check --fix` (import order only) and a new commit; every later local gate uses `--no-cache`. No behaviour changed.
