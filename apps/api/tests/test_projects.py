"""Projects, work packages and matching (contract tag ``projects``, spec §11).

Screens 22–24 (`docs/SCREENS.md`). The TQS-238 test at the bottom exercises the whole
pipeline — seed, category confirmation, ``POST .../match`` — against the API, the way a
manager actually reaches these numbers, and checks the result against spec §11.2.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from vendoriq_api.config import Settings
from vendoriq_api.db import UnitOfWork
from vendoriq_api.models import (
    Application,
    Category,
    Project,
    QualificationCycle,
    ScoringModel,
    Vendor,
)
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
from vendoriq_api.services import categories as categories_service
from vendoriq_scoring import load_model, score

#: A vendor good enough to be class A anywhere: 5M largest project, every KO clear.
STRONG_RAW: dict[str, Any] = {
    "A.1": 3, "A.2": 20, "A.3": 3, "A.4": 3,
    "B.1": 20_000_000, "B.2": 5_000_000, "B.3": 3, "B.4": 3,
    "C.1": 20, "C.2": 5_000_000, "C.3": 5, "C.4": 3,
    "D.1": 3, "D.2": 3, "D.3": 3,
    "E.1": 200, "E.2": 30, "E.3": 3, "E.4": 3,
    "F.1": 3, "F.2": 3, "F.3": 3,
    "G.1": 3, "G.2": 10,
}  # fmt: skip


@pytest.fixture
def sub4_row(session: Session) -> ScoringModel:
    """The real ``sub-4`` model as a DB row — the FK ``cycle.scoring_model_version`` needs,
    and the version the matching engine actually loads its JSON from (packages/scoring)."""
    existing = session.get(ScoringModel, "sub-4")
    if existing is not None:
        return existing
    document = load_model("sub-4")
    row = ScoringModel(
        version="sub-4",
        vendor_type=VendorType.SUB,
        name_az=document.name_az,
        name_en=document.name_en,
        status=ScoringModelStatus.ACTIVE,
        groups=list(document.groups),
        criteria=list(document.criteria),
        classes=list(document.classes),
        pass_mark=document.pass_mark,
        validity_months=document.validity_months,
    )
    session.add(row)
    session.commit()
    return row


@pytest.fixture
def cycle(session: Session, sub4_row: ScoringModel) -> QualificationCycle:
    row = QualificationCycle(
        name=f"cycle-{uuid.uuid4().hex[:6]}",
        kind=CycleKind.TENDER,
        scoring_model_version="sub-4",
        status=CycleStatus.CLOSED,
    )
    session.add(row)
    session.commit()
    return row


def _make_strong_vendor(
    uow: UnitOfWork,
    make_vendor: Any,
    cycle: QualificationCycle,
    category: Category,
    *,
    legal_name: str,
) -> Vendor:
    """A prequalified class-A subcontractor, confirmed in ``category`` (spec §11.1)."""
    vendor: Vendor = make_vendor(
        legal_name=legal_name, type=VendorType.SUB, status=VendorStatus.PREQUALIFIED
    )
    categories_service.set_for_vendor(uow, vendor.id, [category.code])
    categories_service.confirm_for_vendor(uow, vendor.id, [category.code])
    result = score(load_model("sub-4"), STRONG_RAW)
    application = Application(
        vendor_id=vendor.id,
        cycle_id=cycle.id,
        status=ApplicationStatus.PREQUALIFIED,
        raw_snapshot=dict(STRONG_RAW),
        computed=asdict(result),
        decision=DecisionKind.APPROVE,
        decided_at=datetime.now(UTC),
    )
    uow.session.add(application)
    uow.commit()
    return vendor


# ── project CRUD ─────────────────────────────────────────────────────────────
def test_creating_and_listing_a_project(client: TestClient, make_user: Any, login: Any) -> None:
    login(make_user(UserRole.OFFICER))
    created = client.post(
        "/api/projects", json={"code": f"P-{uuid.uuid4().hex[:6]}", "name": "Test Tower"}
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["stage"] == "pipeline"
    assert body["package_count"] == 0
    assert body["match_state"] is None

    listed = client.get("/api/projects").json()
    assert any(item["id"] == body["id"] for item in listed["items"])


def test_creating_a_project_with_a_duplicate_code_conflicts(
    client: TestClient, make_user: Any, login: Any
) -> None:
    login(make_user(UserRole.OFFICER))
    code = f"P-{uuid.uuid4().hex[:6]}"
    first = client.post("/api/projects", json={"code": code, "name": "First"})
    assert first.status_code == 201
    second = client.post("/api/projects", json={"code": code, "name": "Second"})
    assert second.status_code == 409


def test_only_back_office_may_create_a_project(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    login(make_user(UserRole.VENDOR, vendor=make_vendor()))
    response = client.post("/api/projects", json={"code": "P-x", "name": "X"})
    assert response.status_code == 403


def test_a_vendor_may_not_list_projects(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    login(make_user(UserRole.VENDOR, vendor=make_vendor()))
    assert client.get("/api/projects").status_code == 403


def test_deleting_a_project_requires_manager_or_admin(
    client: TestClient, make_user: Any, login: Any
) -> None:
    login(make_user(UserRole.OFFICER))
    created = client.post(
        "/api/projects", json={"code": f"P-{uuid.uuid4().hex[:6]}", "name": "Del"}
    )
    project_id = created.json()["id"]

    forbidden = client.delete(f"/api/projects/{project_id}")
    assert forbidden.status_code == 403

    login(make_user(UserRole.MANAGER))
    allowed = client.delete(f"/api/projects/{project_id}")
    assert allowed.status_code == 204
    assert client.get(f"/api/projects/{project_id}").status_code == 404


def test_patching_a_project(client: TestClient, make_user: Any, login: Any) -> None:
    login(make_user(UserRole.OFFICER))
    created = client.post(
        "/api/projects", json={"code": f"P-{uuid.uuid4().hex[:6]}", "name": "Old"}
    )
    project_id = created.json()["id"]
    updated = client.patch(
        f"/api/projects/{project_id}",
        json={"code": created.json()["code"], "name": "New name", "stage": "tender"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "New name"
    assert updated.json()["stage"] == "tender"


# ── work packages ────────────────────────────────────────────────────────────
@pytest.fixture
def project(client: TestClient, make_user: Any, login: Any) -> dict[str, Any]:
    login(make_user(UserRole.OFFICER))
    created = client.post(
        "/api/projects", json={"code": f"P-{uuid.uuid4().hex[:6]}", "name": "Package host"}
    )
    assert created.status_code == 201, created.text
    body: dict[str, Any] = created.json()
    return body


def test_creating_and_listing_a_package(
    client: TestClient, make_user: Any, make_category: Any, login: Any, project: dict[str, Any]
) -> None:
    category = make_category()
    login(make_user(UserRole.OFFICER))
    created = client.post(
        f"/api/projects/{project['id']}/packages",
        json={"category_code": category.code, "estimated_value": 500_000, "min_class": "B"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["category"]["code"] == category.code
    assert body["min_class"] == "B"

    listed = client.get(f"/api/projects/{project['id']}/packages").json()
    assert len(listed) == 1

    detail = client.get(f"/api/projects/{project['id']}").json()
    assert detail["package_count"] == 1
    assert len(detail["packages"]) == 1


def test_a_package_with_a_negative_value_is_rejected(
    client: TestClient, make_user: Any, make_category: Any, login: Any, project: dict[str, Any]
) -> None:
    category = make_category()
    login(make_user(UserRole.OFFICER))
    response = client.post(
        f"/api/projects/{project['id']}/packages",
        json={"category_code": category.code, "estimated_value": -1},
    )
    assert response.status_code == 422


def test_a_package_with_an_unknown_category_is_rejected(
    client: TestClient, make_user: Any, login: Any, project: dict[str, Any]
) -> None:
    login(make_user(UserRole.OFFICER))
    response = client.post(
        f"/api/projects/{project['id']}/packages",
        json={"category_code": "no-such-category", "estimated_value": 1000},
    )
    assert response.status_code == 422


def test_patching_and_deleting_a_package(
    client: TestClient, make_user: Any, make_category: Any, login: Any, project: dict[str, Any]
) -> None:
    category = make_category()
    other = make_category()
    login(make_user(UserRole.OFFICER))
    created = client.post(
        f"/api/projects/{project['id']}/packages",
        json={"category_code": category.code, "estimated_value": 100},
    ).json()

    patched = client.patch(
        f"/api/projects/{project['id']}/packages/{created['id']}",
        json={"category_code": other.code, "estimated_value": 250, "min_class": "A"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["category"]["code"] == other.code
    assert patched.json()["estimated_value"] == 250

    deleted = client.delete(f"/api/projects/{project['id']}/packages/{created['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/projects/{project['id']}/packages").json() == []


# ── matching ─────────────────────────────────────────────────────────────────
def test_getting_a_project_before_any_match_has_no_latest_match(
    client: TestClient, project: dict[str, Any]
) -> None:
    detail = client.get(f"/api/projects/{project['id']}").json()
    assert detail["latest_match"] is None
    assert detail["coverage_pct"] is None
    assert detail["match_state"] is None


def test_get_latest_match_is_404_before_the_first_run(
    client: TestClient, project: dict[str, Any]
) -> None:
    response = client.get(f"/api/projects/{project['id']}/match/latest")
    assert response.status_code == 404


def test_run_match_persists_a_run_and_get_latest_match_does_not_recompute(
    client: TestClient,
    make_user: Any,
    make_category: Any,
    make_vendor: Any,
    login: Any,
    uow: UnitOfWork,
    cycle: QualificationCycle,
) -> None:
    category = make_category()
    login(make_user(UserRole.OFFICER))
    project = client.post(
        "/api/projects", json={"code": f"P-{uuid.uuid4().hex[:6]}", "name": "Two strong vendors"}
    ).json()
    package = client.post(
        f"/api/projects/{project['id']}/packages",
        json={"category_code": category.code, "estimated_value": 1_000_000, "min_class": "B"},
    ).json()

    _make_strong_vendor(uow, make_vendor, cycle, category, legal_name="Strong One")
    _make_strong_vendor(uow, make_vendor, cycle, category, legal_name="Strong Two")

    ran = client.post(f"/api/projects/{project['id']}/match")
    assert ran.status_code == 201, ran.text
    body = ran.json()
    assert body["state"] == "go"
    assert body["coverage_pct"] == 100
    assert body["recommendation_key"] == "m_rec_go"
    assert len(body["packages"]) == 1
    pkg = body["packages"][0]
    assert pkg["package_id"] == package["id"]
    assert pkg["state"] == "go"
    assert pkg["gap"] is None
    assert len(pkg["candidates"]) == 2
    assert all(c["eligible"] for c in pkg["candidates"])

    latest = client.get(f"/api/projects/{project['id']}/match/latest")
    assert latest.status_code == 200
    assert latest.json()["id"] == body["id"]
    assert latest.json()["coverage_pct"] == 100

    # A different vendor prequalifying later must not change the stored run.
    _make_strong_vendor(uow, make_vendor, cycle, category, legal_name="Strong Three, too late")
    still_latest = client.get(f"/api/projects/{project['id']}/match/latest")
    assert still_latest.json()["id"] == body["id"]
    assert len(still_latest.json()["packages"][0]["candidates"]) == 2


def test_run_match_accepts_a_param_override(
    client: TestClient,
    make_user: Any,
    make_category: Any,
    make_vendor: Any,
    login: Any,
    uow: UnitOfWork,
    cycle: QualificationCycle,
) -> None:
    category = make_category()
    login(make_user(UserRole.OFFICER))
    project = client.post(
        "/api/projects", json={"code": f"P-{uuid.uuid4().hex[:6]}", "name": "One strong vendor"}
    ).json()
    client.post(
        f"/api/projects/{project['id']}/packages",
        json={"category_code": category.code, "estimated_value": 1_000_000, "min_class": "B"},
    )
    _make_strong_vendor(uow, make_vendor, cycle, category, legal_name="Only Strong One")

    default_run = client.post(f"/api/projects/{project['id']}/match").json()
    assert default_run["state"] == "cond"  # one strong vendor, default strong_min=2

    overridden = client.post(f"/api/projects/{project['id']}/match", json={"strong_min": 1}).json()
    assert overridden["state"] == "go"
    assert overridden["params"]["strong_min"] == 1


def test_only_staff_may_run_match(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any, project: dict[str, Any]
) -> None:
    login(make_user(UserRole.VENDOR, vendor=make_vendor()))
    response = client.post(f"/api/projects/{project['id']}/match")
    assert response.status_code == 403


def test_export_project_returns_an_xlsx_file(
    client: TestClient,
    make_user: Any,
    make_category: Any,
    make_vendor: Any,
    login: Any,
    uow: UnitOfWork,
    cycle: QualificationCycle,
) -> None:
    category = make_category()
    login(make_user(UserRole.OFFICER))
    project = client.post(
        "/api/projects", json={"code": f"P-{uuid.uuid4().hex[:6]}", "name": "Exportable"}
    ).json()
    client.post(
        f"/api/projects/{project['id']}/packages",
        json={"category_code": category.code, "estimated_value": 1_000_000, "min_class": "B"},
    )
    _make_strong_vendor(uow, make_vendor, cycle, category, legal_name="Export Vendor")
    client.post(f"/api/projects/{project['id']}/match")

    response = client.get(f"/api/projects/{project['id']}/export.xlsx")
    assert response.status_code == 200
    assert (
        response.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response.content[:2] == b"PK"  # the zip signature every xlsx starts with


# ── TQS-238, the worked example (spec §11.2) ─────────────────────────────────
def test_tqs_238_end_to_end_through_the_endpoints(
    client: TestClient,
    make_user: Any,
    login: Any,
    settings: Settings,
    session: Session,
    uow: UnitOfWork,
) -> None:
    """Seed real + demo, confirm categories (the officer's step spec §11.1 requires before a
    vendor is a candidate), then run matching through the same endpoint the manager screen
    calls, and check the result against spec §11.2's worked example.
    """
    from vendoriq_api.seed import demo as demo_seed
    from vendoriq_api.seed import real as real_seed
    from vendoriq_api.seed.common import external_ref
    from vendoriq_api.seed.data import load_seed_data

    real_seed.load_real(uow, settings=settings)
    demo_seed.load_demo(uow)
    uow.commit()

    data = load_seed_data()
    for row in [*data.vendors, *data.suppliers]:
        codes = row.get("cats") or []
        if not codes:
            continue
        vendor = session.scalar(
            select(Vendor).where(Vendor.external_ref == external_ref(row["id"]))
        )
        assert vendor is not None, row["id"]
        categories_service.set_for_vendor(uow, vendor.id, codes)
        categories_service.confirm_for_vendor(uow, vendor.id, codes)
    uow.commit()

    project = session.scalar(select(Project).where(Project.code == "TQS-238"))
    assert project is not None

    login(make_user(UserRole.MANAGER))
    response = client.post(f"/api/projects/{project.id}/match")
    assert response.status_code == 201, response.text
    result = response.json()

    packages_by_category = {
        pkg["category"]["code"]: pkg
        for pkg in client.get(f"/api/projects/{project.id}").json()["packages"]
    }
    flooring_id = packages_by_category["flooring"]["id"]
    flooring_result = next(p for p in result["packages"] if p["package_id"] == flooring_id)

    print("TQS-238 project state:", result["state"])
    print("TQS-238 coverage_pct:", result["coverage_pct"])
    for pkg in result["packages"]:
        category = next(
            code for code, row in packages_by_category.items() if row["id"] == pkg["package_id"]
        )
        print(f"  package {category}: state={pkg['state']} gap={pkg['gap']}")

    assert result["state"] == "nogo"
    assert flooring_result["state"] == "nogo"
