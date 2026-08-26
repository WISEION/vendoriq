"""Runtime configuration. Every value comes from the environment / ``.env``."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import ClassVar, Literal

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
    #: Readable companion cookie for the double-submit CSRF check (spec §13, security).
    csrf_cookie: str = "vendoriq_csrf"
    access_token_ttl_minutes: int = 480
    otp_ttl_minutes: int = 10
    #: Wrong codes tolerated per issued OTP before it is burned.
    otp_max_attempts: int = 5
    #: OTP requests allowed per e-mail address (and per client address) per window.
    otp_rate_limit: int = 5
    otp_rate_limit_window_seconds: int = 600
    #: Password logins tolerated per address per window before ``429``.
    login_rate_limit: int = 10
    #: TOTP step and the ± window of steps accepted, RFC 6238 §5.2.
    totp_step_seconds: int = 30
    totp_window: int = 1
    #: Lifetime of a password-accepted, TOTP-pending challenge.
    totp_challenge_ttl_seconds: int = 300

    database_url: str = "postgresql+psycopg://vendoriq:vendoriq@localhost:5432/vendoriq"
    test_database_url: str = "postgresql+psycopg://vendoriq:vendoriq@localhost:5432/vendoriq_test"
    db_echo: bool = False

    storage_backend: StorageBackend = "local"
    storage_local_dir: Path = REPO_ROOT / "var" / "storage"
    #: Lifetime of an upload ticket and of a signed download link.
    storage_url_ttl_minutes: int = 15
    #: Largest accepted document, in bytes. PDF only (spec §7).
    upload_max_bytes: int = 20 * 1024 * 1024
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

    #: The value shipped in `.env.example`. One string signs every session cookie, TOTP
    #: challenge and upload ticket in the system, so it being the published default in
    #: production is not a weak secret, it is no secret at all.
    PLACEHOLDER_SESSION_SECRET: ClassVar[str] = "change-me-in-production"
    #: 32 hex characters is 16 bytes of entropy — the floor, not the recommendation. The
    #: runbook says `openssl rand -hex 32`.
    MINIMUM_SESSION_SECRET_LENGTH: ClassVar[int] = 32

    @model_validator(mode="after")
    def _refuse_test_auth_in_production(self) -> Settings:
        """Brief §6: test mode must be impossible to leave on by accident."""
        if self.app_env == "production" and self.auth_mode == "test":
            raise ValueError(
                "AUTH_MODE=test is refused when APP_ENV=production. "
                "Set AUTH_MODE=live or change APP_ENV."
            )
        return self

    @model_validator(mode="after")
    def _refuse_a_guessable_session_secret_in_production(self) -> Settings:
        """The companion guard to the one above, and it was missing (3B, finding 9).

        `AUTH_MODE` was checked and `SESSION_SECRET` was not, which meant a production stack
        could start signing its cookies with the string printed in `infra/.env.example`.
        Anybody who has read this repository can then mint a session for any role.

        Checked here rather than in the compose overlay because a native deployment never
        goes through compose, and this is the one place both paths pass through.
        """
        if self.app_env != "production":
            return self
        if self.session_secret == self.PLACEHOLDER_SESSION_SECRET:
            raise ValueError(
                "SESSION_SECRET is still the placeholder from .env.example and APP_ENV is "
                "production. Generate one: openssl rand -hex 32"
            )
        if len(self.session_secret) < self.MINIMUM_SESSION_SECRET_LENGTH:
            raise ValueError(
                f"SESSION_SECRET must be at least {self.MINIMUM_SESSION_SECRET_LENGTH} "
                "characters when APP_ENV=production. Generate one: openssl rand -hex 32"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings singleton."""
    return Settings()
