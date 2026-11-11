"""The worker has its own settings and never needs the API secrets (hardening before group 16).

The Compose worker used to receive the whole `backend/.env`, and `Settings` made `JWT_SECRET`
mandatory, so the worker could not even start without a secret it never uses. `WorkerSettings`
holds what the worker reads; `Settings` extends it with authentication, CORS and HTTP limits.
"""

import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import (
    ConfigurationError,
    Settings,
    WorkerSettings,
    load_settings,
    load_worker_settings,
)
from tests.constants import TEST_JWT_SECRET
from tests.db_support import BACKEND_DIR

DB_URL = "postgresql+psycopg://u:p@localhost/db"

# Fields that only the API reads. Anything else is shared with, or owned by, the worker.
API_ONLY = {
    "jwt_secret",
    "jwt_issuer",
    "jwt_audience",
    "jwt_expire_minutes",
    "privacy_policy_version",
    "login_rate_limit",
    "register_rate_limit",
    "cors_origins",
    "max_upload_mb",
    "max_documents_per_subject",
    "ingestion_queue_max",
    "ingestion_pending_bytes_max_mb",
    "upload_max_in_flight",
    "upload_rate_limit",
    "upload_body_timeout_seconds",
    "upload_body_idle_seconds",
    "db_statement_timeout_api_seconds",
}


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)


# --- the split ----------------------------------------------------------------------------------


def test_the_worker_settings_hold_no_api_field() -> None:
    assert set(WorkerSettings.model_fields) & API_ONLY == set()


def test_the_api_settings_are_the_worker_settings_plus_exactly_the_api_fields() -> None:
    assert set(Settings.model_fields) == set(WorkerSettings.model_fields) | API_ONLY
    assert issubclass(Settings, WorkerSettings)


def test_no_worker_field_mentions_authentication_or_http() -> None:
    names = " ".join(WorkerSettings.model_fields)

    for word in ("jwt", "cors", "login", "register", "privacy", "upload"):
        assert word not in names, word


# --- the API still requires its secret ----------------------------------------------------------


def test_the_api_settings_require_the_jwt_secret() -> None:
    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=None, database_url=DB_URL)

    assert [error["loc"] for error in caught.value.errors()] == [("jwt_secret",)]


def test_loading_the_api_settings_without_the_secret_names_the_variable() -> None:
    with pytest.raises(ConfigurationError, match="JWT_SECRET"):
        load_settings(env_file=None)


def test_the_api_still_rejects_a_weak_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(_env_file=None, database_url=DB_URL, jwt_secret="short")


def test_the_api_still_checks_its_own_cross_field_rules() -> None:
    with pytest.raises(ValueError, match="INGESTION_PENDING_BYTES_MAX_MB"):
        Settings(
            _env_file=None,
            database_url=DB_URL,
            jwt_secret=TEST_JWT_SECRET,
            max_upload_mb=20,
            ingestion_pending_bytes_max_mb=10,
        )
    with pytest.raises(ValueError, match="UPLOAD_BODY_IDLE_SECONDS"):
        Settings(
            _env_file=None,
            database_url=DB_URL,
            jwt_secret=TEST_JWT_SECRET,
            upload_body_timeout_seconds=10,
            upload_body_idle_seconds=20,
        )
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        Settings(
            _env_file=None,
            database_url=DB_URL,
            jwt_secret=TEST_JWT_SECRET,
            app_env="production",
        )


# --- the worker does not -----------------------------------------------------------------------


def test_the_worker_settings_start_without_any_api_secret() -> None:
    settings = WorkerSettings(_env_file=None, database_url=DB_URL)

    assert settings.database_url == DB_URL
    assert not hasattr(settings, "jwt_secret")


def test_loading_the_worker_settings_needs_only_the_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", DB_URL)

    settings = load_worker_settings(env_file=None)

    assert type(settings) is WorkerSettings
    assert settings.ingestion_lease_seconds == 120


def test_the_worker_ignores_api_variables_that_are_present_in_its_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("JWT_SECRET", "x")  # invalid for the API; must not matter here
    monkeypatch.setenv("CORS_ORIGINS", "*")
    monkeypatch.setenv("MAX_UPLOAD_MB", "not-a-number")

    settings = load_worker_settings(env_file=None)

    assert not hasattr(settings, "jwt_secret")
    assert not hasattr(settings, "cors_origins")
    assert not hasattr(settings, "max_upload_mb")


def test_loading_the_worker_settings_without_a_database_url_names_the_variable() -> None:
    with pytest.raises(ConfigurationError, match="DATABASE_URL"):
        load_worker_settings(env_file=None)


def test_a_worker_configuration_error_never_shows_the_offending_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("INGESTION_LEASE_SECONDS", "not-a-number-CANARY")

    with pytest.raises(ConfigurationError) as caught:
        load_worker_settings(env_file=None)

    assert "INGESTION_LEASE_SECONDS" in str(caught.value)
    assert "CANARY" not in str(caught.value)


def test_the_worker_settings_keep_their_own_validation() -> None:
    with pytest.raises(ValueError, match="EMBEDDER_BACKEND=fake"):
        WorkerSettings(
            _env_file=None,
            database_url=DB_URL,
            app_env="production",
            embedder_backend="fake",
        )
    with pytest.raises(ValueError, match="INGESTION_JOB_DEADLINE_SECONDS"):
        WorkerSettings(
            _env_file=None,
            database_url=DB_URL,
            ingestion_lease_seconds=120,
            ingestion_job_deadline_seconds=120,
        )


def test_the_worker_does_not_demand_the_api_cors_rule_in_production() -> None:
    settings = WorkerSettings(
        _env_file=None,
        database_url=DB_URL,
        app_env="production",
    )

    assert settings.app_env == "production"


def test_the_thread_helper_is_shared_with_the_api_settings() -> None:
    worker = WorkerSettings(_env_file=None, database_url=DB_URL, embedding_threads=3)
    api = Settings(
        _env_file=None,
        database_url=DB_URL,
        jwt_secret=TEST_JWT_SECRET,
        embedding_threads=3,
    )

    assert worker.effective_embedding_threads() == api.effective_embedding_threads() == 3


# --- the worker process --------------------------------------------------------------------------


def run_python(code: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed arguments, test-only
        [sys.executable, "-c", code],
        cwd=BACKEND_DIR,
        env={"PYTHONPATH": str(BACKEND_DIR), "PATH": "", **env},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_a_fresh_worker_process_loads_its_settings_without_any_api_variable() -> None:
    code = (
        "from app.worker import load_worker_settings\n"
        "s = load_worker_settings(env_file=None)\n"
        "assert not hasattr(s, 'jwt_secret')\n"
        "print('ok', s.log_level)\n"
    )

    result = run_python(code, {"DATABASE_URL": DB_URL})

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok INFO"


def test_importing_the_worker_does_not_pull_in_the_api() -> None:
    code = (
        "import sys\n"
        "import app.worker\n"
        "bad = [m for m in ('app.main', 'app.core.security', 'app.api.deps', 'fastapi')"
        " if m in sys.modules]\n"
        "print(','.join(bad))\n"
    )

    result = run_python(code, {"DATABASE_URL": DB_URL})

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_the_worker_module_never_builds_the_api_settings() -> None:
    import inspect

    from app import worker

    source = inspect.getsource(worker)
    assert "load_settings(" not in source.replace("load_worker_settings(", "")
    assert "Settings(" not in source.replace("WorkerSettings(", "").replace(
        "load_worker_settings(", ""
    )


# --- the files each process reads by default -----------------------------------------------------


def test_the_worker_reads_backend_env_worker_by_default_and_never_the_api_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        f"DATABASE_URL={DB_URL}\nJWT_SECRET={TEST_JWT_SECRET}\n", encoding="utf-8"
    )

    with pytest.raises(ConfigurationError, match="DATABASE_URL"):
        load_worker_settings()  # only the API file exists: the worker must not borrow it

    (tmp_path / ".env.worker").write_text("DATABASE_URL=" + DB_URL + "\nLOG_LEVEL=DEBUG\n")
    settings = load_worker_settings()
    assert settings.log_level == "DEBUG"
    assert not hasattr(settings, "jwt_secret")


def test_the_api_reads_the_api_env_file_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.worker").write_text("DATABASE_URL=" + DB_URL + "\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="DATABASE_URL"):
        load_settings()  # only the worker file exists: the API must not read it

    (tmp_path / ".env").write_text(
        f"DATABASE_URL={DB_URL}\nJWT_SECRET={TEST_JWT_SECRET}\n", encoding="utf-8"
    )
    assert load_settings().database_url == DB_URL
