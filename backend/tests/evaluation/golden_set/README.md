# Golden set of the RAG evaluation (v0.1, draft)

**Everything here is fictitious.** The documents are short Spanish study notes about three
invented courses (artificial intelligence, databases, history of Spain); there are no real students,
teachers, institutions, personal data or secrets.

- Authorship: the 60 passages and the 45 self-contained questions come from the spike of the
  `document-ingestion` change (written by the assistant, 2026-11-08); the rest (unanswerable
  questions, follow-ups, traps, injection and isolation cases, four extra documents) were written by the
  assistant for `rag-golden-set-evaluation`. One author, like TD-033: the set measures regressions and
  relative improvements, not absolute quality on real courses.
- Review: **pending the owner's review**. Do not treat the version as final before it.
- Layout: `corpus/<subject>/<file>.md`, `cases.json`, `VERSION`.
- Cases: 76 (45 answerable, 10 unanswerable, 8 follow-ups, 2 marker-in-document traps, 2
  stale-marker-in-history traps, 1 prompt-injection question, 2 injection-in-document, 3
  cross-subject, 3 without access: two not enrolled anywhere and one enrolled in another subject). 49 are marked `model: true`, the ones the answers mode may send
  to the model, so that one run never needs more than 50 calls.
- Judging: each case lists the passages that are acceptable evidence (`passage_contains`, compared
  without case or extra whitespace); no model grades another model.
- Injection documents contain the text "HACKEADO" and "PWNED" on purpose.
