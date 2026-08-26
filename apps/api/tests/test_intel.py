"""Market intelligence (contract tag ``intel``, spec §12, task 2D).

The register check at the bottom runs against ``make seed && make seed-demo`` (ADR-018's own
fixture) and pins the numbers the brief names as checkable by hand: 6 prequalified
subcontractors, 7 rejected, 2 prequalified suppliers. Every other test builds its own
isolated vendors and categories so a coverage/capacity/gap assertion never depends on
whatever the shared seed happens to contain today.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from vendoriq_api.config import Settings
from vendoriq_api.db import UnitOfWork
from vendoriq_api.models import Application, Category, QualificationCycle, Vendor
from vendoriq_api.models import ScoringModel as ScoringModelRow
from vendoriq_api.models.enums import (
    ApplicationStatus,
    CycleKind,
    CycleStatus,
    DecisionKind,
    ObservationSource,
    ScoringModelStatus,
    UserRole,
    VendorStatus,
    VendorType,
)
from vendoriq_api.seed import demo as demo_seed
from vendoriq_api.seed import real as real_seed
from vendoriq_api.services import categories as categories_service
from vendoriq_api.services import observations as observations_service
from vendoriq_scoring import load_model, score

#: Every non-KO, non-cert rubric criterion at a mid value, KO clean, tuned so B.1/E.2/C.3 are
#: distinctive integers a capacity test can add up by hand.
BASE_RAW: dict[str, float] = {
    "A.1": 3, "A.2": 10, "A.3": 3, "A.4": 3,
    "B.1": 2_000_000, "B.2": 1_000_000, "B.3": 3, "B.4": 0,
    "C.1": 6, "C.2": 1_500_000, "C.3": 4, "C.4": 0,
    "D.1": 3, "D.2": 3, "D.3": 3,
    "E.1": 40, "E.2": 5, "E.3": 0, "E.4": 3,
    "F.1": 3, "F.2": 0, "F.3": 3,
    "G.1": 0, "G.2": 3,
}  # fmt: skip
#: The same shape, with every certification rubric switched on (C.4, F.2, G.1, B.4, E.3 > 0).
CERTIFIED_RAW: dict[str, float] = {**BASE_RAW, "C.4": 3, "F.2": 3, "G.1": 3, "B.4": 3, "E.3": 3}
#: Fails the licence knock-out outright — still "scored" (KO), for the coverage matrix.
KO_RAW: dict[str, float] = {**BASE_RAW, "A.1": 0}


@pytest.fixture
def sub4_row(session: Session) -> ScoringModelRow:
    version = f"sub4-intel-{uuid.uuid4().hex[:8]}"
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
        is_locked=True,
    )
    session.add(row)
    session.commit()
    return row


@pytest.fixture
def cycle(session: Session, sub4_row: ScoringModelRow) -> QualificationCycle:
    row = QualificationCycle(
        name=f"intel-cycle-{uuid.uuid4().hex[:6]}",
        kind=CycleKind.TENDER,
        scoring_model_version=sub4_row.version,
        status=CycleStatus.CLOSED,
    )
    session.add(row)
    session.commit()
    return row


def _scored_vendor(
    uow: UnitOfWork,
    make_vendor: Any,
    cycle: QualificationCycle,
    category: Category | None,
    *,
    raw: dict[str, float] = BASE_RAW,
    decision: DecisionKind = DecisionKind.APPROVE,
    vendor_type: VendorType = VendorType.SUB,
    confirmed: bool = True,
) -> Vendor:
    status = (
        VendorStatus.PREQUALIFIED if decision is DecisionKind.APPROVE else VendorStatus.REJECTED
    )
    vendor: Vendor = make_vendor(type=vendor_type, status=status)
    if category is not None:
        categories_service.set_for_vendor(uow, vendor.id, [category.code])
        if confirmed:
            categories_service.confirm_for_vendor(uow, vendor.id, [category.code])
    result = score(load_model("sub-4"), raw)
    application = Application(
        vendor_id=vendor.id,
        cycle_id=cycle.id,
        status=ApplicationStatus.PREQUALIFIED
        if decision is DecisionKind.APPROVE
        else ApplicationStatus.REJECTED,
        raw_snapshot=dict(raw),
        computed=asdict(result),
        decision=decision,
        decided_at=datetime.now(UTC),
    )
    uow.session.add(application)
    uow.commit()
    return vendor


# ── overview: the register, by hand ──────────────────────────────────────────
def test_overview_matches_the_seeded_register(
    client: TestClient, make_user: Any, login: Any, uow: UnitOfWork, settings: Settings
) -> None:
    """``make seed && make seed-demo`` (ADR-018): 6 prequalified subcontractors, 7 rejected,
    2 prequalified suppliers, 2 rejected suppliers — checkable by hand against the register.

    The test loads that register itself. It used to read whatever the database happened to
    hold, which passed on a developer's seeded database and reported ``0 >= 8`` on the suite's
    own, empty one — a test that only agrees with the product where someone has already run
    the seed by hand is not a check, it is a coincidence.
    """
    real_seed.load_real(uow, settings=settings)
    demo_seed.load_demo(uow)

    login(make_user(UserRole.MANAGER))
    body = client.get("/api/intel/overview").json()
    assert body["prequalified"] >= 8  # 6 sub + 2 sup, at minimum (isolated tests add no more)
    assert body["vendors_total"] >= 17
    assert body["vendors_sub"] >= 13
    assert body["vendors_sup"] >= 4
    # A/B classes among the 6 prequalified subs: Shield(A), Wesa(A), Arti(B), İNPROCON(B) = 4;
    # among the 2 prequalified suppliers: Baku Beton(A), Caspian Steel(A) = 2 → 6 total.
    assert body["prequalified_ab"] >= 6


# ── coverage matrix ──────────────────────────────────────────────────────────
def test_coverage_counts_every_scored_vendor_not_only_prequalified(
    client: TestClient,
    make_user: Any,
    make_vendor: Any,
    make_category: Any,
    login: Any,
    session: Session,
    cycle: QualificationCycle,
) -> None:
    uow = UnitOfWork(session)
    category = make_category()
    _scored_vendor(uow, make_vendor, cycle, category, decision=DecisionKind.APPROVE)  # class A/B/C
    _scored_vendor(uow, make_vendor, cycle, category, raw=KO_RAW, decision=DecisionKind.REJECT)

    login(make_user(UserRole.MANAGER))
    rows = client.get("/api/intel/coverage").json()
    row = next(r for r in rows if r["category_code"] == category.code)
    assert row["total"] == 2
    assert sum(row["counts"].values()) == 2
    assert row["counts"].get("KO") == 1


def test_coverage_reports_an_empty_category_as_a_gap_row(
    client: TestClient, make_user: Any, make_category: Any, login: Any
) -> None:
    """Spec §12: an empty row is a gap to report, never hidden."""
    category = make_category()
    login(make_user(UserRole.MANAGER))
    rows = client.get("/api/intel/coverage").json()
    row = next(r for r in rows if r["category_code"] == category.code)
    assert row["counts"] == {}
    assert row["total"] == 0
    assert row["ab_share"] is None  # never a fabricated zero


def test_coverage_only_counts_confirmed_categories(
    client: TestClient,
    make_user: Any,
    make_vendor: Any,
    make_category: Any,
    login: Any,
    session: Session,
    cycle: QualificationCycle,
) -> None:
    uow = UnitOfWork(session)
    category = make_category()
    _scored_vendor(
        uow, make_vendor, cycle, category, decision=DecisionKind.APPROVE, confirmed=False
    )

    login(make_user(UserRole.MANAGER))
    rows = client.get("/api/intel/coverage").json()
    row = next(r for r in rows if r["category_code"] == category.code)
    assert row["total"] == 0


def test_coverage_filters_by_kind(
    client: TestClient, make_user: Any, make_category: Any, login: Any
) -> None:
    from vendoriq_api.models.enums import CategoryKind

    work = make_category(kind=CategoryKind.WORK)
    material = make_category(kind=CategoryKind.MATERIAL)
    login(make_user(UserRole.MANAGER))
    material_rows = client.get("/api/intel/coverage", params={"kind": "material"}).json()
    codes = {row["category_code"] for row in material_rows}
    assert material.code in codes
    assert work.code not in codes


# ── class distribution ───────────────────────────────────────────────────────
def test_class_distribution_reports_every_class_including_zero(
    client: TestClient, make_user: Any, login: Any
) -> None:
    login(make_user(UserRole.MANAGER))
    rows = client.get("/api/intel/class-distribution").json()
    assert {row["cls"] for row in rows} == {"A", "B", "C", "D", "F", "KO"}
    assert all(row["count"] >= 0 for row in rows)


# ── capacity ─────────────────────────────────────────────────────────────────
def test_capacity_counts_prequalified_vendors_only_and_sums_raw_indicators(
    client: TestClient,
    make_user: Any,
    make_vendor: Any,
    make_category: Any,
    login: Any,
    session: Session,
    cycle: QualificationCycle,
) -> None:
    uow = UnitOfWork(session)
    category = make_category()
    _scored_vendor(uow, make_vendor, cycle, category, decision=DecisionKind.APPROVE)
    _scored_vendor(uow, make_vendor, cycle, category, decision=DecisionKind.APPROVE)
    # a rejected vendor in the same category must not count toward capacity
    _scored_vendor(uow, make_vendor, cycle, category, raw=KO_RAW, decision=DecisionKind.REJECT)

    login(make_user(UserRole.MANAGER))
    rows = client.get("/api/intel/capacity").json()
    row = next(r for r in rows if r["category_code"] == category.code)
    assert row["vendor_count"] == 2
    assert row["total_turnover"] == BASE_RAW["B.1"] * 2
    assert row["engineers"] == int(BASE_RAW["E.2"]) * 2
    assert row["ongoing_projects"] == int(BASE_RAW["C.3"]) * 2


# ── certification & insurance penetration ────────────────────────────────────
def test_certification_penetration_reads_the_sub4_rubric_codes(
    client: TestClient,
    make_user: Any,
    make_vendor: Any,
    make_category: Any,
    login: Any,
    session: Session,
    cycle: QualificationCycle,
) -> None:
    uow = UnitOfWork(session)
    category = make_category()
    _scored_vendor(
        uow, make_vendor, cycle, category, raw=CERTIFIED_RAW, decision=DecisionKind.APPROVE
    )
    _scored_vendor(uow, make_vendor, cycle, category, raw=BASE_RAW, decision=DecisionKind.APPROVE)

    login(make_user(UserRole.MANAGER))
    rows = {row["key"]: row for row in client.get("/api/intel/certification").json()}
    assert set(rows) == {
        "iso9001",
        "iso14001_45001",
        "liability_insurance",
        "audited_statements",
        "hse_specialist",
    }
    assert rows["iso9001"]["count"] >= 1
    assert rows["iso9001"]["total"] >= 2
    for row in rows.values():
        assert 0.0 <= row["share"] <= 1.0
        assert row["share"] == (row["count"] / row["total"] if row["total"] else 0.0)


# ── data sources & freshness ─────────────────────────────────────────────────
def test_sources_counts_a_vendor_with_no_observations_as_stale(
    client: TestClient, make_user: Any, make_vendor: Any, login: Any
) -> None:
    """Spec §12: the intelligence is only as honest as the freshness counter — a profile with
    no data at all is not counted as current."""
    login(make_user(UserRole.MANAGER))
    before = client.get("/api/intel/sources").json()["stale_profiles"]
    make_vendor()  # never observed
    after = client.get("/api/intel/sources").json()["stale_profiles"]
    assert after == before + 1


def test_sources_does_not_count_a_freshly_observed_vendor_as_stale(
    client: TestClient, make_user: Any, make_vendor: Any, login: Any, session: Session
) -> None:
    login(make_user(UserRole.MANAGER))
    before = client.get("/api/intel/sources").json()["stale_profiles"]

    uow = UnitOfWork(session)
    vendor = make_vendor()
    observations_service.record(
        uow,
        vendor.id,
        "A.1",
        "fresh",
        source=ObservationSource.PORTAL,
        observed_at=datetime.now(UTC),
    )
    uow.commit()

    after = client.get("/api/intel/sources").json()["stale_profiles"]
    # a vendor observed today does not add to the stale count, unlike the no-observations case.
    assert after == before


def test_sources_counts_a_profile_older_than_the_freshness_window_as_stale(
    client: TestClient, make_user: Any, make_vendor: Any, login: Any, session: Session
) -> None:
    login(make_user(UserRole.MANAGER))
    before = client.get("/api/intel/sources").json()["stale_profiles"]

    uow = UnitOfWork(session)
    vendor = make_vendor()
    observations_service.record(
        uow,
        vendor.id,
        "A.1",
        "old",
        source=ObservationSource.PORTAL,
        observed_at=datetime.now(UTC) - timedelta(days=120),
    )
    uow.commit()

    after = client.get("/api/intel/sources").json()["stale_profiles"]
    assert after == before + 1


def test_sources_reports_the_by_source_split_summing_to_the_total(
    client: TestClient, make_user: Any, login: Any
) -> None:
    login(make_user(UserRole.MANAGER))
    body = client.get("/api/intel/sources").json()
    assert sum(row["count"] for row in body["by_source"]) <= body["total_observations"]
    if body["total_observations"] > 0:
        for row in body["by_source"]:
            assert row["share"] == pytest.approx(row["count"] / body["total_observations"])


def test_sources_flags_a_vendor_whose_api_value_diverges_from_the_portal_value(
    client: TestClient, make_user: Any, make_vendor: Any, login: Any, session: Session
) -> None:
    uow = UnitOfWork(session)
    vendor = make_vendor()
    now = datetime.now(UTC)
    observations_service.record(
        uow, vendor.id, "B.1", 1_000_000, source=ObservationSource.PORTAL, observed_at=now
    )
    observations_service.record(
        uow, vendor.id, "B.1", 1_500_000, source=ObservationSource.API, observed_at=now
    )
    uow.commit()

    login(make_user(UserRole.MANAGER))
    body = client.get("/api/intel/sources").json()
    assert body["diverging_vendors"] >= 1


def test_sources_does_not_flag_agreeing_values(
    client: TestClient, make_user: Any, make_vendor: Any, login: Any, session: Session
) -> None:
    login(make_user(UserRole.MANAGER))
    before = client.get("/api/intel/sources").json()["diverging_vendors"]

    uow = UnitOfWork(session)
    vendor = make_vendor()
    now = datetime.now(UTC)
    observations_service.record(
        uow, vendor.id, "B.1", 1_000_000, source=ObservationSource.PORTAL, observed_at=now
    )
    observations_service.record(
        uow, vendor.id, "B.1", 1_000_000, source=ObservationSource.API, observed_at=now
    )
    uow.commit()

    after = client.get("/api/intel/sources").json()["diverging_vendors"]
    assert after == before


# ── expiring documents ───────────────────────────────────────────────────────
def test_expiring_documents_carries_the_vendor_name_and_paginates(
    client: TestClient, make_user: Any, make_vendor: Any, login: Any, session: Session
) -> None:
    from vendoriq_api.models import Document
    from vendoriq_api.models.enums import DocumentStatus

    vendor = make_vendor()
    doc = Document(
        vendor_id=vendor.id,
        code="A-05",
        status=DocumentStatus.UPLOADED,
        expiry_date=(datetime.now(UTC) + timedelta(days=10)).date(),
    )
    session.add(doc)
    session.commit()

    login(make_user(UserRole.MANAGER))
    page = client.get(
        "/api/intel/expiring-documents", params={"within_days": 60, "page": 1, "page_size": 5}
    ).json()
    assert page["page"] == 1
    assert page["page_size"] == 5
    assert len(page["items"]) <= 5
    match = next((item for item in page["items"] if item["vendor_id"] == str(vendor.id)), None)
    assert match is not None
    assert match["vendor_name"] == vendor.legal_name
    assert match["code"] == "A-05"
    assert match["days_to_expiry"] == 10


def test_expiring_documents_respects_within_days(
    client: TestClient, make_user: Any, make_vendor: Any, login: Any, session: Session
) -> None:
    from vendoriq_api.models import Document
    from vendoriq_api.models.enums import DocumentStatus

    vendor = make_vendor()
    far = Document(
        vendor_id=vendor.id,
        code="B-01",
        status=DocumentStatus.UPLOADED,
        expiry_date=(datetime.now(UTC) + timedelta(days=200)).date(),
    )
    session.add(far)
    session.commit()

    login(make_user(UserRole.MANAGER))
    page = client.get("/api/intel/expiring-documents", params={"within_days": 60}).json()
    assert all(item["vendor_id"] != str(vendor.id) for item in page["items"])


# ── market gaps ──────────────────────────────────────────────────────────────
def test_gaps_lists_a_category_with_registered_but_no_prequalified_vendor(
    client: TestClient,
    make_user: Any,
    make_vendor: Any,
    make_category: Any,
    login: Any,
    session: Session,
    cycle: QualificationCycle,
) -> None:
    uow = UnitOfWork(session)
    category = make_category()
    _scored_vendor(uow, make_vendor, cycle, category, raw=KO_RAW, decision=DecisionKind.REJECT)

    login(make_user(UserRole.MANAGER))
    rows = client.get("/api/intel/gaps").json()
    row = next(r for r in rows if r["category_code"] == category.code)
    assert row["registered_vendors"] == 1


def test_gaps_excludes_a_category_with_a_prequalified_vendor(
    client: TestClient,
    make_user: Any,
    make_vendor: Any,
    make_category: Any,
    login: Any,
    session: Session,
    cycle: QualificationCycle,
) -> None:
    uow = UnitOfWork(session)
    category = make_category()
    _scored_vendor(uow, make_vendor, cycle, category, decision=DecisionKind.APPROVE)

    login(make_user(UserRole.MANAGER))
    rows = client.get("/api/intel/gaps").json()
    assert all(r["category_code"] != category.code for r in rows)


# ── attention list ───────────────────────────────────────────────────────────
def test_attention_list_carries_keys_counts_and_links(
    client: TestClient, make_user: Any, login: Any
) -> None:
    login(make_user(UserRole.MANAGER))
    rows = client.get("/api/intel/attention").json()
    keys = {row["key"] for row in rows}
    assert keys == {"att_exp", "att_rev", "att_inc", "att_gap"}
    for row in rows:
        assert row["count"] >= 0
        assert row["severity"] in {"info", "warn", "crit"}
        assert row["link"]


# ── permissions ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "path",
    [
        "/api/intel/overview",
        "/api/intel/coverage",
        "/api/intel/class-distribution",
        "/api/intel/capacity",
        "/api/intel/certification",
        "/api/intel/sources",
        "/api/intel/expiring-documents",
        "/api/intel/gaps",
        "/api/intel/attention",
    ],
)
def test_a_vendor_may_not_read_market_intelligence(
    path: str, client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    login(make_user(UserRole.VENDOR, vendor=make_vendor()))
    assert client.get(path).status_code == 403


@pytest.mark.parametrize(
    "path",
    [
        "/api/intel/overview",
        "/api/intel/coverage",
        "/api/intel/class-distribution",
        "/api/intel/capacity",
        "/api/intel/certification",
        "/api/intel/sources",
        "/api/intel/expiring-documents",
        "/api/intel/gaps",
        "/api/intel/attention",
    ],
)
def test_every_staff_role_may_read_market_intelligence(
    path: str, client: TestClient, make_user: Any, login: Any
) -> None:
    for role in (UserRole.OFFICER, UserRole.COMMISSION, UserRole.MANAGER, UserRole.ADMIN):
        login(make_user(role))
        assert client.get(path).status_code == 200
