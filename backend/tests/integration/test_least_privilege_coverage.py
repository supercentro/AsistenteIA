"""The role-bound suite covers every entry point (change `database-least-privilege`, task 9.1).

A route, a CLI subcommand or a worker path without a scenario that runs under the least-privilege
roles and asserts the persisted state fails the build. The registries live next to the scenarios
(`SCENARIOS` of `test_db_roles_api_routes`, `CLI_SCENARIOS` and `WORKER_SCENARIOS` below); a new
entry point therefore cannot ship without a role-bound test, which is how the persisted-state
requirement of the `database-roles` capability is kept.
"""

import importlib
import inspect
import re
from types import ModuleType

from app.cli import DATABASE_COMMANDS, build_parser
from app.repositories.ingestion_job_repository import IngestionJobRepository
from tests.integration import test_db_roles_api_routes as api_scenarios
from tests.integration.helpers import build_app

# CLI subcommand -> (module, test function) that runs it under the CLI or administrator role.
CLI_SCENARIOS = {
    "create-teacher": (
        "test_db_roles_teacher",
        "test_the_cli_role_creates_a_teacher_and_prints_no_secret",
    ),
    "seed": ("test_db_roles_teacher", "test_the_seed_follows_the_same_path_under_the_cli_role"),
    "db-bootstrap": (
        "test_db_admin_bootstrap",
        "test_roles_are_created_with_minimal_attributes_and_limits",
    ),
    "db-adopt": ("test_db_admin_adopt", "test_adoption_moves_every_object_keeps_rows_and_catalog"),
    "db-migrate": (
        "test_db_admin_grants",
        "test_migrate_runs_alembic_as_the_migrator_and_applies_the_matrix_exactly",
    ),
    "db-grants": (
        "test_db_admin_grants",
        "test_migrate_runs_alembic_as_the_migrator_and_applies_the_matrix_exactly",
    ),
    "db-verify": ("test_db_admin_verify", "test_a_healthy_database_has_no_findings"),
}
# Worker path -> test function of `test_db_roles_paths` that runs it under the worker role.
WORKER_SCENARIOS = {
    "claim": "test_the_worker_completes_one_and_many_chunk_documents",
    "renew": "test_the_worker_completes_one_and_many_chunk_documents",
    "complete": "test_the_worker_completes_one_and_many_chunk_documents",
    "mark_failed": "test_the_worker_fails_a_document_and_sweeps_under_its_role",
    "erase_payload": "test_the_worker_erases_a_payload_and_clears_the_lease_under_its_role",
    "sweep": "test_the_sweep_writes_under_the_worker_role_on_each_of_its_three_branches",
}


def module(name: str) -> ModuleType:
    return importlib.import_module(f"tests.integration.{name}")


def test_every_api_operation_has_a_role_bound_scenario() -> None:
    spec = build_app("postgresql+psycopg://u:Passw0rd-long-enough-1@localhost/x_test").openapi()
    operations = {(m.upper(), path) for path, item in spec["paths"].items() for m in item}

    assert operations == set(api_scenarios.SCENARIOS)  # none missing, none left over
    for operation, name in api_scenarios.SCENARIOS.items():
        assert callable(getattr(api_scenarios, name, None)), (operation, name)


def test_every_cli_subcommand_has_a_role_bound_scenario() -> None:
    parser = build_parser()
    action = next(a for a in parser._actions if getattr(a, "choices", None))  # noqa: SLF001
    assert action.choices is not None
    commands = set(action.choices)

    assert commands == set(CLI_SCENARIOS)
    assert set(DATABASE_COMMANDS) <= commands
    for command, (file, name) in CLI_SCENARIOS.items():
        assert callable(getattr(module(file), name, None)), (command, file, name)


def test_every_public_method_of_the_worker_repository_has_a_role_bound_scenario() -> None:
    public = {
        name
        for name, member in inspect.getmembers(IngestionJobRepository, inspect.isfunction)
        if not name.startswith("_")
    }

    assert public == set(WORKER_SCENARIOS)  # a new method cannot ship without a scenario
    scenarios = module("test_db_roles_paths")
    source = inspect.getsource(scenarios)
    for path, name in WORKER_SCENARIOS.items():
        assert callable(getattr(scenarios, name, None)), path
        assert f"repo.{path}(" in source or f"Repository(session).{path}(" in source, path


def test_every_route_is_really_called_by_the_scenarios() -> None:
    """The module that holds the scenarios issues a request for each (method, path)."""
    source = inspect.getsource(api_scenarios)
    helpers = {  # requests made through a helper of the module
        ("POST", "/api/v1/auth/login"): "login_token(client",
        ("POST", "/api/v1/subjects/{subject_id}/documents"): "upload(client",
    }
    for method, path in api_scenarios.SCENARIOS:
        if (method, path) in helpers:
            assert helpers[(method, path)] in source, (method, path)
            continue
        parts = path.removeprefix("/api/v1").split("/")
        template = "/".join(
            r"\{[^}]+\}" if part.startswith("{") else re.escape(part) for part in parts
        )
        pattern = rf'client\.{method.lower()}\(\s*f"\{{API\}}{template}"'
        assert re.search(pattern, source), (method, path, pattern)
