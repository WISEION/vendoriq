"""Document expiry rules and the upload round trip (spec §7, §13)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from vendoriq_api.catalog import (
    DOCUMENT_CATALOG,
    MANDATORY_DOCUMENT_CODES,
    checklist_for,
    days_to_expiry,
    expiry_state,
    resolve_expiry,
)
from vendoriq_api.models.enums import (
    DocumentExpiryState,
    DocumentStatus,
    UserRole,
    VendorType,
)
from vendoriq_api.services import documents

TODAY = date(2026, 8, 26)

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


# ── the A-05 rule ───────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("issued", "expected"),
    [
        (date(2026, 1, 15), date(2026, 4, 15)),
        # Month-end clamping: 30 November + 3 months is 28 February, not 30 February.
        (date(2025, 11, 30), date(2026, 2, 28)),
        # …and a leap year gives the 29th.
        (date(2023, 11, 30), date(2024, 2, 29)),
        (date(2026, 10, 31), date(2027, 1, 31)),
    ],
)
def test_a05_expires_three_months_after_issue(issued: date, expected: date) -> None:
    """Spec §7: the tax clearance certificate is valid three months, always."""
    assert resolve_expiry("A-05", issued, None) == expected


def test_a05_overrides_whatever_the_client_sent() -> None:
    """A vendor copying a date off the certificate is corrected, not rejected."""
    assert resolve_expiry("A-05", date(2026, 1, 15), date(2030, 1, 1)) == date(2026, 4, 15)


def test_a05_without_an_issue_date_has_no_expiry() -> None:
    assert resolve_expiry("A-05", None, date(2030, 1, 1)) is None


def test_other_codes_keep_the_expiry_they_were_given() -> None:
    assert resolve_expiry("A-04", date(2026, 1, 1), date(2029, 3, 3)) == date(2029, 3, 3)
    assert resolve_expiry("A-04", date(2026, 1, 1), None) is None


# ── the five expiry states ──────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("status", "expiry", "expected"),
    [
        (DocumentStatus.MISSING, None, DocumentExpiryState.MISSING),
        (DocumentStatus.IN_PREPARATION, None, DocumentExpiryState.MISSING),
        (DocumentStatus.NOT_APPLICABLE, None, DocumentExpiryState.MISSING),
        # "Müddətsiz" — on file, never expires (brief §1.11).
        (DocumentStatus.UPLOADED, None, DocumentExpiryState.PERM),
        (DocumentStatus.UPLOADED, date(2026, 12, 31), DocumentExpiryState.VALID),
        # Boundaries of the 60-day window.
        (DocumentStatus.UPLOADED, TODAY.replace(day=25), DocumentExpiryState.EXPIRED),
        (DocumentStatus.UPLOADED, TODAY, DocumentExpiryState.EXPIRING),
        (DocumentStatus.UPLOADED, date(2026, 10, 25), DocumentExpiryState.EXPIRING),
        (DocumentStatus.UPLOADED, date(2026, 10, 26), DocumentExpiryState.VALID),
    ],
)
def test_expiry_state(
    status: DocumentStatus, expiry: date | None, expected: DocumentExpiryState
) -> None:
    assert expiry_state(status, expiry, today=TODAY) is expected


def test_expiring_boundary_is_inclusive_at_sixty_days() -> None:
    """60 days out is still "expiring"; 61 is "valid". Off-by-one here means a missed job."""
    sixty = date(2026, 10, 25)
    assert days_to_expiry(sixty, today=TODAY) == 60
    assert expiry_state(DocumentStatus.UPLOADED, sixty, today=TODAY) is DocumentExpiryState.EXPIRING


def test_days_to_expiry_is_negative_once_expired_and_none_when_permanent() -> None:
    assert days_to_expiry(date(2026, 8, 20), today=TODAY) == -6
    assert days_to_expiry(None, today=TODAY) is None


# ── the catalogue ───────────────────────────────────────────────────────────
def test_the_catalogue_covers_a01_to_h02() -> None:
    codes = set(DOCUMENT_CATALOG)
    assert {"A-01", "A-05", "G-02", "H-01", "H-02"} <= codes
    assert all(len(code) == 4 and code[1] == "-" for code in codes)


def test_suppliers_reuse_the_same_checklist() -> None:
    """Orchestrator decision (phase 1B): supplier docs reuse A-01 … G-02."""
    assert [d.code for d in checklist_for(VendorType.SUP)] == [
        d.code for d in checklist_for(VendorType.SUB)
    ]


def test_the_mandatory_set_matches_spec_appendix_b() -> None:
    assert set(MANDATORY_DOCUMENT_CODES) == {
        "A-01",
        "A-02",
        "A-03",
        "A-04",
        "A-05",
        "B-01",
        "B-02",
        "C-01",
        "E-01",
        "F-01",
        "G-02",
        "H-01",
        "H-02",
    }


# ── the checklist through the API ───────────────────────────────────────────
def test_the_checklist_lists_every_code_even_when_nothing_is_uploaded(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    """Contract: "Always returns every catalogue code, including the ones with `missing`"."""
    vendor = make_vendor()
    login(make_user(UserRole.OFFICER))
    body = client.get(f"/api/vendors/{vendor.id}/documents").json()
    assert len(body) == len(DOCUMENT_CATALOG)
    assert {row["status"] for row in body} == {"missing"}
    assert body[0]["name_az"] and body[0]["name_en"]


def _upload(client: TestClient, vendor_id: Any, code: str, issue: str | None) -> Any:
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
    return client.post(
        f"/api/vendors/{vendor_id}/documents/upload-complete",
        json={"upload_id": ticket["upload_id"], "code": code, "issue_date": issue},
    )


def test_upload_round_trip_sets_the_a05_expiry(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    """init → PUT the bytes → complete. A-05 gets issue + 3 months whatever was sent."""
    vendor = make_vendor()
    login(make_user(UserRole.VENDOR, vendor=vendor))
    response = _upload(client, vendor.id, "A-05", "2026-01-15")
    assert response.status_code == 200, response.text
    document = response.json()
    assert document["status"] == "uploaded"
    assert document["expiry_date"] == "2026-04-15"
    assert document["days_to_expiry"] is not None


def test_a_download_ticket_is_signed_and_serves_the_file(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    vendor = make_vendor()
    login(make_user(UserRole.OFFICER))
    document = _upload(client, vendor.id, "A-04", "2026-01-15").json()
    ticket = client.get(f"/api/vendors/{vendor.id}/documents/{document['id']}").json()
    assert "token=" in ticket["url"]
    assert client.get(ticket["url"]).content == PDF

    # Tampering invalidates the link — that is the whole security model of the local
    # backend's "pre-signed" URL (ADR-002). The payload half is mangled rather than the
    # signature's last character: base64's final character carries only two data bits, so
    # changing it can decode to the same signature bytes and the check would pass.
    head, _, tail = ticket["url"].partition("token=")
    token, _, rest = tail.partition("&")
    payload, _, signature = token.partition(".")
    mangled = ("B" if payload[0] != "B" else "C") + payload[1:]
    assert client.get(f"{head}token={mangled}.{signature}&{rest}").status_code == 403

    # …and a token that is valid, but for a different object, does not open this one.
    second = _upload(client, vendor.id, "A-01", None).json()
    other = client.get(f"/api/vendors/{vendor.id}/documents/{second['id']}").json()
    other_token = other["url"].partition("token=")[2].partition("&")[0]
    assert client.get(f"{head}token={other_token}&{rest}").status_code == 403


def test_a_non_pdf_upload_is_refused_by_content_and_by_declaration(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    """Two gates: the declared content type, and the file's own magic number."""
    vendor = make_vendor()
    login(make_user(UserRole.OFFICER))
    declared = client.post(
        f"/api/vendors/{vendor.id}/documents/upload-init",
        json={
            "code": "A-04",
            "filename": "x.png",
            "content_type": "image/png",
            "size": 10,
        },
    )
    assert declared.status_code == 422  # rejected by the schema's Literal

    init = client.post(
        f"/api/vendors/{vendor.id}/documents/upload-init",
        json={
            "code": "A-04",
            "filename": "x.pdf",
            "content_type": "application/pdf",
            "size": 10,
        },
    ).json()
    smuggled = client.put(init["url"], content=b"MZ\x90\x00 not a pdf")
    assert smuggled.status_code == 415


def test_a_vendor_may_not_verify_its_own_document(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    """Spec §3: verification is the officer's stamp."""
    vendor = make_vendor()
    login(make_user(UserRole.OFFICER))
    document = _upload(client, vendor.id, "A-04", "2026-01-15").json()
    client.post("/api/auth/logout")
    client.cookies.clear()

    login(make_user(UserRole.VENDOR, vendor=vendor))
    forbidden = client.patch(
        f"/api/vendors/{vendor.id}/documents/{document['id']}", json={"verified": True}
    )
    assert forbidden.status_code == 403
    allowed = client.patch(
        f"/api/vendors/{vendor.id}/documents/{document['id']}",
        json={"status": "in_preparation"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "in_preparation"


def test_an_officer_verifies_and_the_stamp_is_recorded(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    vendor = make_vendor()
    officer = make_user(UserRole.OFFICER)
    login(officer)
    document = _upload(client, vendor.id, "A-04", "2026-01-15").json()
    verified = client.patch(
        f"/api/vendors/{vendor.id}/documents/{document['id']}", json={"verified": True}
    ).json()
    assert verified["verified_by"] == str(officer.id)
    assert verified["verified_at"] is not None


def test_missing_mandatory_reports_the_gap(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any, session: Any
) -> None:
    """The pre-submission check: uploaded-and-unexpired is the only state that counts."""
    vendor = make_vendor()
    login(make_user(UserRole.OFFICER))
    _upload(client, vendor.id, "A-01", "2026-01-15")
    missing = documents.missing_mandatory(session, vendor)
    assert "A-01" not in missing
    assert "F-01" in missing
