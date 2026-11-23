# TDD evidence: failing run before the implementation (task 1.9)

Date: 2026-11-23. Branch `feature/teacher-activity-dashboard` (from `main` at e7e7e71). Fictitious data only. No real Gemini call. No backend file touched.

The tests of tasks 1.1 to 1.7 were written first. Command from `frontend/`: `npx vitest run src/lib/features.test.ts src/services/activityService.test.ts src/hooks/useActivity.test.tsx src/pages/TeacherActivityPage.test.tsx`.

| File | Result | Failure summary |
|---|---|---|
| `src/lib/features.test.ts` | suite failed to load | `Failed to resolve import "./features"` |
| `src/services/activityService.test.ts` | suite failed to load | `Failed to resolve import "./activityService"` |
| `src/hooks/useActivity.test.tsx` | suite failed to load | `Failed to resolve import "./useActivity"` |
| `src/pages/TeacherActivityPage.test.tsx` | 24 failed | `Cannot read properties of undefined (reading 'title')` (the copy `strings.activity` does not exist) and requests to an unregistered route |

The Playwright spec `e2e/teacher-activity.mocked.spec.ts` (task 1.8) is written but is run after the implementation, with the dev server of Playwright and the build flag on.
