# Round 4 verification tools

Used on 2026-11-17 to produce `../2026-11-17-round4-m2-linux-suite-compose.md`. They are evidence, not product code, and they run only against disposable resources.

- `Dockerfile.linux-tests`: test image (Python 3.12, uv 0.12.9, `uv sync --frozen --extra ingestion`, as the CI `backend` job). Build context: a clean copy of the repository made from `git ls-files` (it holds no env file).
- `run_linux_suite.sh`: the CI `backend` steps against one disposable cluster, then `role_bound` and `least_privilege` against a second one; internal Docker network, no published port, tmpfs.
- `make_compose_iso.py`, `iso_compose.sh`: build an isolated Compose project (`chatiso`) from that copy with throwaway env files and unpublished ports, and run every command against it only. The paths in the scripts are the ones of the scratch directory used; adapt them.
- `e2e_in_container.py`: end-to-end check run inside the isolated backend container (fake LLM, real worker and embedder).

Nothing here may be pointed at the current stack (`asistenteia`) or at the persistent database.
