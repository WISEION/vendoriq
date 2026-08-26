"""The register: CRUD, filters, provenance on edit, audit on every mutation (spec §5, §8)."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from vendoriq_api.db import UnitOfWork
from vendoriq_api.models import AuditEvent, Event, FieldObservation
from vendoriq_api.models.enums import (
    ObservationSource,
    UserRole,
    VendorStatus,
    VendorType,
)
from vendoriq_api.services import categories as categories_service
from vendoriq_api.services import observations
from vendoriq_api.services import vendors as vendors_service


def _audit(session: Session, entity_type: str, entity_id: Any) -> list[AuditEvent]:
    return list(
        session.scalars(
            select(AuditEvent)
            .where(AuditEvent.entity_type == entity_type, AuditEvent.entity_id == entity_id)
            .order_by(AuditEvent.created_at.asc())
        )
    )


# ── create ──────────────────────────────────────────────────────────────────
def test_creating_a_vendor_writes_an_audit_row_and_an_event(
    client: TestClient, make_user: Any, login: Any, session: Session
) -> None:
    login(make_user(UserRole.OFFICER))
    created = client.post(
        "/api/vendors",
        json={"legal_name": "Audit Probe MMC", "type": "sub", "voen": "1112223334"},
    )
    assert created.status_code == 201, created.text
    vendor_id = created.json()["id"]

    rows = _audit(session, "vendor", vendor_id)
    assert [row.action for row in rows] == ["create"]
    assert (rows[0].after or {})["legal_name"] == "Audit Probe MMC"

    event = session.scalar(select(Event).where(Event.entity_id == vendor_id))
    assert event is not None and event.type == "vendor.registered"


def test_a_duplicate_voen_is_refused_at_the_service(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    existing = make_vendor(voen="1400915571")
    login(make_user(UserRole.OFFICER))
    response = client.post(
        "/api/vendors", json={"legal_name": "Clone MMC", "type": "sub", "voen": existing.voen}
    )
    assert response.status_code == 409


# ── patch: audit and provenance ─────────────────────────────────────────────
def test_a_patch_writes_an_audit_row_with_before_and_after(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any, session: Session
) -> None:
    """CONTRIBUTING, definition of done §6: every mutation writes an audit event."""
    vendor = make_vendor(legal_name="Before MMC", region="Gəncə")
    login(make_user(UserRole.OFFICER))
    response = client.patch(
        f"/api/vendors/{vendor.id}",
        json={"legal_name": "After MMC", "region": "Bakı", "reason": "Charter amended"},
    )
    assert response.status_code == 200, response.text

    rows = _audit(session, "vendor", vendor.id)
    update = [row for row in rows if row.action == "update"][-1]
    assert update.before == {"legal_name": "Before MMC", "region": "Gəncə"}
    after = update.after or {}
    assert after["legal_name"] == "After MMC"
    assert after["reason"] == "Charter amended"


def test_a_patch_records_the_change_as_a_manual_observation(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any, session: Session
) -> None:
    """Spec §6.5: a correction keeps its provenance rather than overwriting silently."""
    vendor = make_vendor()
    login(make_user(UserRole.OFFICER))
    client.patch(
        f"/api/vendors/{vendor.id}",
        json={"legal_name": "Renamed MMC", "reason": "Registry extract 12.08.2026"},
    )
    rows = list(
        session.scalars(
            select(FieldObservation).where(
                FieldObservation.vendor_id == vendor.id, FieldObservation.field_code == "A.1"
            )
        )
    )
    assert len(rows) == 1
    assert rows[0].source is ObservationSource.MANUAL
    assert observations.unwrap(rows[0].value) == "Renamed MMC"


def test_a_staff_patch_without_a_reason_is_refused(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    vendor = make_vendor()
    login(make_user(UserRole.OFFICER))
    response = client.patch(f"/api/vendors/{vendor.id}", json={"region": "Bakı"})
    assert response.status_code == 422
    assert "reason" in response.json()["error"]["message"].lower()


def test_a_vendor_editing_a_prequalified_profile_is_refused(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    """Spec §7: after prequalification an edit is a change request, not a direct write."""
    vendor = make_vendor(status=VendorStatus.PREQUALIFIED)
    login(make_user(UserRole.VENDOR, vendor=vendor))
    response = client.patch(f"/api/vendors/{vendor.id}", json={"website": "example.az"})
    assert response.status_code == 409


def test_a_vendor_may_edit_its_own_profile_before_prequalification(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    vendor = make_vendor(status=VendorStatus.IN_PROGRESS)
    login(make_user(UserRole.VENDOR, vendor=vendor))
    response = client.patch(f"/api/vendors/{vendor.id}", json={"website": "wesa.az"})
    assert response.status_code == 200
    assert response.json()["website"] == "wesa.az"


def test_a_vendor_cannot_set_its_own_status(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    vendor = make_vendor()
    login(make_user(UserRole.VENDOR, vendor=vendor))
    response = client.patch(f"/api/vendors/{vendor.id}", json={"status": "prequalified"})
    assert response.status_code == 403


def test_suspension_goes_through_its_own_endpoint(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    """Suspension needs a reason, so the generic patch refuses to set it (spec §9)."""
    vendor = make_vendor()
    login(make_user(UserRole.MANAGER))
    blocked = client.patch(
        f"/api/vendors/{vendor.id}", json={"status": "suspended", "reason": "tax debt"}
    )
    assert blocked.status_code == 409


# ── suspend / lift ──────────────────────────────────────────────────────────
def test_suspend_and_lift(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any, session: Session
) -> None:
    vendor = make_vendor(status=VendorStatus.PREQUALIFIED)
    login(make_user(UserRole.MANAGER))
    suspended = client.post(
        f"/api/vendors/{vendor.id}/suspend", json={"suspended": True, "reason": "tax debt"}
    )
    assert suspended.status_code == 200
    assert suspended.json()["status"] == "suspended"

    event = session.scalar(
        select(Event).where(Event.entity_id == vendor.id, Event.type == "vendor.suspended")
    )
    assert event is not None and event.payload["reason"] == "tax debt"

    lifted = client.post(
        f"/api/vendors/{vendor.id}/suspend",
        json={"suspended": False, "reason": "debt cleared"},
    )
    # With no application on file the vendor falls back onto the register.
    assert lifted.json()["status"] == "registered"


def test_suspension_needs_a_reason(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    vendor = make_vendor()
    login(make_user(UserRole.MANAGER))
    response = client.post(
        f"/api/vendors/{vendor.id}/suspend", json={"suspended": True, "reason": "x"}
    )
    assert response.status_code == 422


def test_suspension_survives_an_application_outcome(
    uow: UnitOfWork, make_vendor: Any, session: Session
) -> None:
    """Spec §9: only the manager lifts a suspension, never a workflow step."""
    from vendoriq_api.models.enums import ApplicationStatus

    vendor = make_vendor()
    vendors_service.suspend(uow, vendor, suspended=True, reason="incident on site")
    vendors_service.sync_status_from_application(uow, vendor, ApplicationStatus.PREQUALIFIED)
    assert vendor.status is VendorStatus.SUSPENDED


# ── filters ─────────────────────────────────────────────────────────────────
def test_the_type_filter_matches_both(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    """Contract: "`both` vendors match a filter for `sub` and for `sup`"."""
    make_vendor(type=VendorType.SUB, legal_name="Only Sub MMC")
    make_vendor(type=VendorType.SUP, legal_name="Only Sup MMC")
    make_vendor(type=VendorType.BOTH, legal_name="Both MMC")
    login(make_user(UserRole.OFFICER))

    def names(query: str) -> set[str]:
        body = client.get(f"/api/vendors?page_size=200&{query}").json()
        return {item["legal_name"] for item in body["items"]}

    assert {"Only Sub MMC", "Both MMC"} <= names("type=sub")
    assert "Only Sup MMC" not in names("type=sub")
    assert {"Only Sup MMC", "Both MMC"} <= names("type=sup")


def test_free_text_search_covers_name_and_voen(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    make_vendor(legal_name="Findable Fasad MMC", voen="7777777771")
    login(make_user(UserRole.OFFICER))
    by_name = client.get("/api/vendors?q=findable").json()
    by_voen = client.get("/api/vendors?q=7777777771").json()
    assert by_name["total"] == 1
    assert by_voen["total"] == 1


def test_the_status_and_region_filters(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    make_vendor(status=VendorStatus.PREQUALIFIED, region="Bakı", legal_name="PQ Baku MMC")
    make_vendor(status=VendorStatus.REGISTERED, region="Gəncə", legal_name="Reg Ganja MMC")
    login(make_user(UserRole.OFFICER))
    body = client.get("/api/vendors?status=prequalified&region=Bakı&page_size=200").json()
    names = {item["legal_name"] for item in body["items"]}
    assert "PQ Baku MMC" in names
    assert "Reg Ganja MMC" not in names


def test_the_demo_flag_can_be_excluded(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    """Brief §2: demo rows are flagged and removable; the register can hide them."""
    make_vendor(is_demo=True, legal_name="Demo Only MMC")
    login(make_user(UserRole.OFFICER))
    with_demo = client.get("/api/vendors?page_size=200&include_demo=true").json()
    without = client.get("/api/vendors?page_size=200&include_demo=false").json()
    assert "Demo Only MMC" in {item["legal_name"] for item in with_demo["items"]}
    assert "Demo Only MMC" not in {item["legal_name"] for item in without["items"]}


def test_the_category_filter(
    client: TestClient,
    make_vendor: Any,
    make_user: Any,
    make_category: Any,
    login: Any,
    uow: UnitOfWork,
) -> None:
    category = make_category(code="facade-test")
    inside = make_vendor(legal_name="Facade Co MMC")
    make_vendor(legal_name="Not Facade MMC")
    categories_service.set_for_vendor(uow, inside.id, [category.code])
    uow.commit()
    login(make_user(UserRole.OFFICER))
    body = client.get("/api/vendors?category=facade-test&page_size=200").json()
    assert {item["legal_name"] for item in body["items"]} == {"Facade Co MMC"}


def test_pagination_reports_the_filter_total_not_the_page_size(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    for index in range(5):
        make_vendor(legal_name=f"Paged {index} MMC", region="Paginationland")
    login(make_user(UserRole.OFFICER))
    body = client.get("/api/vendors?region=Paginationland&page=1&page_size=2").json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["page"] == 1 and body["page_size"] == 2


def test_sorting_by_name_both_ways(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    make_vendor(legal_name="Zzz Sorted MMC", region="Sortland")
    make_vendor(legal_name="Aaa Sorted MMC", region="Sortland")
    login(make_user(UserRole.OFFICER))
    ascending = client.get("/api/vendors?region=Sortland&sort=legal_name").json()["items"]
    descending = client.get("/api/vendors?region=Sortland&sort=-legal_name").json()["items"]
    assert ascending[0]["legal_name"].startswith("Aaa")
    assert descending[0]["legal_name"].startswith("Zzz")


# ── detail ──────────────────────────────────────────────────────────────────
def test_the_detail_resolves_the_current_profile_and_the_checklist(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any, uow: UnitOfWork
) -> None:
    vendor = make_vendor()
    observations.record(uow, vendor.id, "E.1", 80, source=ObservationSource.EXCEL)
    observations.record(uow, vendor.id, "E.1", 90, source=ObservationSource.REGISTRY)
    uow.commit()
    login(make_user(UserRole.OFFICER))
    body = client.get(f"/api/vendors/{vendor.id}").json()
    assert body["current_fields"]["E.1"] == 90
    assert body["primary_source"] == "registry"
    assert body["raw_indicators"]["E.1"] == 90.0
    assert len(body["documents"]) >= 30
    assert body["contacts"] == []
    assert body["stale_fields"] == []


# ── contacts ────────────────────────────────────────────────────────────────
def test_contacts_round_trip_and_audit(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any, session: Session
) -> None:
    vendor = make_vendor()
    login(make_user(UserRole.OFFICER))
    created = client.post(
        f"/api/vendors/{vendor.id}/contacts",
        json={"name": "Əli Məmmədov", "email": "ali@example.az", "is_primary": True},
    )
    assert created.status_code == 201
    contact_id = created.json()["id"]
    assert _audit(session, "contact", contact_id)

    patched = client.patch(
        f"/api/vendors/{vendor.id}/contacts/{contact_id}", json={"name": "Əli M."}
    )
    assert patched.json()["name"] == "Əli M."
    assert client.delete(f"/api/vendors/{vendor.id}/contacts/{contact_id}").status_code == 204


def test_only_one_contact_stays_primary(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    vendor = make_vendor()
    login(make_user(UserRole.OFFICER))
    for name in ("First", "Second"):
        client.post(f"/api/vendors/{vendor.id}/contacts", json={"name": name, "is_primary": True})
    contacts = client.get(f"/api/vendors/{vendor.id}/contacts").json()
    assert sum(1 for row in contacts if row["is_primary"]) == 1


def test_the_primary_contact_owning_the_portal_account_cannot_be_deleted(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    """Contract: deleting it would orphan the login."""
    vendor = make_vendor()
    account = make_user(UserRole.VENDOR, vendor=vendor)
    login(make_user(UserRole.OFFICER))
    created = client.post(
        f"/api/vendors/{vendor.id}/contacts",
        json={"name": "Owner", "email": account.email, "is_primary": True},
    ).json()
    assert created["has_portal_account"] is True
    response = client.delete(f"/api/vendors/{vendor.id}/contacts/{created['id']}")
    assert response.status_code == 409


# ── categories ──────────────────────────────────────────────────────────────
def test_a_vendor_selects_and_an_officer_confirms(
    client: TestClient, make_vendor: Any, make_user: Any, make_category: Any, login: Any
) -> None:
    """Spec §11.1: only a confirmed category makes the vendor a matching candidate."""
    vendor = make_vendor()
    category = make_category(code="steel-test")
    login(make_user(UserRole.VENDOR, vendor=vendor))
    selected = client.put(
        f"/api/vendors/{vendor.id}/categories", json={"category_codes": [category.code]}
    ).json()
    assert selected[0]["confirmed"] is False

    client.post("/api/auth/logout")
    client.cookies.clear()
    login(make_user(UserRole.OFFICER))
    confirmed = client.post(
        f"/api/vendors/{vendor.id}/categories/confirm", json={"category_codes": [category.code]}
    ).json()
    assert confirmed[0]["confirmed"] is True
    assert confirmed[0]["confirmed_at"] is not None


def test_replacing_the_selection_keeps_existing_confirmations(
    uow: UnitOfWork, make_vendor: Any, make_category: Any
) -> None:
    """Re-saving the form must not silently un-confirm what the officer agreed to."""
    vendor = make_vendor()
    kept, added = make_category(code="kept"), make_category(code="added")
    categories_service.set_for_vendor(uow, vendor.id, [kept.code])
    categories_service.confirm_for_vendor(uow, vendor.id, [kept.code])
    rows = categories_service.set_for_vendor(uow, vendor.id, [kept.code, added.code])
    by_code = {row.category.code: row for row in rows}
    assert by_code["kept"].confirmed is True
    assert by_code["added"].confirmed is False


def test_an_unknown_category_code_is_rejected(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    vendor = make_vendor()
    login(make_user(UserRole.OFFICER))
    response = client.put(
        f"/api/vendors/{vendor.id}/categories", json={"category_codes": ["no-such-category"]}
    )
    assert response.status_code == 422


# ── observations through the API ────────────────────────────────────────────
def test_manual_entry_needs_a_reason_and_shows_up_as_current(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    vendor = make_vendor()
    login(make_user(UserRole.OFFICER))
    short = client.post(
        f"/api/vendors/{vendor.id}/observations",
        json={"field_code": "B.5", "value": 1, "reason": "x"},
    )
    assert short.status_code == 422

    created = client.post(
        f"/api/vendors/{vendor.id}/observations",
        json={"field_code": "B.5", "value": 1_208_443, "reason": "Balance sheet 2025"},
    )
    assert created.status_code == 201
    assert created.json()["source"] == "manual"
    assert created.json()["trust_rank"] == 5
    assert created.json()["is_current"] is True


def test_the_observation_history_marks_the_current_row(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any, uow: UnitOfWork
) -> None:
    vendor = make_vendor()
    observations.record(uow, vendor.id, "E.1", 40, source=ObservationSource.EXCEL)
    observations.record(uow, vendor.id, "E.1", 90, source=ObservationSource.REGISTRY)
    uow.commit()
    login(make_user(UserRole.OFFICER))

    full = client.get(f"/api/vendors/{vendor.id}/observations").json()
    assert full["total"] == 2
    assert sum(1 for row in full["items"] if row["is_current"]) == 1

    current = client.get(f"/api/vendors/{vendor.id}/observations?current_only=true").json()
    assert current["total"] == 1
    assert current["items"][0]["value"] == 90


def test_observations_can_be_filtered_by_field_and_source(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any, uow: UnitOfWork
) -> None:
    vendor = make_vendor()
    observations.record(uow, vendor.id, "E.1", 40, source=ObservationSource.EXCEL)
    observations.record(uow, vendor.id, "B.1", 1, source=ObservationSource.PORTAL)
    uow.commit()
    login(make_user(UserRole.OFFICER))
    by_field = client.get(f"/api/vendors/{vendor.id}/observations?field_code=E.1").json()
    by_source = client.get(f"/api/vendors/{vendor.id}/observations?source=portal").json()
    assert by_field["total"] == 1 and by_field["items"][0]["field_code"] == "E.1"
    assert by_source["total"] == 1 and by_source["items"][0]["field_code"] == "B.1"
