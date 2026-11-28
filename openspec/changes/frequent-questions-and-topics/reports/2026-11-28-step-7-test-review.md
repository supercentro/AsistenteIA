# Step 7 Report - Review of Existing Tests and Unread Files

- Date: 2026-11-28

## Existing tests changed, and why

- Head revision pins `0008` -> `0009` (`test_db_admin_grants`, `test_db_roles_lifecycle`, `test_migrations_user_role_default`).
- `test_db_privileges_inventory`: the worker now touches the two topic tables; the test also asserts it never updates or deletes them.
- `test_commit_failure_responses`: the new `PUT` is classified as committing before the response.
- `test_worker_settings`: the new API setting. `test_api_contract`: the three new routes and seven schemas.
- `test_db_roles_api_routes`: one role-bound scenario for the three routes.
- No activity test changed; `SourceFact` gained a defaulted `page_number`.

## Files no test reads (lesson L26)

- `frontend/playwright.config.ts`: sets the new build flag for the mocked suite (verified by running it).
- `.env.example` files: both new settings are `false`.
- Compose files and Dockerfiles: no change needed (settings come from the env files). The frontend Dockerfile declares no `VITE_` value.
- `.github/`: not modified. A comment of `privilege_gate.sh` still says "0006"; it predates this change and the commands migrate to head.
- Documentation: see step 11.
