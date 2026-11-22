# chat-source-presentation: verification and independent review (2026-11-22)

Branch `feature/chat-source-presentation` from `main` f8f28b0. Nothing committed. No real Gemini call.

## TDD evidence
`reports/_failing_run_backend.txt`: before the code, `tests/unit/test_source_attribution.py` fails at import (`attribution_of` missing), the integration tests fail with `KeyError: 'attribution'`, and 8 frontend tests fail.

## Mutations (`reports/_mutations.txt`)
13 of 13 detected: flag always cited, always retrieved, derivation without the highest rank, derivation that accepts any marker, a flag for messages without sources, the chat answer or the history without the flag, everything shown as cited or as retrieved, marker numbers for every source, the flag not passed to the block, dropped by the thread, dropped by the live answer.

## Gates (after the last change)
- Backend: `ruff check --no-cache`, `ruff format --check`, `mypy --strict app tests` clean; unit suite 1642 passed, 4 failed (the same four Windows-host-only failures in files this change does not touch); integration suite 984 passed, 444 errors that are the role-bound `privileges` tests, which refuse to run without `TEST_CLUSTER_IS_DISPOSABLE=true` and run in the CI job `privileges`.
- Frontend: `npm run typecheck`, `lint`, `format:check`, `check:api-types` clean; vitest with coverage 594 passed (thresholds hold); Playwright mocked suite 29 passed.
- `openspec validate --all --strict`: see the final run.

## Independent review: PASS WITH GAPS (no Blocker or Major)
| Sev | Finding | Disposition |
|---|---|---|
| Minor | An answer stored before the list form was read, whose only marker is a list covering every retrieved rank (`[1, 2]` with 2 chunks), is derived as `cited` | Accepted and documented (design E3); the shown ranks are identical; unit test added |
| Minor | The group of the retrieved block is named by the long `<summary>`; not tried with a real screen reader; nested `<details>` | Accepted; the native element is keyboard operable and a Playwright test opens it with the keyboard; a manual screen-reader pass stays pending |
| Minor | The cited label does not warn that the marker may sit on an unsupported statement; an invalid marker such as `[9]` stays in the text | The always-visible note covers it; the second point existed before this change; listed in TD-062 |
| Minor | No explicit test that the spec enum equals the Pydantic `Literal` | Already covered by `test_the_response_models_publish_the_same_values_as_the_contract` (the reviewer did not see it) |

Suggestion not taken: showing how many fragments the retrieved block holds.

## Pull request and merge (2026-11-22)
PR #25, head `69f48bcfe82e1c2e95634c92780b9baed393e561`: backend, frontend and privileges green in the `push` and the `pull_request` runs (about 36 billable minutes); the recorder of TD-068 printed no dump. Squash merge into `main` as `4f17dfae1eb7dbdea6d4911486f33ac6ab0a944b`, pinned to that head after checking again that the checks were green and that there were no conflicts. CI of `main` at `4f17dfa`: backend, frontend and privileges passed.
