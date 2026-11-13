"""Typed application settings, read only from environment variables.

Two classes, because two processes read different things:

- `WorkerSettings`: what the ingestion worker needs (database, ingestion limits, PDF child limits,
  embedder, logs). It holds no secret and no HTTP setting, so the worker can run without
  `JWT_SECRET` and its container is never given one.
- `Settings`: the API. It extends `WorkerSettings` with authentication (the JWT secret stays
  mandatory), CORS, rate limits and the upload and admission limits.

Two more classes serve the database administration (change `database-least-privilege`) and share
nothing with the two above, so that a process only ever holds the credentials of its own job:

- `MigrationSettings`: the migrator URL (`MIGRATION_DATABASE_URL`, file `.env.migrate`). It never
  falls back to `DATABASE_URL`.
- `RolesSettings`: the administrator URL and the passwords of the four working roles
  (`.env.roles`), read only by the bootstrap.

Their values are `SecretStr`, and validation messages name variables, never values.
"""

from pathlib import Path
from typing import Annotated, Any, Literal

from limits import parse as parse_rate_limit
from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from app.core.cpu_quota import detect_cpu_quota

DEFAULT_DEV_CORS_ORIGINS = ["http://localhost:5173"]
MIN_JWT_SECRET_BYTES = 32
MIN_JWT_SECRET_DISTINCT_CHARS = 8
SECRET_PLACEHOLDERS = ("change_me", "changeme", "change-me")
MIN_ROLE_PASSWORD_CHARS = 16


class ConfigurationError(RuntimeError):
    """Raised at startup when the configuration is missing or unsafe."""


class WorkerSettings(BaseSettings):
    """Settings read by the ingestion worker; the API settings extend them.

    `TEST_DATABASE_URL` is intentionally absent: it is read only by the integration-test fixtures.
    """

    model_config = SettingsConfigDict(extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    database_url: str
    db_connect_timeout_seconds: int = Field(default=5, ge=1, le=60)

    # Document ingestion (change 6). Defaults are the values approved after the spike.
    max_pdf_pages: int = Field(default=300, ge=1, le=10_000)
    max_extracted_chars: int = Field(default=2_000_000, ge=1, le=50_000_000)
    max_chunks_per_document: int = Field(default=2_000, ge=1, le=100_000)
    ingestion_job_max_age_hours: int = Field(default=24, ge=1, le=720)
    ingestion_max_attempts: int = Field(default=3, ge=1, le=20)
    ingestion_lease_seconds: int = Field(default=120, ge=3, le=3600)
    ingestion_job_deadline_seconds: int = Field(default=600, ge=1, le=86_400)
    ingestion_batch_size: int = Field(default=16, ge=1, le=1024)
    pdf_child_max_memory_mb: int = Field(default=768, ge=64, le=16_384)
    pdf_child_cpu_seconds: int = Field(default=20, ge=1, le=3600)
    pdf_child_timeout_seconds: int = Field(default=30, ge=1, le=3600)
    pdf_child_max_output_mb: int = Field(default=8, ge=1, le=1024)
    db_statement_timeout_worker_seconds: int = Field(default=60, ge=1, le=3600)
    db_idle_in_transaction_timeout_seconds: int = Field(default=30, ge=1, le=3600)
    embedder_backend: Literal["local", "fake"] = "local"
    allow_fake_embedder: bool = False
    # Test-only: the real-server and real-process tests run on throwaway clusters as the owner. The
    # production entry points refuse a superuser connection otherwise (finding PG-01, DD-16).
    allow_superuser_database_role: bool = False
    embedding_model_path: Path = Path("/opt/models/paraphrase-multilingual-MiniLM-L12-v2")
    embedding_threads: int | None = Field(default=None, ge=1, le=256)

    @model_validator(mode="after")
    def _check_worker_ingestion(self) -> "WorkerSettings":
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
        if self.allow_superuser_database_role and self.app_env != "test":
            raise ValueError("ALLOW_SUPERUSER_DATABASE_ROLE is accepted only with APP_ENV=test")
        return self

    def effective_embedding_threads(self) -> int:
        """Inference threads: the explicit setting, otherwise the effective CPU quota."""
        if self.embedding_threads is not None:
            return self.embedding_threads
        return detect_cpu_quota()


class Settings(WorkerSettings):
    """API settings: the worker settings plus authentication, CORS, HTTP and upload limits."""

    db_statement_timeout_api_seconds: int = Field(default=15, ge=1, le=3600)
    jwt_secret: SecretStr
    jwt_issuer: str = Field(default="asistenteia", min_length=1, max_length=100)
    jwt_audience: str = Field(default="asistenteia-api", min_length=1, max_length=100)
    jwt_expire_minutes: int = Field(default=60, ge=1, le=1440)
    privacy_policy_version: str = Field(default="2026-10-v1", min_length=1, max_length=20)
    login_rate_limit: str = "10/minute"
    register_rate_limit: str = "5/minute"
    cors_origins: Annotated[list[str] | None, NoDecode] = None

    # Upload and admission limits (change 6); the worker never reads them.
    max_upload_mb: int = Field(default=10, ge=1, le=100)
    max_documents_per_subject: int = Field(default=50, ge=1, le=10_000)
    ingestion_queue_max: int = Field(default=100, ge=1, le=100_000)
    ingestion_pending_bytes_max_mb: int = Field(default=200, ge=1, le=100_000)
    upload_max_in_flight: int = Field(default=4, ge=1, le=100)
    upload_rate_limit: str = "10/minute"
    upload_body_timeout_seconds: int = Field(default=120, ge=1, le=3600)
    upload_body_idle_seconds: int = Field(default=20, ge=1, le=3600)

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
    def _check_upload_limits(self) -> "Settings":
        if self.upload_body_idle_seconds > self.upload_body_timeout_seconds:
            raise ValueError("UPLOAD_BODY_IDLE_SECONDS must not exceed UPLOAD_BODY_TIMEOUT_SECONDS")
        if self.ingestion_pending_bytes_max_mb < self.max_upload_mb:
            raise ValueError(
                "INGESTION_PENDING_BYTES_MAX_MB must be at least MAX_UPLOAD_MB, "
                "otherwise no file could ever be accepted"
            )
        return self


def _check_database_url(value: SecretStr, variable: str) -> SecretStr:
    """A PostgreSQL URL with user, password and database, without placeholders; never echoed."""
    try:
        url = make_url(value.get_secret_value())
    except ArgumentError:
        raise ValueError(f"{variable} is not a valid database URL") from None
    if not url.drivername.startswith("postgresql"):
        raise ValueError(f"{variable} must be a PostgreSQL URL")
    if not (url.username and url.password and url.database and url.host):
        raise ValueError(f"{variable} needs user, password, host and database")
    if any(marker in url.password.lower() for marker in SECRET_PLACEHOLDERS):
        raise ValueError(f"{variable} holds a placeholder password")
    return value


class MigrationSettings(BaseSettings):
    """What Alembic needs: the URL of the migrator role, nothing else.

    The variable is deliberately not `DATABASE_URL`: running a migration with the API environment
    fails instead of silently using the application (or any other) credential.
    """

    model_config = SettingsConfigDict(extra="ignore")

    migration_database_url: SecretStr

    @field_validator("migration_database_url")
    @classmethod
    def _check_url(cls, value: SecretStr) -> SecretStr:
        return _check_database_url(value, "MIGRATION_DATABASE_URL")


class RolesSettings(BaseSettings):
    """What the bootstrap needs: the administrator URL and the four working-role passwords."""

    model_config = SettingsConfigDict(extra="ignore")

    admin_database_url: SecretStr
    db_migrator_password: SecretStr
    db_app_password: SecretStr
    db_worker_password: SecretStr
    db_cli_password: SecretStr

    @field_validator("admin_database_url")
    @classmethod
    def _check_admin_url(cls, value: SecretStr) -> SecretStr:
        return _check_database_url(value, "ADMIN_DATABASE_URL")

    @field_validator(
        "db_migrator_password", "db_app_password", "db_worker_password", "db_cli_password"
    )
    @classmethod
    def _check_password(cls, value: SecretStr, info: Any) -> SecretStr:
        name = str(info.field_name).upper()
        secret = value.get_secret_value()
        if len(secret) < MIN_ROLE_PASSWORD_CHARS:
            raise ValueError(f"{name} must be at least {MIN_ROLE_PASSWORD_CHARS} characters long")
        if any(marker in secret.lower() for marker in SECRET_PLACEHOLDERS):
            raise ValueError(f"{name} looks like a placeholder; generate a random value")
        return value

    @model_validator(mode="after")
    def _check_distinct(self) -> "RolesSettings":
        passwords = [
            self.db_migrator_password.get_secret_value(),
            self.db_app_password.get_secret_value(),
            self.db_worker_password.get_secret_value(),
            self.db_cli_password.get_secret_value(),
        ]
        if len(set(passwords)) != len(passwords):
            raise ValueError("the four role passwords must be distinct")
        return self


class CliSettings(BaseSettings):
    """What the administrative commands need: the CLI role URL and the environment name.

    The variable is deliberately not `DATABASE_URL`: the command fails instead of silently using the
    API credential, and the CLI never reads `JWT_SECRET` or any other API setting.
    """

    model_config = SettingsConfigDict(extra="ignore")

    cli_database_url: SecretStr
    # Fail closed: the command reads no API file, so an unset APP_ENV must not open the seed gate.
    app_env: Literal["development", "test", "production"] = "production"
    db_connect_timeout_seconds: int = Field(default=5, ge=1, le=60)

    @field_validator("cli_database_url")
    @classmethod
    def _check_url(cls, value: SecretStr) -> SecretStr:
        return _check_database_url(value, "CLI_DATABASE_URL")


def _load[SettingsT: BaseSettings](model: type[SettingsT], env_file: str | None) -> SettingsT:
    """Build `model`, turning validation errors into a message naming the variables only."""
    try:
        return model(_env_file=env_file)
    except ValidationError as exc:
        problems = []
        for error in exc.errors():
            location = error["loc"]
            name = str(location[0]).upper() if location else "CONFIGURATION"
            message = str(error["msg"])
            problems.append(f"{name}: {message}")
        raise ConfigurationError("Invalid configuration - " + "; ".join(problems)) from None


def load_settings(env_file: str | None = ".env") -> Settings:
    """Load the API settings (`.env`)."""
    return _load(Settings, env_file)


def load_cli_settings(env_file: str | None = ".env.cli") -> CliSettings:
    """Load the CLI role credential (`.env.cli`); no API setting is read or required."""
    return _load(CliSettings, env_file)


def load_worker_settings(env_file: str | None = ".env.worker") -> WorkerSettings:
    """Load the worker settings (`.env.worker`); no API secret is read or required."""
    return _load(WorkerSettings, env_file)


class VerifySettings(BaseSettings):
    """What `db-verify` needs: the migrator URL and the four passwords for the login probe."""

    model_config = SettingsConfigDict(extra="ignore")

    migration_database_url: SecretStr
    db_migrator_password: SecretStr
    db_app_password: SecretStr
    db_worker_password: SecretStr
    db_cli_password: SecretStr

    @field_validator("migration_database_url")
    @classmethod
    def _check_url(cls, value: SecretStr) -> SecretStr:
        return _check_database_url(value, "MIGRATION_DATABASE_URL")


def load_verify_settings(
    env_files: tuple[str, ...] | None = (".env.migrate", ".env.roles"),
) -> VerifySettings:
    """Load the verifier credentials; the administrator URL in `.env.roles` is never read."""
    try:
        return VerifySettings(_env_file=env_files)
    except ValidationError as exc:
        problems = [
            f"{str(e['loc'][0]).upper() if e['loc'] else 'CONFIGURATION'}: {e['msg']}"
            for e in exc.errors()
        ]
        raise ConfigurationError("Invalid configuration - " + "; ".join(problems)) from None


def load_migration_settings(env_file: str | None = ".env.migrate") -> MigrationSettings:
    """Load the migrator URL (`.env.migrate`); no API setting is read or required."""
    return _load(MigrationSettings, env_file)


def load_roles_settings(env_file: str | None = ".env.roles") -> RolesSettings:
    """Load the bootstrap credentials (`.env.roles`); read only by the bootstrap."""
    return _load(RolesSettings, env_file)
