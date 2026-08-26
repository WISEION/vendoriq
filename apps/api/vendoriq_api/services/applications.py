"""Applications: invitation and the state transitions (spec §9).

Phase 1B implements the parts the register needs — inviting a vendor into a cycle and moving
an application through the machine, with the vendor status derived from it. Answers,
scoring, decisions and the commission export are phase 2A/2B; they change the *status* by
calling :func:`transition`, never by assigning to ``application.status``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import UnitOfWork
from ..errors import ApiError
from ..models import Application, QualificationCycle, User, Vendor
from ..models.enums import ApplicationStatus, EventType, ScoreClass, UserRole
from ..schemas import Application as ApplicationSchema
from . import audit, events, state_machine
from . import vendors as vendors_service


def decided_application(session: Session, vendor_id: uuid.UUID) -> Application | None:
    """The newest application this vendor has a decision on, or ``None``.

    Four call sites need the row rather than the flattened score `latest_result` returns —
    the evaluation screen, market intelligence, matching and the vendor register — because
    each of them prefers the frozen `raw_snapshot` over re-deriving indicators from the
    current profile. Shared here so that preference is one rule with one query, not four
    copies that can drift apart; the register was the one that had already drifted.
    """
    return session.scalars(
        select(Application)
        .where(Application.vendor_id == vendor_id, Application.decided_at.is_not(None))
        .order_by(Application.decided_at.desc())
        .limit(1)
    ).first()


def get(session: Session, application_id: uuid.UUID) -> Application:
    application = session.get(Application, application_id)
    if application is None:
        raise ApiError(404, "not_found", "No such application.")
    return application


def payload(session: Session, application: Application) -> ApplicationSchema:
    """The contract's ``Application`` summary row."""
    vendor = session.get(Vendor, application.vendor_id)
    cycle = session.get(QualificationCycle, application.cycle_id)
    evaluator = (
        session.get(User, application.decided_by) if application.decided_by is not None else None
    )
    computed = application.computed or {}
    cls_value = computed.get("cls")
    return ApplicationSchema(
        id=application.id,
        vendor_id=application.vendor_id,
        vendor_name=vendor.legal_name if vendor else None,
        cycle_id=application.cycle_id,
        cycle_name=cycle.name if cycle else None,
        status=application.status,
        submitted_at=application.submitted_at,
        total=computed.get("total"),
        cls=ScoreClass(cls_value) if cls_value in set(ScoreClass) else None,
        decision=application.decision.value if application.decision else None,
        decided_at=application.decided_at,
        evaluator_name=evaluator.full_name if evaluator else None,
        is_demo=application.is_demo,
    )


def invite(uow: UnitOfWork, vendor: Vendor, *, cycle_id: uuid.UUID) -> Application:
    """Open an application for this vendor in this cycle (spec §9, "Registered → Invited")."""
    cycle = uow.session.get(QualificationCycle, cycle_id)
    if cycle is None:
        raise ApiError(404, "not_found", "No such qualification cycle.")
    existing = uow.session.scalar(
        select(Application).where(
            Application.vendor_id == vendor.id, Application.cycle_id == cycle_id
        )
    )
    if existing is not None:
        raise ApiError(
            409,
            "conflict",
            "This vendor already has an application in this cycle.",
            {"application_id": str(existing.id), "status": existing.status.value},
        )

    application = Application(
        vendor_id=vendor.id,
        cycle_id=cycle_id,
        status=ApplicationStatus.INVITED,
        is_demo=vendor.is_demo or cycle.is_demo,
    )
    uow.session.add(application)
    uow.flush()
    audit.record(
        uow,
        entity_type="application",
        entity_id=application.id,
        action="invite",
        after={
            "vendor_id": str(vendor.id),
            "cycle_id": str(cycle_id),
            "status": ApplicationStatus.INVITED.value,
        },
    )
    vendors_service.sync_status_from_application(uow, vendor, ApplicationStatus.INVITED)
    return application


def transition(
    uow: UnitOfWork,
    application: Application,
    target: ApplicationStatus,
    *,
    role: UserRole | None,
    note: str | None = None,
) -> Application:
    """Move the application, then derive the vendor status from where it landed.

    This is the only writer of ``application.status``. Everything else — submit, decide,
    request information — expresses itself as a transition, so the machine's rules cannot
    be bypassed by a handler that "just" assigns the field.
    """
    source = application.status
    state_machine.assert_transition(source, target, role)
    application.status = target
    uow.flush()
    audit.record(
        uow,
        entity_type="application",
        entity_id=application.id,
        action="status",
        before={"status": source.value},
        after={"status": target.value, "note": note},
    )

    vendor = uow.session.get(Vendor, application.vendor_id)
    if vendor is not None:
        vendors_service.sync_status_from_application(uow, vendor, target)

    if target is ApplicationStatus.SUBMITTED:
        events.emit(
            uow,
            EventType.APPLICATION_SUBMITTED,
            entity_type="application",
            entity_id=application.id,
            payload={
                "vendor_id": str(application.vendor_id),
                "cycle_id": str(application.cycle_id),
            },
        )
    elif target is ApplicationStatus.PREQUALIFIED:
        events.emit(
            uow,
            EventType.VENDOR_PREQUALIFIED,
            entity_type="vendor",
            entity_id=application.vendor_id,
            payload={
                "application_id": str(application.id),
                "cls": (application.computed or {}).get("cls"),
                "total": (application.computed or {}).get("total"),
            },
        )
    elif target is ApplicationStatus.REJECTED:
        events.emit(
            uow,
            EventType.VENDOR_REJECTED,
            entity_type="vendor",
            entity_id=application.vendor_id,
            payload={"application_id": str(application.id)},
        )
    return application
