"""Settings introduced by the document-ingestion change (group 2, task 2.1)."""

from pathlib import Path

import pytest

from app.core import config as config_module
from app.core.config import ConfigurationError, Settings, load_settings
from tests.constants import TEST_JWT_SECRET

DB_URL = "postgresql+psycopg://user:pw@localhost:5432/asistenteia"

INGESTION_VARIABLES = (
    "MAX_UPLOAD_MB",
    "MAX_PDF_PAGES",
    "MAX_EXTRACTED_CHARS",
    "MAX_CHUNKS_PER_DOCUMENT",
    "MAX_DOCUMENTS_PER_SUBJECT",
    "INGESTION_QUEUE_MAX",
    "INGESTION_PENDING_BYTES_MAX_MB",
    "INGESTION_JOB_MAX_AGE_HOURS",
    "INGESTION_MAX_ATTEMPTS",
    "INGESTION_LEASE_SECONDS",
    "INGESTION_JOB_DEADLINE_SECONDS",
    "INGESTION_BATCH_SIZE",
    "UPLOAD_MAX_IN_FLIGHT",
    "UPLOAD_RATE_LIMIT",
    "UPLOAD_BODY_TIMEOUT_SECONDS",
    "UPLOAD_BODY_IDLE_SECONDS",
    "PDF_CHILD_MAX_MEMORY_MB",
    "PDF_CHILD_CPU_SECONDS",
    "PDF_CHILD_TIMEOUT_SECONDS",
    "PDF_CHILD_MAX_OUTPUT_MB",
    "DB_STATEMENT_TIMEOUT_API_SECONDS",
    "DB_STATEMENT_TIMEOUT_WORKER_SECONDS",
    "DB_IDLE_IN_TRANSACTION_TIMEOUT_SECONDS",
    "EMBEDDER_BACKEND",
    "ALLOW_FAKE_EMBEDDER",
    "EMBEDDING_MODEL_PATH",
    "EMBEDDING_THREADS",
    "APP_ENV",
    "CORS_ORIGINS",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in INGESTION_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    monkeypatch.delenv("ALLOW_FAKE_LLM", raising=False)
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("GOOGLE_API_KEY", "AIza-test-key-for-unit-tests-only")


def test_defaults_are_the_values_approved_after_the_spike() -> None:
    settings = load_settings(env_file=None)

    assert settings.max_upload_mb == 10
    assert settings.max_pdf_pages == 300
    assert settings.max_extracted_chars == 2_000_000
    assert settings.max_chunks_per_document == 2_000
    assert settings.max_documents_per_subject == 50
    assert settings.ingestion_queue_max == 100
    assert settings.ingestion_pending_bytes_max_mb == 200
    assert settings.ingestion_job_max_age_hours == 24
    assert settings.ingestion_max_attempts == 3
    assert settings.ingestion_lease_seconds == 120
    assert settings.ingestion_job_deadline_seconds == 600
    assert settings.ingestion_batch_size == 16
    assert settings.upload_max_in_flight == 4
    assert settings.upload_rate_limit == "10/minute"
    assert settings.upload_body_timeout_seconds == 120
    assert settings.upload_body_idle_seconds == 20
    assert settings.pdf_child_max_memory_mb == 768
    assert settings.pdf_child_cpu_seconds == 20
    assert settings.pdf_child_timeout_seconds == 30
    assert settings.pdf_child_max_output_mb == 8
    assert settings.db_statement_timeout_api_seconds == 15
    assert settings.db_statement_timeout_worker_seconds == 60
    assert settings.db_idle_in_transaction_timeout_seconds == 30
    assert settings.embedder_backend == "local"
    assert settings.allow_fake_embedder is False
    assert settings.embedding_model_path == Path(
        "/opt/models/paraphrase-multilingual-MiniLM-L12-v2"
    )
    assert settings.embedding_threads is None


@pytest.mark.parametrize(
    ("variable", "value", "attribute", "expected"),
    [
        ("MAX_UPLOAD_MB", "5", "max_upload_mb", 5),
        ("MAX_PDF_PAGES", "100", "max_pdf_pages", 100),
        ("MAX_EXTRACTED_CHARS", "500000", "max_extracted_chars", 500_000),
        ("MAX_CHUNKS_PER_DOCUMENT", "500", "max_chunks_per_document", 500),
        ("MAX_DOCUMENTS_PER_SUBJECT", "20", "max_documents_per_subject", 20),
        ("INGESTION_QUEUE_MAX", "7", "ingestion_queue_max", 7),
        ("INGESTION_PENDING_BYTES_MAX_MB", "64", "ingestion_pending_bytes_max_mb", 64),
        ("INGESTION_JOB_MAX_AGE_HOURS", "6", "ingestion_job_max_age_hours", 6),
        ("INGESTION_MAX_ATTEMPTS", "5", "ingestion_max_attempts", 5),
        ("INGESTION_LEASE_SECONDS", "3", "ingestion_lease_seconds", 3),
        ("INGESTION_JOB_DEADLINE_SECONDS", "300", "ingestion_job_deadline_seconds", 300),
        ("INGESTION_BATCH_SIZE", "32", "ingestion_batch_size", 32),
        ("UPLOAD_MAX_IN_FLIGHT", "2", "upload_max_in_flight", 2),
        ("UPLOAD_RATE_LIMIT", "3/second", "upload_rate_limit", "3/second"),
        ("UPLOAD_BODY_TIMEOUT_SECONDS", "90", "upload_body_timeout_seconds", 90),
        ("UPLOAD_BODY_IDLE_SECONDS", "10", "upload_body_idle_seconds", 10),
        ("PDF_CHILD_MAX_MEMORY_MB", "512", "pdf_child_max_memory_mb", 512),
        ("PDF_CHILD_CPU_SECONDS", "10", "pdf_child_cpu_seconds", 10),
        ("PDF_CHILD_TIMEOUT_SECONDS", "15", "pdf_child_timeout_seconds", 15),
        ("PDF_CHILD_MAX_OUTPUT_MB", "4", "pdf_child_max_output_mb", 4),
        ("DB_STATEMENT_TIMEOUT_API_SECONDS", "5", "db_statement_timeout_api_seconds", 5),
        ("DB_STATEMENT_TIMEOUT_WORKER_SECONDS", "30", "db_statement_timeout_worker_seconds", 30),
        (
            "DB_IDLE_IN_TRANSACTION_TIMEOUT_SECONDS",
            "10",
            "db_idle_in_transaction_timeout_seconds",
            10,
        ),
        ("EMBEDDING_THREADS", "2", "embedding_threads", 2),
    ],
)
def test_every_value_can_be_set_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
    value: str,
    attribute: str,
    expected: object,
) -> None:
    monkeypatch.setenv(variable, value)

    settings = load_settings(env_file=None)

    assert getattr(settings, attribute) == expected


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("MAX_UPLOAD_MB", "0"),
        ("MAX_UPLOAD_MB", "-1"),
        ("MAX_UPLOAD_MB", "101"),
        ("MAX_UPLOAD_MB", "ten"),
        ("MAX_PDF_PAGES", "0"),
        ("MAX_EXTRACTED_CHARS", "0"),
        ("MAX_CHUNKS_PER_DOCUMENT", "0"),
        ("MAX_DOCUMENTS_PER_SUBJECT", "0"),
        ("INGESTION_QUEUE_MAX", "0"),
        ("INGESTION_PENDING_BYTES_MAX_MB", "0"),
        ("INGESTION_JOB_MAX_AGE_HOURS", "0"),
        ("INGESTION_MAX_ATTEMPTS", "0"),
        ("INGESTION_LEASE_SECONDS", "2"),
        ("INGESTION_JOB_DEADLINE_SECONDS", "0"),
        ("INGESTION_BATCH_SIZE", "0"),
        ("INGESTION_BATCH_SIZE", "1025"),
        ("UPLOAD_MAX_IN_FLIGHT", "0"),
        ("UPLOAD_RATE_LIMIT", "often"),
        ("UPLOAD_RATE_LIMIT", "0/minute"),
        ("UPLOAD_BODY_TIMEOUT_SECONDS", "0"),
        ("UPLOAD_BODY_IDLE_SECONDS", "0"),
        ("PDF_CHILD_MAX_MEMORY_MB", "63"),
        ("PDF_CHILD_CPU_SECONDS", "0"),
        ("PDF_CHILD_TIMEOUT_SECONDS", "0"),
        ("PDF_CHILD_MAX_OUTPUT_MB", "0"),
        ("DB_STATEMENT_TIMEOUT_API_SECONDS", "0"),
        ("DB_STATEMENT_TIMEOUT_WORKER_SECONDS", "0"),
        ("DB_IDLE_IN_TRANSACTION_TIMEOUT_SECONDS", "0"),
        ("EMBEDDER_BACKEND", "remote"),
        ("EMBEDDING_THREADS", "0"),
        ("EMBEDDING_THREADS", "-2"),
        ("EMBEDDING_THREADS", "many"),
    ],
)
def test_invalid_values_are_rejected_naming_the_variable(
    monkeypatch: pytest.MonkeyPatch, variable: str, value: str
) -> None:
    monkeypatch.setenv(variable, value)

    with pytest.raises(ConfigurationError) as exc:
        load_settings(env_file=None)

    assert variable in str(exc.value)


@pytest.mark.parametrize("app_env", ["development", "production"])
def test_fake_embedder_is_rejected_outside_the_test_environment(
    monkeypatch: pytest.MonkeyPatch, app_env: str
) -> None:
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example")
    monkeypatch.setenv("EMBEDDER_BACKEND", "fake")

    with pytest.raises(ConfigurationError) as exc:
        load_settings(env_file=None)

    assert "EMBEDDER_BACKEND" in str(exc.value)


def test_fake_embedder_is_accepted_in_the_test_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("EMBEDDER_BACKEND", "fake")

    assert load_settings(env_file=None).embedder_backend == "fake"


def test_fake_embedder_needs_an_explicit_flag_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("EMBEDDER_BACKEND", "fake")
    monkeypatch.setenv("ALLOW_FAKE_EMBEDDER", "true")

    assert load_settings(env_file=None).embedder_backend == "fake"


def test_fake_embedder_is_never_accepted_in_production_even_with_the_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example")
    monkeypatch.setenv("EMBEDDER_BACKEND", "fake")
    monkeypatch.setenv("ALLOW_FAKE_EMBEDDER", "true")

    with pytest.raises(ConfigurationError) as exc:
        load_settings(env_file=None)

    assert "EMBEDDER_BACKEND" in str(exc.value)


def test_the_allow_flag_alone_does_not_select_the_fake_embedder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ALLOW_FAKE_EMBEDDER", "true")

    assert load_settings(env_file=None).embedder_backend == "local"


@pytest.mark.parametrize(
    ("variable", "value", "other"),
    [
        ("INGESTION_JOB_DEADLINE_SECONDS", "120", "INGESTION_LEASE_SECONDS"),
        ("UPLOAD_BODY_IDLE_SECONDS", "121", "UPLOAD_BODY_TIMEOUT_SECONDS"),
        ("INGESTION_PENDING_BYTES_MAX_MB", "9", "MAX_UPLOAD_MB"),
    ],
)
def test_inconsistent_combinations_are_rejected(
    monkeypatch: pytest.MonkeyPatch, variable: str, value: str, other: str
) -> None:
    monkeypatch.setenv(variable, value)

    with pytest.raises(ConfigurationError) as exc:
        load_settings(env_file=None)

    assert variable in str(exc.value)
    assert other in str(exc.value)


def test_embedding_threads_default_follows_the_cpu_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config_module, "detect_cpu_quota", lambda: 3)

    assert load_settings(env_file=None).effective_embedding_threads() == 3


def test_an_explicit_embedding_threads_overrides_the_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config_module, "detect_cpu_quota", lambda: 3)
    monkeypatch.setenv("EMBEDDING_THREADS", "2")

    assert load_settings(env_file=None).effective_embedding_threads() == 2


def test_settings_class_does_not_read_a_quota_until_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail() -> int:
        raise AssertionError("the quota must be read lazily")

    monkeypatch.setattr(config_module, "detect_cpu_quota", fail)

    assert isinstance(load_settings(env_file=None), Settings)
