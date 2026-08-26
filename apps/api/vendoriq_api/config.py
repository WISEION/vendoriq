"""Runtime configuration. Every value comes from the environment / ``.env``."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Repository root — used to locate ``docs/openapi.yaml`` and the local storage dir.
REPO_ROOT = Path(__file__).resolve().parents[3]

AuthMode = Literal["test", "live"]
AppEnv = Literal["development", "staging", "production"]
StorageBackend = Literal["local", "s3"]


class Settings(BaseSettings):
    """Typed view of the environment described in ``infra/.env.example``."""

    model_config = SettingsConfigDict(
        env_file=(".env", "infra/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: AppEnv = "development"
    app_name: str = "VendorIQ"
    api_prefix: str = "/api"
    log_level: str = "INFO"

    #: ``test`` seeds the test accounts and reveals OTP/TOTP codes; refused in production.
    auth_mode: AuthMode = "test"
    session_secret: str = "change-me-in-production"
    session_cookie: str = "vendoriq_session"
    access_token_ttl_minutes: int = 480
    otp_ttl_minutes: int = 10

    database_url: str = "postgresql+psycopg://vendoriq:vendoriq@localhost:5432/vendoriq"
    test_database_url: str = "postgresql+psycopg://vendoriq:vendoriq@localhost:5432/vendoriq_test"
    db_echo: bool = False

    storage_backend: StorageBackend = "local"
    storage_local_dir: Path = REPO_ROOT / "var" / "storage"
    s3_endpoint_url: str | None = None
    s3_bucket: str = "vendoriq"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_region: str = "us-east-1"

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "noreply@vendoriq.local"
    smtp_tls: bool = True

    default_locale: Literal["az", "en"] = "az"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @model_validator(mode="after")
    def _refuse_test_auth_in_production(self) -> Settings:
        """Brief §6: test mode must be impossible to leave on by accident."""
        if self.app_env == "production" and self.auth_mode == "test":
            raise ValueError(
                "AUTH_MODE=test is refused when APP_ENV=production. "
                "Set AUTH_MODE=live or change APP_ENV."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings singleton."""
    return Settings()
