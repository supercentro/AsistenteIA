"""Typed application settings, read only from environment variables."""

from typing import Annotated, Any, Literal

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_DEV_CORS_ORIGINS = ["http://localhost:5173"]


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
    cors_origins: Annotated[list[str] | None, NoDecode] = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
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
