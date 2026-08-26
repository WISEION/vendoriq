"""Health, authentication, sessions and user administration.

Contract tags ``health``, ``auth`` and the user half of ``admin``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from ..models.enums import (
    UserRole,
    VendorType,
)
from .base import EmailStr, Model, PageMeta


class Health(Model):
    status: Literal["ok"]
    version: str
    app_env: Literal["development", "staging", "production"]
    auth_mode: Literal["test", "live"]
    storage_backend: Literal["local", "s3"]


class VendorRegistration(Model):
    legal_name: str = Field(min_length=2)
    voen: str = Field(pattern=r"^[0-9]{10}$")
    type: VendorType
    contact_name: str
    position: str | None = None
    phone: str | None = None
    email: EmailStr
    locale: Literal["az", "en"] = "az"


class OtpRequest(Model):
    email: EmailStr


class OtpChallenge(Model):
    email: str
    expires_at: datetime
    debug_code: str | None = None


class OtpVerification(Model):
    email: EmailStr
    code: str = Field(pattern=r"^[0-9]{6}$")


class StaffLogin(Model):
    email: EmailStr
    password: str


class TotpChallenge(Model):
    challenge_id: uuid.UUID
    totp_required: bool
    debug_code: str | None = None


class TotpVerification(Model):
    challenge_id: uuid.UUID
    code: str = Field(pattern=r"^[0-9]{6}$")


class User(Model):
    id: uuid.UUID
    email: str
    full_name: str | None = None
    role: UserRole
    vendor_id: uuid.UUID | None = None
    vendor_name: str | None = None
    locale: Literal["az", "en"] = "az"
    is_active: bool
    has_totp: bool = False
    last_login_at: datetime | None = None


class UserCreated(User):
    totp_provisioning_uri: str | None = None


class UserPage(PageMeta):
    items: list[User]


class UserInput(Model):
    email: EmailStr
    full_name: str | None = None
    role: UserRole
    vendor_id: uuid.UUID | None = None
    locale: Literal["az", "en"] | None = None
    is_active: bool | None = None
    password: str | None = None


class UserRoleInput(Model):
    role: UserRole


class Session(Model):
    user: User
    expires_at: datetime
    csrf_token: str | None = None


class Me(User):
    permissions: list[str] = Field(default_factory=list)
    auth_mode: Literal["test", "live"] = "test"
