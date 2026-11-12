# Group 14: frontend regression (no UI flow for this change)

Branch `feature/document-ingestion`. Task 14.1. Only checks were run; no source, test, configuration or dependency file of the frontend or the backend was changed. No group after 14 was run; migration `0005` was not applied to the development database.

## Scope of the change in the frontend
`git diff main...HEAD -- frontend` touches one file: `frontend/src/types/api.generated.ts` (111 insertions, 18 deletions), regenerated from `docs/api-spec.yml` with `npm run generate:api`. No component, hook, service, route or string references documents or uploads (a search of `frontend/src` finds no use outside the generated file). **No UI flow exists yet for this change**; the document screens belong to a later change.

## Environment
Host Node v24.19.0 with the committed `package-lock.json` (the frontend toolchain is not affected by the Windows Application Control that blocks the Python virtual environment). The mocked Playwright suite ran against a Vite dev server started by hand on **127.0.0.1:15173** (`--strictPort`), so 5173 and 8000 were not used; `E2E_BASE_URL` pointed to it and the API origin is stubbed by `page.route`. The server was stopped afterwards (no listener left on 15173).

## Results
| Check | Result |
|---|---|
| `npm run typecheck` | clean |
| `npm run lint` | clean |
| `npm run format:check` | all files formatted |
| `npm run check:api-types` | "API types are up to date" (the generated types equal the contract) |
| `npm test` (Vitest) | 16 files, **236 tests passed** |
| `npm run build` (`tsc -b && vite build`) | built |
| Mocked Playwright (`npx playwright test`, chromium) | **11 passed**, 6 skipped |

The 6 skipped tests are the `real-backend.spec.ts` cases, which need a running backend and are outside the mocked suite; this group did not run them. The regenerated types did not break anything.

## Backend and gates
The backend, its tests and its configuration did not change since group 13, whose results stand: 1712 passed, 1 skipped, 16 deselected, coverage of `app` 99 %; `ruff --no-cache`, `ruff format --check`, `mypy --strict` (169 files) and `pip-audit` clean. `openspec validate document-ingestion --strict` and `openspec validate --all --strict` (15 items) are valid. No adversarial review applies to this group (it contains no security-relevant change; the independent review is group 16).

## Risks and limits
1. Dependabot alert #1 (`minimatch`, frontend development dependency) is still open; `npm audit` was not part of this group (tasks 15.1 and 17.3).
2. The real-backend Playwright cases were skipped by design; the real API was exercised with `curl` in group 13.
3. The mocked suite proves the existing auth screens still work; it says nothing about future document screens.
