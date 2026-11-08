# EXPLAIN plans and recall of `find_similar` (task 5.4)

Date: 2026-11-07. Environment: scratch database `asistenteia_g5_scratch_test` (created and dropped by the script, migrated to `0004`) on the local PostgreSQL 15 + pgvector 0.8.7 container. Planner and pgvector settings were the defaults (`enable_indexscan=on`, `enable_seqscan=on`, `hnsw.ef_search=40`, `hnsw.iterative_scan=off`, `random_page_cost=4`); nothing was changed in code (design D3).

## Method
- Dataset (`tests/retrieval_support.py::build_mixed_dataset`): one target subject with 60 ready chunks 30 to 148 degrees from the query, plus N other subjects whose chunks are all 1 to 19 degrees from the query (strictly nearer than any target chunk). The target is therefore never in the global top results: the case where an approximate index with a post-filter loses rows.
- Reference: exact ranking of the target subject computed in Python (double precision) from the same vectors.
- Search: the real `ChunkRepository.find_similar` as a student enrolled in the target subject, `top_k` 5, 20 and 50. The executed statement was captured and re-run under `EXPLAIN (ANALYZE, BUFFERS)`.

## Results

| Dataset | Chunks | Other subjects | Returned (top_k 5/20/50) | Recall | Same order as exact | Execution time of the plan |
|---|---|---|---|---|---|---|
| small | 1,060 | 40 | 5 / 20 / 50 | 1.00 | yes | 0.31 ms |
| medium | 10,060 | 200 | 5 / 20 / 50 | 1.00 | yes | 1.07 ms |
| large | 30,060 | 600 | 5 / 20 / 50 | 1.00 | yes | 2.63 ms |

Plan with default settings, identical in the three sizes: `Limit` over `Sort` over a nested loop of `Seq Scan on documents` (status `ready`) and `Bitmap Heap Scan on document_chunks` combining `ix_document_chunks_subject_id` and `uq_document_chunks_document_id`; the enrollment check is an `InitPlan` using `uq_enrollments_subject_id`. **The HNSW index (`ix_document_chunks_embedding`) is not used.** The query is filter-first and exact, as D3 intends.

## Why HNSW is not used and what that means
- The statement orders by `embedding <=> :query, id` (the `id` tie-break makes the order deterministic). pgvector's index scan can serve only an `ORDER BY embedding <=> const` without a second key, so the planner cannot choose it. An index-forced experiment (rolled-back `SET LOCAL enable_seqscan/bitmapscan/sort = off`, evidence only) also did not select the HNSW index for the same reason and returned the 50 rows by b-tree index scans.
- Consequence: the MVP search is exact, so there is no recall loss and no incomplete result; the HNSW index exists (ticket requirement) but is currently unused. Its write cost is paid at ingestion without a read benefit. This is residual information for change 12 or later, not a defect.
- Cost grows with the rows of the subject (all of them are read and sorted), not with the table. For the MVP corpus (tens of documents per subject) the measured time is milliseconds.

## Decision
No stop condition of the authorization was reached: recall is 1.00 and results are complete. No alternative needs approval now. For the record, if a subject ever grows so large that the exact sort is slow, the options to present then are: keep exact search, build an index per subject, or drop the secondary sort key and use `SET LOCAL hnsw.iterative_scan = strict_order` inside the statement transaction (D3), each with its own recall measurement.

## Reproduction
`scratchpad/explain_recall.py` (not committed; it needs the compose `db` service running). The recall check in the repository is `tests/integration/test_chunk_retrieval.py::test_results_are_complete_with_many_subjects_and_equal_the_exact_search` (1,060 chunks, 40 subjects).
