from functools import lru_cache
from typing import Literal, Self

from pydantic import AnyHttpUrl, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from Schema Sentry environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="SCHEMA_SENTRY_",
        env_file=".env",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    metadata_database_url: str
    source_database_url: str
    api_key: SecretStr
    auth_disabled: bool = False
    trust_proxy_auth: bool = False
    log_level: str = "INFO"
    slack_webhook_url: SecretStr | None = None
    smtp_host: str = "mailpit"
    smtp_port: int = 1025
    email_from: str = "schema-sentry@localhost"
    email_to: tuple[str, ...] = ()
    dashboard_base_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8000/")

    @model_validator(mode="after")
    def protect_production_authentication(self) -> Self:
        if self.environment == "production" and self.auth_disabled:
            raise ValueError("AUTH_DISABLED cannot be true in production")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # Values come from BaseSettings sources.
