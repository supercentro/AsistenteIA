"""The files that deploy and test the change agree with the code (change 6, task 11.1).

Change 6 added settings, a worker, a second Compose service, Docker targets and dependency groups.
None of the tests written with those steps looked at the files themselves, so a drift (a setting
that `.env.example` forgot, a default that differs, the API image growing a machine-learning
dependency, the worker losing its start command, CI installing the wrong groups) would have been
silent. These tests read the real files; they do not start anything.
"""

import re

import pytest
import yaml

from app.core.config import Settings
from tests.db_support import BACKEND_DIR

REPO = BACKEND_DIR.parent
ENV_EXAMPLE = BACKEND_DIR / ".env.example"
DOCKERFILE = BACKEND_DIR / "Dockerfile"
COMPOSE = REPO / "docker-compose.yml"
CI = REPO / ".github" / "workflows" / "ci.yml"

# Read by the Compose "db" service or by the tests, never by `Settings`.
NOT_SETTINGS = {"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "TEST_DATABASE_URL"}
# Seed variables are read by the CLI, not by `Settings`; they are documented commented-out.
SEED = {
    "SEED_TEACHER_EMAIL",
    "SEED_TEACHER_PASSWORD",
    "SEED_STUDENT_EMAIL",
    "SEED_STUDENT_PASSWORD",
}
ASSIGNMENT = re.compile(r"^(#\s*)?([A-Z][A-Z0-9_]*)=(.*)$")


def example_assignments() -> dict[str, tuple[bool, str]]:
    """Variable -> (is it active, raw value without the trailing comment)."""
    found: dict[str, tuple[bool, str]] = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        match = ASSIGNMENT.match(line.strip())
        if match:
            value = match.group(3).split("  #")[0].strip()
            found[match.group(2)] = (match.group(1) is None, value)
    return found


def minimal_settings(**extra: object) -> Settings:
    values: dict[str, object] = {
        "database_url": "postgresql+psycopg://u:p@localhost/db",
        "jwt_secret": "t3sT-s3cr3t-only-for-automated-tests-9Zq",
    }
    values.update(extra)
    return Settings(**values)  # type: ignore[arg-type]


# --- .env.example -------------------------------------------------------------------------------


def test_every_setting_is_documented_in_env_example() -> None:
    documented = set(example_assignments())
    fields = {name.upper() for name in Settings.model_fields}

    assert fields - documented == set()


def test_env_example_documents_no_variable_the_application_does_not_read() -> None:
    fields = {name.upper() for name in Settings.model_fields}
    unknown = set(example_assignments()) - fields - NOT_SETTINGS - SEED

    assert unknown == set()


def test_active_values_of_env_example_equal_the_defaults_of_the_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for field in Settings.model_fields:  # the defaults, not what this process's environment sets
        monkeypatch.delenv(field.upper(), raising=False)
    defaults = minimal_settings()
    checked = 0
    for name, (active, raw) in example_assignments().items():
        field = name.lower()
        if not active or name in NOT_SETTINGS or "CHANGE_ME" in raw:
            continue
        if field not in Settings.model_fields:
            continue
        parsed = getattr(minimal_settings(**{field: raw}), field)
        assert parsed == getattr(defaults, field), name
        checked += 1
    assert checked >= 30  # the ingestion settings and the older ones, not an empty loop


def test_secrets_in_env_example_are_placeholders() -> None:
    assignments = example_assignments()

    for name in ("JWT_SECRET", "POSTGRES_PASSWORD", "DATABASE_URL", "TEST_DATABASE_URL"):
        assert "CHANGE_ME" in assignments[name][1], name
    for name, (active, raw) in assignments.items():
        if "PASSWORD" in name or "SECRET" in name:
            assert not active or raw in {"CHANGE_ME", ""}, name


# --- Docker targets -----------------------------------------------------------------------------


def stage(name: str) -> str:
    source = DOCKERFILE.read_text(encoding="utf-8")
    parts = re.split(r"^FROM .* AS (\w+)$", source, flags=re.MULTILINE)
    stages = dict(zip(parts[1::2], parts[2::2], strict=True))
    return stages[name]


def test_the_api_image_does_not_install_the_machine_learning_groups() -> None:
    api = stage("api")

    assert "--extra" not in api
    assert "torch" not in api.lower()
    assert "embedding" not in api.lower()
    assert "fetch_model" not in api
    assert "uvicorn" in api
    assert "--no-proxy-headers" in api


def test_the_worker_image_installs_both_groups_bakes_the_model_and_starts_the_worker() -> None:
    worker = stage("worker")

    assert "--extra ingestion" in worker
    assert "--extra embedding" in worker
    assert "fetch_model.py" in worker
    assert "HF_HUB_OFFLINE=1" in worker
    assert re.search(r'CMD \["python", "-m", "app.worker"\]', worker)
    assert "USER appuser" in worker


# --- Compose ------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def compose() -> dict[str, dict[str, object]]:
    loaded = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    services = loaded["services"]
    assert isinstance(services, dict)
    return services


def test_compose_has_the_four_services(compose: dict[str, dict[str, object]]) -> None:
    assert set(compose) == {"db", "backend", "worker", "frontend"}


def test_compose_builds_the_api_and_the_worker_from_their_own_targets(
    compose: dict[str, dict[str, object]],
) -> None:
    assert compose["backend"]["build"]["target"] == "api"  # type: ignore[index]
    assert compose["worker"]["build"]["target"] == "worker"  # type: ignore[index]


def test_a_plain_compose_up_starts_the_worker(compose: dict[str, dict[str, object]]) -> None:
    worker = compose["worker"]

    assert "profiles" not in worker
    assert worker["depends_on"] == {"db": {"condition": "service_healthy"}}
    assert "ports" not in worker  # the worker listens on nothing
    assert "command" not in worker  # it uses the image's own `python -m app.worker`
    assert worker["env_file"] == ["./backend/.env"]


def test_the_worker_has_the_resources_validated_by_the_spike(
    compose: dict[str, dict[str, object]],
) -> None:
    worker = compose["worker"]

    assert worker["cpus"] == 4
    assert worker["mem_limit"] == "2g"
    assert "EMBEDDING_THREADS" not in str(worker.get("environment", ""))  # follows the CPU quota


def test_the_api_service_publishes_only_on_loopback_and_keeps_its_arguments(
    compose: dict[str, dict[str, object]],
) -> None:
    backend = compose["backend"]

    assert backend["ports"] == ["127.0.0.1:8000:8000"]
    command = backend["command"]
    assert isinstance(command, list)
    assert "--no-proxy-headers" in command
    assert "--factory" in command


# --- CI -----------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def backend_job() -> dict[str, object]:
    loaded = yaml.safe_load(CI.read_text(encoding="utf-8"))
    job = loaded["jobs"]["backend"]
    assert isinstance(job, dict)
    return job


def steps_text(job: dict[str, object]) -> str:
    steps = job["steps"]
    assert isinstance(steps, list)
    return "\n".join(str(step.get("run", "")) for step in steps)


def test_ci_installs_the_ingestion_group_and_not_the_embedding_group(
    backend_job: dict[str, object],
) -> None:
    text = steps_text(backend_job)

    assert "uv sync --frozen --extra ingestion" in text
    assert "embedding" not in text


def test_ci_runs_the_unit_and_integration_tests_with_the_gates(
    backend_job: dict[str, object],
) -> None:
    text = steps_text(backend_job)

    for command in (
        "ruff check",
        "ruff format --check",
        "mypy --strict app tests",
        "pytest tests/unit",
        "pytest tests/integration",
    ):
        assert command in text, command


def test_ci_uses_the_pgvector_database_of_the_project(backend_job: dict[str, object]) -> None:
    services = backend_job["services"]
    assert isinstance(services, dict)

    assert services["postgres"]["image"] == "pgvector/pgvector:0.8.7-pg15"
    env = backend_job["env"]
    assert isinstance(env, dict)
    assert env["APP_ENV"] == "test"  # the fake embedder is accepted only here
    assert str(env["TEST_DATABASE_URL"]).endswith("_test")
