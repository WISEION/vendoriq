"""Accounts, one-time codes and machine credentials (brief §6, spec §3)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, JsonList, TimestampMixin, pg_enum, uuid_pk
from .enums import UserRole

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .vendor import Vendor


class User(Base, TimestampMixin):
    """Staff account (password + TOTP) or vendor portal account (e-mail + OTP)."""

    __tablename__ = "app_user"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255))
    #: NULL for vendor accounts, which authenticate with a one-time code only.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(
        pg_enum(UserRole, "user_role"), nullable=False, index=True
    )
    #: Set for role ``vendor``; scopes every read to that vendor's own data.
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vendor.id", ondelete="CASCADE"), nullable=True, index=True
    )
    totp_secret: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: UI language preference, ``az`` or ``en``.
    locale: Mapped[str] = mapped_column(String(8), nullable=False, default="az")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    vendor: Mapped[Vendor | None] = relationship()


class OtpCode(Base):
    """A hashed one-time code issued to a vendor e-mail address."""

    __tablename__ = "otp_code"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ApiKey(Base, TimestampMixin):
    """Machine credential for other products; scoped read/write per module (brief §2)."""

    __tablename__ = "api_key"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    #: Only the hash is stored; the plaintext key is shown once at creation.
    hashed_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    #: First characters of the key, so a person can tell two keys apart in the list without
    #: the plaintext ever being retrievable. Declared by the contract's ``ApiKey``.
    prefix: Mapped[str | None] = mapped_column(String(16))
    #: e.g. ``["vendors:read", "projects:write"]``.
    scopes: Mapped[JsonList] = mapped_column(nullable=False, default=list)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class RevokedSession(Base):
    """One row per logout, kept only until that token would have expired anyway.

    The session cookie is a stateless signature, so there is nothing to delete when a user
    logs out — the token stays valid until `exp` no matter what the server does with its
    cookies. This is the list of tokens that have been withdrawn early (3B, finding 3,
    migration `0005`).

    Keyed by the token's own `jti` rather than by user: signing out on a phone must not sign
    out the desktop.
    """

    __tablename__ = "revoked_session"

    jti: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: When the token expires on its own; after that this row proves nothing new. Indexed
    #: because the only bulk query against this table is the housekeeping delete by expiry.
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    #: Server-side default: the instant belongs to the database, not to whichever process
    #: happened to handle the logout.
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
