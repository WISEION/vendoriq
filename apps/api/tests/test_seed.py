"""The seed CLI (phase 1E, brief §2, §1.10; seed/README.md).

Exercises the loader functions directly against the per-test transaction the ``session``
fixture gives every test (see ``conftest.py``): each test starts from an empty, migrated
database and nothing it does can leak into another test. The CLI's argument parsing and
its own transaction handling are covered separately by manual runs against a live database
(see the final report) — `session_scope` opens a process-wide engine that would not honour
this file's isolation.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from vendoriq_api.config import Settings
from vendoriq_api.db import UnitOfWork
from vendoriq_api.models import (
    Application,
    Category,
    Contact,
    Document,
    FieldObservation,
    Project,
    QualificationCycle,
    ScoringModel,
    User,
    Vendor,
    VendorCategory,
    WorkPackage,
)
from vendoriq_api.models.enums import ApplicationStatus, DecisionKind, VendorStatus
from vendoriq_api.seed import demo as demo_seed
from vendoriq_api.seed import purge as purge_seed
from vendoriq_api.seed import real as real_seed
from vendoriq_api.seed.common import PREQUALIFYING_CLASSES
from vendoriq_api.seed.data import load_seed_data
from vendoriq_api.seed.errors import SeedError
from vendoriq_api.services import observations as observations_service
from vendoriq_api.services.accounts import STAFF_ACCOUNTS, VENDOR_ACCOUNTS
from vendoriq_scoring import ScoreResult

#: The 13 real vendors' own expectation, straight from seed/data.json (the acceptance
#: fixture brief §1.10 and seed/README.md both point at).
_DATA = load_seed_data()
#: `sub-4` has 24 criteria, and the Rev4 workbook records a raw indicator for each. They are
#: stored as the application's `raw_snapshot` — *not* as vendor field observations, which are
#: the form's own namespace and mean something else under the same codes (ADR-021).
_RAW_INDICATORS_PER_VENDOR = 24
#: Answers in `seed/wesa_form.json` — Wesa's real application form, the only one there is.
_WESA_FORM_ANSWERS = len(
    json.loads(
        (Path(__file__).resolve().parents[3] / "seed" / "wesa_form.json").read_text(
            encoding="utf-8"
        )
    )["answers"]
)
_SUPPLIER_CRITERIA_COUNT = 23


def _count(session, model) -> int:  # type: ignore[no-untyped-def]
    return session.scalar(select(func.count()).select_from(model)) or 0


def _demo_count(session, model, *, is_demo: bool) -> int:  # type: ignore[no-untyped-def]
    return (
        session.scalar(select(func.count()).select_from(model).where(model.is_demo.is_(is_demo)))
        or 0
    )


# ── load --real ───────────────────────────────────────────────────────────────
def test_load_real_loads_every_documented_entity(uow: UnitOfWork, settings: Settings) -> None:
    summary = real_seed.load_real(uow, settings=settings)

    assert summary.vendors_created == 13
    assert summary.scoring_models_loaded == 2
    assert summary.categories_created == 15
    assert summary.project_created is True
    assert summary.cycle_created is True
    assert summary.applications_created == 13
    # Field observations are *form* answers, and Uni Ko had exactly one filled-in form:
    # Wesa's (ADR-023). The other twelve were scored from the Rev4 spreadsheet alone, so
    # their forms are genuinely empty. Their Rev4 indicators live on the applications
    # instead, asserted below.
    assert summary.observations_created == _WESA_FORM_ANSWERS

    session = uow.session
    # 13 real vendors, plus the one `vendor.new@vendoriq.test` placeholder that
    # `services.accounts.create_test_accounts` itself creates as `is_demo=True` — the seed
    # loads real data first, so that account has nothing real to attach to yet.
    assert _count(session, Vendor) == 14
    assert _demo_count(session, Vendor, is_demo=False) == 13
    assert _count(session, Category) == 15
    assert _count(session, ScoringModel) == 2
    assert _count(session, Application) == 13
    assert _count(session, FieldObservation) == _WESA_FORM_ANSWERS
    snapshots = [
        application.raw_snapshot
        for application in session.scalars(select(Application))
        if application.raw_snapshot is not None
    ]
    assert len(snapshots) == 13
    assert all(len(snapshot) == _RAW_INDICATORS_PER_VENDOR for snapshot in snapshots)


def test_the_thirteen_recomputed_totals_match_the_rev4_sheet(
    uow: UnitOfWork, settings: Settings
) -> None:
    """The acceptance fixture: seed/vendors_seed.json / data.json's sheetTotal, 13/13."""
    real_seed.load_real(uow, settings=settings)
    applications = uow.session.scalars(select(Application)).all()
    assert len(applications) == 13

    by_voen_or_name = {row["id"]: row for row in _DATA.vendors}
    seen = 0
    for application in applications:
        vendor = uow.session.get(Vendor, application.vendor_id)
        assert vendor is not None
        row = next(r for r in by_voen_or_name.values() if r["name"].strip() == vendor.legal_name)
        computed = application.computed or {}
        assert computed["total"] == row["sheetTotal"], vendor.legal_name
        prequalified = computed["cls"] in PREQUALIFYING_CLASSES
        expected_status = (
            ApplicationStatus.PREQUALIFIED if prequalified else ApplicationStatus.REJECTED
        )
        expected_decision = DecisionKind.APPROVE if prequalified else DecisionKind.REJECT
        assert application.status is expected_status
        assert application.decision is expected_decision
        assert vendor.status is (
            VendorStatus.PREQUALIFIED if prequalified else VendorStatus.REJECTED
        )
        seen += 1
    assert seen == 13


def test_a_wrong_total_is_refused_loudly(uow: UnitOfWork) -> None:
    """brief §1.10: a mismatch fails the load, it does not store a wrong number."""
    row = _DATA.vendors[0]
    wrong = replace(
        ScoreResult(per={}, groups={}, total=0.0, ko=True, cls="A"),
        total=row["sheetTotal"] + 1,
    )
    with pytest.raises(SeedError):
        real_seed._assert_matches_sheet(row, wrong)


def test_load_real_is_idempotent(uow: UnitOfWork, settings: Settings) -> None:
    real_seed.load_real(uow, settings=settings)
    session = uow.session
    before = {
        "vendor": _count(session, Vendor),
        "contact": _count(session, Contact),
        "observation": _count(session, FieldObservation),
        "application": _count(session, Application),
        "category": _count(session, Category),
        "project": _count(session, Project),
        "cycle": _count(session, QualificationCycle),
        "user": _count(session, User),
    }
    before_ids = {app.id for app in session.scalars(select(Application))}

    second = real_seed.load_real(uow, settings=settings)

    assert second.vendors_created == 0
    assert second.vendors_matched == 13
    assert second.categories_created == 0
    assert second.applications_created == 0
    assert second.applications_matched == 13
    assert second.observations_created == 0
    assert second.project_created is False
    assert second.cycle_created is False

    after = {
        "vendor": _count(session, Vendor),
        "contact": _count(session, Contact),
        "observation": _count(session, FieldObservation),
        "application": _count(session, Application),
        "category": _count(session, Category),
        "project": _count(session, Project),
        "cycle": _count(session, QualificationCycle),
        "user": _count(session, User),
    }
    assert after == before
    assert {app.id for app in session.scalars(select(Application))} == before_ids


def test_running_real_a_third_time_still_changes_nothing(
    uow: UnitOfWork, settings: Settings
) -> None:
    """Not just "twice" — the Makefile target is run every deploy."""
    real_seed.load_real(uow, settings=settings)
    real_seed.load_real(uow, settings=settings)
    session = uow.session
    before = (
        _count(session, Vendor),
        _count(session, FieldObservation),
        _count(session, Application),
    )
    real_seed.load_real(uow, settings=settings)
    after = (
        _count(session, Vendor),
        _count(session, FieldObservation),
        _count(session, Application),
    )
    assert before == after


def test_scoring_models_are_loaded_and_sub4_is_locked_once_used(
    uow: UnitOfWork, settings: Settings
) -> None:
    real_seed.load_real(uow, settings=settings)
    sub4 = uow.session.get(ScoringModel, "sub-4")
    sup1 = uow.session.get(ScoringModel, "sup-1")
    assert sub4 is not None and sup1 is not None
    assert len(sub4.criteria) == 24
    assert len(sup1.criteria) == _SUPPLIER_CRITERIA_COUNT
    # 13 real applications are scored with sub-4 (brief §1.10) -> spec §10.3 immutability.
    assert sub4.is_locked is True
    # sup-1 is not used by anything the seed loads -> still open for the model editor.
    assert sup1.is_locked is False


def test_test_accounts_are_created_only_in_auth_mode_test(
    uow: UnitOfWork, settings: Settings
) -> None:
    live_settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        app_env="development",
        auth_mode="live",
        database_url=settings.database_url,
        session_secret=settings.session_secret,
    )
    summary = real_seed.load_real(uow, settings=live_settings)
    assert summary.test_accounts == []
    assert uow.session.scalar(select(User).where(User.email == "admin@vendoriq.test")) is None

    summary = real_seed.load_real(uow, settings=settings)
    # A silent six would mean one documented account cannot log in — assert the count, not
    # just the set (the account-cascade defect this pins started as exactly that).
    assert len(summary.test_accounts) == 7
    assert {user.email for user, _ in summary.test_accounts} == {
        "admin@vendoriq.test",
        "manager@vendoriq.test",
        "commission@vendoriq.test",
        "officer@vendoriq.test",
        "habib.atakisiyev@wesa.az",
        "a.tabit@shield.az",
        "vendor.new@vendoriq.test",
    }


def test_vendor_test_accounts_link_to_the_real_vendors(uow: UnitOfWork, settings: Settings) -> None:
    real_seed.load_real(uow, settings=settings)
    wesa_user = uow.session.scalar(select(User).where(User.email == "habib.atakisiyev@wesa.az"))
    shield_user = uow.session.scalar(select(User).where(User.email == "a.tabit@shield.az"))
    assert wesa_user is not None and wesa_user.vendor_id is not None
    assert shield_user is not None and shield_user.vendor_id is not None
    wesa = uow.session.get(Vendor, wesa_user.vendor_id)
    shield = uow.session.get(Vendor, shield_user.vendor_id)
    assert wesa is not None and wesa.voen == "1003915341" and wesa.is_demo is False
    assert shield is not None and shield.voen == "2002138471" and shield.is_demo is False


# ── load --demo ─────────────────────────────────────────────────────────────
def test_load_demo_requires_real_data_first(uow: UnitOfWork) -> None:
    with pytest.raises(SeedError):
        demo_seed.load_demo(uow)


def test_load_demo_adds_only_is_demo_rows(uow: UnitOfWork, settings: Settings) -> None:
    real_seed.load_real(uow, settings=settings)
    summary = demo_seed.load_demo(uow)

    session = uow.session
    assert summary.suppliers_created == 4
    assert summary.projects_created == 1
    assert summary.work_packages_created == 12
    assert summary.documents_created == 18
    # As for the real vendors: criterion-coded indicators are the application's snapshot.
    assert summary.supplier_observations_created == 0

    demo_vendors = session.scalars(select(Vendor).where(Vendor.is_demo.is_(True))).all()
    # 4 demo suppliers + the one placeholder `vendor.new` account creates (accounts.py).
    assert len(demo_vendors) == 5
    assert all(v.is_demo for v in demo_vendors)

    assert _count(session, WorkPackage) == 12
    assert all(wp.is_demo for wp in session.scalars(select(WorkPackage)))
    assert _count(session, Document) == 18
    assert all(d.is_demo for d in session.scalars(select(Document)))
    assert (
        session.scalar(
            select(func.count()).select_from(VendorCategory).where(VendorCategory.is_demo.is_(True))
        )
        == 29
    )

    # The real project (TQS-238) itself stays real; only its packages are demo.
    real_project = session.scalar(select(Project).where(Project.code == "TQS-238"))
    assert real_project is not None and real_project.is_demo is False
    demo_project = session.scalar(select(Project).where(Project.code == "TQS-301"))
    assert demo_project is not None and demo_project.is_demo is True

    # The 13 real vendors themselves are untouched by the demo load.
    assert _count(session, Vendor) - len(demo_vendors) == 13


def test_load_demo_is_idempotent(uow: UnitOfWork, settings: Settings) -> None:
    real_seed.load_real(uow, settings=settings)
    demo_seed.load_demo(uow)
    session = uow.session
    before = {
        "vendor": _count(session, Vendor),
        "vendor_category": _count(session, VendorCategory),
        "document": _count(session, Document),
        "work_package": _count(session, WorkPackage),
        "project": _count(session, Project),
        "application": _count(session, Application),
        "cycle": _count(session, QualificationCycle),
    }
    confirmed_before = {vc.id: vc.confirmed for vc in session.scalars(select(VendorCategory))}

    second = demo_seed.load_demo(uow)

    assert second.suppliers_created == 0
    assert second.projects_created == 0
    assert second.work_packages_created == 0
    assert second.documents_created == 0
    assert second.category_assignments_created == 0
    assert second.supplier_applications_created == 0
    assert second.supplier_applications_matched == 4
    assert second.supplier_cycle_created is False
    after = {
        "vendor": _count(session, Vendor),
        "vendor_category": _count(session, VendorCategory),
        "document": _count(session, Document),
        "work_package": _count(session, WorkPackage),
        "project": _count(session, Project),
        "application": _count(session, Application),
        "cycle": _count(session, QualificationCycle),
    }
    assert after == before
    confirmed_after = {vc.id: vc.confirmed for vc in session.scalars(select(VendorCategory))}
    assert confirmed_after == confirmed_before
    assert all(confirmed_after.values())


# ── purge-demo ───────────────────────────────────────────────────────────────
def test_purge_demo_leaves_exactly_the_real_state(uow: UnitOfWork, settings: Settings) -> None:
    """seed real -> seed demo -> purge-demo == seed real alone (the acceptance property).

    Holds without exception, including on ``vendor`` and ``app_user``: purging the demo
    layer must never take a login with it (Gate 1, ``seed/purge.py``'s "the one exception"
    paragraph), so the ``vendor.new@vendoriq.test`` placeholder — itself `is_demo=True`,
    with no real vendor behind it — survives the purge along with the six other accounts.
    """
    session = uow.session
    real_seed.load_real(uow, settings=settings)

    real_only = {
        "vendor": _count(session, Vendor),
        "contact": _count(session, Contact),
        "application": _count(session, Application),
        "observation": _count(session, FieldObservation),
        "category": _count(session, Category),
        "project": _count(session, Project),
        "cycle": _count(session, QualificationCycle),
        "user": _count(session, User),
    }
    vendor_ids = {v.id for v in session.scalars(select(Vendor))}
    user_emails = {u.email for u in session.scalars(select(User))}

    demo_seed.load_demo(uow)
    assert _count(session, Vendor) > real_only["vendor"]  # the demo layer really landed

    purge_seed.purge_demo(uow)

    after_purge = {
        "vendor": _count(session, Vendor),
        "contact": _count(session, Contact),
        "application": _count(session, Application),
        "observation": _count(session, FieldObservation),
        "category": _count(session, Category),
        "project": _count(session, Project),
        "cycle": _count(session, QualificationCycle),
        "user": _count(session, User),
    }
    assert after_purge == real_only
    assert {v.id for v in session.scalars(select(Vendor))} == vendor_ids
    assert {u.email for u in session.scalars(select(User))} == user_emails
    assert _count(session, VendorCategory) == 0
    assert _count(session, Document) == 0
    assert _count(session, WorkPackage) == 0


def test_purge_demo_leaves_real_vendors_referentially_valid(
    uow: UnitOfWork, settings: Settings
) -> None:
    session = uow.session
    real_seed.load_real(uow, settings=settings)
    demo_seed.load_demo(uow)
    purge_seed.purge_demo(uow)

    for application in session.scalars(select(Application)):
        assert session.get(Vendor, application.vendor_id) is not None
        assert session.get(QualificationCycle, application.cycle_id) is not None
    for observation in session.scalars(select(FieldObservation)):
        assert session.get(Vendor, observation.vendor_id) is not None
    wesa = session.scalar(select(Vendor).where(Vendor.voen == "1003915341"))
    assert wesa is not None
    assert any(c.vendor_id == wesa.id for c in session.scalars(select(Contact)))


def test_purge_demo_is_idempotent(uow: UnitOfWork, settings: Settings) -> None:
    real_seed.load_real(uow, settings=settings)
    demo_seed.load_demo(uow)
    purge_seed.purge_demo(uow)
    session = uow.session
    before = _count(session, Vendor), _count(session, Application)

    second = purge_seed.purge_demo(uow)

    assert second.total == 0
    assert (_count(session, Vendor), _count(session, Application)) == before


def test_purge_demo_without_a_demo_load_removes_nothing(
    uow: UnitOfWork, settings: Settings
) -> None:
    """`load --real` (AUTH_MODE=test) creates one is_demo=True row of its own — the
    `vendor.new` placeholder — but it is a live account's vendor, so purge-demo leaves it."""
    real_seed.load_real(uow, settings=settings)
    summary = purge_seed.purge_demo(uow)
    assert summary.total == 0
    assert _count(uow.session, Vendor) == 14
    assert _count(uow.session, User) == 7


def test_purge_demo_protects_the_vendor_behind_a_login(uow: UnitOfWork, settings: Settings) -> None:
    """The mechanism directly: a demo vendor with no ``app_user`` pointing at it is removed;
    one a live account still uses is not, even though both are ``is_demo=True``."""
    real_seed.load_real(uow, settings=settings)
    demo_seed.load_demo(uow)
    session = uow.session

    placeholder = session.scalar(select(User).where(User.email == "vendor.new@vendoriq.test"))
    assert placeholder is not None and placeholder.vendor_id is not None
    orphan_demo_vendor = session.scalar(
        select(Vendor).where(Vendor.is_demo.is_(True), Vendor.id != placeholder.vendor_id)
    )
    assert orphan_demo_vendor is not None  # one of the 4 demo suppliers

    purge_seed.purge_demo(uow)

    assert session.get(Vendor, placeholder.vendor_id) is not None
    assert session.get(User, placeholder.id) is not None
    assert session.get(Vendor, orphan_demo_vendor.id) is None


def test_all_seven_test_accounts_still_authenticate_after_a_full_seed_and_purge_cycle(
    uow: UnitOfWork, settings: Settings, client: TestClient
) -> None:
    """The Gate 1 criterion, pinned as a test rather than a manual check: `load --real` ->
    `load --demo` -> `purge-demo` and every account in docs/TEST_ACCOUNTS.md still logs in.
    """
    real_seed.load_real(uow, settings=settings)
    demo_seed.load_demo(uow)
    purge_seed.purge_demo(uow)
    uow.commit()

    assert len(STAFF_ACCOUNTS) == 4
    assert len(VENDOR_ACCOUNTS) == 3
    for account in STAFF_ACCOUNTS:
        first = client.post(
            "/api/auth/staff/login",
            json={"email": account.email, "password": account.password},
        )
        assert first.status_code == 200, (account.email, first.text)
        second = client.post(
            "/api/auth/staff/totp/verify",
            json={"challenge_id": first.json()["challenge_id"], "code": "000000"},
        )
        assert second.status_code == 200, (account.email, second.text)
        assert second.json()["user"]["email"] == account.email
        client.post("/api/auth/logout")
        client.cookies.clear()

    for account in VENDOR_ACCOUNTS:
        response = client.post(
            "/api/auth/otp/verify", json={"email": account.email, "code": "000000"}
        )
        assert response.status_code == 200, (account.email, response.text)
        assert response.json()["user"]["email"] == account.email
        client.post("/api/auth/logout")
        client.cookies.clear()


# ── real vs. demo classification (brief §1.10) ──────────────────────────────
def test_category_taxonomy_is_real_but_assignments_are_demo(
    uow: UnitOfWork, settings: Settings
) -> None:
    real_seed.load_real(uow, settings=settings)
    session = uow.session
    assert all(c.is_demo is False for c in session.scalars(select(Category)))
    assert _count(session, VendorCategory) == 0  # nothing yet — that is the demo layer

    demo_seed.load_demo(uow)
    assert _count(session, VendorCategory) > 0
    assert all(vc.is_demo for vc in session.scalars(select(VendorCategory)))


def test_wesa_and_shield_carry_the_fullest_real_records(
    uow: UnitOfWork, settings: Settings
) -> None:
    """brief §1.10: "the WESA detail (the fullest vendor record)"."""
    real_seed.load_real(uow, settings=settings)
    session = uow.session
    wesa = session.scalar(select(Vendor).where(Vendor.voen == "1003915341"))
    assert wesa is not None
    application = session.scalar(select(Application).where(Application.vendor_id == wesa.id))
    assert application is not None
    assert (application.computed or {}).get("cls") == "A"

    # "The fullest vendor record" is the Rev4 outcome, and it lives on the application: all
    # 24 raw indicators, frozen at the decision. Wesa's real turnover and headcount are in
    # there and are what every screen reads.
    snapshot = application.raw_snapshot or {}
    assert len(snapshot) == _RAW_INDICATORS_PER_VENDOR
    assert snapshot["B.1"] == 5189111  # avg annual turnover (3y), from the workbook
    assert snapshot["E.1"] == 80  # permanent staff

    # The form answers are a *separate* record in a separate namespace, and Wesa is the one
    # vendor with both. `A.1` in the profile is the company's name; `A.1` in the snapshot is
    # its construction-licence score. Writing one into the other made the portal show Wesa's
    # legal name as `3` (ADR-021); having both, correctly, is what lets them be compared at
    # all (`test_seed_form.py`).
    profile = observations_service.current_profile(session, wesa.id)
    assert len(profile) == _WESA_FORM_ANSWERS
    assert profile["A.1"] == "VVESA MMC"
    assert snapshot["A.1"] == 3

    # Shield was scored from the spreadsheet alone, so its form is empty and stays empty.
    shield = session.scalar(select(Vendor).where(Vendor.legal_name.ilike("%shield%")))
    assert shield is not None
    assert observations_service.current_profile(session, shield.id) == {}


def test_vendors_with_no_submission_still_score_one_via_c3_not_a2(
    uow: UnitOfWork, settings: Settings
) -> None:
    """seed/README.md's corrected explanation: C.3's 25% ongoing-projects floor, not A.2.

    A.2 is a `bands` criterion whose `zero` value is 0 (packages/scoring/models/sub-4.json)
    — it contributes nothing when a vendor submitted nothing. C.3 is `ongoing`, and
    `ongoing` scores 25% of its max even at zero (packages/scoring/engine.py's own
    docstring says as much). That is where V02/V03/V04/V12's 1.0 comes from.
    """
    real_seed.load_real(uow, settings=settings)
    session = uow.session
    empty_ids = {"V02", "V03", "V04", "V12"}
    empty_names = {row["name"].strip() for row in _DATA.vendors if row["id"] in empty_ids}
    for name in empty_names:
        vendor = session.scalar(select(Vendor).where(Vendor.legal_name == name))
        assert vendor is not None
        application = session.scalar(select(Application).where(Application.vendor_id == vendor.id))
        assert application is not None
        computed = application.computed or {}
        assert computed["total"] == 1.0
        assert computed["cls"] == "KO"
        assert computed["per"]["A.2"] == 0.0
        assert computed["per"]["C.3"] == 1.0


# ── the demo layer actually demonstrates something (2C's defect, ADR-018) ──────
def test_demo_category_assignments_are_confirmed(uow: UnitOfWork, settings: Settings) -> None:
    """A vendor is a matching candidate only once its category is *confirmed* (spec §11.1).

    The real/import path's default stays `False` (`common.ensure_category_assignments`,
    unchanged) — this asserts the demo layer's own deliberate override, not a relaxation of
    that default.
    """
    real_seed.load_real(uow, settings=settings)
    demo_seed.load_demo(uow)
    session = uow.session
    rows = list(session.scalars(select(VendorCategory)))
    assert len(rows) == 29
    assert all(row.is_demo for row in rows)
    assert all(row.confirmed for row in rows)


def test_demo_suppliers_earn_their_status_against_sup1(uow: UnitOfWork, settings: Settings) -> None:
    """seed/README.md's table: S01/S02 prequalified, S03/S04 rejected — computed, not read
    off a (now-deleted) ``data.json`` claim."""
    real_seed.load_real(uow, settings=settings)
    summary = demo_seed.load_demo(uow)
    session = uow.session

    assert summary.supplier_applications_created == 4
    assert summary.suppliers_prequalified == 2
    assert summary.suppliers_rejected == 2

    expected = {
        "Caspian Steel Supply (demo)": ("A", "prequalified", 90.3),
        "Baku Beton (demo)": ("A", "prequalified", 94.7),
        "AzGlass Systems (demo)": ("D", "rejected", 64.8),
        "Nur Elektrik Tədarük (demo)": ("KO", "rejected", 55.3),
    }
    for name, (cls, status, total) in expected.items():
        supplier = session.scalar(select(Vendor).where(Vendor.legal_name == name))
        assert supplier is not None, name
        assert supplier.status.value == status, name
        application = session.scalar(
            select(Application).where(Application.vendor_id == supplier.id)
        )
        assert application is not None, name
        computed = application.computed or {}
        assert computed.get("cls") == cls, name
        assert computed.get("total") == total, name
        assert application.decided_at is not None, name
        assert application.is_demo is True, name

    # One shared cycle, scored against sup-1 — not the subcontractors' TQS2026006/sub-4 one.
    cycle = session.scalar(
        select(QualificationCycle).where(
            QualificationCycle.name == "Demo supplier qualification (sup-1)"
        )
    )
    assert cycle is not None
    assert cycle.scoring_model_version == "sup-1"
    assert cycle.is_demo is True


def test_tqs_238_matches_at_96_percent_with_flooring_as_the_only_gap(
    uow: UnitOfWork, settings: Settings
) -> None:
    """The end-to-end claim task 2C measures through its endpoints, asserted here against
    the database `make seed && make seed-demo` actually builds (brief §11.2's 96%).

    Not a `packages/scoring` engine test (that is `test_matching.py`'s job, unchanged) —
    this is the seed producing data the *real* candidate-assembly path
    (`services.matching.build_candidates`) can find, which is exactly what was missing.
    """
    from vendoriq_api.services import matching  # local: services/ is not this task's to own

    real_seed.load_real(uow, settings=settings)
    demo_seed.load_demo(uow)
    session = uow.session

    project = session.scalar(select(Project).where(Project.code == "TQS-238"))
    assert project is not None
    category_by_package: dict[str, str] = {}
    for wp in session.scalars(select(WorkPackage).where(WorkPackage.project_id == project.id)):
        category = session.get(Category, wp.category_id)
        assert category is not None
        category_by_package[str(wp.id)] = category.code

    params = matching.resolve_params(session, None)
    result = matching.run(session, project, params)

    assert result.coverage_pct == 96
    assert result.state == "nogo"  # any NO-GO package makes the project NO-GO (brief §1.7)

    by_category = {category_by_package[pkg.package_id]: pkg for pkg in result.packages}
    assert by_category["flooring"].state == "nogo"
    assert by_category["flooring"].gap == "no_prequalified_vendor"
    for code, pkg in by_category.items():
        if code != "flooring":
            assert pkg.state != "nogo", (code, pkg.gap)
