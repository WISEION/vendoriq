"""Every integration endpoint, and every refusal (task 2E, contract tag ``integrations``).

The refusals are the point of half of this file. An API key that can mint another API key,
a webhook secret that can be read back, a preview that quietly writes, or a revoked key that
keeps working for one more minute are each a security failure that a green "it returns 200"
test would never catch.
"""

from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from vendoriq_api.models import ApiKey, FieldObservation, ImportPreview, SyncLog, Webhook
from vendoriq_api.models.enums import ObservationSource, UserRole

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = REPO_ROOT / "seed/fixtures"
WESA_FORM = FIXTURES / "98dfa150-WESA_Prekvalifikasiya_Muraciet_Formasi.xlsx"
BLANK_FORM = FIXTURES / "55783af7-Form_Prekvalifikasiya_Muraciet_Formasi.xlsx"
REV4_WORKBOOK = FIXTURES / "3b699c4f-Rev4_Prekvalifikasiya_TQS2026006.xlsx"

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ── a local endpoint for the adapter and the webhook to reach ───────────────
class _Local(BaseHTTPRequestHandler):
    payload: bytes = b"{}"
    status: int = 200
    posts: ClassVar[list[dict[str, Any]]] = []

    def do_GET(self) -> None:
        self.send_response(type(self).status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(type(self).payload)))
        self.end_headers()
        self.wfile.write(type(self).payload)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        type(self).posts.append(
            {
                "body": self.rfile.read(length),
                "headers": {k.lower(): v for k, v in self.headers.items()},
            }
        )
        self.send_response(type(self).status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *_: Any) -> None:
        return


@pytest.fixture
def local() -> Iterator[tuple[str, type[_Local]]]:
    _Local.payload = b"{}"
    _Local.status = 200
    _Local.posts = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Local)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", _Local
    finally:
        server.shutdown()
        server.server_close()


def _upload(path: Path, name: str | None = None) -> dict[str, Any]:
    return {"file": (name or path.name, path.read_bytes(), XLSX_MIME)}


# ── adapters ────────────────────────────────────────────────────────────────
def test_the_adapter_list_covers_the_contract(
    client: TestClient, make_user: Any, login: Any
) -> None:
    login(make_user(UserRole.OFFICER))

    response = client.get("/api/integrations/adapters")

    assert response.status_code == 200
    body = response.json()
    assert {item["key"] for item in body} == {
        "generic_rest",
        "csv",
        "erp_1c",
        "erp_sap",
        "erp_odoo",
        "registry",
        "excel",
    }
    for item in body:
        assert item["name_az"] and item["name_en"]
        assert set(item) >= {"status", "record_count", "last_sync_at", "configured_vendor_count"}


def test_the_registry_adapter_is_listed_as_planned(
    client: TestClient, make_user: Any, login: Any
) -> None:
    """It must never present as "active": nothing behind it can verify anything."""
    login(make_user(UserRole.OFFICER))

    body = client.get("/api/integrations/adapters").json()

    registry = next(item for item in body if item["key"] == "registry")
    assert registry["status"] == "planned"
    assert registry["record_count"] == 0


def test_a_vendor_may_not_see_the_adapter_list(
    client: TestClient, make_user: Any, make_vendor: Any, login: Any
) -> None:
    vendor = make_vendor()
    login(make_user(UserRole.VENDOR, vendor=vendor))

    assert client.get("/api/integrations/adapters").status_code == 403


def test_an_unknown_adapter_key_is_a_404(
    client: TestClient, make_user: Any, make_vendor: Any, login: Any
) -> None:
    login(make_user(UserRole.OFFICER))
    vendor = make_vendor()

    response = client.get(f"/api/integrations/adapters/no_such/vendors/{vendor.id}/config")

    assert response.status_code == 404


def test_the_registry_split_keys_are_not_addressable(
    client: TestClient, make_user: Any, make_vendor: Any, login: Any
) -> None:
    """``registry_tax``/``registry_licence`` exist in the enum but not in the contract."""
    login(make_user(UserRole.OFFICER))
    vendor = make_vendor()

    response = client.get(f"/api/integrations/adapters/registry_tax/vendors/{vendor.id}/config")

    assert response.status_code == 404


# ── adapter configuration ───────────────────────────────────────────────────
def test_only_an_admin_may_configure_a_connector(
    client: TestClient, make_user: Any, make_vendor: Any, login: Any, logout: Any
) -> None:
    vendor = make_vendor()
    path = f"/api/integrations/adapters/generic_rest/vendors/{vendor.id}/config"
    body = {"is_enabled": True, "base_url": "https://erp.example/api"}

    login(make_user(UserRole.OFFICER))
    assert client.put(path, json=body).status_code == 403
    logout()

    login(make_user(UserRole.ADMIN))
    assert client.put(path, json=body).status_code == 200


def test_a_stored_secret_is_never_returned(
    client: TestClient, make_user: Any, make_vendor: Any, login: Any
) -> None:
    vendor = make_vendor()
    login(make_user(UserRole.ADMIN))
    path = f"/api/integrations/adapters/generic_rest/vendors/{vendor.id}/config"

    stored = client.put(
        path,
        json={
            "is_enabled": True,
            "base_url": "https://erp.example/api",
            "auth_type": "bearer",
            "secret": "super-secret-token",
        },
    ).json()
    read_back = client.get(path).json()

    assert "secret" not in stored
    assert stored["secret_masked"] == "••••••••"
    assert read_back["secret_masked"] == "••••••••"
    assert "super-secret-token" not in json.dumps(stored) + json.dumps(read_back)


def test_echoing_the_mask_back_keeps_the_stored_secret(
    client: TestClient,
    session: Session,
    make_user: Any,
    make_vendor: Any,
    login: Any,
) -> None:
    """Contract: "a masked value sent back unchanged leaves the stored secret alone"."""
    from vendoriq_api.adapters import config_store
    from vendoriq_api.models.enums import AdapterKey

    vendor = make_vendor()
    login(make_user(UserRole.ADMIN))
    path = f"/api/integrations/adapters/generic_rest/vendors/{vendor.id}/config"
    client.put(path, json={"is_enabled": True, "base_url": "https://a", "secret": "keep-me"})

    client.put(path, json={"base_url": "https://b", "secret": "••••••••"})

    stored = config_store.load(session, AdapterKey.GENERIC_REST, vendor.id)
    assert stored is not None
    assert stored.secret == "keep-me"
    assert stored.base_url == "https://b"


def test_an_empty_secret_clears_it(
    client: TestClient,
    session: Session,
    make_user: Any,
    make_vendor: Any,
    login: Any,
) -> None:
    from vendoriq_api.adapters import config_store
    from vendoriq_api.models.enums import AdapterKey

    vendor = make_vendor()
    login(make_user(UserRole.ADMIN))
    path = f"/api/integrations/adapters/generic_rest/vendors/{vendor.id}/config"
    client.put(path, json={"is_enabled": True, "base_url": "https://a", "secret": "old"})

    client.put(path, json={"secret": ""})

    stored = config_store.load(session, AdapterKey.GENERIC_REST, vendor.id)
    assert stored is not None and stored.secret is None


def test_configuring_a_connector_writes_an_audit_row_without_the_secret(
    client: TestClient, session: Session, make_user: Any, make_vendor: Any, login: Any
) -> None:
    from vendoriq_api.models import AuditEvent

    vendor = make_vendor()
    login(make_user(UserRole.ADMIN))
    client.put(
        f"/api/integrations/adapters/generic_rest/vendors/{vendor.id}/config",
        json={"is_enabled": True, "base_url": "https://erp", "secret": "audit-leak-check"},
    )

    rows = session.scalars(
        select(AuditEvent).where(AuditEvent.entity_type == "adapter_config")
    ).all()

    assert rows
    assert all("audit-leak-check" not in json.dumps(row.after) for row in rows)
    assert rows[-1].after is not None and rows[-1].after["has_secret"] is True


def test_adapter_configuration_never_writes_a_setting_row(
    client: TestClient, session: Session, make_user: Any, make_vendor: Any, login: Any
) -> None:
    """Connector settings belong in ``adapter_config``, not smuggled into ``setting``.

    They were `setting` rows while no table existed. That is the arrangement this test
    exists to prevent coming back: ``services/settings_store.py`` refuses every key outside
    its five declared groups, so configuration parked there is invisible to the admin
    settings screen and uneditable through it — while still deciding whether a scheduled
    pull runs against a vendor's ERP.
    """
    from vendoriq_api.models import AdapterConfig as AdapterConfigRow
    from vendoriq_api.models import Setting

    vendor = make_vendor()
    login(make_user(UserRole.ADMIN))
    before = session.scalar(select(func.count()).select_from(Setting))

    client.put(
        f"/api/integrations/adapters/generic_rest/vendors/{vendor.id}/config",
        json={
            "is_enabled": True,
            "base_url": "https://erp.example/api",
            "auth_type": "bearer",
            "secret": "token",
            "field_map": {"a.b": "B.1"},
        },
    )

    assert session.scalar(select(func.count()).select_from(Setting)) == before
    assert not session.scalars(select(Setting).where(Setting.key.like("integration.%"))).all()
    row = session.scalars(
        select(AdapterConfigRow).where(AdapterConfigRow.vendor_id == vendor.id)
    ).one()
    assert row.adapter == "generic_rest"
    assert row.is_enabled is True
    assert row.field_map == {"a.b": "B.1"}


def test_configuring_the_same_connector_twice_updates_one_row(
    client: TestClient, session: Session, make_user: Any, make_vendor: Any, login: Any
) -> None:
    """The unique constraint on (adapter, vendor_id) is the point of the table."""
    from vendoriq_api.models import AdapterConfig as AdapterConfigRow

    vendor = make_vendor()
    login(make_user(UserRole.ADMIN))
    path = f"/api/integrations/adapters/generic_rest/vendors/{vendor.id}/config"

    client.put(path, json={"is_enabled": True, "base_url": "https://one"})
    client.put(path, json={"base_url": "https://two"})

    rows = session.scalars(
        select(AdapterConfigRow).where(AdapterConfigRow.vendor_id == vendor.id)
    ).all()
    assert len(rows) == 1
    assert rows[0].base_url == "https://two"
    assert rows[0].is_enabled is True


def test_the_stored_secret_is_not_in_the_configuration_row_the_api_returns(
    client: TestClient, session: Session, make_user: Any, make_vendor: Any, login: Any
) -> None:
    """The column holds it (an outbound call needs it); no response path exposes it."""
    from vendoriq_api.models import AdapterConfig as AdapterConfigRow

    vendor = make_vendor()
    login(make_user(UserRole.ADMIN))
    path = f"/api/integrations/adapters/generic_rest/vendors/{vendor.id}/config"

    client.put(path, json={"is_enabled": True, "base_url": "https://erp", "secret": "in-column"})
    body = client.get(path).json()

    row = session.scalars(
        select(AdapterConfigRow).where(AdapterConfigRow.vendor_id == vendor.id)
    ).one()
    assert row.secret == "in-column"
    assert "in-column" not in json.dumps(body)
    assert body["secret_masked"] == "••••••••"


def test_the_excel_adapter_is_not_configured_per_vendor(
    client: TestClient, make_user: Any, make_vendor: Any, login: Any
) -> None:
    vendor = make_vendor()
    login(make_user(UserRole.ADMIN))

    response = client.put(
        f"/api/integrations/adapters/excel/vendors/{vendor.id}/config",
        json={"is_enabled": True},
    )

    assert response.status_code == 409


# ── running a sync ──────────────────────────────────────────────────────────
def test_a_configured_connector_writes_observations_and_a_sync_log(
    client: TestClient,
    session: Session,
    make_user: Any,
    make_vendor: Any,
    login: Any,
    local: tuple[str, type[_Local]],
) -> None:
    base, handler = local
    handler.payload = json.dumps({"fin": {"turnover": "3 400 000", "equity": 900000}}).encode()
    vendor = make_vendor()
    login(make_user(UserRole.ADMIN))
    client.put(
        f"/api/integrations/adapters/generic_rest/vendors/{vendor.id}/config",
        json={
            "is_enabled": True,
            "base_url": f"{base}/erp",
            "field_map": {"fin.turnover": "B.1", "fin.equity": "B.2"},
        },
    )

    response = client.post(
        "/api/integrations/adapters/generic_rest/sync", json={"vendor_id": str(vendor.id)}
    )

    assert response.status_code == 202
    body = response.json()
    assert body["result"] == "success"
    assert body["fields_written"] == 2
    assert body["adapter"] == "generic_rest"
    written = session.scalars(
        select(FieldObservation).where(FieldObservation.vendor_id == vendor.id)
    ).all()
    assert {row.field_code for row in written} == {"B.1", "B.2"}
    assert all(row.source is ObservationSource.API for row in written)
    assert all(row.source_ref for row in written)


def test_a_registry_sync_is_refused_with_409(
    client: TestClient, make_user: Any, make_vendor: Any, login: Any
) -> None:
    """The most important refusal in the system: no fabricated tax clearance, ever."""
    vendor = make_vendor()
    login(make_user(UserRole.ADMIN))

    response = client.post(
        "/api/integrations/adapters/registry/sync", json={"vendor_id": str(vendor.id)}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
    assert response.json()["error"]["details"]["adapter_code"] == "registry_not_configured"


def test_a_registry_sync_writes_no_observation(
    client: TestClient, session: Session, make_user: Any, make_vendor: Any, login: Any
) -> None:
    vendor = make_vendor()
    login(make_user(UserRole.ADMIN))

    client.post("/api/integrations/adapters/registry/sync", json={"vendor_id": str(vendor.id)})

    assert (
        session.scalar(
            select(func.count())
            .select_from(FieldObservation)
            .where(FieldObservation.vendor_id == vendor.id)
        )
        == 0
    )


def test_an_unconfigured_adapter_is_refused_with_409(
    client: TestClient, make_user: Any, make_vendor: Any, login: Any
) -> None:
    vendor = make_vendor()
    login(make_user(UserRole.ADMIN))

    response = client.post(
        "/api/integrations/adapters/erp_sap/sync", json={"vendor_id": str(vendor.id)}
    )

    assert response.status_code == 409


def test_a_run_that_failed_is_still_logged_with_zero_records(
    client: TestClient,
    session: Session,
    make_user: Any,
    make_vendor: Any,
    login: Any,
) -> None:
    """ "It ran and failed" and "it was never configured" are different answers."""
    vendor = make_vendor()
    login(make_user(UserRole.ADMIN))
    client.put(
        f"/api/integrations/adapters/generic_rest/vendors/{vendor.id}/config",
        json={
            "is_enabled": True,
            "base_url": "http://127.0.0.1:9/erp",
            "field_map": {"a": "B.1"},
        },
    )

    response = client.post(
        "/api/integrations/adapters/generic_rest/sync", json={"vendor_id": str(vendor.id)}
    )

    assert response.status_code == 202
    body = response.json()
    assert body["result"] == "failed"
    assert body["fields_written"] == 0
    assert body["warnings"][0]["code"] == "source_unreachable"
    assert body["warnings"][0]["message_az"]


def test_a_mocked_erp_sync_writes_what_the_fixture_says(
    client: TestClient, session: Session, make_user: Any, make_vendor: Any, login: Any
) -> None:
    vendor = make_vendor(voen="1000000001", external_ref="1000000001")
    login(make_user(UserRole.ADMIN))
    client.put(
        f"/api/integrations/adapters/erp_1c/vendors/{vendor.id}/config",
        json={"is_enabled": True, "base_url": "https://1c.example/odata"},
    )

    body = client.post(
        "/api/integrations/adapters/erp_1c/sync", json={"vendor_id": str(vendor.id)}
    ).json()

    assert body["result"] == "success"
    assert body["fields_written"] == 7
    rows = session.scalars(
        select(FieldObservation).where(FieldObservation.vendor_id == vendor.id)
    ).all()
    assert all((row.source_ref or "").startswith("mock:erp_1c/") for row in rows)


def test_an_officer_may_run_a_sync_but_a_commission_member_may_not(
    client: TestClient, make_user: Any, make_vendor: Any, login: Any, logout: Any
) -> None:
    vendor = make_vendor()
    path = "/api/integrations/adapters/generic_rest/sync"

    login(make_user(UserRole.COMMISSION))
    assert client.post(path, json={"vendor_id": str(vendor.id)}).status_code == 403
    logout()

    login(make_user(UserRole.OFFICER))
    # 409 rather than 403: allowed to ask, but nothing is configured.
    assert client.post(path, json={"vendor_id": str(vendor.id)}).status_code == 409


def test_syncing_an_unknown_vendor_is_a_404(client: TestClient, make_user: Any, login: Any) -> None:
    login(make_user(UserRole.ADMIN))

    response = client.post(
        "/api/integrations/adapters/generic_rest/sync", json={"vendor_id": str(uuid.uuid4())}
    )

    assert response.status_code == 404


# ── the sync log ────────────────────────────────────────────────────────────
def test_the_sync_log_pages_and_filters(
    client: TestClient, session: Session, make_user: Any, make_vendor: Any, login: Any
) -> None:
    from datetime import UTC, datetime

    from vendoriq_api.models.enums import SyncResult

    vendor = make_vendor()
    for index in range(3):
        session.add(
            SyncLog(
                adapter="csv" if index else "generic_rest",
                vendor_id=vendor.id,
                started_at=datetime.now(UTC),
                fields_written=index,
                warnings=[],
                result=SyncResult.SUCCESS,
            )
        )
    session.commit()
    login(make_user(UserRole.MANAGER))

    everything = client.get("/api/integrations/sync-log", params={"vendor_id": str(vendor.id)})
    filtered = client.get("/api/integrations/sync-log", params={"adapter": "csv"})

    assert everything.status_code == 200
    assert set(everything.json()) == {"items", "total", "page", "page_size"}
    assert everything.json()["total"] == 3
    assert all(item["adapter"] == "csv" for item in filtered.json()["items"])
    assert everything.json()["items"][0]["vendor_name"] == vendor.legal_name


# ── the Excel import: preview ───────────────────────────────────────────────
def test_the_wesa_preview_reports_the_anomalies_the_parser_found(
    client: TestClient, make_user: Any, login: Any
) -> None:
    login(make_user(UserRole.OFFICER))

    response = client.post("/api/integrations/excel-import/preview", files=_upload(WESA_FORM))

    assert response.status_code == 200
    body = response.json()
    codes = sorted(warning["code"] for warning in body["warnings"])
    assert codes == [
        "currency_label_mismatch",
        "document_status_missing",
        "mixed_percent_format",
        "no_expiry_literal",
        "stale_certificate",
        "unparsable_date",
        "unparsable_value",
        "unparsable_value",
    ]
    # The three the brief names explicitly (§1.11).
    assert {"stale_certificate", "mixed_percent_format", "currency_label_mismatch"} <= set(codes)
    assert all(warning["message_az"] and warning["message_en"] for warning in body["warnings"])
    # `severity` is required by the contract: an officer triaging eight warnings has to know
    # which one blocks the import. The stale tax certificate is the only error here.
    assert all(warning["severity"] in ("error", "warning", "info") for warning in body["warnings"])
    errors = [w["code"] for w in body["warnings"] if w["severity"] == "error"]
    assert errors == ["stale_certificate"]


def test_the_wesa_preview_carries_the_mapping_the_officer_confirms(
    client: TestClient, make_user: Any, login: Any
) -> None:
    login(make_user(UserRole.OFFICER))

    body = client.post("/api/integrations/excel-import/preview", files=_upload(WESA_FORM)).json()

    codes = {item["field_code"]: item for item in body["fields"]}
    assert codes["A.3"]["value"] == "1003915341"
    assert body["derived_raw"]["B.1"] == 5189111.38
    assert body["derived_raw"]["C.1"] == 10
    assert len(body["tables"]["C.t1"]) == 10
    assert {item["code"] for item in body["documents"]} >= {"A-01", "A-05"}
    assert body["kind"] == "application_form"


def test_a_preview_writes_nothing_into_the_register(
    client: TestClient, session: Session, make_user: Any, make_vendor: Any, login: Any
) -> None:
    """Step one of two. The whole design of the import rests on this being true.

    "Nothing" means nothing the register is made of: no observation, no sync-log row. The
    preview does write its own ``import_preview`` row — that is what the table is for, and
    it is what lets the confirmation land on a different API process than the upload did.
    """
    vendor = make_vendor(voen="1003915341")
    login(make_user(UserRole.OFFICER))
    before_observations = session.scalar(select(func.count()).select_from(FieldObservation))
    before_runs = session.scalar(select(func.count()).select_from(SyncLog))

    response = client.post("/api/integrations/excel-import/preview", files=_upload(WESA_FORM))

    assert response.status_code == 200
    assert response.json()["matched_vendor"]["id"] == str(vendor.id)
    assert session.scalar(select(func.count()).select_from(FieldObservation)) == before_observations
    assert session.scalar(select(func.count()).select_from(SyncLog)) == before_runs

    stored = session.get(ImportPreview, uuid.UUID(response.json()["preview_id"]))
    assert stored is not None
    assert stored.consumed_at is None
    assert stored.vendor_id == vendor.id
    assert stored.filename == WESA_FORM.name


def test_the_preview_matches_the_vendor_on_voen(
    client: TestClient, make_user: Any, make_vendor: Any, login: Any
) -> None:
    make_vendor(voen="1003915341", legal_name="VVESA MMC")
    login(make_user(UserRole.OFFICER))

    body = client.post("/api/integrations/excel-import/preview", files=_upload(WESA_FORM)).json()

    assert body["matched_vendor"]["legal_name"] == "VVESA MMC"


def test_the_preview_shows_what_would_change(
    client: TestClient, session: Session, make_user: Any, make_vendor: Any, login: Any, uow: Any
) -> None:
    from vendoriq_api.services import observations as observations_service

    vendor = make_vendor(voen="1003915341")
    observations_service.record(
        uow, vendor.id, "A.3", "1003915341", source=ObservationSource.MANUAL
    )
    uow.commit()
    login(make_user(UserRole.OFFICER))

    body = client.post("/api/integrations/excel-import/preview", files=_upload(WESA_FORM)).json()

    same = next(item for item in body["fields"] if item["field_code"] == "A.3")
    assert same["current_value"] == "1003915341"
    assert same["will_change"] is False


def test_the_blank_template_previews_without_answers(
    client: TestClient, make_user: Any, login: Any
) -> None:
    login(make_user(UserRole.OFFICER))

    body = client.post("/api/integrations/excel-import/preview", files=_upload(BLANK_FORM)).json()

    assert body["fields"] == []
    assert body["matched_vendor"] is None
    assert any(item["code"] == "mandatory_cell_empty" for item in body["warnings"])


def test_a_scoring_workbook_needs_the_vendor_named(
    client: TestClient, make_user: Any, login: Any
) -> None:
    """Thirteen participants and no vendor id is a question, not something to guess."""
    login(make_user(UserRole.OFFICER))

    response = client.post(
        "/api/integrations/excel-import/preview",
        files=_upload(REV4_WORKBOOK),
        data={"kind": "scoring_workbook"},
    )

    assert response.status_code == 422
    assert len(response.json()["error"]["details"]["participants"]) == 13


def test_a_scoring_workbook_column_previews_for_a_named_vendor(
    client: TestClient, make_user: Any, make_vendor: Any, login: Any
) -> None:
    vendor = make_vendor(voen="1003915341")
    login(make_user(UserRole.OFFICER))

    response = client.post(
        "/api/integrations/excel-import/preview",
        files=_upload(REV4_WORKBOOK),
        data={"kind": "scoring_workbook", "vendor_id": str(vendor.id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "scoring_workbook"
    assert {item["field_code"] for item in body["fields"]} >= {"A.1", "B.1", "C.1"}


# ── the Excel import: file validation (spec §13) ────────────────────────────
def test_a_pdf_renamed_to_xlsx_is_refused(client: TestClient, make_user: Any, login: Any) -> None:
    login(make_user(UserRole.OFFICER))

    response = client.post(
        "/api/integrations/excel-import/preview",
        files={"file": ("evil.xlsx", b"%PDF-1.7\n%fake", XLSX_MIME)},
    )

    assert response.status_code == 415
    assert response.json()["error"]["details"]["reason"] == "magic"


def test_a_zip_that_is_not_a_workbook_is_refused(
    client: TestClient, make_user: Any, login: Any
) -> None:
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", "<w:document/>")
    login(make_user(UserRole.OFFICER))

    response = client.post(
        "/api/integrations/excel-import/preview",
        files={"file": ("doc.xlsx", buffer.getvalue(), XLSX_MIME)},
    )

    assert response.status_code == 415
    assert response.json()["error"]["details"]["reason"] == "no_workbook_part"


def test_a_wrong_extension_is_refused(client: TestClient, make_user: Any, login: Any) -> None:
    login(make_user(UserRole.OFFICER))

    response = client.post(
        "/api/integrations/excel-import/preview",
        files={"file": ("report.pdf", WESA_FORM.read_bytes(), "application/pdf")},
    )

    assert response.status_code == 415


def test_an_oversize_upload_is_refused(
    client: TestClient, make_user: Any, login: Any, settings: Any
) -> None:
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/workbook.xml", "x")
    payload = buffer.getvalue() + b"\0" * (settings.upload_max_bytes + 1)
    login(make_user(UserRole.OFFICER))

    response = client.post(
        "/api/integrations/excel-import/preview",
        files={"file": ("big.xlsx", payload, XLSX_MIME)},
    )

    assert response.status_code == 413


def test_a_vendor_may_not_import(
    client: TestClient, make_user: Any, make_vendor: Any, login: Any
) -> None:
    vendor = make_vendor()
    login(make_user(UserRole.VENDOR, vendor=vendor))

    response = client.post("/api/integrations/excel-import/preview", files=_upload(WESA_FORM))

    assert response.status_code == 403


# ── the Excel import: the run ───────────────────────────────────────────────
def test_a_confirmed_preview_writes_observations_with_source_excel(
    client: TestClient, session: Session, make_user: Any, make_vendor: Any, login: Any
) -> None:
    vendor = make_vendor(voen="1003915341")
    login(make_user(UserRole.OFFICER))
    preview = client.post("/api/integrations/excel-import/preview", files=_upload(WESA_FORM)).json()

    response = client.post(
        "/api/integrations/excel-import/runs", json={"preview_id": preview["preview_id"]}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["adapter"] == "excel"
    assert body["fields_written"] > 80
    rows = session.scalars(
        select(FieldObservation).where(FieldObservation.vendor_id == vendor.id)
    ).all()
    assert all(row.source is ObservationSource.EXCEL for row in rows)
    assert all(preview["preview_id"] in (row.source_ref or "") for row in rows)


def test_a_run_may_accept_only_some_field_codes(
    client: TestClient, session: Session, make_user: Any, make_vendor: Any, login: Any
) -> None:
    vendor = make_vendor(voen="1003915341")
    login(make_user(UserRole.OFFICER))
    preview = client.post("/api/integrations/excel-import/preview", files=_upload(WESA_FORM)).json()

    body = client.post(
        "/api/integrations/excel-import/runs",
        json={"preview_id": preview["preview_id"], "accept_field_codes": ["A.3", "B.1"]},
    ).json()

    assert body["fields_written"] == 2
    written = {
        row.field_code
        for row in session.scalars(
            select(FieldObservation).where(FieldObservation.vendor_id == vendor.id)
        )
    }
    assert written == {"A.3", "B.1"}


def test_the_import_run_carries_the_anomalies_into_the_sync_log(
    client: TestClient, make_user: Any, make_vendor: Any, login: Any
) -> None:
    make_vendor(voen="1003915341")
    login(make_user(UserRole.OFFICER))
    preview = client.post("/api/integrations/excel-import/preview", files=_upload(WESA_FORM)).json()

    body = client.post(
        "/api/integrations/excel-import/runs", json={"preview_id": preview["preview_id"]}
    ).json()

    assert any(warning["code"] == "stale_certificate" for warning in body["warnings"])


def test_a_preview_can_only_be_confirmed_once(
    client: TestClient, session: Session, make_user: Any, make_vendor: Any, login: Any
) -> None:
    """A replayable confirmation would double every observation on a second click.

    Observations are append-only (ADR-004), so a duplicated import cannot be undone — it
    becomes part of the vendor's recorded history. ``consumed_at`` is stamped in the same
    transaction as the observations, so the claim and the write cannot come apart.
    """
    vendor = make_vendor(voen="1003915341")
    login(make_user(UserRole.OFFICER))
    preview = client.post("/api/integrations/excel-import/preview", files=_upload(WESA_FORM)).json()
    payload = {"preview_id": preview["preview_id"]}

    first = client.post("/api/integrations/excel-import/runs", json=payload)
    written = session.scalar(
        select(func.count())
        .select_from(FieldObservation)
        .where(FieldObservation.vendor_id == vendor.id)
    )
    second = client.post("/api/integrations/excel-import/runs", json=payload)

    assert first.status_code == 201
    assert second.status_code == 404
    assert second.json()["error"]["details"]["reason"] == "consumed"
    # The refusal wrote nothing: the count is exactly what the first run left.
    assert (
        session.scalar(
            select(func.count())
            .select_from(FieldObservation)
            .where(FieldObservation.vendor_id == vendor.id)
        )
        == written
    )
    stored = session.get(ImportPreview, uuid.UUID(preview["preview_id"]))
    assert stored is not None and stored.consumed_at is not None


def test_an_expired_preview_is_refused(
    client: TestClient, session: Session, make_user: Any, make_vendor: Any, login: Any
) -> None:
    """The contract says a preview is valid for one hour; after that the officer re-uploads.

    An hour-old mapping is a mapping against a register that has moved: the `current_value`
    column the officer approved may no longer be the current value.
    """
    make_vendor(voen="1003915341")
    login(make_user(UserRole.OFFICER))
    preview = client.post("/api/integrations/excel-import/preview", files=_upload(WESA_FORM)).json()
    stored = session.get(ImportPreview, uuid.UUID(preview["preview_id"]))
    assert stored is not None
    stored.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    session.commit()

    response = client.post(
        "/api/integrations/excel-import/runs", json={"preview_id": preview["preview_id"]}
    )

    assert response.status_code == 404
    assert response.json()["error"]["details"]["reason"] == "expired"


def test_a_preview_records_who_uploaded_it(
    client: TestClient, session: Session, make_user: Any, make_vendor: Any, login: Any
) -> None:
    """The officer who parsed the file is on the row, so the audit trail joins up."""
    make_vendor(voen="1003915341")
    officer = make_user(UserRole.OFFICER)
    login(officer)

    preview = client.post("/api/integrations/excel-import/preview", files=_upload(WESA_FORM)).json()

    stored = session.get(ImportPreview, uuid.UUID(preview["preview_id"]))
    assert stored is not None and stored.created_by == officer.id


def test_expired_previews_can_be_swept(
    client: TestClient, session: Session, uow: Any, make_user: Any, make_vendor: Any, login: Any
) -> None:
    """An abandoned upload must not accumulate; the scheduled jobs call this."""
    from vendoriq_api.services import imports as imports_service

    make_vendor(voen="1003915341")
    login(make_user(UserRole.OFFICER))
    preview = client.post("/api/integrations/excel-import/preview", files=_upload(WESA_FORM)).json()
    stored = session.get(ImportPreview, uuid.UUID(preview["preview_id"]))
    assert stored is not None
    stored.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    session.commit()

    removed = imports_service.purge_expired(uow)

    assert removed >= 1
    assert session.get(ImportPreview, uuid.UUID(preview["preview_id"])) is None


def test_an_unknown_preview_is_a_404(client: TestClient, make_user: Any, login: Any) -> None:
    login(make_user(UserRole.OFFICER))

    response = client.post(
        "/api/integrations/excel-import/runs", json={"preview_id": str(uuid.uuid4())}
    )

    assert response.status_code == 404


def test_a_run_without_a_matched_vendor_is_a_404(
    client: TestClient, make_user: Any, login: Any
) -> None:
    """The workbook matched nobody and the caller named nobody — there is nowhere to write."""
    login(make_user(UserRole.OFFICER))
    preview = client.post("/api/integrations/excel-import/preview", files=_upload(WESA_FORM)).json()
    assert preview["matched_vendor"] is None

    response = client.post(
        "/api/integrations/excel-import/runs", json={"preview_id": preview["preview_id"]}
    )

    assert response.status_code == 404


def test_a_run_can_be_directed_at_a_named_vendor(
    client: TestClient, session: Session, make_user: Any, make_vendor: Any, login: Any
) -> None:
    other = make_vendor()
    login(make_user(UserRole.OFFICER))
    preview = client.post("/api/integrations/excel-import/preview", files=_upload(WESA_FORM)).json()

    body = client.post(
        "/api/integrations/excel-import/runs",
        json={"preview_id": preview["preview_id"], "vendor_id": str(other.id)},
    ).json()

    assert body["vendor_id"] == str(other.id)
    assert session.scalar(
        select(func.count())
        .select_from(FieldObservation)
        .where(FieldObservation.vendor_id == other.id)
    )


# ── API keys ────────────────────────────────────────────────────────────────
def test_a_created_key_is_shown_once_and_never_again(
    client: TestClient, make_user: Any, login: Any
) -> None:
    login(make_user(UserRole.ADMIN))

    created = client.post(
        "/api/integrations/api-keys", json={"name": "Partner ERP", "scopes": ["vendors:read"]}
    )
    listed = client.get("/api/integrations/api-keys")

    assert created.status_code == 201
    plaintext = created.json()["key"]
    assert plaintext.startswith("vq_")
    assert "key" not in json.dumps(listed.json())
    assert plaintext not in json.dumps(listed.json())
    # The prefix survives into the listing so two keys are distinguishable; it is a prefix
    # of a 32-byte random body, so knowing it leaves the remaining entropy untouched.
    prefix = created.json()["prefix"]
    assert plaintext.startswith(prefix)
    assert listed.json()[0]["prefix"] == prefix
    assert len(prefix) < len(plaintext)


def test_only_the_hash_of_a_key_is_stored(
    client: TestClient, session: Session, make_user: Any, login: Any
) -> None:
    login(make_user(UserRole.ADMIN))

    plaintext = client.post(
        "/api/integrations/api-keys", json={"name": "Hashed", "scopes": ["intel:read"]}
    ).json()["key"]

    stored = session.scalars(select(ApiKey).where(ApiKey.name == "Hashed")).one()
    assert stored.hashed_key != plaintext
    assert len(stored.hashed_key) == 64  # sha256 hex


def test_a_key_authenticates_within_its_scopes_and_not_beyond(
    client: TestClient, make_user: Any, login: Any, logout: Any
) -> None:
    login(make_user(UserRole.ADMIN))
    key = client.post(
        "/api/integrations/api-keys", json={"name": "Reader", "scopes": ["vendors:read"]}
    ).json()["key"]
    logout()

    allowed = client.get("/api/vendors", headers={"X-API-Key": key})
    refused = client.get("/api/admin/users", headers={"X-API-Key": key})

    assert allowed.status_code == 200
    assert refused.status_code == 403


def test_a_revoked_key_is_refused_immediately(
    client: TestClient, make_user: Any, login: Any, logout: Any
) -> None:
    login(make_user(UserRole.ADMIN))
    created = client.post(
        "/api/integrations/api-keys", json={"name": "Doomed", "scopes": ["vendors:read"]}
    ).json()
    key = created["key"]
    assert client.get("/api/vendors", headers={"X-API-Key": key}).status_code == 200

    client.delete(f"/api/integrations/api-keys/{created['id']}")
    logout()

    assert client.get("/api/vendors", headers={"X-API-Key": key}).status_code == 401


def test_a_deactivated_key_is_refused(
    client: TestClient, make_user: Any, login: Any, logout: Any
) -> None:
    login(make_user(UserRole.ADMIN))
    created = client.post(
        "/api/integrations/api-keys", json={"name": "Paused", "scopes": ["vendors:read"]}
    ).json()

    client.patch(f"/api/integrations/api-keys/{created['id']}", json={"is_active": False})
    logout()

    assert client.get("/api/vendors", headers={"X-API-Key": created["key"]}).status_code == 401


def test_a_revoked_key_cannot_be_reactivated(
    client: TestClient, make_user: Any, login: Any
) -> None:
    login(make_user(UserRole.ADMIN))
    created = client.post(
        "/api/integrations/api-keys", json={"name": "Gone", "scopes": ["vendors:read"]}
    ).json()
    client.delete(f"/api/integrations/api-keys/{created['id']}")

    response = client.patch(f"/api/integrations/api-keys/{created['id']}", json={"is_active": True})

    assert response.status_code == 409


def test_an_api_key_can_never_mint_another_api_key(
    client: TestClient, make_user: Any, login: Any, logout: Any
) -> None:
    """The closure that keeps a leaked key from becoming a permanent foothold."""
    login(make_user(UserRole.ADMIN))
    key = client.post(
        "/api/integrations/api-keys",
        json={"name": "Ambitious", "scopes": ["integrations:read", "integrations:write"]},
    ).json()["key"]
    logout()

    response = client.post(
        "/api/integrations/api-keys",
        headers={"X-API-Key": key},
        json={"name": "Child", "scopes": ["admin:write"]},
    )

    assert response.status_code == 403


def test_an_api_key_cannot_manage_webhooks(
    client: TestClient, make_user: Any, login: Any, logout: Any
) -> None:
    """Redirecting the event stream is a person's decision, never a machine's."""
    login(make_user(UserRole.ADMIN))
    key = client.post(
        "/api/integrations/api-keys",
        json={"name": "Streamer", "scopes": ["integrations:read", "integrations:write"]},
    ).json()["key"]
    logout()

    listed = client.get("/api/integrations/webhooks", headers={"X-API-Key": key})
    created = client.post(
        "/api/integrations/webhooks",
        headers={"X-API-Key": key},
        json={"url": "https://attacker.example/hook", "events": ["vendor.prequalified"]},
    )

    assert listed.status_code == 403
    assert created.status_code == 403


def test_an_officer_may_not_manage_api_keys(client: TestClient, make_user: Any, login: Any) -> None:
    login(make_user(UserRole.OFFICER))

    assert client.get("/api/integrations/api-keys").status_code == 403
    assert (
        client.post(
            "/api/integrations/api-keys", json={"name": "x", "scopes": ["vendors:read"]}
        ).status_code
        == 403
    )


def test_a_key_with_no_scope_is_refused(client: TestClient, make_user: Any, login: Any) -> None:
    login(make_user(UserRole.ADMIN))

    response = client.post("/api/integrations/api-keys", json={"name": "Useless", "scopes": []})

    assert response.status_code == 422


def test_a_key_can_be_renamed_and_rescoped(client: TestClient, make_user: Any, login: Any) -> None:
    login(make_user(UserRole.ADMIN))
    created = client.post(
        "/api/integrations/api-keys", json={"name": "Before", "scopes": ["vendors:read"]}
    ).json()

    body = client.patch(
        f"/api/integrations/api-keys/{created['id']}",
        json={"name": "After", "scopes": ["vendors:read", "projects:read"]},
    ).json()

    assert body["name"] == "After"
    assert set(body["scopes"]) == {"vendors:read", "projects:read"}


def test_using_a_key_stamps_last_used_at(
    client: TestClient, make_user: Any, login: Any, logout: Any
) -> None:
    login(make_user(UserRole.ADMIN))
    created = client.post(
        "/api/integrations/api-keys", json={"name": "Tracked", "scopes": ["vendors:read"]}
    ).json()
    # The cookie wins over the header when both are present, so the session goes first.
    logout()
    client.get("/api/vendors", headers={"X-API-Key": created["key"]})

    login(make_user(UserRole.ADMIN))
    listed = client.get("/api/integrations/api-keys").json()

    row = next(item for item in listed if item["id"] == created["id"])
    assert row["last_used_at"] is not None


# ── webhooks ────────────────────────────────────────────────────────────────
def test_a_webhook_secret_is_returned_once_and_never_again(
    client: TestClient, make_user: Any, login: Any
) -> None:
    login(make_user(UserRole.ADMIN))

    created = client.post(
        "/api/integrations/webhooks",
        json={"url": "https://partner.example/hook", "events": ["vendor.prequalified"]},
    )
    listed = client.get("/api/integrations/webhooks")
    patched = client.patch(
        f"/api/integrations/webhooks/{created.json()['id']}",
        json={"url": "https://partner.example/hook2", "events": ["project.matched"]},
    )

    assert created.status_code == 201
    secret = created.json()["secret"]
    assert secret
    assert "secret" not in json.dumps(listed.json())
    assert secret not in json.dumps(listed.json())
    assert "secret" not in patched.json()
    assert secret not in json.dumps(patched.json())


def test_the_four_named_events_can_be_subscribed_to(
    client: TestClient, make_user: Any, login: Any
) -> None:
    """Brief §4.2 names these four by name."""
    login(make_user(UserRole.ADMIN))

    response = client.post(
        "/api/integrations/webhooks",
        json={
            "url": "https://partner.example/hook",
            "events": [
                "vendor.prequalified",
                "application.submitted",
                "document.expiring",
                "project.matched",
            ],
        },
    )

    assert response.status_code == 201
    assert len(response.json()["events"]) == 4


def test_an_unknown_event_type_is_refused(client: TestClient, make_user: Any, login: Any) -> None:
    login(make_user(UserRole.ADMIN))

    response = client.post(
        "/api/integrations/webhooks",
        json={"url": "https://partner.example/hook", "events": ["vendor.exploded"]},
    )

    assert response.status_code == 422


def test_a_non_http_webhook_url_is_refused(client: TestClient, make_user: Any, login: Any) -> None:
    login(make_user(UserRole.ADMIN))

    response = client.post(
        "/api/integrations/webhooks",
        json={"url": "file:///etc/passwd", "events": ["vendor.prequalified"]},
    )

    assert response.status_code == 422


def test_a_test_delivery_is_signed_and_reports_the_answer(
    client: TestClient,
    session: Session,
    make_user: Any,
    login: Any,
    local: tuple[str, type[_Local]],
) -> None:
    from vendoriq_api.services import webhooks as webhooks_service

    base, handler = local
    login(make_user(UserRole.ADMIN))
    created = client.post(
        "/api/integrations/webhooks",
        json={"url": f"{base}/hook", "events": ["vendor.prequalified"]},
    ).json()

    response = client.post(f"/api/integrations/webhooks/{created['id']}/test")

    assert response.status_code == 200
    body = response.json()
    assert body["delivered"] is True
    assert body["status_code"] == 200
    assert body["duration_ms"] >= 0
    sent = handler.posts[0]
    assert webhooks_service.verify(
        created["secret"], sent["headers"]["x-vendoriq-signature"], sent["body"]
    )


def test_a_test_delivery_to_a_dead_endpoint_reports_the_failure(
    client: TestClient, make_user: Any, login: Any
) -> None:
    login(make_user(UserRole.ADMIN))
    created = client.post(
        "/api/integrations/webhooks",
        json={"url": "http://127.0.0.1:9/hook", "events": ["vendor.prequalified"]},
    ).json()

    body = client.post(f"/api/integrations/webhooks/{created['id']}/test").json()

    assert body["delivered"] is False
    assert body["status_code"] is None
    assert body["error"]


def test_a_deleted_webhook_is_gone(
    client: TestClient, session: Session, make_user: Any, login: Any
) -> None:
    login(make_user(UserRole.ADMIN))
    created = client.post(
        "/api/integrations/webhooks",
        json={"url": "https://partner.example/hook", "events": ["project.matched"]},
    ).json()

    response = client.delete(f"/api/integrations/webhooks/{created['id']}")

    assert response.status_code == 204
    assert session.get(Webhook, uuid.UUID(created["id"])) is None


def test_a_manager_may_not_manage_webhooks(client: TestClient, make_user: Any, login: Any) -> None:
    """Integration credentials are the admin's (permission matrix, spec §3)."""
    login(make_user(UserRole.MANAGER))

    assert client.get("/api/integrations/webhooks").status_code == 403


def test_testing_an_unknown_webhook_is_a_404(
    client: TestClient, make_user: Any, login: Any
) -> None:
    login(make_user(UserRole.ADMIN))

    assert client.post(f"/api/integrations/webhooks/{uuid.uuid4()}/test").status_code == 404


# ── the whole tag, against the contract ─────────────────────────────────────
def test_every_integration_operation_in_the_contract_is_served(app: Any) -> None:
    """The gate-2 criterion for this task: no declared operation left unimplemented."""
    import yaml
    from vendoriq_api.openapi import OPENAPI_PATH

    document = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    declared = {
        (method.upper(), path)
        for path, item in document["paths"].items()
        for method, operation in item.items()
        if method in {"get", "post", "put", "patch", "delete"}
        and operation["tags"][0] == "integrations"
    }

    served: set[tuple[str, str]] = set()
    for route in app.routes:
        contexts = getattr(route, "effective_route_contexts", None)
        for item in contexts() if callable(contexts) else [route]:
            path = getattr(item, "path", "")
            for method in getattr(item, "methods", set()) or set():
                if path.startswith("/api/"):
                    served.add((method, path[len("/api") :]))

    assert declared <= served, sorted(declared - served)


def test_anonymous_callers_reach_nothing(client: TestClient) -> None:
    for method, path in (
        ("get", "/api/integrations/adapters"),
        ("get", "/api/integrations/api-keys"),
        ("get", "/api/integrations/webhooks"),
        ("get", "/api/integrations/sync-log"),
    ):
        response = getattr(client, method)(path)
        assert response.status_code == 401, path
