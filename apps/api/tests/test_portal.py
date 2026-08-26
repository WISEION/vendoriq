"""The vendor portal's application endpoints (spec §7): answers, submission, the score gate.

``listApplications`` / ``getApplication`` / ``patchAnswers`` / ``submitApplication`` — task 2A.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from vendoriq_api.catalog import MANDATORY_DOCUMENT_CODES
from vendoriq_api.db import UnitOfWork
from vendoriq_api.models import Application, Event, QualificationCycle, ScoringModel, Vendor
from vendoriq_api.models.enums import (
    ApplicationStatus,
    CycleKind,
    CycleStatus,
    UserRole,
    VendorType,
)
from vendoriq_api.services import applications as applications_service

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"

#: Enough of the form to pass every check on the declaration screen: the three KO answers
#: "Yes", a turnover series, a balance sheet pair, three completed projects and headcount.
COMPLETE_ANSWERS: dict[str, Any] = {
    "A.1": "Test Tikinti MMC",
    "A.11": "Var",
    "A.12": "LIC-2026-001",
    "A.13": "2020-01-01",
    "A.14": "2030-01-01",
    "A.15": "Var",
    "A.16": "2026-08-01",
    "F.1": "Var",
    "B.1": 1_200_000,
    "B.2": 1_100_000,
    "B.3": 900_000,
    "B.5": 400_000,
    "B.6": 500_000,
    "B.7": 250_000,
    "C.t1": [
        {"name": "Proj 1", "value": 800_000},
        {"name": "Proj 2", "value": 900_000},
        {"name": "Proj 3", "value": 700_000},
    ],
    "E.1": 60,
    "E.4": 3,
    "E.5": 4,
}


# ── fixtures ─────────────────────────────────────────────────────────────────
@pytest.fixture
def cycle(session: Session) -> QualificationCycle:
    version = f"test-{uuid.uuid4().hex[:6]}"
    session.add(
        ScoringModel(
            version=version,
            vendor_type=VendorType.SUB,
            name_az="Sınaq modeli",
            name_en="Test model",
            groups=[],
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


def _invite(session: Session, vendor: Vendor, cycle: QualificationCycle) -> Application:
    application = applications_service.invite(UnitOfWork(session), vendor, cycle_id=cycle.id)
    session.commit()
    return application


def _upload(client: TestClient, vendor_id: uuid.UUID, code: str, issue: str | None = None) -> None:
    init = client.post(
        f"/api/vendors/{vendor_id}/documents/upload-init",
        json={
            "code": code,
            "filename": f"{code}.pdf",
            "content_type": "application/pdf",
            "size": len(PDF),
        },
    )
    assert init.status_code == 200, init.text
    ticket = init.json()
    put = client.put(ticket["url"], content=PDF, headers={"Content-Type": "application/pdf"})
    assert put.status_code == 204, put.text
    complete = client.post(
        f"/api/vendors/{vendor_id}/documents/upload-complete",
        json={"upload_id": ticket["upload_id"], "code": code, "issue_date": issue},
    )
    assert complete.status_code == 200, complete.text


def _upload_all_mandatory(client: TestClient, vendor_id: uuid.UUID) -> None:
    for code in MANDATORY_DOCUMENT_CODES:
        _upload(client, vendor_id, code, "2026-08-01")


# ── listApplications / getApplication ───────────────────────────────────────
def test_a_vendor_lists_only_its_own_application(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    cycle: QualificationCycle,
    session: Session,
) -> None:
    mine = make_vendor()
    other = make_vendor()
    _invite(session, mine, cycle)
    _invite(session, other, cycle)

    login(make_user(UserRole.VENDOR, vendor=mine))
    response = client.get("/api/applications")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["vendor_id"] == str(mine.id)


def test_staff_lists_every_application(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    cycle: QualificationCycle,
    session: Session,
) -> None:
    _invite(session, make_vendor(), cycle)
    _invite(session, make_vendor(), cycle)

    login(make_user(UserRole.OFFICER))
    response = client.get("/api/applications", params={"cycle_id": str(cycle.id)})
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 2


def test_a_vendor_cannot_read_another_vendors_application(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    cycle: QualificationCycle,
    session: Session,
) -> None:
    """404, not 403 — existence itself is information (spec §13)."""
    other = make_vendor()
    application = _invite(session, other, cycle)

    login(make_user(UserRole.VENDOR, vendor=make_vendor()))
    response = client.get(f"/api/applications/{application.id}")
    assert response.status_code == 404, response.text


def test_getting_an_unknown_application_is_not_found(
    client: TestClient, make_user: Any, login: Any
) -> None:
    login(make_user(UserRole.OFFICER))
    response = client.get(f"/api/applications/{uuid.uuid4()}")
    assert response.status_code == 404


# ── patchAnswers ─────────────────────────────────────────────────────────────
def test_patch_answers_opens_the_application_and_records_observations(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    cycle: QualificationCycle,
    session: Session,
) -> None:
    vendor = make_vendor()
    application = _invite(session, vendor, cycle)
    # A local binding, not `application.status` itself — asserting the identity of the
    # attribute directly here would have mypy narrow it to `Literal[INVITED]` for the rest
    # of the function, making the later re-assertion (after the mutation below) a reported
    # "non-overlapping identity check" even though the row genuinely changes underneath it.
    initial_status = application.status
    assert initial_status is ApplicationStatus.INVITED

    login(make_user(UserRole.VENDOR, vendor=vendor))
    response = client.patch(
        f"/api/applications/{application.id}/answers",
        json={
            "answers": {
                "A.1": "Test Tikinti MMC",
                "B.1": 1_200_000,
                "B.2": 1_100_000,
                "B.3": 900_000,
            }
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert 0 < body["completion_pct"] < 100
    # B.4 "3-year average (auto)" is the same figure derive_raw returns as raw indicator B.1.
    assert body["computed_fields"]["B.4"] == pytest.approx((1_200_000 + 1_100_000 + 900_000) / 3)
    assert body["checks"]["mandatory_fields"] is False  # A.11/A.15/F.1 still unanswered

    session.refresh(application)
    assert application.status is ApplicationStatus.IN_PROGRESS

    detail = client.get(f"/api/applications/{application.id}").json()
    assert detail["answers"]["A.1"] == "Test Tikinti MMC"


def test_patch_answers_is_last_write_wins_per_field_code(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    cycle: QualificationCycle,
    session: Session,
) -> None:
    vendor = make_vendor()
    application = _invite(session, vendor, cycle)
    login(make_user(UserRole.VENDOR, vendor=vendor))

    client.patch(
        f"/api/applications/{application.id}/answers", json={"answers": {"A.1": "First name"}}
    )
    second = client.patch(
        f"/api/applications/{application.id}/answers", json={"answers": {"A.1": "Corrected name"}}
    )
    assert second.status_code == 200, second.text

    detail = client.get(f"/api/applications/{application.id}").json()
    assert detail["answers"]["A.1"] == "Corrected name"


def test_an_officer_may_patch_answers_on_a_vendors_behalf(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    cycle: QualificationCycle,
    session: Session,
) -> None:
    vendor = make_vendor()
    application = _invite(session, vendor, cycle)
    login(make_user(UserRole.OFFICER))
    response = client.patch(
        f"/api/applications/{application.id}/answers", json={"answers": {"A.1": "Excel intake"}}
    )
    assert response.status_code == 200, response.text


def test_commission_may_not_patch_answers(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    cycle: QualificationCycle,
    session: Session,
) -> None:
    vendor = make_vendor()
    application = _invite(session, vendor, cycle)
    login(make_user(UserRole.COMMISSION))
    response = client.patch(
        f"/api/applications/{application.id}/answers", json={"answers": {"A.1": "x"}}
    )
    assert response.status_code == 403, response.text


def test_patch_answers_is_refused_once_the_application_moved_past_filling(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    cycle: QualificationCycle,
    session: Session,
) -> None:
    vendor = make_vendor()
    application = _invite(session, vendor, cycle)
    uow = UnitOfWork(session)
    applications_service.transition(
        uow, application, ApplicationStatus.IN_PROGRESS, role=UserRole.VENDOR
    )
    applications_service.transition(
        uow, application, ApplicationStatus.SUBMITTED, role=UserRole.VENDOR
    )
    session.commit()

    login(make_user(UserRole.VENDOR, vendor=vendor))
    response = client.patch(
        f"/api/applications/{application.id}/answers", json={"answers": {"A.1": "too late"}}
    )
    assert response.status_code == 409, response.text


# ── submitApplication ────────────────────────────────────────────────────────
def test_submit_refuses_an_incomplete_application_with_machine_readable_checks(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    cycle: QualificationCycle,
    session: Session,
) -> None:
    vendor = make_vendor()
    application = _invite(session, vendor, cycle)
    login(make_user(UserRole.VENDOR, vendor=vendor))
    client.patch(
        f"/api/applications/{application.id}/answers", json={"answers": {"A.1": "Incomplete Co"}}
    )

    response = client.post(
        f"/api/applications/{application.id}/submit",
        json={"signatory_name": "Director", "signatory_position": "CEO", "agreed": True},
    )
    assert response.status_code == 409, response.text
    checks = response.json()["error"]["details"]["checks"]
    assert checks["mandatory_fields"] is False
    assert checks["mandatory_documents"] is False
    assert checks["knock_out_answers"] is False
    assert "A.11" in response.json()["error"]["details"]["missing_field_codes"]

    session.refresh(application)
    assert application.status is ApplicationStatus.IN_PROGRESS
    assert application.raw_snapshot is None


def test_submit_freezes_the_snapshot_and_moves_to_submitted(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    cycle: QualificationCycle,
    session: Session,
) -> None:
    vendor = make_vendor()
    application = _invite(session, vendor, cycle)
    login(make_user(UserRole.VENDOR, vendor=vendor))

    client.patch(f"/api/applications/{application.id}/answers", json={"answers": COMPLETE_ANSWERS})
    _upload_all_mandatory(client, vendor.id)

    response = client.post(
        f"/api/applications/{application.id}/submit",
        json={"signatory_name": "Director", "signatory_position": "CEO", "agreed": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "submitted"
    assert body["submitted_at"] is not None
    assert body["raw_snapshot"] is not None
    # C.1 raw indicator: the completed-project count from the C.t1 table.
    assert body["raw_snapshot"]["C.1"] == 3
    assert body["declaration"]["signatory_name"] == "Director"
    assert body["declaration"]["agreed"] is True

    session.refresh(application)
    assert application.status is ApplicationStatus.SUBMITTED
    assert application.submitted_at is not None
    assert application.raw_snapshot is not None
    assert application.raw_snapshot["C.1"] == 3

    events = session.scalars(select(Event).where(Event.entity_id == application.id)).all()
    assert any(row.type == "application.submitted" for row in events)


def test_a_second_submit_is_a_conflict_not_a_second_snapshot(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    cycle: QualificationCycle,
    session: Session,
) -> None:
    vendor = make_vendor()
    application = _invite(session, vendor, cycle)
    login(make_user(UserRole.VENDOR, vendor=vendor))
    client.patch(f"/api/applications/{application.id}/answers", json={"answers": COMPLETE_ANSWERS})
    _upload_all_mandatory(client, vendor.id)

    declaration = {"signatory_name": "Director", "signatory_position": "CEO", "agreed": True}
    first = client.post(f"/api/applications/{application.id}/submit", json=declaration)
    assert first.status_code == 200, first.text
    first_snapshot = first.json()["raw_snapshot"]

    second = client.post(f"/api/applications/{application.id}/submit", json=declaration)
    assert second.status_code == 409, second.text

    session.refresh(application)
    assert application.raw_snapshot == first_snapshot


def test_a_vendor_may_not_submit_another_vendors_application(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    cycle: QualificationCycle,
    session: Session,
) -> None:
    other = make_vendor()
    application = _invite(session, other, cycle)
    login(make_user(UserRole.VENDOR, vendor=make_vendor()))
    response = client.post(
        f"/api/applications/{application.id}/submit",
        json={"signatory_name": "X", "signatory_position": "Y", "agreed": True},
    )
    assert response.status_code == 404, response.text


def test_manager_may_not_submit_on_a_vendors_behalf(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    cycle: QualificationCycle,
    session: Session,
) -> None:
    """``submitApplication`` is vendor/officer only — the manager approves, later (spec §9)."""
    vendor = make_vendor()
    application = _invite(session, vendor, cycle)
    login(make_user(UserRole.MANAGER))
    response = client.post(
        f"/api/applications/{application.id}/submit",
        json={"signatory_name": "X", "signatory_position": "Y", "agreed": True},
    )
    assert response.status_code == 403, response.text


# ── the score gate (spec §7: "a vendor sees the breakdown only after the decision") ──────
def test_a_vendor_does_not_see_the_score_before_the_commission_decides(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    cycle: QualificationCycle,
    session: Session,
) -> None:
    vendor = make_vendor()
    application = _invite(session, vendor, cycle)
    application.computed = {"per": {}, "groups": {"A": 10.0}, "total": 94.7, "ko": True, "cls": "A"}
    application.rubric_scores = {"A.1": 3}
    session.add(application)
    session.commit()

    login(make_user(UserRole.VENDOR, vendor=vendor))
    detail = client.get(f"/api/applications/{application.id}").json()
    assert detail["score_released"] is False
    assert detail["computed"] is None
    assert detail["rubric_scores"] is None
    assert detail["total"] is None
    assert detail["cls"] is None

    summary = client.get("/api/applications").json()["items"][0]
    assert summary["total"] is None
    assert summary["cls"] is None


def test_the_score_is_visible_once_decided(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    cycle: QualificationCycle,
    session: Session,
) -> None:
    vendor = make_vendor()
    application = _invite(session, vendor, cycle)
    application.computed = {"per": {}, "groups": {"A": 10.0}, "total": 94.7, "ko": True, "cls": "A"}
    application.decided_at = datetime.now(UTC)
    session.add(application)
    session.commit()

    login(make_user(UserRole.VENDOR, vendor=vendor))
    detail = client.get(f"/api/applications/{application.id}").json()
    assert detail["score_released"] is True
    assert detail["computed"]["total"] == 94.7
    assert detail["total"] == 94.7
    assert detail["cls"] == "A"


def test_staff_always_sees_the_score(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    cycle: QualificationCycle,
    session: Session,
) -> None:
    vendor = make_vendor()
    application = _invite(session, vendor, cycle)
    application.computed = {"per": {}, "groups": {}, "total": 38.3, "ko": False, "cls": "KO"}
    session.add(application)
    session.commit()

    login(make_user(UserRole.OFFICER))
    detail = client.get(f"/api/applications/{application.id}").json()
    assert detail["score_released"] is False  # not decided yet
    assert detail["computed"]["cls"] == "KO"


def test_the_detail_carries_completion_even_once_the_application_is_locked(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    cycle: QualificationCycle,
    session: Session,
) -> None:
    """3A, finding 4: the form's own state must be readable without writing.

    `patchAnswers` returns `completion_pct` and `computed_fields`, and the form used to fetch
    them with an empty patch. The server refuses that patch once the application is submitted
    — correctly, since answers are frozen at submission — so screens 6-12 showed
    "Completion 0 / 100" and blank computed cells for a complete, prequalified application.
    The figures now ride on `getApplication`, which is a read.

    The check that matters is the *second* one: before the freeze the old route worked too.
    """
    vendor = make_vendor()
    application = _invite(session, vendor, cycle)
    login(make_user(UserRole.VENDOR, vendor=vendor))

    client.patch(
        f"/api/applications/{application.id}/answers",
        json={"answers": {"A.1": "Test MMC", "B.1": 3_000_000, "B.2": 2_800_000, "B.3": 2_500_000}},
    )
    open_detail = client.get(f"/api/applications/{application.id}").json()
    assert open_detail["completion_pct"] > 0
    assert open_detail["computed_fields"]["B.4"] == pytest.approx(2_766_666.67, rel=1e-6)

    applications_service.transition(
        UnitOfWork(session), application, ApplicationStatus.SUBMITTED, role=UserRole.VENDOR
    )
    session.commit()

    # The write route is refused, which is right ...
    refused = client.patch(f"/api/applications/{application.id}/answers", json={"answers": {}})
    assert refused.status_code == 409

    # ... and the read route still answers, which is the fix.
    locked_detail = client.get(f"/api/applications/{application.id}").json()
    assert locked_detail["completion_pct"] == open_detail["completion_pct"]
    assert locked_detail["computed_fields"] == open_detail["computed_fields"]
