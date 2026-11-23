# TDD evidence: failing run before the implementation (task 1.6)

Date: 2026-11-23. Branch `feature/activity-events-and-metrics` (from `main` at 5167292). Fictitious data only. No real Gemini call.

The tests of tasks 1.1 to 1.5 were written first, with no production code for them. Commands run from `backend/` with `uv run --no-sync python -m pytest ... -p no:cacheprovider`.

| Command | Result | Failure summary |
|---|---|---|
| `tests/unit/test_activity_service.py tests/unit/test_activity_schema_shape.py` | 2 errors in collection | `ModuleNotFoundError: No module named 'app.schemas.activity'` (and `app.services.activity_service`) |
| `tests/integration/test_activity_endpoint.py` | 1 error in collection | `ModuleNotFoundError: No module named 'app.repositories.activity_repository'` |
| `tests/integration/test_least_privilege_coverage.py` | 1 failed, 3 passed | `test_every_api_operation_has_a_role_bound_scenario`: the registry lists `GET /api/v1/subjects/{subject_id}/activity` and the application has no such operation |

A failure at collection is the expected first failure: the modules, schemas and the route do not exist yet. The mutation checks of task 2.3 show that the assertions themselves fail when the guarded code is removed once the implementation exists.
