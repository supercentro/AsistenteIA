# TDD Evidence

- Date: 2026-11-28
- Change: frequent-questions-and-topics

## Failing runs recorded before the code

| Tests | Result before the code |
|---|---|
| `tests/integration/test_migrations_topics.py` | 10 failed (no tables) |
| `tests/unit/test_topic_privileges.py` | 4 failed (no grants) |
| `tests/unit/test_topic_rules.py` | collection error: `No module named 'app.schemas.topic'` |
| `tests/unit/test_topic_ranking_service.py` | collection error (module missing) |
| `tests/unit/test_bookmark_topics.py` | collection error (module missing) |
| `frontend` topic page tests | 2 files failed to load |

## Deviations

- The integration tests of tasks 2.2, 3.2, 3.3 and 6.3 were written before the code but not run before it.
- The real-process Linux tests of the PDF child, the role-bound route test, the real-PDF ingestion test, the Playwright spec and three late tests (pool of one, delete during a write, child out of memory) were written after the code.
- The baseline integration run is not usable: migration 0009 was added while it ran (6 migration tests failed for that reason). The reference baseline is the green CI of `main` (run 46077967343).

## Compensation: mutation checks

Each guard was removed, the tests that should notice were run, and the file was restored byte for byte.

| Removed guard | Result |
|---|---|
| marker never set | caught (4 failed) |
| marker may move back | caught (1) |
| ranking ignores the document start | caught (2) |
| no minimum group per topic | caught (1) |
| retrieved sources count | caught (1) |
| document read without the owner | caught (2) |
| topics switch ignored | caught (2) |
| overlap accepted | caught (1) |
| stale revision accepted | caught (3) |
| no row lock on write | caught (1) |
| bookmark failure fails the document | caught (5) |
| deadline not respected | **survived** at first: the test double raised inside a catch-all (lesson L53). Test fixed; then caught (1) |
| bookmarks read for text files | caught (2), after the same fix |

## Defects found by the gates during implementation

Privilege inventory (dynamic update values hid a column; method names clashed with built-ins), 48 type errors and one Linux-only unit failure, two accessibility lint errors, one false positive of the wording test, one unused type ignore.


## Corrections after the independent review

Failing runs recorded before the code:

| Tests | Result before the code |
|---|---|
| Delete between the checks of a write | 409 `no_pages` instead of 404 |
| Invisible titles (schema) | 6 failed: no error raised |
| Invisible bookmark title | kept instead of dropped |
| No message read without topics | `questions` and `answers` were read |
| Editor: failed reload, save in flight, focus on cancel, title length | 4 failed |

The tests of the snapshot, the repository scope, the status filter and the minimum of active students passed on the existing code, which already had those guards. They were checked by mutation on a copy of the tree: replacing the snapshot with the request session, removing the teacher scope of `document()`, `last_page()`, `stored()` and `material()`, removing the `ready` filter and removing the minimum of active students each made at least one of them fail (7 of 7).

After the incremental review: the focus after a successful reload failed before the code (1 of 21); the read-only assertion on the page fields passed on the existing code and fails when `readOnly` is removed from the first page field. The approved warning text failed before the change (1 of 21).
