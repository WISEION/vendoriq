"""Accounts and API keys (spec §3, brief §2)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import UnitOfWork
from ..errors import ApiError
from ..models import ApiKey, User, Vendor
from ..models.enums import Scope, UserRole
from ..security import hashing
from ..security import totp as totp_module
from ..security.tokens import new_api_key
from . import audit

FIELDS = ("email", "full_name", "role", "vendor_id", "locale", "is_active")

STAFF_ROLES = frozenset({UserRole.OFFICER, UserRole.COMMISSION, UserRole.MANAGER, UserRole.ADMIN})


def get(session: Session, user_id: uuid.UUID) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise ApiError(404, "not_found", "No such user.")
    return user


def list_page(
    session: Session,
    *,
    roles: list[UserRole] | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[User], int]:
    query = select(User)
    if roles:
        query = query.where(User.role.in_(roles))
    if q:
        needle = f"%{q.strip().lower()}%"
        query = query.where(
            or_(func.lower(User.email).like(needle), func.lower(User.full_name).like(needle))
        )
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(
        query.order_by(User.email.asc()).limit(page_size).offset((page - 1) * page_size)
    ).all()
    return list(rows), total


def vendor_name(session: Session, user: User) -> str | None:
    if user.vendor_id is None:
        return None
    vendor = session.get(Vendor, user.vendor_id)
    return vendor.legal_name if vendor else None


def _validate_shape(role: UserRole, vendor_id: uuid.UUID | None) -> None:
    """Contract: a ``vendor`` role requires ``vendor_id``; staff roles must not have one."""
    if role is UserRole.VENDOR and vendor_id is None:
        raise ApiError(422, "validation_error", "A vendor account requires vendor_id.")
    if role is not UserRole.VENDOR and vendor_id is not None:
        raise ApiError(422, "validation_error", "A staff account must not carry vendor_id.")


def create(uow: UnitOfWork, data: dict[str, Any]) -> tuple[User, str | None]:
    """Create an account. Staff accounts are enrolled in TOTP and the URI is returned once."""
    email = str(data["email"]).strip().lower()
    if uow.session.scalar(select(User).where(User.email == email)) is not None:
        raise ApiError(409, "conflict", "An account with this e-mail already exists.")
    role = UserRole(data["role"])
    vendor_id = data.get("vendor_id")
    _validate_shape(role, vendor_id)

    password = data.get("password")
    if role is UserRole.VENDOR and password:
        raise ApiError(
            422,
            "validation_error",
            "Vendor accounts authenticate with a one-time code, not a password.",
        )

    user = User(
        email=email,
        full_name=data.get("full_name"),
        role=role,
        vendor_id=vendor_id,
        locale=data.get("locale") or "az",
        is_active=bool(data.get("is_active", True)),
        password_hash=hashing.hash_password(password) if password else None,
        totp_secret=totp_module.generate_secret() if role in STAFF_ROLES else None,
    )
    uow.session.add(user)
    uow.flush()
    audit.record(
        uow,
        entity_type="app_user",
        entity_id=user.id,
        action="create",
        after=audit.snapshot(user, FIELDS),
    )
    uri = (
        totp_module.provisioning_uri(user.totp_secret, user.email)
        if user.totp_secret is not None
        else None
    )
    return user, uri


def patch(uow: UnitOfWork, user: User, data: dict[str, Any]) -> User:
    before = audit.snapshot(user, FIELDS)
    if data.get("email"):
        address = str(data["email"]).strip().lower()
        clash = uow.session.scalar(select(User).where(User.email == address))
        if clash is not None and clash.id != user.id:
            raise ApiError(409, "conflict", "An account with this e-mail already exists.")
        user.email = address
    for key in ("full_name", "locale"):
        if data.get(key) is not None:
            setattr(user, key, data[key])
    if data.get("is_active") is not None:
        _guard_last_admin(uow.session, user, active=bool(data["is_active"]), role=user.role)
        user.is_active = bool(data["is_active"])
    if data.get("password"):
        if user.role is UserRole.VENDOR:
            raise ApiError(422, "validation_error", "Vendor accounts have no password.")
        user.password_hash = hashing.hash_password(str(data["password"]))
    uow.flush()
    after = audit.snapshot(user, FIELDS)
    audit.record(
        uow,
        entity_type="app_user",
        entity_id=user.id,
        action="update",
        before={key: before[key] for key in audit.diff(before, after)},
        after=audit.diff(before, after),
    )
    return user


def set_role(uow: UnitOfWork, user: User, role: UserRole) -> User:
    """Contract: the last active ``admin`` cannot be demoted."""
    _guard_last_admin(uow.session, user, active=user.is_active, role=role)
    _validate_shape(role, user.vendor_id)
    before = {"role": user.role.value}
    user.role = role
    if role in STAFF_ROLES and not user.totp_secret:
        user.totp_secret = totp_module.generate_secret()
    uow.flush()
    audit.record(
        uow,
        entity_type="app_user",
        entity_id=user.id,
        action="role",
        before=before,
        after={"role": role.value},
    )
    return user


def deactivate(uow: UnitOfWork, user: User) -> User:
    """Accounts are deactivated, never deleted — the audit log references them (contract)."""
    _guard_last_admin(uow.session, user, active=False, role=user.role)
    before = {"is_active": user.is_active}
    user.is_active = False
    uow.flush()
    audit.record(
        uow,
        entity_type="app_user",
        entity_id=user.id,
        action="deactivate",
        before=before,
        after={"is_active": False},
    )
    return user


def _guard_last_admin(session: Session, user: User, *, active: bool, role: UserRole) -> None:
    """Refuse the change that would leave nobody able to make it again."""
    still_admin = active and role is UserRole.ADMIN
    if user.role is not UserRole.ADMIN or still_admin:
        return
    remaining = (
        session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.ADMIN, User.is_active.is_(True), User.id != user.id)
        )
        or 0
    )
    if remaining == 0:
        raise ApiError(409, "conflict", "The last active admin cannot be demoted or deactivated.")


# ── API keys ────────────────────────────────────────────────────────────────
def create_api_key(
    uow: UnitOfWork, *, name: str, scopes: list[str], created_by: uuid.UUID | None
) -> tuple[ApiKey, str]:
    """Mint a machine credential. The plaintext is returned once and never stored."""
    unknown = [scope for scope in scopes if scope not in set(Scope)]
    if unknown:
        raise ApiError(422, "validation_error", "Unknown scope.", {"scopes": unknown})
    plaintext, prefix = new_api_key()
    record = ApiKey(
        name=name,
        hashed_key=hashing.hash_token(plaintext),
        scopes=sorted(set(scopes)),
        created_by=created_by,
        is_active=True,
    )
    uow.session.add(record)
    uow.flush()
    audit.record(
        uow,
        entity_type="api_key",
        entity_id=record.id,
        action="create",
        after={"name": name, "scopes": record.scopes, "prefix": prefix},
    )
    return record, plaintext


def revoke_api_key(uow: UnitOfWork, record: ApiKey) -> ApiKey:
    """Revocation is a flag, not a delete: the audit log references the key by id."""
    record.is_active = False
    record.revoked_at = datetime.now(UTC)
    uow.flush()
    audit.record(
        uow,
        entity_type="api_key",
        entity_id=record.id,
        action="revoke",
        after={"is_active": False},
    )
    return record
