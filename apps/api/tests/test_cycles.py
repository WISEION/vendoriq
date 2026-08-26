"""Qualification cycles: CRUD and bulk invitation (contract tag ``cycles``, spec §9, §11).

Screen 21 (`docs/SCREENS.md`).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from vendoriq_api.models import Application, QualificationCycle, ScoringModel
from vendoriq_api.models.enums import (
    ApplicationStatus,
    CycleKind,
    CycleStatus,
    DecisionKind,
    ScoringModelStatus,
    UserRole,
    VendorStatus,
    VendorType,
)


@pytest.fixture
def model_version(session: Session) -> str:
    """A scoring model row a cycle can reference — tests make their own, the seed's is separate."""
    version = f"test-{uuid.uuid4().hex[:6]}"
    session.add(
        ScoringModel(
            version=version,
            vendor_type=VendorType.SUB,
            name_az="Sınaq modeli",
            name_en="Test model",
            status=ScoringModelStatus.ACTIVE,
            groups=[],
            criteria=[],
            classes=[],
            pass_mark=70,
        )
    )
    session.commit()
    return version


@pytest.fixture
def cycle(session: Session, model_version: str) -> QualificationCycle:
    row = QualificationCycle(
        name="TQS2026099",
        kind=CycleKind.TENDER,
        scoring_model_version=model_version,
        status=CycleStatus.OPEN,
        opens_at=datetime.now(UTC),
    )
    session.add(row)
    session.commit()
    return row


# ── CRUD ─────────────────────────────────────────────────────────────────────
def test_creating_and_listing_a_cycle(
    client: TestClient, make_user: Any, login: Any, model_version: str
) -> None:
    login(make_user(UserRole.OFFICER))
    created = client.post(
        "/api/cycles",
        json={"name": "TQS2026100", "kind": "tender", "scoring_model_version": model_version},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "draft"
    assert body["application_count"] == 0

    listed = client.get("/api/cycles").json()
    assert any(item["id"] == body["id"] for item in listed["items"])


def test_creating_a_cycle_with_an_unknown_model_version_is_rejected(
    client: TestClient, make_user: Any, login: Any
) -> None:
    login(make_user(UserRole.OFFICER))
    response = client.post(
        "/api/cycles",
        json={"name": "TQS-x", "kind": "tender", "scoring_model_version": "no-such-version"},
    )
    assert response.status_code == 422


def test_a_vendor_may_not_create_a_cycle(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any, model_version: str
) -> None:
    login(make_user(UserRole.VENDOR, vendor=make_vendor()))
    response = client.post(
        "/api/cycles",
        json={"name": "TQS-y", "kind": "tender", "scoring_model_version": model_version},
    )
    assert response.status_code == 403


def test_getting_a_cycle_returns_application_counts_by_status(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any, cycle: QualificationCycle
) -> None:
    vendor = make_vendor()
    login(make_user(UserRole.OFFICER))
    invited = client.post(f"/api/vendors/{vendor.id}/invite", json={"cycle_id": str(cycle.id)})
    assert invited.status_code == 201, invited.text

    detail = client.get(f"/api/cycles/{cycle.id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["counts_by_status"] == {"invited": 1}
    assert body["committee"] == []


def test_patching_a_cycle_updates_its_fields(
    client: TestClient, make_user: Any, login: Any, cycle: QualificationCycle, model_version: str
) -> None:
    login(make_user(UserRole.OFFICER))
    response = client.patch(
        f"/api/cycles/{cycle.id}",
        json={
            "name": "TQS2026099 Rev2",
            "kind": "tender",
            "scoring_model_version": model_version,
            "status": "closed",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "TQS2026099 Rev2"
    assert body["status"] == "closed"


def test_the_scoring_model_version_cannot_change_once_scored(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    cycle: QualificationCycle,
    session: Session,
) -> None:
    vendor = make_vendor()
    application = Application(
        vendor_id=vendor.id,
        cycle_id=cycle.id,
        status=ApplicationStatus.PREQUALIFIED,
        computed={"per": {}, "groups": {}, "total": 91.0, "ko": True, "cls": "A"},
        decision=DecisionKind.APPROVE,
        decided_at=datetime.now(UTC),
    )
    session.add(application)
    session.commit()

    other_version = f"test-{uuid.uuid4().hex[:6]}"
    session.add(
        ScoringModel(
            version=other_version,
            vendor_type=VendorType.SUB,
            name_az="Sınaq modeli 2",
            name_en="Test model 2",
            status=ScoringModelStatus.ACTIVE,
            groups=[],
            criteria=[],
            classes=[],
            pass_mark=70,
        )
    )
    session.commit()

    login(make_user(UserRole.OFFICER))
    response = client.patch(
        f"/api/cycles/{cycle.id}",
        json={"name": cycle.name, "kind": "tender", "scoring_model_version": other_version},
    )
    assert response.status_code == 409, response.text


def test_deleting_a_cycle_with_applications_is_refused_not_cascaded(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    cycle: QualificationCycle,
    session: Session,
) -> None:
    vendor = make_vendor()
    login(make_user(UserRole.MANAGER))
    invited = client.post(f"/api/vendors/{vendor.id}/invite", json={"cycle_id": str(cycle.id)})
    assert invited.status_code == 201, invited.text
    application_id = uuid.UUID(invited.json()["id"])

    response = client.delete(f"/api/cycles/{cycle.id}")
    assert response.status_code == 409, response.text

    # Not cascaded: the cycle and its application are both still there.
    assert client.get(f"/api/cycles/{cycle.id}").status_code == 200
    assert session.get(Application, application_id) is not None


def test_deleting_an_empty_cycle_requires_manager_or_admin(
    client: TestClient, make_user: Any, login: Any, cycle: QualificationCycle
) -> None:
    login(make_user(UserRole.OFFICER))
    forbidden = client.delete(f"/api/cycles/{cycle.id}")
    assert forbidden.status_code == 403


def test_deleting_an_empty_cycle_succeeds_for_a_manager(
    client: TestClient, make_user: Any, login: Any, cycle: QualificationCycle
) -> None:
    login(make_user(UserRole.MANAGER))
    response = client.delete(f"/api/cycles/{cycle.id}")
    assert response.status_code == 204
    assert client.get(f"/api/cycles/{cycle.id}").status_code == 404


# ── bulk invitation ──────────────────────────────────────────────────────────
def test_bulk_invite_moves_each_vendor_to_invited_and_records_skips(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    cycle: QualificationCycle,
    session: Session,
) -> None:
    fresh = make_vendor()
    suspended = make_vendor(status=VendorStatus.SUSPENDED)
    already = make_vendor()
    login(make_user(UserRole.OFFICER))
    # Already invited before the bulk call, so the bulk call must skip it, not double-invite.
    pre = client.post(f"/api/vendors/{already.id}/invite", json={"cycle_id": str(cycle.id)})
    assert pre.status_code == 201, pre.text

    response = client.post(
        f"/api/cycles/{cycle.id}/invite",
        json={
            "vendor_ids": [str(fresh.id), str(suspended.id), str(already.id)],
            "message_az": "Dəvət",
            "message_en": "Invitation",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["vendor_id"] for item in body["invited"]] == [str(fresh.id)]
    skipped = {item["vendor_id"]: item["reason"] for item in body["skipped"]}
    assert skipped[str(suspended.id)] == "suspended"
    assert skipped[str(already.id)] == "already_invited"

    session.refresh(fresh)
    assert fresh.status is VendorStatus.INVITED
    session.refresh(suspended)
    assert suspended.status is VendorStatus.SUSPENDED  # untouched


def test_a_vendor_may_not_call_invite_to_cycle(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any, cycle: QualificationCycle
) -> None:
    other = make_vendor()
    login(make_user(UserRole.VENDOR, vendor=make_vendor()))
    response = client.post(f"/api/cycles/{cycle.id}/invite", json={"vendor_ids": [str(other.id)]})
    assert response.status_code == 403
