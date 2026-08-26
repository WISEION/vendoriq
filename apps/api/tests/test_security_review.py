"""Phase 3B adversarial review: authorisation, data integrity, credentials, i18n.

This file is a *review*, not a feature suite. Two kinds of test live here and they read
differently on purpose:

* **Plain tests** are the attacks that bounced. They are the part that makes the review
  checkable — "a vendor cannot read another vendor's evaluation" is only worth writing down
  if the attempt is in the repository and runs on every push.
* **`xfail(strict=True)` tests** are the attacks that landed. Each one is a demonstration of
  a defect that exists in the code as reviewed; the `reason` names it. Nothing here is
  fixed — deciding what to fix is the orchestrator's call (brief §4.2, task 3B), and a
  strict xfail turns green the moment somebody does fix it, which is exactly the signal
  wanted.

Findings are listed, ranked and explained in ``docs/security-review.md``.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from vendoriq_api.config import Settings
from vendoriq_api.db import UnitOfWork
from vendoriq_api.models import Application, AuditEvent, OtpCode, QualificationCycle, Vendor
from vendoriq_api.models import ScoringModel as ScoringModelRow
from vendoriq_api.models.enums import (
    ApplicationStatus,
    CycleKind,
    CycleStatus,
    ObservationSource,
    ScoringModelStatus,
    UserRole,
    VendorType,
)
from vendoriq_api.openapi import load_contract
from vendoriq_api.services import applications as applications_service
from vendoriq_api.services import observations as observations_service
from vendoriq_api.storage.base import ObjectNotFoundError
from vendoriq_scoring import load_model

REPO_ROOT = Path(__file__).resolve().parents[3]
I18N_DIR = REPO_ROOT / "apps" / "web" / "src" / "i18n"

#: Rev4 raw indicators that score 100.0 / class A with the knock-outs clean.
GOOD_RAW: dict[str, float] = {
    "A.1": 3,
    "A.2": 10,
    "A.3": 3,
    "A.4": 3,
    "B.1": 20_000_000,
    "B.2": 5_000_000,
    "B.3": 3,
    "B.4": 3,
    "C.1": 15,
    "C.2": 8_000_000,
    "C.3": 5,
    "C.4": 3,
    "D.1": 3,
    "D.2": 3,
    "D.3": 3,
    "E.1": 150,
    "E.2": 20,
    "E.3": 3,
    "E.4": 3,
    "F.1": 3,
    "F.2": 3,
    "F.3": 3,
    "G.1": 3,
    "G.2": 10,
}
#: Everything at the floor except the three knock-outs: total 5.7, class F, KO clean.
LOW_RAW: dict[str, float] = {code: (1 if code in ("A.1", "A.4", "F.1") else 0) for code in GOOD_RAW}


# ── fixtures ─────────────────────────────────────────────────────────────────
@pytest.fixture
def model_version(session: Session) -> str:
    """A private copy of the real Rev4 definition, so no test here touches seeded rows."""
    document = load_model("sub-4")
    version = f"sub-3b-{uuid.uuid4().hex[:8]}"
    session.add(
        ScoringModelRow(
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
        )
    )
    session.commit()
    return version


@pytest.fixture
def cycle(session: Session, model_version: str) -> QualificationCycle:
    row = QualificationCycle(
        name=f"3B review cycle {uuid.uuid4().hex[:6]}",
        kind=CycleKind.TENDER,
        scoring_model_version=model_version,
        status=CycleStatus.OPEN,
        opens_at=datetime.now(UTC),
    )
    session.add(row)
    session.commit()
    return row


def _application(
    uow: UnitOfWork,
    vendor: Vendor,
    cycle: QualificationCycle,
    *,
    raw: dict[str, float] | None = None,
    stop_at: ApplicationStatus = ApplicationStatus.UNDER_REVIEW,
) -> Application:
    """Walk an application to ``stop_at`` the way the state machine allows."""
    application = applications_service.invite(uow, vendor, cycle_id=cycle.id)
    for step in (
        ApplicationStatus.IN_PROGRESS,
        ApplicationStatus.SUBMITTED,
        ApplicationStatus.UNDER_REVIEW,
    ):
        applications_service.transition(uow, application, step, role=UserRole.OFFICER)
        if step is stop_at:
            break
    if raw is not None:
        application.raw_snapshot = dict(raw)
    uow.commit()
    return application


def _dictionary(language: str) -> dict[str, str]:
    """The shared dictionary folded over with every per-feature one, as ``i18n/index.ts`` does."""
    merged: dict[str, str] = json.loads((I18N_DIR / f"{language}.json").read_text(encoding="utf-8"))
    for feature in sorted((I18N_DIR / "features").glob(f"*.{language}.json")):
        merged.update(json.loads(feature.read_text(encoding="utf-8")))
    return merged


# ═════════════════════════════════════════════════════════════════════════════
# 1. Authorisation — per vendor
# ═════════════════════════════════════════════════════════════════════════════
def test_a_vendor_cannot_reach_another_vendors_records_by_guessing_the_id(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    uow: UnitOfWork,
    cycle: QualificationCycle,
) -> None:
    """Every vendor-scoped path, walked with the *other* vendor's id. All must 404.

    404 rather than 403 is the contract's own choice (``security/deps.scope_to_vendor``):
    existence is information, and a 403 would turn the register into a VÖEN oracle.
    """
    victim = make_vendor()
    attacker = make_vendor()
    victim_application = _application(uow, victim, cycle, raw=GOOD_RAW)
    login(make_user(UserRole.VENDOR, vendor=attacker))

    reads = [
        f"/api/vendors/{victim.id}",
        f"/api/vendors/{victim.id}/categories",
        f"/api/vendors/{victim.id}/contacts",
        f"/api/vendors/{victim.id}/observations",
        f"/api/vendors/{victim.id}/documents",
        f"/api/applications/{victim_application.id}",
    ]
    for path in reads:
        assert client.get(path).status_code == 404, f"{path} leaked to another vendor"

    assert client.patch(f"/api/vendors/{victim.id}", json={"legal_name": "x"}).status_code == 404
    assert (
        client.patch(
            f"/api/applications/{victim_application.id}/answers", json={"answers": {"B.2": 1}}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/applications/{victim_application.id}/submit",
            json={"signatory_name": "x", "signatory_position": "y", "agreed": True},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/vendors/{victim.id}/documents/upload-init",
            json={
                "code": "A-01",
                "filename": "a.pdf",
                "content_type": "application/pdf",
                "size": 10,
            },
        ).status_code
        == 404
    )


def test_a_vendor_listing_never_returns_another_vendors_rows(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    uow: UnitOfWork,
    cycle: QualificationCycle,
) -> None:
    """The register and the application queue are shared endpoints; they must narrow, not filter
    in the browser — including when the caller supplies somebody else's ``vendor_id``."""
    victim = make_vendor()
    attacker = make_vendor()
    _application(uow, victim, cycle, raw=GOOD_RAW)
    _application(uow, attacker, cycle, raw=LOW_RAW)
    login(make_user(UserRole.VENDOR, vendor=attacker))

    vendors = client.get("/api/vendors?page_size=200").json()
    assert [row["id"] for row in vendors["items"]] == [str(attacker.id)]

    applications = client.get(f"/api/applications?vendor_id={victim.id}&page_size=200").json()
    assert {row["vendor_id"] for row in applications["items"]} == {str(attacker.id)}


def test_a_vendor_cannot_read_its_own_score_before_the_decision(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    uow: UnitOfWork,
    cycle: QualificationCycle,
) -> None:
    """Spec §7: the breakdown is released only after the commission decision."""
    vendor = make_vendor()
    application = _application(uow, vendor, cycle, raw=GOOD_RAW)
    application.computed = {"total": 100.0, "cls": "A", "ko": True, "per": {}, "groups": {}}
    application.rubric_scores = {"A.1": 3}
    uow.commit()

    login(make_user(UserRole.VENDOR, vendor=vendor))
    body = client.get(f"/api/applications/{application.id}").json()
    assert body["score_released"] is False
    assert body["computed"] is None
    assert body["rubric_scores"] is None
    assert body["total"] is None and body["cls"] is None

    # And the staff-only evaluation sheet is closed to it outright.
    assert client.get(f"/api/applications/{application.id}/evaluation").status_code == 403


# ═════════════════════════════════════════════════════════════════════════════
# 2. Authorisation — per role
# ═════════════════════════════════════════════════════════════════════════════
def test_a_commission_member_cannot_edit_the_rubric(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    uow: UnitOfWork,
    cycle: QualificationCycle,
) -> None:
    """Spec §3: the commission records a decision; the officer enters the 0–3 cells."""
    application = _application(uow, make_vendor(), cycle, raw=GOOD_RAW)
    login(make_user(UserRole.COMMISSION))
    response = client.put(
        f"/api/applications/{application.id}/evaluation", json={"rubric_scores": {"A.1": 3}}
    )
    assert response.status_code == 403, response.text


def test_an_officer_cannot_approve_and_a_commission_member_cannot_prequalify(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    logout: Any,
    uow: UnitOfWork,
    cycle: QualificationCycle,
) -> None:
    """Spec §9: rejection is the commission's, prequalification is the manager's, and the
    officer records neither. Two different refusals — the matrix for the officer, the state
    machine for the commission."""
    application = _application(uow, make_vendor(), cycle, raw=GOOD_RAW)
    application.computed = {"total": 100.0, "cls": "A", "ko": True, "per": {}, "groups": {}}
    uow.commit()

    login(make_user(UserRole.OFFICER))
    assert (
        client.post(
            f"/api/applications/{application.id}/decide", json={"decision": "approve"}
        ).status_code
        == 403
    )
    logout()

    login(make_user(UserRole.COMMISSION))
    refused = client.post(
        f"/api/applications/{application.id}/decide", json={"decision": "approve"}
    )
    assert refused.status_code == 403, refused.text
    assert refused.json()["error"]["code"] == "forbidden"


def test_approval_is_refused_below_the_pass_mark_and_on_a_knock_out(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    uow: UnitOfWork,
    cycle: QualificationCycle,
) -> None:
    """The score gate is server-side, not a disabled button (spec §8)."""
    application = _application(uow, make_vendor(), cycle, raw=LOW_RAW)
    login(make_user(UserRole.MANAGER))
    client.put(f"/api/applications/{application.id}/evaluation", json={"rubric_scores": {}})

    response = client.post(
        f"/api/applications/{application.id}/decide", json={"decision": "approve"}
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["details"]["total"] < 70.0


def test_an_api_key_can_never_mint_another_api_key_or_an_account(
    client: TestClient, make_user: Any, login: Any, session: Session
) -> None:
    """``permissions.py`` gives the account and credential operations ``scope=None``; this
    checks the *runtime* consequence, not the table."""
    login(make_user(UserRole.ADMIN))
    created = client.post(
        "/api/integrations/api-keys",
        json={"name": "review", "scopes": ["admin:write", "admin:read"]},
    )
    assert created.status_code == 201, created.text
    plaintext = created.json()["key"]

    client.post("/api/auth/logout")
    client.cookies.clear()
    client.headers.pop("X-CSRF-Token", None)
    headers = {"X-API-Key": plaintext}
    assert client.get("/api/integrations/api-keys", headers=headers).status_code == 403
    assert (
        client.post(
            "/api/integrations/api-keys",
            json={"name": "x", "scopes": ["admin:read"]},
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/admin/users",
            json={"email": "x@y.test", "full_name": "X", "role": "admin"},
            headers=headers,
        ).status_code
        == 403
    )


@pytest.mark.xfail(
    strict=True,
    reason="FINDING 1: PATCH /vendors/{id} accepts status=prequalified from any staff role. "
    "An officer or a commission member can prequalify a vendor with no evaluation, no score "
    "and no manager approval — and matching reads exactly that column.",
)
def test_only_a_manager_can_put_a_vendor_into_the_prequalified_state(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any, session: Session
) -> None:
    vendor = make_vendor()
    login(make_user(UserRole.OFFICER))
    response = client.patch(
        f"/api/vendors/{vendor.id}",
        json={"status": "prequalified", "reason": "no evaluation ever happened"},
    )
    assert response.status_code == 403, (
        f"an officer set vendor.status={response.json().get('status')!r} directly, "
        "bypassing spec §9"
    )


@pytest.mark.xfail(
    strict=True,
    reason="FINDING 4: patchVendor is open to EVERYONE, so a commission member can rewrite the "
    "register (legal name, VÖEN, type). Spec §3 gives the commission decisions only.",
)
def test_a_commission_member_cannot_rewrite_the_register(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    vendor = make_vendor()
    login(make_user(UserRole.COMMISSION))
    response = client.patch(
        f"/api/vendors/{vendor.id}", json={"legal_name": "Renamed", "reason": "because"}
    )
    assert response.status_code == 403, response.text


# ═════════════════════════════════════════════════════════════════════════════
# 3. Data integrity
# ═════════════════════════════════════════════════════════════════════════════
def test_a_vendor_cannot_edit_answers_once_the_application_has_been_submitted(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    uow: UnitOfWork,
    cycle: QualificationCycle,
) -> None:
    vendor = make_vendor()
    application = _application(uow, vendor, cycle, stop_at=ApplicationStatus.SUBMITTED)
    login(make_user(UserRole.VENDOR, vendor=vendor))
    response = client.patch(
        f"/api/applications/{application.id}/answers", json={"answers": {"B.2": 9_000_000}}
    )
    assert response.status_code == 409, response.text


def test_the_submission_snapshot_survives_a_later_profile_edit(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    uow: UnitOfWork,
    session: Session,
    cycle: QualificationCycle,
) -> None:
    """Spec §5: the frozen snapshot is what the score is read from, whatever the profile does."""
    vendor = make_vendor()
    application = _application(uow, vendor, cycle, raw=GOOD_RAW)
    login(make_user(UserRole.OFFICER))

    observations_service.record_many(
        uow, vendor.id, {"B.2": 1, "B.3": 1, "B.4": 1}, source=ObservationSource.MANUAL
    )
    uow.commit()

    rows = {
        row["code"]: row["raw_value"]
        for row in client.get(f"/api/applications/{application.id}/evaluation").json()["rows"]
    }
    assert rows["B.1"] == 20_000_000.0


def test_a_decided_application_can_no_longer_be_re_evaluated(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    uow: UnitOfWork,
    cycle: QualificationCycle,
) -> None:
    application = _application(uow, make_vendor(), cycle, raw=GOOD_RAW)
    login(make_user(UserRole.MANAGER))
    client.put(f"/api/applications/{application.id}/evaluation", json={"rubric_scores": {}})
    approved = client.post(
        f"/api/applications/{application.id}/decide", json={"decision": "approve"}
    )
    assert approved.status_code == 200, approved.text

    again = client.put(f"/api/applications/{application.id}/evaluation", json={"rubric_scores": {}})
    assert again.status_code == 409, again.text


def test_an_audit_row_never_outlives_the_mutation_it_describes(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    session: Session,
) -> None:
    """One request is one transaction (``db.UnitOfWork``): a refused mutation must leave the
    audit log untouched, because a log that records attempts as facts is worse than none."""
    vendor = make_vendor()
    before = session.scalar(select(AuditEvent.id).where(AuditEvent.entity_id == vendor.id).limit(1))
    assert before is None

    login(make_user(UserRole.OFFICER))
    # A staff edit with no reason is refused after the row has already been touched.
    refused = client.patch(f"/api/vendors/{vendor.id}", json={"legal_name": "Half applied"})
    assert refused.status_code == 422, refused.text

    session.expire_all()
    rows = list(session.scalars(select(AuditEvent).where(AuditEvent.entity_id == vendor.id)))
    assert rows == []
    reloaded = session.get(Vendor, vendor.id)
    assert reloaded is not None and reloaded.legal_name != "Half applied"


@pytest.mark.xfail(
    strict=True,
    reason="FINDING 2: ScoringModel.is_locked is only ever set by seed/real.py for sub-4. "
    "No code path sets it when an application is scored, so patchScoringModelDraft rewrites "
    "the criteria and the pass mark of any other version — including an active one that has "
    "already scored applications (ADR-014/017, spec §10.3).",
)
def test_a_model_version_that_has_scored_an_application_is_immutable(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    session: Session,
    uow: UnitOfWork,
    cycle: QualificationCycle,
    model_version: str,
) -> None:
    application = _application(uow, make_vendor(), cycle, raw=LOW_RAW)
    login(make_user(UserRole.MANAGER))
    scored = client.put(
        f"/api/applications/{application.id}/evaluation", json={"rubric_scores": {}}
    )
    assert scored.status_code == 200, scored.text
    assert scored.json()["computed"]["total"] < 70.0

    # The version is live and has been scored with. Its definition must be frozen.
    edited = client.patch(f"/api/scoring-models/{model_version}", json={"pass_mark": 1.0})
    assert edited.status_code == 409, (
        "the pass mark of a live, already-used model version was rewritten to "
        f"{edited.json().get('pass_mark')!r} while application_count="
        f"{edited.json().get('application_count')!r}"
    )


def test_lowering_the_pass_mark_of_a_used_model_approves_a_failing_application(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    uow: UnitOfWork,
    cycle: QualificationCycle,
    model_version: str,
) -> None:
    """What FINDING 2 buys: the same application, refused and then approved, with nothing
    about the *evidence* changed. Not xfail — this is the current behaviour, recorded."""
    application = _application(uow, make_vendor(), cycle, raw=LOW_RAW)
    login(make_user(UserRole.MANAGER))
    client.put(f"/api/applications/{application.id}/evaluation", json={"rubric_scores": {}})

    refused = client.post(
        f"/api/applications/{application.id}/decide", json={"decision": "approve"}
    )
    assert refused.status_code == 409

    assert (
        client.patch(f"/api/scoring-models/{model_version}", json={"pass_mark": 1.0}).status_code
        == 200
    )
    approved = client.post(
        f"/api/applications/{application.id}/decide", json={"decision": "approve"}
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "prequalified"


@pytest.mark.xfail(
    strict=True,
    reason="FINDING 3: the raw snapshot is frozen at submission and never refreshed, so the "
    "information_requested loop of spec §9 cannot correct a numeric indicator — the officer "
    "scores the number the vendor first sent, not the one it was asked to correct.",
)
def test_information_requested_lets_a_corrected_indicator_reach_the_score(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    login: Any,
    logout: Any,
    uow: UnitOfWork,
    cycle: QualificationCycle,
) -> None:
    vendor = make_vendor()
    application = _application(uow, vendor, cycle, raw={**GOOD_RAW, "B.1": 1_000.0})
    applications_service.transition(
        uow, application, ApplicationStatus.INFORMATION_REQUESTED, role=UserRole.OFFICER
    )
    uow.commit()

    login(make_user(UserRole.VENDOR, vendor=vendor))
    supplied = client.patch(
        f"/api/applications/{application.id}/answers",
        json={"answers": {"B.2": 9_000_000, "B.3": 9_000_000, "B.4": 9_000_000}},
    )
    assert supplied.status_code == 200, supplied.text
    logout()

    login(make_user(UserRole.OFFICER))
    rows = {
        row["code"]: row["raw_value"]
        for row in client.get(f"/api/applications/{application.id}/evaluation").json()["rows"]
    }
    assert rows["B.1"] == 9_000_000.0, (
        f"the officer is still scoring the superseded figure {rows['B.1']!r}"
    )


# ═════════════════════════════════════════════════════════════════════════════
# 4. Credentials and files
# ═════════════════════════════════════════════════════════════════════════════
def test_an_api_key_is_never_recoverable_and_a_revoked_one_dies_at_once(
    client: TestClient, make_user: Any, login: Any
) -> None:
    login(make_user(UserRole.ADMIN))
    created = client.post(
        "/api/integrations/api-keys", json={"name": "review", "scopes": ["vendors:read"]}
    )
    body = created.json()
    plaintext = body["key"]
    key_id = body["id"]

    listed = client.get("/api/integrations/api-keys").json()
    rows = listed["items"] if isinstance(listed, dict) else listed
    row = next(item for item in rows if item["id"] == key_id)
    assert "key" not in row and plaintext not in json.dumps(listed)

    machine = {"X-API-Key": plaintext}
    assert client.get("/api/vendors", headers=machine).status_code == 200
    assert client.delete(f"/api/integrations/api-keys/{key_id}").status_code == 204

    client.post("/api/auth/logout")
    client.cookies.clear()
    client.headers.pop("X-CSRF-Token", None)
    assert client.get("/api/vendors", headers=machine).status_code == 401


def test_a_webhook_secret_is_returned_once_and_never_again(
    client: TestClient, make_user: Any, login: Any
) -> None:
    login(make_user(UserRole.ADMIN))
    created = client.post(
        "/api/integrations/webhooks",
        json={"url": "https://example.invalid/hook", "events": ["application.submitted"]},
    )
    assert created.status_code == 201, created.text
    secret = created.json()["secret"]
    assert secret

    listed = client.get("/api/integrations/webhooks").text
    assert secret not in listed and '"secret"' not in listed
    patched = client.patch(
        f"/api/integrations/webhooks/{created.json()['id']}",
        json={"events": ["application.submitted", "vendor.prequalified"]},
    )
    assert secret not in patched.text


def test_the_upload_route_refuses_a_non_pdf_and_a_key_outside_the_storage_root(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any, storage: Any
) -> None:
    """Content type is the client's claim; the magic number is the file's. And the local
    backend's key is user-influenced, so it must not be able to name ``../../``."""
    vendor = make_vendor()
    login(make_user(UserRole.VENDOR, vendor=vendor))

    refused = client.post(
        f"/api/vendors/{vendor.id}/documents/upload-init",
        json={
            "code": "A-01",
            "filename": "x.exe",
            "content_type": "application/x-msdownload",
            "size": 10,
        },
    )
    assert refused.status_code in (415, 422), refused.text

    ticket = client.post(
        f"/api/vendors/{vendor.id}/documents/upload-init",
        json={
            "code": "A-01",
            "filename": "../../../etc/passwd",
            "content_type": "application/pdf",
            "size": 10,
        },
    ).json()
    assert "/../" not in ticket["url"], ticket["url"]

    put = client.put(ticket["url"], content=b"MZ\x90 not a pdf at all")
    assert put.status_code == 415, put.text

    with pytest.raises(ObjectNotFoundError):
        storage.put(
            "documents/../../escape.pdf", b"%PDF-1.4 escaped", content_type="application/pdf"
        )


def test_the_otp_endpoints_rate_limit(
    client: TestClient, make_vendor: Any, make_user: Any, settings: Settings
) -> None:
    user = make_user(UserRole.VENDOR, vendor=make_vendor())
    codes = [
        client.post("/api/auth/otp/request", json={"email": user.email}).status_code
        for _ in range(settings.otp_rate_limit + 1)
    ]
    assert codes[-1] == 429, codes


@pytest.mark.xfail(
    strict=True,
    reason="FINDING 5: a wrong code increments OtpCode.attempts, but the 401 is raised inside "
    "the request transaction, which get_uow then rolls back. attempts is always 0, so "
    "OTP_MAX_ATTEMPTS is inert and only the in-process rate limiter bounds guessing.",
)
def test_a_wrong_otp_code_burns_an_attempt(
    client: TestClient, make_vendor: Any, make_user: Any, session: Session
) -> None:
    user = make_user(UserRole.VENDOR, vendor=make_vendor())
    assert client.post("/api/auth/otp/request", json={"email": user.email}).status_code == 202

    for _ in range(3):
        assert (
            client.post(
                "/api/auth/otp/verify", json={"email": user.email, "code": "111111"}
            ).status_code
            == 401
        )

    session.expire_all()
    row = session.scalars(select(OtpCode).where(OtpCode.email == user.email)).one()
    assert row.attempts == 3, f"three wrong codes left attempts={row.attempts}"


@pytest.mark.xfail(
    strict=True,
    reason="FINDING 6: Settings refuses AUTH_MODE=test in production but accepts the built-in "
    "placeholder SESSION_SECRET. That one string signs session cookies, TOTP challenges, "
    "upload tickets and every signed storage URL.",
)
def test_production_refuses_the_placeholder_session_secret() -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, app_env="production", auth_mode="live")  # type: ignore[call-arg]


# ═════════════════════════════════════════════════════════════════════════════
# 5. i18n completeness
# ═════════════════════════════════════════════════════════════════════════════
def test_every_error_envelope_code_has_a_sentence_in_both_languages() -> None:
    """``features/admin/shared.tsx`` renders ``err_${code}``; a missing key shows the code."""
    contract = load_contract()
    codes = contract["components"]["schemas"]["ErrorEnvelope"]["properties"]["error"]["properties"][
        "code"
    ]["enum"]
    assert codes
    for language in ("az", "en"):
        dictionary = _dictionary(language)
        missing = [code for code in codes if not dictionary.get(f"err_{code}", "").strip()]
        assert not missing, f"{language}.json has no sentence for: {missing}"


@pytest.mark.xfail(
    strict=True,
    reason="FINDING 7: ApplicationsQueue renders the status filter as t(`st_${value}`) and "
    "only three of the eight ApplicationStatus values have an st_ key. The other five fall "
    "through to the raw identifier — 'in_progress', 'information_requested', 'withdrawn' — "
    "in Azerbaijani as well as English.",
)
def test_every_application_status_has_an_st_label_in_both_languages() -> None:
    contract = load_contract()
    statuses = contract["components"]["schemas"]["ApplicationStatus"]["enum"]
    for language in ("az", "en"):
        dictionary = _dictionary(language)
        missing = [s for s in statuses if not dictionary.get(f"st_{s}", "").strip()]
        assert not missing, f"{language}.json has no st_ label for: {missing}"


@pytest.mark.xfail(
    strict=True,
    reason="FINDING 8: features/manager/shared.tsx maps withdrawn and suspended onto "
    "st_rejected, so a withdrawn application and a suspended vendor are both labelled "
    "'Rədd edilib' / 'Rejected' — a factual misstatement, not a missing translation.",
)
def test_withdrawn_and_suspended_are_not_labelled_rejected() -> None:
    source = (REPO_ROOT / "apps" / "web" / "src" / "features" / "manager" / "shared.tsx").read_text(
        encoding="utf-8"
    )
    block = source.split("const STATUS_KEY", 1)[1].split("};", 1)[0]
    mapping = dict(
        line.strip().rstrip(",").split(": ", 1) for line in block.splitlines() if ": '" in line
    )
    assert mapping["withdrawn"] != mapping["rejected"], "withdrawn is labelled as rejected"
    assert mapping["suspended"] != mapping["rejected"], "suspended is labelled as rejected"


def test_the_two_dictionaries_stay_the_same_size_after_the_feature_merge() -> None:
    """A regression guard for the merge order: a per-feature file present in one language only
    silently shrinks the other, and ``test_i18n_contract`` only compares the merged keys."""
    az_files = sorted(
        p.name.replace(".az.", ".") for p in (I18N_DIR / "features").glob("*.az.json")
    )
    en_files = sorted(
        p.name.replace(".en.", ".") for p in (I18N_DIR / "features").glob("*.en.json")
    )
    assert az_files == en_files


# ═════════════════════════════════════════════════════════════════════════════
# 6. Sessions
# ═════════════════════════════════════════════════════════════════════════════
def test_the_csrf_double_submit_check_is_enforced_on_a_cookie_mutation(
    client: TestClient, make_user: Any, login: Any
) -> None:
    login(make_user(UserRole.ADMIN))
    del client.headers["X-CSRF-Token"]
    response = client.post(
        "/api/admin/categories",
        json={"code": f"c{uuid.uuid4().hex[:6]}", "name_az": "a", "name_en": "b", "kind": "work"},
    )
    assert response.status_code == 403, response.text
    assert "CSRF" in response.json()["error"]["message"]


def test_deactivating_an_account_kills_its_live_session(
    client: TestClient, make_user: Any, login: Any, session: Session
) -> None:
    """The documented revocation mechanism for a stateless session (``security/deps.py``)."""
    user = make_user(UserRole.OFFICER)
    login(user)
    assert client.get("/api/auth/me").status_code == 200

    user.is_active = False
    session.commit()
    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.xfail(
    strict=True,
    reason="FINDING 4: POST /auth/logout only clears the cookies in the browser. The session "
    "token is a stateless signature with no server-side record, so a copy captured before "
    "logout keeps authenticating for the remaining ACCESS_TOKEN_TTL_MINUTES (8 hours by "
    "default). There is no way to revoke one session short of deactivating the account.",
)
def test_logging_out_revokes_the_session_token(
    client: TestClient, make_user: Any, login: Any
) -> None:
    login(make_user(UserRole.ADMIN))
    captured = dict(client.cookies)

    client.post("/api/auth/logout")
    client.cookies.clear()
    assert client.get("/api/auth/me").status_code == 401

    for name, value in captured.items():
        client.cookies.set(name, value)
    replayed = client.get("/api/auth/me")
    assert replayed.status_code == 401, (
        f"a cookie captured before logout still authenticates as {replayed.json().get('role')!r}"
    )


def test_an_admin_read_key_reads_the_staff_directory_and_the_audit_log(
    client: TestClient, make_user: Any, login: Any
) -> None:
    """Recorded behaviour, not a defect claim. ``docs/integration-guide.md`` names the two
    closures it considers permanent (no key mints a key, no key manages webhooks) but not
    this: one ``admin:read`` scope on a machine credential reads every staff account and the
    whole audit trail, which spec §13 describes as committee minutes. Scope granularity is
    the orchestrator's call; the review's job is to say what the scope actually buys."""
    login(make_user(UserRole.ADMIN))
    plaintext = client.post(
        "/api/integrations/api-keys", json={"name": "review", "scopes": ["admin:read"]}
    ).json()["key"]
    client.post("/api/auth/logout")
    client.cookies.clear()
    client.headers.pop("X-CSRF-Token", None)

    machine = {"X-API-Key": plaintext}
    users = client.get("/api/admin/users", headers=machine)
    assert users.status_code == 200
    assert any("email" in row for row in users.json()["items"])
    assert client.get("/api/admin/audit", headers=machine).status_code == 200


def test_a_vendor_can_read_the_full_criteria_and_thresholds_of_a_scoring_model(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any, model_version: str
) -> None:
    """Recorded behaviour. ``permissions.py`` justifies the vendor's access as "vendors see
    the class bands of the version they were scored with (spec §10.3)", but the handler
    returns the whole definition — every threshold cut point of every numeric criterion. A
    vendor can read exactly which turnover figure buys the next band."""
    login(make_user(UserRole.VENDOR, vendor=make_vendor()))
    body = client.get(f"/api/scoring-models/{model_version}").json()
    turnover = next(row for row in body["criteria"] if row["code"] == "B.1")
    assert turnover["spec"]["cuts"], "no thresholds returned"
