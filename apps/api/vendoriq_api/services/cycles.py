"""Qualification cycles: repository queries, CRUD and bulk invitation (spec §9, §11).

Follows the pattern of ``services/vendors.py``: a mutation changes the row, writes an audit
event and, where relevant, emits a domain event, all inside the caller's transaction.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import Settings
from ..db import UnitOfWork
from ..errors import ApiError
from ..models import Application, QualificationCycle, ScoringModel, Vendor
from ..models.enums import CycleStatus, VendorStatus
from . import applications as applications_service
from . import audit
from . import auth as auth_service

PATCHABLE = ("name", "kind", "opens_at", "closes_at", "project_id", "status")
AUDIT_FIELDS = (*PATCHABLE, "scoring_model_version", "is_demo")


@dataclass(frozen=True, slots=True)
class CycleFilters:
    """The cycles screen's controls (screen 21, spec §9)."""

    statuses: Sequence[CycleStatus] = ()
    kind: str | None = None


def get(session: Session, cycle_id: uuid.UUID) -> QualificationCycle:
    cycle = session.get(QualificationCycle, cycle_id)
    if cycle is None:
        raise ApiError(404, "not_found", "No such qualification cycle.")
    return cycle


def application_count(session: Session, cycle_id: uuid.UUID) -> int:
    return (
        session.scalar(
            select(func.count()).select_from(Application).where(Application.cycle_id == cycle_id)
        )
        or 0
    )


def counts_by_status(session: Session, cycle_id: uuid.UUID) -> dict[str, int]:
    rows = session.execute(
        select(Application.status, func.count())
        .where(Application.cycle_id == cycle_id)
        .group_by(Application.status)
    ).all()
    return {status.value: count for status, count in rows}


def list_page(
    session: Session, filters: CycleFilters, *, page: int = 1, page_size: int = 25
) -> tuple[list[QualificationCycle], int]:
    query = select(QualificationCycle)
    if filters.statuses:
        query = query.where(QualificationCycle.status.in_(list(filters.statuses)))
    if filters.kind:
        query = query.where(QualificationCycle.kind == filters.kind)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(
        query.order_by(QualificationCycle.created_at.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()
    return list(rows), total


def _validate_model_version(session: Session, version: str) -> None:
    if session.get(ScoringModel, version) is None:
        raise ApiError(
            422,
            "validation_error",
            "Unknown scoring model version.",
            {"scoring_model_version": version},
        )


def create(uow: UnitOfWork, data: dict[str, Any]) -> QualificationCycle:
    _validate_model_version(uow.session, str(data["scoring_model_version"]))
    cycle = QualificationCycle(
        name=str(data["name"]).strip(),
        kind=data["kind"],
        scoring_model_version=data["scoring_model_version"],
        opens_at=data.get("opens_at"),
        closes_at=data.get("closes_at"),
        project_id=data.get("project_id"),
        status=data.get("status") or CycleStatus.DRAFT,
    )
    uow.session.add(cycle)
    try:
        uow.flush()
    except IntegrityError as exc:
        uow.session.rollback()
        raise ApiError(422, "validation_error", "Could not create the cycle.") from exc
    audit.record(
        uow,
        entity_type="qualification_cycle",
        entity_id=cycle.id,
        action="create",
        after=audit.snapshot(cycle, AUDIT_FIELDS),
    )
    return cycle


def patch(uow: UnitOfWork, cycle: QualificationCycle, data: dict[str, Any]) -> QualificationCycle:
    """Apply the editable fields. The model version is locked once a score exists.

    ``docs/openapi.yaml`` on ``patchCycle``: "The scoring model version cannot change once an
    application has been scored." — checked against ``Application.computed``, not the
    application count, so re-inviting into a still-empty cycle stays free to change models.
    """
    before = audit.snapshot(cycle, AUDIT_FIELDS)

    new_version = data.get("scoring_model_version")
    if new_version is not None and new_version != cycle.scoring_model_version:
        scored = uow.session.scalar(
            select(func.count())
            .select_from(Application)
            .where(Application.cycle_id == cycle.id, Application.computed.is_not(None))
        )
        if scored:
            raise ApiError(
                409,
                "conflict",
                "The scoring model version cannot change once an application has been scored.",
                {"cycle_id": str(cycle.id)},
            )
        _validate_model_version(uow.session, str(new_version))
        cycle.scoring_model_version = new_version

    for key in PATCHABLE:
        if key not in data or data[key] is None:
            continue
        setattr(cycle, key, data[key])

    uow.flush()
    after = audit.snapshot(cycle, AUDIT_FIELDS)
    audit.record(
        uow,
        entity_type="qualification_cycle",
        entity_id=cycle.id,
        action="update",
        before={key: before[key] for key in audit.diff(before, after)},
        after=audit.diff(before, after),
    )
    return cycle


def delete(uow: UnitOfWork, cycle: QualificationCycle) -> None:
    """Refuse when the cycle has applications — never cascade (brief §2C)."""
    count = application_count(uow.session, cycle.id)
    if count:
        raise ApiError(
            409,
            "conflict",
            "This cycle has applications and cannot be deleted.",
            {"application_count": count},
        )
    audit.record(
        uow,
        entity_type="qualification_cycle",
        entity_id=cycle.id,
        action="delete",
        before=audit.snapshot(cycle, AUDIT_FIELDS),
    )
    uow.session.delete(cycle)
    uow.flush()


@dataclass(frozen=True, slots=True)
class InviteOutcome:
    invited: list[Application]
    skipped: list[tuple[uuid.UUID, str]]


def invite_bulk(
    uow: UnitOfWork,
    cycle: QualificationCycle,
    vendor_ids: Sequence[uuid.UUID],
    *,
    settings: Settings,
    message_az: str | None,
    message_en: str | None,
) -> InviteOutcome:
    """Move each invited vendor's application into ``invited`` (spec §9, brief §2C).

    Every vendor goes through the same state-machine entry point
    (``services.applications.invite``) that a single invitation uses — bulk is not a
    second, looser path. A vendor already in this cycle, or suspended, is skipped with a
    reason rather than failing the whole batch.
    """
    invited: list[Application] = []
    skipped: list[tuple[uuid.UUID, str]] = []
    for vendor_id in vendor_ids:
        vendor = uow.session.get(Vendor, vendor_id)
        if vendor is None:
            skipped.append((vendor_id, "no_such_vendor"))
            continue
        if vendor.status is VendorStatus.SUSPENDED:
            skipped.append((vendor_id, "suspended"))
            continue
        existing = uow.session.scalar(
            select(Application).where(
                Application.vendor_id == vendor_id, Application.cycle_id == cycle.id
            )
        )
        if existing is not None:
            skipped.append((vendor_id, "already_invited"))
            continue
        application = applications_service.invite(uow, vendor, cycle_id=cycle.id)
        auth_service.notify_invitation(
            uow, settings, vendor, message_az=message_az, message_en=message_en
        )
        invited.append(application)
    return InviteOutcome(invited=invited, skipped=skipped)


__all__ = [
    "AUDIT_FIELDS",
    "CycleFilters",
    "InviteOutcome",
    "application_count",
    "counts_by_status",
    "create",
    "delete",
    "get",
    "invite_bulk",
    "list_page",
    "patch",
]
