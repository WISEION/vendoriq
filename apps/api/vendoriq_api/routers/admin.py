"""Admin: taxonomy, accounts, settings and the audit log (contract ``/admin/*``)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from ..db import UnitOfWork
from ..models import AuditEvent as AuditEventRow
from ..models import Category as CategoryRow
from ..models import User as UserRow
from ..models.enums import CategoryKind, UserRole
from ..schemas import (
    AuditEvent,
    AuditEventPage,
    Category,
    CategoryInput,
    Settings,
    User,
    UserCreated,
    UserInput,
    UserPage,
    UserRoleInput,
)
from ..security import Principal, get_uow, require
from ..services import categories as categories_service
from ..services import settings_store
from ..services import users as users_service

router = APIRouter(tags=["admin"])


def category_payload(uow: UnitOfWork, category: CategoryRow) -> Category:
    confirmed, prequalified = categories_service.counts(uow.session, category.id)
    return Category(
        id=category.id,
        code=category.code,
        name_az=category.name_az,
        name_en=category.name_en,
        kind=category.kind,
        parent_id=category.parent_id,
        is_active=category.is_active,
        vendor_count=confirmed,
        prequalified_count=prequalified,
    )


def user_payload(uow: UnitOfWork, user: UserRow) -> User:
    return User(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        vendor_id=user.vendor_id,
        vendor_name=users_service.vendor_name(uow.session, user),
        locale="en" if user.locale == "en" else "az",
        is_active=user.is_active,
        has_totp=bool(user.totp_secret),
        last_login_at=user.last_login_at,
    )


# ── categories ──────────────────────────────────────────────────────────────
@router.get("/admin/categories")
def list_categories(
    kind: CategoryKind | None = None,
    include_inactive: bool = False,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("listCategories")),
) -> list[Category]:
    """Readable by everyone: a vendor picks its categories from this list."""
    return [
        category_payload(uow, row)
        for row in categories_service.list_all(
            uow.session, kind=kind, include_inactive=include_inactive
        )
    ]


@router.post("/admin/categories", status_code=status.HTTP_201_CREATED)
def create_category(
    body: CategoryInput,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("createCategory")),
) -> Category:
    return category_payload(uow, categories_service.create(uow, body.model_dump()))


@router.patch("/admin/categories/{category_id}")
def patch_category(
    category_id: uuid.UUID,
    body: CategoryInput,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("patchCategory")),
) -> Category:
    category = categories_service.get(uow.session, category_id)
    categories_service.patch(uow, category, body.model_dump(exclude_unset=True))
    return category_payload(uow, category)


@router.delete("/admin/categories/{category_id}", status_code=204)
def delete_category(
    category_id: uuid.UUID,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("deleteCategory")),
) -> None:
    """A category in use is deactivated, not deleted — history would lose its labels."""
    categories_service.deactivate(uow, categories_service.get(uow.session, category_id))


# ── users ───────────────────────────────────────────────────────────────────
@router.get("/admin/users")
def list_users(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 25,
    role: Annotated[list[UserRole] | None, Query()] = None,
    q: str | None = None,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("listUsers")),
) -> UserPage:
    rows, total = users_service.list_page(
        uow.session, roles=role, q=q, page=page, page_size=page_size
    )
    return UserPage(
        items=[user_payload(uow, row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/admin/users", status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserInput,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("createUser")),
) -> UserCreated:
    """Staff accounts are enrolled in TOTP; the ``otpauth://`` URI is returned once."""
    user, uri = users_service.create(uow, body.model_dump(exclude_unset=True))
    return UserCreated(**user_payload(uow, user).model_dump(), totp_provisioning_uri=uri)


@router.patch("/admin/users/{user_id}")
def patch_user(
    user_id: uuid.UUID,
    body: UserInput,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("patchUser")),
) -> User:
    user = users_service.get(uow.session, user_id)
    users_service.patch(uow, user, body.model_dump(exclude_unset=True))
    return user_payload(uow, user)


@router.delete("/admin/users/{user_id}", status_code=204)
def deactivate_user(
    user_id: uuid.UUID,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("deactivateUser")),
) -> None:
    """Accounts are deactivated, never deleted — the audit log references them."""
    users_service.deactivate(uow, users_service.get(uow.session, user_id))


@router.put("/admin/users/{user_id}/role")
def put_user_role(
    user_id: uuid.UUID,
    body: UserRoleInput,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("putUserRole")),
) -> User:
    user = users_service.set_role(uow, users_service.get(uow.session, user_id), body.role)
    return user_payload(uow, user)


# ── settings ────────────────────────────────────────────────────────────────
@router.get("/admin/settings")
def get_settings_endpoint(
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("getSettings")),
) -> Settings:
    """Every threshold in spec §11 — a setting, not code."""
    return Settings.model_validate(settings_store.all_settings(uow.session))


@router.put("/admin/settings")
def put_settings(
    body: dict[str, dict[str, object]],
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("putSettings")),
) -> Settings:
    """A partial map; an unknown group or key is a 422, never a silent no-op."""
    return Settings.model_validate(settings_store.update(uow, body))


# ── audit log ───────────────────────────────────────────────────────────────
@router.get("/admin/audit")
def list_audit_events(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 25,
    actor_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    action: str | None = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("listAuditEvents")),
) -> AuditEventPage:
    """Newest first — the committee-minutes view (spec §13)."""
    query = select(AuditEventRow)
    if actor_id is not None:
        query = query.where(AuditEventRow.actor_id == actor_id)
    if entity_type:
        query = query.where(AuditEventRow.entity_type == entity_type)
    if entity_id is not None:
        query = query.where(AuditEventRow.entity_id == entity_id)
    if action:
        query = query.where(AuditEventRow.action == action)
    if from_ is not None:
        query = query.where(AuditEventRow.created_at >= from_)
    if to is not None:
        query = query.where(AuditEventRow.created_at <= to)

    total = uow.session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = uow.session.scalars(
        query.order_by(AuditEventRow.created_at.desc(), AuditEventRow.id.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()

    emails = _actor_emails(uow, [row.actor_id for row in rows if row.actor_id])
    return AuditEventPage(
        items=[
            AuditEvent(
                id=row.id,
                actor_id=row.actor_id,
                actor_email=emails.get(row.actor_id) if row.actor_id else None,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                action=row.action,
                before=row.before,
                after=row.after,
                created_at=row.created_at,
            )
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


def _actor_emails(uow: UnitOfWork, ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    """One query for the whole page rather than one per row."""
    if not ids:
        return {}
    rows = uow.session.execute(
        select(UserRow.id, UserRow.email).where(UserRow.id.in_(set(ids)))
    ).all()
    return {row[0]: row[1] for row in rows}
