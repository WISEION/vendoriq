"""Vendor register: repository queries and the mutating services (spec §5, §9).

Every mutation here does three things in one transaction: change the row, append an audit
event, and — where the change is a *value the vendor reported* rather than an internal flag
— append a ``manual`` field observation so the change keeps its provenance (spec §6.5).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from ..db import UnitOfWork
from ..errors import ApiError
from ..models import (
    Application,
    Category,
    Contact,
    FieldObservation,
    Vendor,
    VendorCategory,
)
from ..models.enums import (
    ApplicationStatus,
    DecisionKind,
    EventType,
    ObservationSource,
    ScoreClass,
    UserRole,
    VendorStatus,
    VendorType,
)
from . import audit, events, observations, state_machine

#: Columns a patch may set. ``status`` is here but goes through the state rules below.
PATCHABLE = (
    "legal_name",
    "voen",
    "type",
    "legal_form",
    "registration_year",
    "address",
    "region",
    "website",
    "external_ref",
)

#: Vendor columns that are also form answers, so a staff edit must leave a trail that the
#: provenance view can show beside the vendor's own claim (spec §6.5).
COLUMN_FIELD_CODES: dict[str, str] = {
    "legal_name": "A.1",
    "voen": "A.3",
    "registration_year": "A.4",
    "address": "A.5",
    "website": "A.10",
    "legal_form": "A.17",
}

AUDIT_FIELDS = (*PATCHABLE, "status", "is_demo")

#: Default prequalification validity (spec §9). Overridable per approval and per settings.
DEFAULT_VALIDITY_MONTHS = 12


@dataclass(frozen=True, slots=True)
class VendorFilters:
    """The register screen's controls, one to one (spec §8)."""

    type: VendorType | None = None
    categories: Sequence[str] = ()
    classes: Sequence[ScoreClass] = ()
    statuses: Sequence[VendorStatus] = ()
    region: str | None = None
    q: str | None = None
    include_demo: bool = True
    sort: str = "legal_name"


@dataclass(frozen=True, slots=True)
class LatestResult:
    """The newest decided application of a vendor, flattened for the register row."""

    total: float | None
    cls: ScoreClass | None
    decided_at: datetime | None
    prequalified_until: date | None


def get(session: Session, vendor_id: uuid.UUID) -> Vendor:
    vendor = session.get(Vendor, vendor_id)
    if vendor is None:
        raise ApiError(404, "not_found", "No such vendor.")
    return vendor


def by_voen(session: Session, voen: str) -> Vendor | None:
    return session.scalar(select(Vendor).where(Vendor.voen == voen))


def _sorted(query: Select[tuple[Vendor]], sort: str) -> Select[tuple[Vendor]]:
    # `score` sorting needs the evaluation join; until phase 2B persists a denormalised
    # score, sorting by score falls back to the update time, which is what the register
    # column shows next to it.
    orders: dict[str, ColumnElement[Any]] = {
        "legal_name": Vendor.legal_name.asc(),
        "-legal_name": Vendor.legal_name.desc(),
        "updated_at": Vendor.updated_at.asc(),
        "-updated_at": Vendor.updated_at.desc(),
        "score": Vendor.updated_at.asc(),
        "-score": Vendor.updated_at.desc(),
    }
    column = orders.get(sort, Vendor.legal_name.asc())
    return query.order_by(column, Vendor.id.asc())


def _filtered(filters: VendorFilters, principal_vendor_id: uuid.UUID | None) -> Select[Any]:
    query = select(Vendor)
    if principal_vendor_id is not None:
        query = query.where(Vendor.id == principal_vendor_id)
    if filters.type is not None:
        # A `both` vendor answers a filter for `sub` and for `sup` (contract note).
        if filters.type is VendorType.BOTH:
            query = query.where(Vendor.type == VendorType.BOTH)
        else:
            query = query.where(Vendor.type.in_([filters.type, VendorType.BOTH]))
    if filters.statuses:
        query = query.where(Vendor.status.in_(list(filters.statuses)))
    if filters.region:
        query = query.where(Vendor.region == filters.region)
    if not filters.include_demo:
        query = query.where(Vendor.is_demo.is_(False))
    if filters.q:
        needle = f"%{filters.q.strip().lower()}%"
        query = query.where(
            or_(func.lower(Vendor.legal_name).like(needle), Vendor.voen.like(needle))
        )
    if filters.categories:
        query = query.where(
            Vendor.id.in_(
                select(VendorCategory.vendor_id)
                .join(Category, Category.id == VendorCategory.category_id)
                .where(Category.code.in_(list(filters.categories)))
            )
        )
    return query


def list_page(
    session: Session,
    filters: VendorFilters,
    *,
    page: int = 1,
    page_size: int = 25,
    principal_vendor_id: uuid.UUID | None = None,
) -> tuple[list[Vendor], int]:
    """One page of the register plus the total matching the filter (not the page)."""
    query = _filtered(filters, principal_vendor_id)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(
        _sorted(query, filters.sort).limit(page_size).offset((page - 1) * page_size)
    ).all()
    # The class filter is applied after the page query because a vendor's class lives on its
    # newest decided application, not on the vendor row. At the target scale (1 000 vendors,
    # spec §13) this is a bounded post-filter; phase 2B denormalises it if it ever is not.
    if filters.classes:
        wanted = set(filters.classes)
        rows = [v for v in rows if latest_result(session, v.id).cls in wanted]
    return list(rows), total


def latest_result(session: Session, vendor_id: uuid.UUID) -> LatestResult:
    """Score, class and validity from the newest *decided* application (spec §8)."""
    application = session.scalars(
        select(Application)
        .where(
            Application.vendor_id == vendor_id,
            Application.decided_at.is_not(None),
        )
        .order_by(Application.decided_at.desc())
        .limit(1)
    ).first()
    if application is None:
        return LatestResult(None, None, None, None)
    computed = application.computed or {}
    total = computed.get("total")
    cls_value = computed.get("cls")
    cls = ScoreClass(cls_value) if cls_value in set(ScoreClass) else None
    until: date | None = None
    if application.decision is DecisionKind.APPROVE and application.decided_at is not None:
        months = int((application.declaration or {}).get("valid_months", DEFAULT_VALIDITY_MONTHS))
        until = (application.decided_at + timedelta(days=int(months * 30.4375))).date()
    return LatestResult(
        total=float(total) if isinstance(total, int | float) else None,
        cls=cls,
        decided_at=application.decided_at,
        prequalified_until=until,
    )


def primary_source(session: Session, vendor_id: uuid.UUID) -> ObservationSource | None:
    """The most common source among the vendor's current values — the register's badge."""
    sources = list(observations.current_sources(session, vendor_id).values())
    if not sources:
        return None
    return max(set(sources), key=sources.count)


def create(
    uow: UnitOfWork,
    *,
    legal_name: str,
    type: VendorType,
    voen: str | None = None,
    is_demo: bool = False,
    status: VendorStatus = VendorStatus.REGISTERED,
    **columns: Any,
) -> Vendor:
    """Create a vendor. VÖEN is unique across the register (spec §5)."""
    if voen and by_voen(uow.session, voen) is not None:
        raise ApiError(409, "conflict", "A vendor with this VÖEN already exists.", {"voen": voen})
    vendor = Vendor(
        legal_name=legal_name.strip(),
        voen=voen,
        type=type,
        status=status,
        is_demo=is_demo,
        **{key: value for key, value in columns.items() if key in PATCHABLE},
    )
    uow.session.add(vendor)
    try:
        uow.flush()
    except IntegrityError as exc:  # a concurrent insert of the same VÖEN
        uow.session.rollback()
        raise ApiError(409, "conflict", "A vendor with this VÖEN already exists.") from exc
    audit.record(
        uow,
        entity_type="vendor",
        entity_id=vendor.id,
        action="create",
        after=audit.snapshot(vendor, AUDIT_FIELDS),
    )
    events.emit(
        uow,
        EventType.VENDOR_REGISTERED,
        entity_type="vendor",
        entity_id=vendor.id,
        payload={"legal_name": vendor.legal_name, "voen": vendor.voen, "type": vendor.type.value},
    )
    return vendor


def patch(
    uow: UnitOfWork,
    vendor: Vendor,
    changes: dict[str, Any],
    *,
    role: UserRole | None,
    reason: str | None = None,
) -> Vendor:
    """Apply column changes, writing an audit event and a ``manual`` observation each.

    A staff edit needs a reason (spec §6.5). A vendor editing its own already-prequalified
    profile is refused here: spec §7 makes that a change request the officer confirms, and
    silently accepting it would let a prequalified vendor rewrite the basis of its score.
    """
    if role in {UserRole.OFFICER, UserRole.COMMISSION, UserRole.MANAGER, UserRole.ADMIN} and not (
        reason and reason.strip()
    ):
        raise ApiError(
            422, "validation_error", "A reason is mandatory for a staff edit (spec §6.5)."
        )
    if role is UserRole.VENDOR and vendor.status is VendorStatus.PREQUALIFIED:
        raise ApiError(
            409,
            "conflict",
            "A prequalified profile is changed through a change request, not a direct edit "
            "(spec §7).",
            {"status": vendor.status.value},
        )

    before = audit.snapshot(vendor, AUDIT_FIELDS)
    status_change = changes.pop("status", None)
    applied: dict[str, Any] = {}
    for key, value in changes.items():
        if key not in PATCHABLE or value is None:
            continue
        if key == "voen" and value != vendor.voen:
            existing = by_voen(uow.session, str(value))
            if existing is not None and existing.id != vendor.id:
                raise ApiError(409, "conflict", "A vendor with this VÖEN already exists.")
        setattr(vendor, key, value)
        applied[key] = value

    if status_change is not None:
        _set_status(uow, vendor, VendorStatus(status_change), role=role, reason=reason)

    uow.flush()
    after = audit.snapshot(vendor, AUDIT_FIELDS)
    audit.record(
        uow,
        entity_type="vendor",
        entity_id=vendor.id,
        action="update",
        before={key: before[key] for key in audit.diff(before, after)},
        after={**audit.diff(before, after), "reason": reason},
    )
    # The provenance half: only the columns that are also form answers.
    for key, value in applied.items():
        field_code = COLUMN_FIELD_CODES.get(key)
        if field_code is None:
            continue
        observations.record(
            uow,
            vendor.id,
            field_code,
            value,
            source=ObservationSource.MANUAL,
            reason=reason,
            write_audit=False,
        )
    return vendor


#: Statuses only `decideApplication` may produce (spec §9). See `_set_status`.
_DECIDED_STATUSES = frozenset({VendorStatus.PREQUALIFIED, VendorStatus.REJECTED})


def _set_status(
    uow: UnitOfWork,
    vendor: Vendor,
    target: VendorStatus,
    *,
    role: UserRole | None,
    reason: str | None,
) -> None:
    """Direct status writes are a staff instrument; outcomes and suspension are not among them.

    `prequalified` and `rejected` are what a commission decision *produces*
    (`sync_status_from_application`, spec §9). Writing one here reached the same column by a
    route with no application, no score, no pass mark and no decision behind it — and
    `services/matching.py` reads exactly that column to build the eligible-candidate pool, so
    a single PATCH put an arbitrary vendor in front of a project (3B, finding 1). Restricting
    it by role would not have been enough: a manager may not conjure a prequalification
    either, because the point is that the commission decided, not that someone senior asked.
    """
    if role is UserRole.VENDOR:
        raise ApiError(403, "forbidden", "A vendor cannot set its own status.")
    if target in _DECIDED_STATUSES:
        raise ApiError(
            409,
            "conflict",
            f"{target.value!r} is the outcome of a commission decision, not a value that can "
            "be set. Use POST /applications/{id}/decide.",
        )
    if target is VendorStatus.SUSPENDED:
        raise ApiError(
            409,
            "conflict",
            "Suspension goes through POST /vendors/{id}/suspend, which requires a reason.",
        )
    vendor.status = target


def sync_status_from_application(
    uow: UnitOfWork, vendor: Vendor, application_status: ApplicationStatus
) -> None:
    """Derive the vendor status from an application outcome (spec §9)."""
    target = state_machine.derive_vendor_status(application_status, current=vendor.status)
    if target is vendor.status:
        return
    before = {"status": vendor.status.value}
    vendor.status = target
    uow.flush()
    audit.record(
        uow,
        entity_type="vendor",
        entity_id=vendor.id,
        action="status",
        before=before,
        after={"status": target.value, "derived_from": application_status.value},
    )


def suspend(uow: UnitOfWork, vendor: Vendor, *, suspended: bool, reason: str) -> Vendor:
    """Manager suspends or lifts, always with a reason (spec §9)."""
    if not reason or len(reason.strip()) < 3:
        raise ApiError(422, "validation_error", "A reason of at least 3 characters is required.")
    before = {"status": vendor.status.value}
    if suspended:
        vendor.status = VendorStatus.SUSPENDED
    else:
        # Lifting returns the vendor to whatever its newest application says it is; with no
        # application at all it goes back on the register as `registered`.
        newest = uow.session.scalars(
            select(Application)
            .where(Application.vendor_id == vendor.id)
            .order_by(Application.updated_at.desc())
            .limit(1)
        ).first()
        vendor.status = (
            state_machine.VENDOR_STATUS_FOR_APPLICATION[newest.status]
            if newest is not None
            else VendorStatus.REGISTERED
        )
    uow.flush()
    audit.record(
        uow,
        entity_type="vendor",
        entity_id=vendor.id,
        action="suspend" if suspended else "unsuspend",
        before=before,
        after={"status": vendor.status.value, "reason": reason},
    )
    if suspended:
        events.emit(
            uow,
            EventType.VENDOR_SUSPENDED,
            entity_type="vendor",
            entity_id=vendor.id,
            payload={"reason": reason, "legal_name": vendor.legal_name},
        )
    return vendor


def observation_count(session: Session, vendor_id: uuid.UUID) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(FieldObservation)
            .where(FieldObservation.vendor_id == vendor_id)
        )
        or 0
    )


def primary_contact(session: Session, vendor_id: uuid.UUID) -> Contact | None:
    return session.scalars(
        select(Contact).where(Contact.vendor_id == vendor_id, Contact.is_primary.is_(True)).limit(1)
    ).first()


def now() -> datetime:
    """Single clock, so tests can reason about "today" without patching three modules."""
    return datetime.now(UTC)
