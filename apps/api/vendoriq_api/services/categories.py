"""Category taxonomy and vendor↔category assignment (spec §5, §11.1).

The confirmation flag matters more than it looks: only a *confirmed* assignment makes a
vendor a candidate in project matching, so "the vendor said it does façades" and "we agree
it does façades" are different facts and the matching engine only sees the second.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import UnitOfWork
from ..errors import ApiError
from ..models import Category, Vendor, VendorCategory, WorkPackage
from ..models.enums import CategoryKind, VendorStatus
from . import audit

FIELDS = ("code", "name_az", "name_en", "kind", "parent_id", "is_active")


def list_all(
    session: Session, *, kind: CategoryKind | None = None, include_inactive: bool = False
) -> list[Category]:
    query = select(Category)
    if kind is not None:
        query = query.where(Category.kind == kind)
    if not include_inactive:
        query = query.where(Category.is_active.is_(True))
    return list(session.scalars(query.order_by(Category.kind.asc(), Category.code.asc())))


def get(session: Session, category_id: uuid.UUID) -> Category:
    category = session.get(Category, category_id)
    if category is None:
        raise ApiError(404, "not_found", "No such category.")
    return category


def by_code(session: Session, code: str) -> Category | None:
    return session.scalar(select(Category).where(Category.code == code))


def counts(session: Session, category_id: uuid.UUID) -> tuple[int, int]:
    """``(confirmed vendors, of which prequalified)`` — the taxonomy screen's two columns."""
    confirmed = (
        session.scalar(
            select(func.count())
            .select_from(VendorCategory)
            .where(
                VendorCategory.category_id == category_id,
                VendorCategory.confirmed.is_(True),
            )
        )
        or 0
    )
    prequalified = (
        session.scalar(
            select(func.count())
            .select_from(VendorCategory)
            .join(Vendor, Vendor.id == VendorCategory.vendor_id)
            .where(
                VendorCategory.category_id == category_id,
                VendorCategory.confirmed.is_(True),
                Vendor.status == VendorStatus.PREQUALIFIED,
            )
        )
        or 0
    )
    return confirmed, prequalified


def create(uow: UnitOfWork, data: dict[str, Any]) -> Category:
    code = str(data["code"]).strip()
    if by_code(uow.session, code) is not None:
        raise ApiError(409, "conflict", "A category with this code already exists.", {"code": code})
    category = Category(
        code=code,
        name_az=data["name_az"],
        name_en=data["name_en"],
        kind=CategoryKind(data["kind"]),
        parent_id=data.get("parent_id"),
        is_active=bool(data.get("is_active", True)),
    )
    uow.session.add(category)
    uow.flush()
    audit.record(
        uow,
        entity_type="category",
        entity_id=category.id,
        action="create",
        after=audit.snapshot(category, FIELDS),
    )
    return category


def patch(uow: UnitOfWork, category: Category, data: dict[str, Any]) -> Category:
    before = audit.snapshot(category, FIELDS)
    for key in FIELDS:
        if key not in data or data[key] is None:
            continue
        value = CategoryKind(data[key]) if key == "kind" else data[key]
        if key == "code" and value != category.code:
            clash = by_code(uow.session, str(value))
            if clash is not None and clash.id != category.id:
                raise ApiError(409, "conflict", "A category with this code already exists.")
        setattr(category, key, value)
    if category.parent_id == category.id:
        raise ApiError(422, "validation_error", "A category cannot be its own parent.")
    uow.flush()
    after = audit.snapshot(category, FIELDS)
    audit.record(
        uow,
        entity_type="category",
        entity_id=category.id,
        action="update",
        before={key: before[key] for key in audit.diff(before, after)},
        after=audit.diff(before, after),
    )
    return category


def deactivate(uow: UnitOfWork, category: Category) -> None:
    """A category in use is deactivated, never deleted — history would lose its labels."""
    in_use = bool(
        uow.session.scalar(
            select(func.count())
            .select_from(VendorCategory)
            .where(VendorCategory.category_id == category.id)
        )
    ) or bool(
        uow.session.scalar(
            select(func.count())
            .select_from(WorkPackage)
            .where(WorkPackage.category_id == category.id)
        )
    )
    before = audit.snapshot(category, FIELDS)
    if in_use:
        category.is_active = False
        uow.flush()
        audit.record(
            uow,
            entity_type="category",
            entity_id=category.id,
            action="deactivate",
            before=before,
            after={"is_active": False},
        )
        return
    audit.record(uow, entity_type="category", entity_id=category.id, action="delete", before=before)
    uow.session.delete(category)
    uow.flush()


# ── vendor assignments ──────────────────────────────────────────────────────
def list_for_vendor(session: Session, vendor_id: uuid.UUID) -> list[VendorCategory]:
    return list(
        session.scalars(
            select(VendorCategory)
            .join(Category, Category.id == VendorCategory.category_id)
            .where(VendorCategory.vendor_id == vendor_id)
            .order_by(Category.code.asc())
        )
    )


def set_for_vendor(
    uow: UnitOfWork, vendor_id: uuid.UUID, codes: Sequence[str]
) -> list[VendorCategory]:
    """Replace the selection. New rows arrive unconfirmed; existing ones keep their flag.

    Keeping the flag matters: re-saving a form must not silently un-confirm a category the
    officer already agreed to, and must not silently keep a confirmation for one that was
    removed and re-added.
    """
    wanted = {code.strip() for code in codes if code and code.strip()}
    resolved: dict[str, Category] = {}
    for code in wanted:
        category = by_code(uow.session, code)
        if category is None:
            raise ApiError(422, "validation_error", f"Unknown category code {code!r}.")
        resolved[code] = category

    existing = {row.category.code: row for row in list_for_vendor(uow.session, vendor_id)}
    before = sorted(existing)

    for code, row in existing.items():
        if code not in wanted:
            uow.session.delete(row)
    for code, category in resolved.items():
        if code not in existing:
            uow.session.add(
                VendorCategory(vendor_id=vendor_id, category_id=category.id, confirmed=False)
            )
    uow.flush()
    audit.record(
        uow,
        entity_type="vendor",
        entity_id=vendor_id,
        action="categories",
        before={"codes": before},
        after={"codes": sorted(wanted)},
    )
    return list_for_vendor(uow.session, vendor_id)


def confirm_for_vendor(
    uow: UnitOfWork, vendor_id: uuid.UUID, codes: Sequence[str], *, confirmed: bool = True
) -> list[VendorCategory]:
    """Officer agrees (or withdraws agreement) — this is what matching reads (spec §11.1)."""
    wanted = {code.strip() for code in codes}
    touched: list[str] = []
    for row in list_for_vendor(uow.session, vendor_id):
        if row.category.code not in wanted:
            continue
        row.confirmed = confirmed
        touched.append(row.category.code)
    uow.flush()
    audit.record(
        uow,
        entity_type="vendor",
        entity_id=vendor_id,
        action="confirm_categories",
        after={
            "codes": sorted(touched),
            "confirmed": confirmed,
            "at": datetime.now(UTC).isoformat(),
        },
    )
    return list_for_vendor(uow.session, vendor_id)
