"""Invitation and the derived vendor status (spec §9).

The rest of the application lifecycle — answers, evaluation, decisions — is phase 2A/2B.
What phase 1B owns is the machine itself and the rule that a vendor's status follows from
its application rather than being maintained beside it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from vendoriq_api.db import UnitOfWork
from vendoriq_api.models import Event, QualificationCycle, ScoringModel
from vendoriq_api.models.enums import (
    ApplicationStatus,
    CycleKind,
    CycleStatus,
    UserRole,
    VendorStatus,
    VendorType,
)
from vendoriq_api.services import applications


@pytest.fixture
def cycle(session: Session) -> QualificationCycle:
    """A cycle needs a scoring model version; the seed loads sub-4, tests make their own."""
    version = f"test-{uuid.uuid4().hex[:6]}"
    session.add(
        ScoringModel(
            version=version,
            vendor_type=VendorType.SUB,
            name="Test model",
            criteria=[],
            classes=[],
            pass_mark=70,
        )
    )
    session.flush()
    row = QualificationCycle(
        name="TQS2026006",
        kind=CycleKind.TENDER,
        scoring_model_version=version,
        status=CycleStatus.OPEN,
        opens_at=datetime.now(UTC),
    )
    session.add(row)
    session.commit()
    return row


def test_inviting_a_vendor_opens_an_application_and_moves_the_vendor(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    cycle: QualificationCycle,
    session: Session,
) -> None:
    vendor = make_vendor()
    login(make_user(UserRole.OFFICER))
    response = client.post(f"/api/vendors/{vendor.id}/invite", json={"cycle_id": str(cycle.id)})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "invited"
    assert body["cycle_name"] == "TQS2026006"
    assert body["vendor_name"] == vendor.legal_name

    session.refresh(vendor)
    assert vendor.status is VendorStatus.INVITED

    event = session.scalar(
        select(Event).where(Event.entity_id == vendor.id, Event.type == "vendor.invited")
    )
    assert event is not None


def test_inviting_twice_into_the_same_cycle_is_a_conflict(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    cycle: QualificationCycle,
) -> None:
    vendor = make_vendor()
    login(make_user(UserRole.OFFICER))
    client.post(f"/api/vendors/{vendor.id}/invite", json={"cycle_id": str(cycle.id)})
    again = client.post(f"/api/vendors/{vendor.id}/invite", json={"cycle_id": str(cycle.id)})
    assert again.status_code == 409
    assert "application_id" in again.json()["error"]["details"]


def test_inviting_into_an_unknown_cycle_is_not_found(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    vendor = make_vendor()
    login(make_user(UserRole.OFFICER))
    response = client.post(f"/api/vendors/{vendor.id}/invite", json={"cycle_id": str(uuid.uuid4())})
    assert response.status_code == 404


def test_the_happy_path_through_the_machine_drags_the_vendor_with_it(
    uow: UnitOfWork, make_vendor: Any, cycle: QualificationCycle, session: Session
) -> None:
    """invited → in_progress → submitted → under_review → prequalified, statuses in step."""
    vendor = make_vendor()
    application = applications.invite(uow, vendor, cycle_id=cycle.id)
    seen = [vendor.status]

    for target, role in (
        (ApplicationStatus.IN_PROGRESS, UserRole.VENDOR),
        (ApplicationStatus.SUBMITTED, UserRole.VENDOR),
        (ApplicationStatus.UNDER_REVIEW, UserRole.OFFICER),
        (ApplicationStatus.PREQUALIFIED, UserRole.MANAGER),
    ):
        applications.transition(uow, application, target, role=role)
        seen.append(vendor.status)

    assert seen == [
        VendorStatus.INVITED,
        VendorStatus.IN_PROGRESS,
        VendorStatus.SUBMITTED,
        VendorStatus.UNDER_REVIEW,
        VendorStatus.PREQUALIFIED,
    ]


def test_submission_and_prequalification_emit_their_events(
    uow: UnitOfWork, make_vendor: Any, cycle: QualificationCycle, session: Session
) -> None:
    """Brief §2 names four domain events; two of them come from the machine."""
    vendor = make_vendor()
    application = applications.invite(uow, vendor, cycle_id=cycle.id)
    applications.transition(uow, application, ApplicationStatus.IN_PROGRESS, role=UserRole.VENDOR)
    applications.transition(uow, application, ApplicationStatus.SUBMITTED, role=UserRole.VENDOR)
    applications.transition(uow, application, ApplicationStatus.UNDER_REVIEW, role=UserRole.OFFICER)
    applications.transition(uow, application, ApplicationStatus.PREQUALIFIED, role=UserRole.MANAGER)

    types = {
        row.type
        for row in session.scalars(
            select(Event).where(Event.entity_id.in_([vendor.id, application.id]))
        )
    }
    assert {"application.submitted", "vendor.prequalified"} <= types


def test_a_forbidden_transition_leaves_the_vendor_alone(
    uow: UnitOfWork, make_vendor: Any, cycle: QualificationCycle
) -> None:
    """An officer approving is a 403; the vendor must not have moved on the way to it."""
    from vendoriq_api.errors import ApiError

    vendor = make_vendor()
    application = applications.invite(uow, vendor, cycle_id=cycle.id)
    applications.transition(uow, application, ApplicationStatus.IN_PROGRESS, role=UserRole.VENDOR)
    applications.transition(uow, application, ApplicationStatus.SUBMITTED, role=UserRole.VENDOR)
    applications.transition(uow, application, ApplicationStatus.UNDER_REVIEW, role=UserRole.OFFICER)

    with pytest.raises(ApiError) as raised:
        applications.transition(
            uow, application, ApplicationStatus.PREQUALIFIED, role=UserRole.OFFICER
        )
    assert raised.value.status_code == 403
    assert application.status is ApplicationStatus.UNDER_REVIEW
    assert vendor.status is VendorStatus.UNDER_REVIEW


def test_every_transition_is_audited(
    uow: UnitOfWork, make_vendor: Any, cycle: QualificationCycle, session: Session
) -> None:
    from vendoriq_api.models import AuditEvent

    vendor = make_vendor()
    application = applications.invite(uow, vendor, cycle_id=cycle.id)
    applications.transition(uow, application, ApplicationStatus.IN_PROGRESS, role=UserRole.VENDOR)

    rows = list(
        session.scalars(
            select(AuditEvent)
            .where(AuditEvent.entity_type == "application", AuditEvent.entity_id == application.id)
            .order_by(AuditEvent.created_at.asc())
        )
    )
    assert [row.action for row in rows] == ["invite", "status"]
    assert rows[1].before == {"status": "invited"}
    assert (rows[1].after or {})["status"] == "in_progress"


def test_a_withdrawn_application_returns_the_vendor_to_the_register(
    uow: UnitOfWork, make_vendor: Any, cycle: QualificationCycle
) -> None:
    vendor = make_vendor()
    application = applications.invite(uow, vendor, cycle_id=cycle.id)
    applications.transition(uow, application, ApplicationStatus.WITHDRAWN, role=UserRole.VENDOR)
    assert vendor.status is VendorStatus.REGISTERED


def test_an_application_inherits_the_demo_flag_from_its_parents(
    uow: UnitOfWork, make_vendor: Any, cycle: QualificationCycle
) -> None:
    """Orchestrator decision: ``is_demo`` lives on the parents and the purge cascades."""
    demo_vendor = make_vendor(is_demo=True)
    application = applications.invite(uow, demo_vendor, cycle_id=cycle.id)
    assert application.is_demo is True
