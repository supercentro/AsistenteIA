"""The Compose flow db, bootstrap, migrate, backend and worker (database-least-privilege).

The file is read as YAML; nothing is started. The behaviours that shaped these rules were measured
in task 1 (H13) and again with the real commands (task 6.4): finished one-shots are started again by
a plain `up`, a service in an inactive profile that others depend on invalidates the whole project,
and a failed `migrate` leaves its dependants created but never started.
"""

import os
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.db_support import BACKEND_DIR

REPO = BACKEND_DIR.parent
# COMPOSE_FILE_UNDER_TEST lets the mutation harness (reports/group-6/mutate_compose.py) point the
# tests at a mutated copy; without it the real file is read.
COMPOSE = Path(os.environ.get("COMPOSE_FILE_UNDER_TEST", REPO / "docker-compose.yml"))
GUIDE = REPO / "docs" / "development_guide.md"
ONE_SHOTS = ("bootstrap", "migrate")


@pytest.fixture(scope="module")
def services() -> dict[str, dict[str, Any]]:
    loaded = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return dict(loaded["services"])


def env_paths(service: dict[str, Any]) -> list[str]:
    """The paths of the environment files, whether written as strings or as path/required maps."""
    return [e if isinstance(e, str) else str(e["path"]) for e in service["env_file"]]


def conditions(service: dict[str, Any]) -> dict[str, str]:
    depends = service.get("depends_on", {})
    assert isinstance(depends, dict), "dependencies must state their condition"
    return {name: str(spec["condition"]) for name, spec in depends.items()}


def test_the_one_shots_exist_and_are_in_the_default_profile(
    services: dict[str, dict[str, Any]],
) -> None:
    for name in ONE_SHOTS:
        assert name in services
        assert "profiles" not in services[name], name  # a profiled dependency breaks the project


def test_no_service_depends_on_a_service_with_a_profile(
    services: dict[str, dict[str, Any]],
) -> None:
    profiled = {name for name, spec in services.items() if spec.get("profiles")}
    for name, spec in services.items():
        depends = spec.get("depends_on", {})
        needed = set(depends if isinstance(depends, dict) else list(depends))
        assert not needed & profiled, name


def test_the_order_is_database_then_bootstrap_then_migrate(
    services: dict[str, dict[str, Any]],
) -> None:
    assert conditions(services["bootstrap"]) == {"db": "service_healthy"}
    assert conditions(services["migrate"]) == {"bootstrap": "service_completed_successfully"}


def test_the_api_and_the_worker_wait_for_a_migration_that_finished_successfully(
    services: dict[str, dict[str, Any]],
) -> None:
    for name in ("backend", "worker"):
        assert conditions(services[name]) == {
            "db": "service_healthy",
            "migrate": "service_completed_successfully",
        }, name


def test_the_one_shots_run_once_and_leave(services: dict[str, dict[str, Any]]) -> None:
    for name in ONE_SHOTS:
        service = services[name]
        assert service["restart"] == "no", name
        assert "healthcheck" not in service, name


def test_the_one_shots_use_the_api_image_and_the_real_commands(
    services: dict[str, dict[str, Any]],
) -> None:
    for name in ONE_SHOTS:
        assert services[name]["build"] == {"context": "./backend", "target": "api"}, name
    assert services["bootstrap"]["command"] == [
        "python",
        "-m",
        "app.cli",
        "db-bootstrap",
        "--database",
        "asistenteia",
    ]
    assert services["migrate"]["command"] == ["python", "-m", "app.cli", "db-migrate"]


def test_a_missing_one_shot_file_fails_the_service_not_the_compose_tooling(
    services: dict[str, dict[str, Any]],
) -> None:
    # The real files are created by a separate, authorised step; until then `ps`, `logs`, `exec` and
    # `down` must keep working, and running a one-shot without its file must stop it loudly.
    for name in ONE_SHOTS:
        entries = services[name]["env_file"]
        assert len(entries) == 1 and entries[0]["required"] is False, name


def test_the_one_shots_run_the_code_of_the_image_not_the_working_tree(
    services: dict[str, dict[str, Any]],
) -> None:
    for name in ONE_SHOTS:
        assert "volumes" not in services[name], name  # a stale or edited checkout never migrates


def test_the_one_shots_publish_nothing(services: dict[str, dict[str, Any]]) -> None:
    for name in ONE_SHOTS:
        assert "ports" not in services[name] and "expose" not in services[name], name


def test_each_identity_has_its_own_environment_file(services: dict[str, dict[str, Any]]) -> None:
    files = {name: env_paths(spec) for name, spec in services.items()}

    assert files["bootstrap"] == ["./backend/.env.roles"]
    assert files["migrate"] == ["./backend/.env.migrate"]
    assert files["backend"] == ["./backend/.env"]
    assert files["worker"] == ["./backend/.env.worker"]
    assert files["db"] == ["./backend/.env.db"]
    assert files["cli"] == ["./backend/.env.cli"]
    flat = [f for listed in files.values() for f in listed]
    assert len(flat) == len(set(flat)), "an environment file is shared between two services"


def test_the_administrator_files_reach_only_the_database_and_the_bootstrap(
    services: dict[str, dict[str, Any]],
) -> None:
    holders = {
        file: [n for n, s in services.items() if file in env_paths(s)]
        for file in ("./backend/.env.db", "./backend/.env.roles", "./backend/.env.migrate")
    }

    assert holders == {
        "./backend/.env.db": ["db"],
        "./backend/.env.roles": ["bootstrap"],
        "./backend/.env.migrate": ["migrate"],
    }


def test_the_cli_is_a_profiled_one_shot_with_its_own_identity(
    services: dict[str, dict[str, Any]],
) -> None:
    cli = services["cli"]

    assert cli["profiles"] == ["cli"]  # never started by a plain `up`
    assert cli["restart"] == "no"
    assert cli["entrypoint"] == ["python", "-m", "app.cli"]
    assert cli["env_file"] == [{"path": "./backend/.env.cli", "required": False}]
    assert "ports" not in cli and "volumes" not in cli
    assert conditions(cli) == {"migrate": "service_completed_successfully"}


def test_only_the_cli_holds_the_cli_credential(services: dict[str, dict[str, Any]]) -> None:
    holders = [n for n, s in services.items() if "./backend/.env.cli" in env_paths(s)]

    assert holders == ["cli"]  # the API, the worker and the one-shots never receive it


def test_no_test_file_and_no_inline_secret_reaches_any_service(
    services: dict[str, dict[str, Any]],
) -> None:
    for name, spec in services.items():
        assert "./backend/.env.test" not in env_paths(spec), name
        inline = str(spec.get("environment", "")).upper()
        for word in ("PASSWORD", "SECRET", "TOKEN", "DATABASE_URL"):
            assert word not in inline, (name, word)


def test_only_the_existing_loopback_ports_are_published(
    services: dict[str, dict[str, Any]],
) -> None:
    published = {n: s["ports"] for n, s in services.items() if "ports" in s}

    assert published == {
        "db": ["127.0.0.1:5442:5432"],
        "backend": ["127.0.0.1:8000:8000"],
        "frontend": ["127.0.0.1:5173:5173"],
    }


def test_the_worker_keeps_its_restart_policy_resources_and_healthcheck(
    services: dict[str, dict[str, Any]],
) -> None:
    worker = services["worker"]

    assert worker["restart"] == "unless-stopped"
    assert worker["healthcheck"]["test"] == ["CMD", "python", "-m", "app.worker_health"]
    assert worker["cpus"] == 4 and worker["mem_limit"] == "2g"
    assert worker["volumes"] == ["./backend/app:/app/app:ro"]


def test_the_guide_explains_rebuild_restart_and_the_one_shots() -> None:
    text = GUIDE.read_text(encoding="utf-8")

    for phrase in (
        "up -d --build",
        "`restart` does not apply a changed environment",
        "runs on every `up`",
        "docker compose logs bootstrap migrate",
        ".env.roles",
        ".env.migrate",
    ):
        assert phrase in text, phrase


def test_the_dockerignore_keeps_the_new_real_files_out_of_every_image() -> None:
    lines = (BACKEND_DIR / ".dockerignore").read_text(encoding="utf-8").splitlines()

    assert ".env.*" in lines
    ignores = lines + (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
    for name in (".env.roles", ".env.migrate", ".env.test"):
        assert not [line for line in ignores if line.startswith("!") and name in line], name


def test_no_service_asks_for_more_than_it_needs_from_the_host(
    services: dict[str, dict[str, Any]],
) -> None:
    for name, spec in services.items():
        for key in ("privileged", "cap_add", "network_mode", "pid", "ipc", "secrets", "configs"):
            assert key not in spec, (name, key)
        for mount in spec.get("volumes", []):
            assert "docker.sock" not in str(mount), name
        assert "extends" not in spec and "include" not in spec, name
