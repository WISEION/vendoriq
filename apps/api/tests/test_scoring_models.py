"""Scoring model versions and the editor (contract tag ``scoring-models``, spec §10.3, task 2D).

Every scenario builds its own throwaway model version and cycle, mirroring
``test_evaluations.py``'s and ``test_projects.py``'s fixtures — a locked-model refusal test
must not depend on whichever version the shared seed happens to have locked today.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from vendoriq_api.db import UnitOfWork
from vendoriq_api.models import Application, QualificationCycle, Vendor
from vendoriq_api.models import ScoringModel as ScoringModelRow
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
from vendoriq_scoring import load_model, score

#: A vendor scored at exactly the Rev4 threshold boundaries a B.1 weight change will move.
RAW: dict[str, float] = {
    "A.1": 3, "A.2": 10, "A.3": 3, "A.4": 3,
    "B.1": 6_000_000, "B.2": 5_000_000, "B.3": 3, "B.4": 3,
    "C.1": 10, "C.2": 4_000_000, "C.3": 3, "C.4": 3,
    "D.1": 3, "D.2": 3, "D.3": 3,
    "E.1": 60, "E.2": 8, "E.3": 3, "E.4": 3,
    "F.1": 3, "F.2": 3, "F.3": 3,
    "G.1": 3, "G.2": 6,
}  # fmt: skip


@pytest.fixture
def sub4_row(session: Session) -> ScoringModelRow:
    """A throwaway copy of the real Rev4 criteria under its own version, so a locked-flag or
    a criteria-edit test never touches whichever ``sub-4`` row the shared seed left behind."""
    version = f"sub4-test-{uuid.uuid4().hex[:8]}"
    document = load_model("sub-4")
    row = ScoringModelRow(
        version=version,
        vendor_type=VendorType.SUB,
        name_az=document.name_az,
        name_en=document.name_en,
        status=ScoringModelStatus.ACTIVE,
        groups=list(document.groups),
        criteria=list(document.criteria),
        classes=list(document.classes),
        pass_mark=document.pass_mark,
        validity_months=document.validity_months,
        is_locked=False,
    )
    session.add(row)
    session.commit()
    return row


@pytest.fixture
def cycle(session: Session, sub4_row: ScoringModelRow) -> QualificationCycle:
    row = QualificationCycle(
        name=f"cycle-{uuid.uuid4().hex[:6]}",
        kind=CycleKind.TENDER,
        scoring_model_version=sub4_row.version,
        status=CycleStatus.CLOSED,
    )
    session.add(row)
    session.commit()
    return row


def _decided_application(
    uow: UnitOfWork,
    make_vendor: Any,
    cycle: QualificationCycle,
    *,
    raw: dict[str, float] = RAW,
) -> Application:
    vendor: Vendor = make_vendor(type=VendorType.SUB, status=VendorStatus.PREQUALIFIED)
    # The throwaway version is a byte-for-byte copy of the real Rev4 criteria (`sub4_row`
    # fixture), so scoring against the shipped `sub-4` JSON gives the identical result.
    result = score(load_model("sub-4"), raw)
    application = Application(
        vendor_id=vendor.id,
        cycle_id=cycle.id,
        status=ApplicationStatus.PREQUALIFIED,
        raw_snapshot=dict(raw),
        computed=asdict(result),
        decision=DecisionKind.APPROVE,
        decided_at=datetime.now(UTC),
    )
    uow.session.add(application)
    uow.commit()
    return application


# ── list / get ───────────────────────────────────────────────────────────────
def test_listing_scoring_models_includes_the_new_version(
    client: TestClient, make_user: Any, login: Any, sub4_row: ScoringModelRow
) -> None:
    login(make_user(UserRole.OFFICER))
    listed = client.get("/api/scoring-models").json()
    versions = {row["version"] for row in listed}
    assert sub4_row.version in versions
    row = next(r for r in listed if r["version"] == sub4_row.version)
    assert row["vendor_type"] == "sub"
    assert row["is_locked"] is False
    assert row["application_count"] == 0


def test_listing_filters_by_vendor_type(
    client: TestClient, make_user: Any, login: Any, sub4_row: ScoringModelRow
) -> None:
    login(make_user(UserRole.OFFICER))
    subs = client.get("/api/scoring-models", params={"vendor_type": "sub"}).json()
    assert any(row["version"] == sub4_row.version for row in subs)
    sups = client.get("/api/scoring-models", params={"vendor_type": "sup"}).json()
    assert all(row["version"] != sub4_row.version for row in sups)


def test_getting_an_unknown_version_is_404(client: TestClient, make_user: Any, login: Any) -> None:
    login(make_user(UserRole.OFFICER))
    assert client.get("/api/scoring-models/no-such-version").status_code == 404


def test_getting_a_version_returns_its_full_criteria_set(
    client: TestClient, make_user: Any, login: Any, sub4_row: ScoringModelRow
) -> None:
    login(make_user(UserRole.OFFICER))
    body = client.get(f"/api/scoring-models/{sub4_row.version}").json()
    assert body["total_max"] == 100.0
    assert body["currency"] == "AZN"
    assert len(body["criteria"]) == len(sub4_row.criteria)
    assert len(body["groups"]) == 7
    assert {band["cls"] for band in body["classes"]} == {"A", "B", "C", "D", "F"}


# ── create draft ─────────────────────────────────────────────────────────────
def test_creating_a_draft_copies_criteria_without_mutating_the_source(
    client: TestClient, make_user: Any, login: Any, sub4_row: ScoringModelRow, session: Session
) -> None:
    login(make_user(UserRole.MANAGER))
    new_version = f"{sub4_row.version}-v2"
    created = client.post(
        "/api/scoring-models",
        json={"from_version": sub4_row.version, "version": new_version, "note": "widen B.1"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "draft"
    assert body["is_locked"] is False
    assert body["application_count"] == 0
    assert len(body["criteria"]) == len(sub4_row.criteria)

    # the source is untouched
    session.refresh(sub4_row)
    assert sub4_row.status == ScoringModelStatus.ACTIVE
    assert [c["max"] for c in sub4_row.criteria] == [c["max"] for c in load_model("sub-4").criteria]


def test_creating_a_draft_from_an_unknown_source_is_404(
    client: TestClient, make_user: Any, login: Any
) -> None:
    login(make_user(UserRole.MANAGER))
    response = client.post(
        "/api/scoring-models", json={"from_version": "no-such-version", "version": "x-1"}
    )
    assert response.status_code == 404


def test_creating_a_draft_with_a_version_that_already_exists_conflicts(
    client: TestClient, make_user: Any, login: Any, sub4_row: ScoringModelRow
) -> None:
    login(make_user(UserRole.MANAGER))
    response = client.post(
        "/api/scoring-models",
        json={"from_version": sub4_row.version, "version": sub4_row.version},
    )
    assert response.status_code == 409


def test_only_manager_or_admin_may_create_a_draft(
    client: TestClient, make_user: Any, login: Any, sub4_row: ScoringModelRow
) -> None:
    login(make_user(UserRole.OFFICER))
    response = client.post(
        "/api/scoring-models",
        json={"from_version": sub4_row.version, "version": f"{sub4_row.version}-refused"},
    )
    assert response.status_code == 403


# ── patch (ADR-017) ──────────────────────────────────────────────────────────
def test_patching_an_unlocked_draft_updates_criteria_and_pass_mark(
    client: TestClient, make_user: Any, login: Any, sub4_row: ScoringModelRow
) -> None:
    login(make_user(UserRole.MANAGER))
    criteria = client.get(f"/api/scoring-models/{sub4_row.version}").json()["criteria"]
    for criterion in criteria:
        if criterion["code"] == "B.1":
            criterion["max"] = 10
    response = client.patch(
        f"/api/scoring-models/{sub4_row.version}",
        json={"criteria": criteria, "pass_mark": 65},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pass_mark"] == 65
    assert next(c for c in body["criteria"] if c["code"] == "B.1")["max"] == 10


def test_patching_a_locked_version_is_refused(
    client: TestClient,
    make_user: Any,
    login: Any,
    sub4_row: ScoringModelRow,
    session: Session,
) -> None:
    """ADR-017: ``is_locked`` freezes the *definition*, and ``patchScoringModelDraft`` is
    exactly where that bites — the operation this task owns."""
    sub4_row.is_locked = True
    session.commit()

    login(make_user(UserRole.MANAGER))
    response = client.patch(f"/api/scoring-models/{sub4_row.version}", json={"pass_mark": 60})
    assert response.status_code == 409
    assert response.json()["error"]["details"]["is_locked"] is True

    # untouched
    session.refresh(sub4_row)
    assert float(sub4_row.pass_mark) == 70.0


def test_a_locked_model_may_still_be_status_active_or_retired_and_is_refused_either_way(
    client: TestClient,
    make_user: Any,
    login: Any,
    sub4_row: ScoringModelRow,
    session: Session,
) -> None:
    """ADR-017's whole point: locked-and-active is a normal, legal state — the refusal is on
    ``is_locked``, never on ``status``."""
    sub4_row.is_locked = True
    sub4_row.status = ScoringModelStatus.ACTIVE
    session.commit()

    login(make_user(UserRole.MANAGER))
    response = client.patch(f"/api/scoring-models/{sub4_row.version}", json={"pass_mark": 60})
    assert response.status_code == 409


def test_only_manager_or_admin_may_patch_a_draft(
    client: TestClient, make_user: Any, login: Any, sub4_row: ScoringModelRow
) -> None:
    login(make_user(UserRole.OFFICER))
    response = client.patch(f"/api/scoring-models/{sub4_row.version}", json={"pass_mark": 60})
    assert response.status_code == 403


def test_a_vendor_cannot_read_or_write_scoring_models_it_should_not(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any, sub4_row: ScoringModelRow
) -> None:
    login(make_user(UserRole.VENDOR, vendor=make_vendor()))
    # vendors may read (spec §10.3: "the vendor sees the class bands") …
    assert client.get(f"/api/scoring-models/{sub4_row.version}").status_code == 200
    # … but never create, edit or publish.
    assert (
        client.patch(f"/api/scoring-models/{sub4_row.version}", json={"pass_mark": 1}).status_code
        == 403
    )
    assert (
        client.post(
            "/api/scoring-models", json={"from_version": sub4_row.version, "version": "v-x"}
        ).status_code
        == 403
    )


# ── publish ──────────────────────────────────────────────────────────────────
def test_publishing_a_draft_sets_active_and_effective_from(
    client: TestClient, make_user: Any, login: Any, sub4_row: ScoringModelRow, session: Session
) -> None:
    sub4_row.status = ScoringModelStatus.DRAFT
    session.commit()

    login(make_user(UserRole.MANAGER))
    response = client.post(
        f"/api/scoring-models/{sub4_row.version}/publish", json={"effective_from": "2027-01-01"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "active"
    assert body["effective_from"] == "2027-01-01"


def test_publishing_a_proposed_version_is_allowed(
    client: TestClient, make_user: Any, login: Any, sub4_row: ScoringModelRow, session: Session
) -> None:
    sub4_row.status = ScoringModelStatus.PROPOSED
    session.commit()
    login(make_user(UserRole.MANAGER))
    response = client.post(f"/api/scoring-models/{sub4_row.version}/publish")
    assert response.status_code == 200
    assert response.json()["status"] == "active"
    assert response.json()["effective_from"] is not None


def test_publishing_an_already_active_version_conflicts(
    client: TestClient, make_user: Any, login: Any, sub4_row: ScoringModelRow
) -> None:
    login(make_user(UserRole.MANAGER))
    response = client.post(f"/api/scoring-models/{sub4_row.version}/publish")
    assert response.status_code == 409


def test_publishing_a_retired_version_conflicts(
    client: TestClient, make_user: Any, login: Any, sub4_row: ScoringModelRow, session: Session
) -> None:
    sub4_row.status = ScoringModelStatus.RETIRED
    session.commit()
    login(make_user(UserRole.MANAGER))
    response = client.post(f"/api/scoring-models/{sub4_row.version}/publish")
    assert response.status_code == 409


def test_only_manager_or_admin_may_publish(
    client: TestClient, make_user: Any, login: Any, sub4_row: ScoringModelRow, session: Session
) -> None:
    sub4_row.status = ScoringModelStatus.DRAFT
    session.commit()
    login(make_user(UserRole.OFFICER))
    response = client.post(f"/api/scoring-models/{sub4_row.version}/publish")
    assert response.status_code == 403


# ── test re-score ────────────────────────────────────────────────────────────
def test_rescore_reports_deltas_and_persists_nothing(
    client: TestClient,
    make_user: Any,
    make_vendor: Any,
    login: Any,
    session: Session,
    sub4_row: ScoringModelRow,
    cycle: QualificationCycle,
) -> None:
    uow = UnitOfWork(session)
    application = _decided_application(uow, make_vendor, cycle)
    original_computed = dict(application.computed or {})

    login(make_user(UserRole.MANAGER))
    draft_version = f"{sub4_row.version}-draft"
    created = client.post(
        "/api/scoring-models",
        json={"from_version": sub4_row.version, "version": draft_version},
    )
    assert created.status_code == 201, created.text
    criteria = created.json()["criteria"]
    for criterion in criteria:
        if criterion["code"] == "B.1":
            criterion["max"] = criterion["max"] + 4  # widen the turnover weight
    patched = client.patch(f"/api/scoring-models/{draft_version}", json={"criteria": criteria})
    assert patched.status_code == 200, patched.text

    before_app_count = session.scalar(select(func.count()).select_from(Application))
    before_model_count = session.scalar(select(func.count()).select_from(ScoringModelRow))
    before_criteria = list(session.get(ScoringModelRow, sub4_row.version).criteria)  # type: ignore[union-attr]

    report = client.post(
        f"/api/scoring-models/{draft_version}/test-rescore",
        json={"cycle_id": str(cycle.id)},
    )
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["from_version"] == sub4_row.version
    assert body["to_version"] == draft_version
    assert len(body["rows"]) == 1
    row = body["rows"][0]
    assert row["vendor_id"] == str(application.vendor_id)
    assert row["old_total"] == original_computed["total"]
    assert row["new_total"] > row["old_total"]  # B.1 widened -> more points, never fewer
    assert row["changed"] is True
    assert body["summary"]["changed_count"] == 1

    # nothing was written: same row counts, the *source* model's own criteria untouched, and
    # the application's stored score is exactly what it was before the test ran.
    after_app_count = session.scalar(select(func.count()).select_from(Application))
    after_model_count = session.scalar(select(func.count()).select_from(ScoringModelRow))
    assert after_app_count == before_app_count
    assert after_model_count == before_model_count
    session.refresh(application)
    assert application.computed == original_computed
    session.refresh(sub4_row)
    assert list(sub4_row.criteria) == before_criteria


def test_rescore_against_an_unknown_cycle_is_404(
    client: TestClient, make_user: Any, login: Any, sub4_row: ScoringModelRow
) -> None:
    login(make_user(UserRole.MANAGER))
    response = client.post(
        f"/api/scoring-models/{sub4_row.version}/test-rescore",
        json={"cycle_id": str(uuid.uuid4())},
    )
    assert response.status_code == 404


def test_rescore_is_gated_the_same_as_the_write_operations(
    client: TestClient,
    make_user: Any,
    login: Any,
    sub4_row: ScoringModelRow,
    cycle: QualificationCycle,
) -> None:
    login(make_user(UserRole.OFFICER))
    response = client.post(
        f"/api/scoring-models/{sub4_row.version}/test-rescore",
        json={"cycle_id": str(cycle.id)},
    )
    assert response.status_code == 403
