"""Typed application settings, read only from environment variables."""

from pathlib import Path
from typing import Annotated, Any, Literal

from limits import parse as parse_rate_limit
from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.core.cpu_quota import detect_cpu_quota

DEFAULT_DEV_CORS_ORIGINS = ["http://localhost:5173"]
MIN_JWT_SECRET_BYTES = 32
MIN_JWT_SECRET_DISTINCT_CHARS = 8
SECRET_PLACEHOLDERS = ("change_me", "changeme", "change-me")


class ConfigurationError(RuntimeError):
    """Raised at startup when the configuration is missing or unsafe."""


class Settings(BaseSettings):
    """Application settings.

    `TEST_DATABASE_URL` is intentionally absent: it is read only by the integration-test fixtures.
    """

    model_config = SettingsConfigDict(extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    database_url: str
    db_connect_timeout_seconds: int = Field(default=5, ge=1, le=60)
    jwt_secret: SecretStr
    jwt_issuer: str = Field(default="asistenteia", min_length=1, max_length=100)
    jwt_audience: str = Field(default="asistenteia-api", min_length=1, max_length=100)
    jwt_expire_minutes: int = Field(default=60, ge=1, le=1440)
    privacy_policy_version: str = Field(default="2026-10-v1", min_length=1, max_length=20)
    login_rate_limit: str = "10/minute"
    register_rate_limit: str = "5/minute"
    cors_origins: Annotated[list[str] | None, NoDecode] = None

    # Document ingestion (change 6). Defaults are the values approved after the spike.
    max_upload_mb: int = Field(default=10, ge=1, le=100)
    max_pdf_pages: int = Field(default=300, ge=1, le=10_000)
    max_extracted_chars: int = Field(default=2_000_000, ge=1, le=50_000_000)
    max_chunks_per_document: int = Field(default=2_000, ge=1, le=100_000)
    max_documents_per_subject: int = Field(default=50, ge=1, le=10_000)
    ingestion_queue_max: int = Field(default=100, ge=1, le=100_000)
    ingestion_pending_bytes_max_mb: int = Field(default=200, ge=1, le=100_000)
    ingestion_job_max_age_hours: int = Field(default=24, ge=1, le=720)
    ingestion_max_attempts: int = Field(default=3, ge=1, le=20)
    ingestion_lease_seconds: int = Field(default=120, ge=3, le=3600)
    ingestion_job_deadline_seconds: int = Field(default=600, ge=1, le=86_400)
    ingestion_batch_size: int = Field(default=16, ge=1, le=1024)
    upload_max_in_flight: int = Field(default=4, ge=1, le=100)
    upload_rate_limit: str = "10/minute"
    upload_body_timeout_seconds: int = Field(default=120, ge=1, le=3600)
    upload_body_idle_seconds: int = Field(default=20, ge=1, le=3600)
    pdf_child_max_memory_mb: int = Field(default=768, ge=64, le=16_384)
    pdf_child_cpu_seconds: int = Field(default=20, ge=1, le=3600)
    pdf_child_timeout_seconds: int = Field(default=30, ge=1, le=3600)
    pdf_child_max_output_mb: int = Field(default=8, ge=1, le=1024)
    db_statement_timeout_api_seconds: int = Field(default=15, ge=1, le=3600)
    db_statement_timeout_worker_seconds: int = Field(default=60, ge=1, le=3600)
    db_idle_in_transaction_timeout_seconds: int = Field(default=30, ge=1, le=3600)
    embedder_backend: Literal["local", "fake"] = "local"
    allow_fake_embedder: bool = False
    embedding_model_path: Path = Path("/opt/models/paraphrase-multilingual-MiniLM-L12-v2")
    embedding_threads: int | None = Field(default=None, ge=1, le=256)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("jwt_secret")
    @classmethod
    def _check_jwt_secret(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if len(secret.encode("utf-8")) < MIN_JWT_SECRET_BYTES:
            raise ValueError(f"JWT_SECRET must be at least {MIN_JWT_SECRET_BYTES} bytes long")
        if any(marker in secret.lower() for marker in SECRET_PLACEHOLDERS):
            raise ValueError("JWT_SECRET looks like a placeholder; generate a random value")
        if len(set(secret)) < MIN_JWT_SECRET_DISTINCT_CHARS:
            raise ValueError("JWT_SECRET has too little variety; generate a random value")
        return value

    @field_validator("login_rate_limit", "register_rate_limit", "upload_rate_limit")
    @classmethod
    def _check_rate_limit(cls, value: str) -> str:
        try:
            item = parse_rate_limit(value)
        except ValueError:
            raise ValueError("rate limit must look like '10/minute'") from None
        if item.amount < 1:
            raise ValueError("rate limit must allow at least one request")
        return value

    @model_validator(mode="after")
    def _check_cors(self) -> "Settings":
        if self.cors_origins is None:
            if self.app_env == "production":
                raise ValueError("CORS_ORIGINS must be set explicitly when APP_ENV=production")
            self.cors_origins = list(DEFAULT_DEV_CORS_ORIGINS)
        if not self.cors_origins and self.app_env == "production":
            raise ValueError("CORS_ORIGINS must not be empty when APP_ENV=production")
        if "*" in self.cors_origins:
            raise ValueError("CORS_ORIGINS must not contain a wildcard '*'")
        return self

    @model_validator(mode="after")
    def _check_ingestion(self) -> "Settings":
        if self.embedder_backend == "fake" and not (
            self.app_env == "test" or (self.allow_fake_embedder and self.app_env != "production")
        ):
            raise ValueError(
                "EMBEDDER_BACKEND=fake is accepted only with APP_ENV=test, or with "
                "ALLOW_FAKE_EMBEDDER=true outside production"
            )
        if self.ingestion_job_deadline_seconds <= self.ingestion_lease_seconds:
            raise ValueError(
                "INGESTION_JOB_DEADLINE_SECONDS must be greater than INGESTION_LEASE_SECONDS"
            )
        if self.upload_body_idle_seconds > self.upload_body_timeout_seconds:
            raise ValueError("UPLOAD_BODY_IDLE_SECONDS must not exceed UPLOAD_BODY_TIMEOUT_SECONDS")
        if self.ingestion_pending_bytes_max_mb < self.max_upload_mb:
            raise ValueError(
                "INGESTION_PENDING_BYTES_MAX_MB must be at least MAX_UPLOAD_MB, "
                "otherwise no file could ever be accepted"
            )
        return self

    def effective_embedding_threads(self) -> int:
        """Inference threads: the explicit setting, otherwise the effective CPU quota."""
        if self.embedding_threads is not None:
            return self.embedding_threads
        return detect_cpu_quota()


def load_settings(env_file: str | None = ".env") -> Settings:
    """Load settings, turning validation errors into a message naming the variables."""
    try:
        return Settings(_env_file=env_file)
    except ValidationError as exc:
        problems = []
        for error in exc.errors():
            location = error["loc"]
            name = str(location[0]).upper() if location else "CONFIGURATION"
            message = str(error["msg"])
            problems.append(f"{name}: {message}")
        raise ConfigurationError("Invalid configuration - " + "; ".join(problems)) from None
