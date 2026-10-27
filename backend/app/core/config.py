"""Typed application settings, read only from environment variables."""

from typing import Annotated, Any, Literal

from limits import parse as parse_rate_limit
from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

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

    @field_validator("login_rate_limit", "register_rate_limit")
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
