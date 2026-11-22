# rag-source-attribution slice 1: independent adversarial review (2026-11-21)

Independent read-only subagent, clean context; it ran the 115 unit tests and about 25 spoofing and ReDoS probes. **Verdict: PASS WITH GAPS** (no Blocker, no Major).

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | Minor | Unicode channels (zero-width, fullwidth brackets) are closed only by the call order (`neutralize_delimiters` strips Cf and applies NFKC before `neutralize_markers`); no test proved it | Fixed: `test_disguised_markers_leave_no_citation_in_the_history_or_the_chunks` (5 disguises) fails if the order is reversed (checked by mutation) |
| 2 | Minor | Arabic-Indic digits match `\d`, are neutralised and are also read as citations | Accepted: same as the old pattern, not a regression; neutralising is the safe direction |
| 3 | Minor | A marker in the current question is left as typed (by design); a model may echo it | Accepted and written in TD-062 |
| 4 | Minor | Code comment said "no spaces next to the brackets" while spaces around a comma are allowed | Fixed (comment) |
| 5 | Minor | `[1,2,]`, `[1,,2]` are neither read nor rewritten (consistent) but untested | Fixed: test added |

Verified clean by the reviewer: no ReDoS (100k-character inputs in about 0.1 s), padding and size limits agree on both sides, delimiter neutralisation cannot create a marker nor the reverse, forged labels are rewritten, the new pattern is a strict superset of the old one (no regression), the harness uses the production functions, TD-062 and `api-spec.yml` stay true. Limit: it did not read the delta spec line by line.
