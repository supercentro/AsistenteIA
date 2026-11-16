"""The files that deploy and test the change agree with the code (change 6, task 11.1).

Change 6 added settings, a worker, a second Compose service, Docker targets and dependency groups.
None of the tests written with those steps looked at the files themselves, so a drift (a setting
that an example forgot, a default that differs, the API image growing a machine-learning
dependency, the worker losing its start command, CI installing the wrong groups) would have been
silent. These tests read the real files; they do not start anything.

Each Compose service receives only its own environment file: `backend/.env` (API),
`backend/.env.worker` (worker) and `backend/.env.db` (PostgreSQL). The worker and the database no
longer see `JWT_SECRET` or any other variable they do not read.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import yaml

from app.core.config import Settings, WorkerSettings
from tests.db_support import BACKEND_DIR

REPO = BACKEND_DIR.parent
ENV_EXAMPLE = BACKEND_DIR / ".env.example"
WORKER_EXAMPLE = BACKEND_DIR / ".env.worker.example"
DB_EXAMPLE = BACKEND_DIR / ".env.db.example"
DOCKERFILE = BACKEND_DIR / "Dockerfile"
COMPOSE = Path(os.environ.get("COMPOSE_FILE_UNDER_TEST", REPO / "docker-compose.yml"))
CI = REPO / ".github" / "workflows" / "ci.yml"

# Read by the tests only, never by `Settings` (they live in backend/.env.test.example).
NOT_SETTINGS: set[str] = set()  # no example carries a test variable any more
# Read by the Compose "db" service (backend/.env.db), never by the application.
DB_VARIABLES = {"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"}
# Seed variables are read by the CLI, not by `Settings`; they are documented commented-out.
SEED = {
    "SEED_TEACHER_EMAIL",
    "SEED_TEACHER_PASSWORD",
    "SEED_STUDENT_EMAIL",
    "SEED_STUDENT_PASSWORD",
}
# Read by both processes: documented in backend/.env.example and in backend/.env.worker.example.
SHARED = {
    "app_env",
    "log_level",
    "database_url",
    "db_connect_timeout_seconds",
    "db_idle_in_transaction_timeout_seconds",
}
API_FIELDS = set(Settings.model_fields)
WORKER_FIELDS = set(WorkerSettings.model_fields)
WORKER_ONLY = WORKER_FIELDS - SHARED
API_FILE_FIELDS = API_FIELDS - WORKER_ONLY  # what backend/.env.example documents
ASSIGNMENT = re.compile(r"^(#\s*)?([A-Z][A-Z0-9_]*)=(.*)$")


def example_assignments(path: Path = ENV_EXAMPLE) -> dict[str, tuple[bool, str]]:
    """Variable -> (is it active, raw value without the trailing comment)."""
    found: dict[str, tuple[bool, str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = ASSIGNMENT.match(line.strip())
        if match:
            value = match.group(3).split("  #")[0].strip()
            found[match.group(2)] = (match.group(1) is None, value)
    return found


def upper(fields: set[str]) -> set[str]:
    return {name.upper() for name in fields}


# --- .env.example (API), .env.worker.example (worker), .env.db.example (PostgreSQL) -------------


def test_every_api_setting_is_documented_in_env_example() -> None:
    documented = set(example_assignments())

    assert upper(API_FILE_FIELDS) - documented == set()


def test_env_example_documents_no_variable_the_api_does_not_read() -> None:
    documented = set(example_assignments())
    unknown = documented - upper(API_FILE_FIELDS) - NOT_SETTINGS - SEED

    assert unknown == set()


def test_env_example_holds_no_worker_only_and_no_database_server_variable() -> None:
    documented = set(example_assignments())

    assert documented & upper(WORKER_ONLY) == set()
    assert documented & DB_VARIABLES == set()


def test_every_worker_setting_is_documented_in_env_worker_example() -> None:
    documented = set(example_assignments(WORKER_EXAMPLE))

    assert upper(WORKER_FIELDS) - documented == set()


def test_env_worker_example_documents_only_what_the_worker_reads() -> None:
    documented = set(example_assignments(WORKER_EXAMPLE))

    assert documented - upper(WORKER_FIELDS) == set()
    assert documented & upper(API_FIELDS - WORKER_FIELDS) == set()
    for forbidden in ("JWT", "CORS", "POSTGRES_", "SEED_", "RATE_LIMIT"):
        assert not [name for name in documented if forbidden in name], forbidden


def test_env_db_example_holds_exactly_the_three_database_server_variables() -> None:
    assert set(example_assignments(DB_EXAMPLE)) == DB_VARIABLES


@pytest.mark.parametrize(
    ("path", "api"),
    [(ENV_EXAMPLE, True), (WORKER_EXAMPLE, False)],
    ids=["api", "worker"],
)
def test_active_values_of_the_examples_equal_the_defaults_of_their_settings(
    path: Path, api: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    for field in Settings.model_fields:  # the defaults, not what this process's environment sets
        monkeypatch.delenv(field.upper(), raising=False)
    model: type[WorkerSettings] = Settings if api else WorkerSettings

    def build(**extra: object) -> WorkerSettings:
        values: dict[str, object] = {"database_url": "postgresql+psycopg://u:p@localhost/db"}
        if api:
            values["jwt_secret"] = "t3sT-s3cr3t-only-for-automated-tests-9Zq"
        values.update(extra)
        return model(_env_file=None, **values)  # type: ignore[arg-type]

    defaults = build()
    checked = 0
    for name, (active, raw) in example_assignments(path).items():
        field = name.lower()
        if not active or name in NOT_SETTINGS or "CHANGE_ME" in raw:
            continue
        if field not in model.model_fields:
            continue
        assert getattr(build(**{field: raw}), field) == getattr(defaults, field), name
        checked += 1
    assert checked >= (8 if api else 20)  # not an empty loop


def test_secrets_in_the_examples_are_placeholders() -> None:
    api = example_assignments()
    worker = example_assignments(WORKER_EXAMPLE)
    database = example_assignments(DB_EXAMPLE)

    for name in ("JWT_SECRET", "DATABASE_URL"):
        assert "CHANGE_ME" in api[name][1], name
    assert "CHANGE_ME" in worker["DATABASE_URL"][1]
    assert "CHANGE_ME" in database["POSTGRES_PASSWORD"][1]
    for assignments in (api, worker, database):
        for name, (active, raw) in assignments.items():
            if "PASSWORD" in name or "SECRET" in name:
                assert not active or raw in {"CHANGE_ME", ""}, name
            if "URL" in name:
                assert "CHANGE_ME" in raw, name


def test_the_database_url_examples_use_the_restricted_roles_not_the_administrator() -> None:
    """Finding PG-01: the examples of the API and of the worker never carry the superuser."""
    server = example_assignments(DB_EXAMPLE)
    administrator = server["POSTGRES_USER"][1]
    expected_database = server["POSTGRES_DB"][1]
    expected_user = {ENV_EXAMPLE: "asistente_app", WORKER_EXAMPLE: "asistente_worker"}

    for path, user in expected_user.items():
        parts = urlsplit(example_assignments(path)["DATABASE_URL"][1])
        assert parts.username == user, path.name
        assert parts.username != administrator, path.name
        assert parts.path == "/" + expected_database, path.name
        assert parts.hostname == "db", path.name  # the Compose service name


def test_the_database_url_examples_differ_only_in_the_role() -> None:
    api = urlsplit(example_assignments(ENV_EXAMPLE)["DATABASE_URL"][1])
    worker = urlsplit(example_assignments(WORKER_EXAMPLE)["DATABASE_URL"][1])

    assert api.username != worker.username
    assert (api.hostname, api.port, api.path) == (worker.hostname, worker.port, worker.path)


def test_the_examples_do_not_tell_to_reuse_the_administrator_for_the_services() -> None:
    for path in (ENV_EXAMPLE, WORKER_EXAMPLE, DB_EXAMPLE):
        text = path.read_text(encoding="utf-8")
        assert "same database and credentials" not in text, path.name
        assert "Keep these values equal to the ones inside DATABASE_URL" not in text, path.name
    assert "future CLI file" not in (ENV_EXAMPLE.parent / ".env.roles.example").read_text(
        encoding="utf-8"
    )


# --- Git ----------------------------------------------------------------------------------------


def git_ignores(path: str) -> bool | None:
    if shutil.which("git") is None or not (REPO / ".git").exists():
        return None
    result = subprocess.run(  # noqa: S603 - fixed arguments, test-only
        ["git", "check-ignore", "-q", path],  # noqa: S607
        cwd=REPO,
        capture_output=True,
        check=False,
    )
    return {0: True, 1: False}.get(result.returncode)


def test_gitignore_hides_every_real_environment_file_and_keeps_the_examples() -> None:
    # Text check that also runs where git is unavailable; the tests below ask git itself.
    lines = (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert ".env" in lines
    assert ".env.*" in lines
    assert lines.index("!.env.example") > lines.index(".env.*")
    assert lines.index("!.env.*.example") > lines.index(".env.*")


@pytest.mark.parametrize("name", ["backend/.env", "backend/.env.worker", "backend/.env.db"])
def test_the_real_environment_files_are_ignored_by_git(name: str) -> None:
    verdict = git_ignores(name)
    if verdict is None:
        pytest.skip("git or the repository metadata is not available")

    assert verdict is True


@pytest.mark.parametrize(
    "name",
    ["backend/.env.example", "backend/.env.worker.example", "backend/.env.db.example"],
)
def test_the_example_environment_files_are_not_ignored_by_git(name: str) -> None:
    verdict = git_ignores(name)
    if verdict is None:
        pytest.skip("git or the repository metadata is not available")

    assert verdict is False


def test_no_real_environment_file_is_tracked() -> None:
    if shutil.which("git") is None or not (REPO / ".git").exists():
        pytest.skip("git or the repository metadata is not available")

    tracked = subprocess.run(  # noqa: S603 - fixed arguments, test-only
        ["git", "ls-files", "backend/.env", "backend/.env.worker", "backend/.env.db"],  # noqa: S607
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    ).stdout

    assert tracked.strip() == ""


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


def test_no_image_can_contain_a_real_environment_file() -> None:
    ignored = (BACKEND_DIR / ".dockerignore").read_text(encoding="utf-8").splitlines()

    assert ".env" in ignored
    assert ".env.*" in ignored  # covers .env.worker and .env.db


# --- Compose ------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def compose() -> dict[str, dict[str, object]]:
    loaded = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    services = loaded["services"]
    assert isinstance(services, dict)
    return services


def test_compose_has_the_seven_services(compose: dict[str, dict[str, object]]) -> None:
    assert set(compose) == {"db", "bootstrap", "migrate", "cli", "backend", "worker", "frontend"}


def test_compose_builds_the_api_and_the_worker_from_their_own_targets(
    compose: dict[str, dict[str, object]],
) -> None:
    assert compose["backend"]["build"]["target"] == "api"  # type: ignore[index]
    assert compose["worker"]["build"]["target"] == "worker"  # type: ignore[index]


def test_a_plain_compose_up_starts_the_worker(compose: dict[str, dict[str, object]]) -> None:
    worker = compose["worker"]

    assert "profiles" not in worker
    assert worker["depends_on"] == {
        "db": {"condition": "service_healthy"},
        "migrate": {"condition": "service_completed_successfully"},
    }
    assert "ports" not in worker  # the worker listens on nothing
    assert "command" not in worker  # it uses the image's own `python -m app.worker`
    assert worker["env_file"] == ["./backend/.env.worker"]


def test_each_service_receives_only_its_own_environment_file(
    compose: dict[str, dict[str, object]],
) -> None:
    assert compose["backend"]["env_file"] == ["./backend/.env"]
    assert compose["worker"]["env_file"] == ["./backend/.env.worker"]
    assert compose["db"]["env_file"] == ["./backend/.env.db"]
    assert compose["bootstrap"]["env_file"] == [{"path": "./backend/.env.roles", "required": False}]
    assert compose["migrate"]["env_file"] == [{"path": "./backend/.env.migrate", "required": False}]
    assert compose["frontend"]["env_file"] == ["./frontend/.env"]


def test_no_service_other_than_the_api_receives_the_api_environment_file(
    compose: dict[str, dict[str, object]],
) -> None:
    for name, service in compose.items():
        files = service["env_file"]
        assert isinstance(files, list)
        uses_api_file = "./backend/.env" in files
        assert uses_api_file is (name == "backend"), name


def test_no_service_passes_a_secret_inline(compose: dict[str, dict[str, object]]) -> None:
    for name, service in compose.items():
        inline = str(service.get("environment", "")).upper()
        for word in ("JWT", "PASSWORD", "SECRET"):
            assert word not in inline, (name, word)


def test_the_database_server_and_the_worker_receive_the_variables_they_need() -> None:
    server = set(example_assignments(DB_EXAMPLE))
    worker = set(example_assignments(WORKER_EXAMPLE))

    # The image refuses to initialise without a password; the healthcheck reads user and name.
    assert server >= DB_VARIABLES
    assert "DATABASE_URL" in worker
    assert not {"JWT_SECRET", "CORS_ORIGINS"} & (server | worker)


def test_the_database_healthcheck_uses_only_variables_of_its_own_file(
    compose: dict[str, dict[str, object]],
) -> None:
    healthcheck = str(compose["db"]["healthcheck"])

    used = set(re.findall(r"\$\$\{(\w+)\}", healthcheck))
    assert used <= DB_VARIABLES


def test_the_worker_has_the_resources_validated_by_the_spike(
    compose: dict[str, dict[str, object]],
) -> None:
    worker = compose["worker"]

    assert worker["cpus"] == 4
    assert worker["mem_limit"] == "2g"
    assert "EMBEDDING_THREADS" not in str(worker.get("environment", ""))  # follows the CPU quota


def test_the_worker_restarts_by_itself_and_has_a_real_healthcheck(
    compose: dict[str, dict[str, object]],
) -> None:
    # Review finding R-02. A healthcheck alone restarts nothing: the restart policy handles an
    # exit (crash, out-of-memory kill, or the worker's own exit when it stalls).
    worker = compose["worker"]
    healthcheck = worker["healthcheck"]
    assert isinstance(healthcheck, dict)

    assert worker["restart"] == "unless-stopped"
    assert healthcheck["test"] == ["CMD", "python", "-m", "app.worker_health"]
    # the model needs time to load before the first beat
    assert int(str(healthcheck["start_period"]).rstrip("s")) >= 60
    assert int(str(healthcheck["interval"]).rstrip("s")) <= 60
    assert int(healthcheck["retries"]) >= 2


def test_the_worker_source_mount_is_read_only_and_the_api_mount_is_not(
    compose: dict[str, dict[str, object]],
) -> None:
    # Review finding R-06: the worker parses untrusted files and has no reason to write its code.
    assert compose["worker"]["volumes"] == ["./backend/app:/app/app:ro"]
    assert compose["backend"]["volumes"] == ["./backend/app:/app/app"]  # auto-reload needs it


def test_the_worker_has_no_other_writable_mount_and_the_container_is_not_read_only(
    compose: dict[str, dict[str, object]],
) -> None:
    worker = compose["worker"]

    assert len(worker["volumes"]) == 1  # type: ignore[arg-type]
    assert "read_only" not in worker  # not validated for every write path yet (change 13)


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
