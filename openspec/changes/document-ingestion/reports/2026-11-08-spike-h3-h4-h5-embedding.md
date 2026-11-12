# Spike H3, H4 and H5: CPU and memory, Spanish retrieval, vector compatibility

Date: 2026-11-08. Tasks 1.3, 1.4 and 1.5. All runs: final-candidate worker image environment, model from the pinned revision, `--network none`, `--memory 2g`, `--pids-limit 200`, CPU quota as stated. Scripts: `reports/spike-scripts/h3_h4_h5.py`, `corpus_es.py`, `h5_pg.py`.

## H3. Throughput, memory and threads

512 chunks of exactly 100 model tokens (102 with special tokens), taken from the Spanish corpus.

| CPU quota (threads set to the quota) | batch 8 | batch 16 | batch 32 | batch 64 | 2,000 chunks at best |
|---|---|---|---|---|---|
| 4 CPUs | 39.3 chunks/s | **40.1** | 34.5 | 32.4 | **49.9 s** (batch 16) |
| 2 CPUs | **27.1** | 26.5 | 25.1 | 22.9 | **73.9 s** (batch 8) |
| 1 CPU | 16.7 | **17.3** | 16.9 | 14.6 | **115.9 s** (batch 16) |
| 4 CPUs, but torch left at its default of 16 threads | 1.2 | 2.7 | 4.9 | 6.0 | 332 s at best (1,662 s at batch 8) |

- **Critical finding:** under a container CPU quota, `torch` still sees all host cores and starts 16 threads. With the quota of 4 CPUs this made embedding about **33 times slower** at batch 8 (1.2 against 39.3 chunks/s). The worker must set the number of `torch` threads to the CPU quota (read from the cgroup, or an explicit setting) before the first inference. This also explains a slow first measurement in H2 (4.3 s for two texts).
- Memory: resident set after loading about 800 MB; peak (`VmHWM`) 1.16 GB at batch 8 to 16, 1.21 GB at 32 and **1.32 GB at 64**, inside a 2 GB limit that was never reached. The out-of-memory ceiling below 2 GB was **not** measured (only one ceiling was tried); a limit of 2 GB is validated, 1.5 GB is untested.
- Best batch size: 16 (never worse than 3 % below the best, and lower peak memory than 32 or 64).
- Extrapolation for a document of 2,000 chunks: about 50 s with 4 CPUs, 75 s with 2, 2 minutes with 1, plus up to a few seconds of PDF parsing (see H6).

## H4. Spanish retrieval (calibrated, no absolute threshold)

Corpus written for the spike by the assistant: 60 passages (20 each in three subjects: artificial intelligence, databases, contemporary history of Spain; each passage has at most 100 tokens, since 60 passages gave 60 chunks at size 100) and 45 questions, each a paraphrase of one passage (no copy of its wording). Limits of this evaluation: one author wrote passages and questions; 45 questions give wide intervals; every passage is shorter than one chunk. Ranking is within the subject, as `find_similar` does.

| Method | Hit@1 | Hit@3 | MRR |
|---|---|---|---|
| Dense (cosine, this model) | 0.689 [0.56 to 0.82] | **0.889** [0.80 to 0.98] | 0.798 [0.71 to 0.89] |
| Lexical BM25 (accent-folded, stop words removed) | 0.622 [0.49 to 0.76] | 0.756 [0.62 to 0.89] | 0.732 [0.62 to 0.83] |
| Random order | 0.089 [0.02 to 0.18] | 0.178 [0.07 to 0.29] | 0.207 [0.14 to 0.29] |

(95 % bootstrap intervals, 4,000 resamples.) Ranking across all three subjects together: dense 0.689 / 0.889 / 0.795 against BM25 0.556 / 0.733 / 0.671 and random 0.022 / 0.089 / 0.081.

- The dense method is better than the lexical baseline on every measure, but the intervals overlap (Hit@3: 0.80 to 0.98 against 0.62 to 0.89); this corpus cannot prove a difference. Both are far above random.
- Five of the 45 questions missed the top 3 (ranks 5 to 9), for example a question about "correcciones por capa" (back-propagation) and one about "gobernar con apoyo del rey" (Primo de Rivera), which use words far from the passages.
- Cosine similarity: relevant passages median 0.556 (p10 0.425, p90 0.681, max 0.744); irrelevant passages of the same subject median 0.285 (p10 0.137, p90 0.438, max 0.630). Only 73 % of the relevant passages exceed the 95th percentile of the irrelevant ones, so a fixed `MIN_SIMILARITY` between about 0.35 and 0.45 would trade lost answers against off-topic ones. This is information for change 9, not a decision.
- **Chunking effect** on long documents (each subject's passages joined into five-passage documents, 12 documents, a hit counts only if the part of a chunk the model can see overlaps the expected passage):

| Chunk size / overlap (tokens) | Chunks | Chunks over 128 tokens | Hit@1 | Hit@3 |
|---|---|---|---|---|
| 60 / 12 | 68 | 0 | 0.622 | **0.889** |
| **100 / 20 (approved)** | 41 | 0 | 0.556 | 0.800 |
| 200 / 40 | 24 | 14 | 0.400 | 0.667 |
| 400 / 40 | 12 | 12 | 0.244 | 0.378 |

  Chunks above 128 tokens lose quality because the model ignores the tail (see H5). Smaller chunks did better on this small test; 100/20 is acceptable, 60/12 is an option to re-test with a larger corpus before fixing it.
- No pass mark was applied. The numbers are for the user's decision.

## H5. Compatibility of embeddings

- 112 vectors (60 passages, 45 questions and 7 edge texts: `"a"`, a space, `"0"`, 50 inverted question marks, 2,000 `x`, a repeated word, 200 emoji): shape (112, 384), `float32`, norms from **2.56 to 6.74** (median 3.76). Inside the accepted range `1e-6` to `1e6` by many orders of magnitude.
- `validate_embedding` (copy of `backend/app/core/vector_validation.py` at `3960132`): **0 failures** out of 112.
- On a scratch PostgreSQL (pgvector 0.8.7) with a table that has the same `vector_norm(embedding) BETWEEN 1e-6 AND 1e6` check, binding the validated values: 112 inserted, **0 rejected by the check**, 0 vectors accepted by the helper and rejected by the database; stored norms 2.5609 to 6.7425; the cosine search in PostgreSQL returned the same vector first (similarity 1.0).
- **Silent truncation confirmed:** for a text of 319 tokens the cosine between its embedding and the embedding of only its first 126 tokens is **1.000000**; the discarded tail alone has cosine 0.62 with the full text. Everything beyond the first 126 tokens is ignored, which justifies the chunk limit and the runtime guard of the design.
- The warning "Token indices sequence length is longer than ... (156 > 128)" appears when a text over 128 tokens is tokenized; the chunker's re-measurement must therefore not rely on the model to complain.
