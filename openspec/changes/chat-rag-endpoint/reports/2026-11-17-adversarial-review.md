# Adversarial review: chat-rag-endpoint

**Date**: 2026-11-17
**Reviewer**: independent clean-context subagent (read-only; it did not implement the change). Findings were then verified in code by the implementing session before fixing.
**Scope**: authorization, SQL, GDPR, secrets, prompt injection, citations, migration 0007, transactions, tests.
**Limits of the review**: the reviewer did not run the pytest suites, did not run migration 0007 up/down, did not do a deep review of Dockerfile/compose/`.dockerignore`, and read test names rather than bodies. Axes 7 and 9 are only partly covered. No SQL injection vector was found in the code it read (parameterised queries only).

## Findings and status

| # | Severity | Finding | Verified | Status |
|---|---|---|---|---|
| 1 | Major | A `conversation_id` of the same student but another subject was accepted, and ownership was checked only after the LLM call | yes (`rag_service.py`) | **Fixed**: lookup bound to `subject_id` and done before embedding/LLM. Tests: `test_foreign_conversation_is_rejected_before_embedding_or_llm`, `test_conversation_lookup_is_bound_to_the_subject`, integration `test_chat_conversation_of_other_subject_returns_404`. Failing run recorded first (17 failures across findings 1-4), mutation checked |
| 2 | Major | Conversation history was never loaded (`_load_history` returned `[]`) | yes | **Fixed**: history read through the student-scoped `list_by_conversation`. Test `test_previous_messages_reach_the_llm`; mutation checked. Also fixed an ordering defect found while doing it: messages of one turn share `created_at`, so ordering now ties-break on role (user first); test `test_messages_of_one_turn_are_returned_user_first` |
| 3 | Major | Delimiter neutralisation bypassed by `</CONTEXT >`, `< /CONTEXT>`, zero-width and fullwidth forms, attributes | yes (probe) | **Fixed**: NFKC + removal of format characters + tolerant pattern (`prompt_builder.py`); 7 bypass tests; mutation checked |
| 4 | Major | Whitespace-only message accepted (spec says 422) | yes (probe) | **Fixed**: trimmed, visible text required (`schemas/chat.py`); tests in `tests/unit/test_chat_schema.py` and integration |
| 5 | Major | Response contract differs from `docs/api-spec.yml`: spec `Source` has `filename`, `document_id`, `snippet`; code returns `document_filename`, no `document_id`, an extra `score`; history sources have no `snippet` | yes | **Open: owner decision.** `docs/` owns the contract. Options: (a) amend `api-spec.yml` to the implemented shape; (b) align code (rename to `filename`, add `document_id` and snippet snapshot, which needs a migration). Not changed silently |
| 6 | Major | The conversation-history OpenSpec spec says migration 0007 grants SELECT/DELETE to `asistente_cli` on all three tables; the grants actually come from `db_privileges.MATRIX` (CLI: SELECT/DELETE on `conversations`, SELECT on `messages`, nothing on `message_sources`), which agrees with `docs/data-model.md` | yes | **Open: owner decision.** Code and `data-model.md` agree with each other; the OpenSpec requirement text diverges. Needs a spec update (`/opsx:update`) or a matrix change |
| 7 | Major | The DB connection/transaction stays open during the LLM call (up to the timeout); embedding and queries are synchronous inside an `async` endpoint; the LLM client is built per request | yes (code) | **Open: architectural, owner decision.** Fix means releasing the transaction before the LLM call and/or moving sync work to a thread pool, which changes the transaction model approved in the design (explicit commit pattern). Not changed. Proposed as a follow-up change or accepted debt |
| 8 | Minor | Design D7 logs (ID-only request/no-material/complete) not implemented | yes | Open (minor) |
| 9 | Minor | Consent compared inline instead of the existing `has_current_consent` helper | yes | **Fixed** |
| 10 | Minor | Safety block detected by text match on the exception message | yes | Open (minor) |
| 11 | Minor | Missing negative tests | partly | **Fixed** for findings 1, 3, 4 and history; concurrent double-submit on one conversation not covered |
| Q1 | Question | Does the privacy text disclose sending questions and chunks to Google (Gemini)? | no | Owner |
| Q3 | Question | `last_message_preview` is never populated by the list endpoint (`GET /conversations` returned `null` in the manual run) | seen in curl run | Owner / spec check |
| Q4 | Question | Consent is checked before enrolment, so a non-enrolled student without consent gets 403, not 404 | yes | No leak; informational |

## Also found while closing the tasks (not from the reviewer)

- `docs/api-spec.yml` says a non-enrolled student gets 403 on chat; the implementation, tasks and tests use 404. Contract divergence, not changed.
- `docs/api-spec.yml` still says "recorded consent" where TD-003 asked for "consent for the current policy version".

## Update 2026-11-17 (round 2)

Findings 1-4 fixed earlier; 5 (contract), 6 (privileges) and the 403 decision are resolved in `2026-11-17-round2-findings-matrix.md`. Finding 7 remains open (owner decision).

## Verdict

Reviewer verdict on the original code: **FAIL** (Majors 1-7).
After fixes of 1-4 (and minors 9, 11): **FAIL remains** because Majors 5, 6 and 7 are open and need owner decisions (contract, spec, transaction model). Per base-standards 9.8, a change is not closed with an open major finding. Archiving is **not advisable**; opening a PR is **NO-GO** until 5-7 are decided.
