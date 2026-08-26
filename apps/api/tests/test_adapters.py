"""The adapter interface, its five implementations and the mapping they share (task 2E).

These tests never reach a real remote. The working connector is exercised against a
``http.server`` started on a loopback port for the duration of one test; the mocked ERP
families read the fixtures shipped beside them. That is the whole point of the interface:
the same assertions hold for both, because only ``_fetch`` differs.
"""

from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest
from vendoriq_api.adapters import (
    ADAPTERS,
    CONTRACT_ADAPTER_KEYS,
    AdapterConfig,
    AdapterNotConfiguredError,
    AdapterUnreachableError,
    CsvAdapter,
    Erp1CAdapter,
    ErpOdooAdapter,
    ErpSapAdapter,
    ExcelAdapter,
    GenericRestAdapter,
    MockedErpAdapter,
    RegistryAdapter,
    SourceAdapter,
    VendorRef,
    build,
    mask_secret,
)
from vendoriq_api.adapters.mapping import coerce, observations_from, parse_csv, resolve_path
from vendoriq_api.adapters.transport import TransportError, auth_header, validate_url
from vendoriq_api.models.enums import AdapterKey, ObservationSource

REPO_ROOT = Path(__file__).resolve().parents[3]
WESA_FORM = REPO_ROOT / "seed/fixtures/98dfa150-WESA_Prekvalifikasiya_Muraciet_Formasi.xlsx"

VENDOR = VendorRef(
    id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
    legal_name="Test Vendor MMC",
    voen="1234567890",
)


# ── a local stub, never a real remote ───────────────────────────────────────
class _Stub(BaseHTTPRequestHandler):
    """Answers whatever the test put in ``routes``; records what it was asked."""

    routes: ClassVar[dict[str, tuple[int, str, bytes]]] = {}
    seen: ClassVar[list[tuple[str, dict[str, str]]]] = []

    def do_GET(self) -> None:
        type(self).seen.append((self.path, {k.lower(): v for k, v in self.headers.items()}))
        path = self.path.split("?")[0]
        status, content_type, body = type(self).routes.get(path, (404, "text/plain", b"no"))
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_: Any) -> None:  # keep the test output readable
        return


@pytest.fixture
def stub() -> Iterator[tuple[str, type[_Stub]]]:
    _Stub.routes = {}
    _Stub.seen = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", _Stub
    finally:
        server.shutdown()
        server.server_close()


# ── the interface itself ────────────────────────────────────────────────────
def test_every_contract_adapter_key_has_an_implementation() -> None:
    """The screen lists what the contract declares; a missing class would be a blank row."""
    assert set(ADAPTERS) == set(CONTRACT_ADAPTER_KEYS)


@pytest.mark.parametrize("key", sorted(CONTRACT_ADAPTER_KEYS, key=str))
def test_every_adapter_implements_the_one_interface(key: AdapterKey) -> None:
    """`pull(vendor, since) -> Observation[]` (brief §5) — the same signature for all of them."""
    adapter = build(key)
    assert isinstance(adapter, SourceAdapter)
    assert adapter.key is key
    assert isinstance(adapter.source, ObservationSource)
    assert adapter.name_az and adapter.name_en
    assert callable(adapter.pull)


@pytest.mark.parametrize("key", sorted(CONTRACT_ADAPTER_KEYS, key=str))
def test_an_unconfigured_adapter_refuses_rather_than_returning_values(key: AdapterKey) -> None:
    """No adapter ever answers a pull it could not perform with a plausible-looking value."""
    with pytest.raises(AdapterNotConfiguredError):
        build(key).pull(VENDOR)


# ── generic REST — the working one ──────────────────────────────────────────
def _rest_config(base_url: str, **overrides: Any) -> AdapterConfig:
    return AdapterConfig(
        adapter=AdapterKey.GENERIC_REST,
        vendor_id=VENDOR.id,
        is_enabled=True,
        base_url=base_url,
        field_map={
            "financials.turnover_avg_3y": "B.1",
            "financials.equity": "B.2",
            "headcount.total": "E.1",
            "headcount.engineers": "E.2",
        },
        **overrides,
    )


def test_the_generic_adapter_reads_a_live_endpoint(stub: tuple[str, type[_Stub]]) -> None:
    base, handler = stub
    handler.routes["/erp/vendor"] = (
        200,
        "application/json",
        json.dumps(
            {
                "financials": {"turnover_avg_3y": "4 812 500,00", "equity": 1150000},
                "headcount": {"total": 64, "engineers": 9},
            }
        ).encode(),
    )
    adapter = GenericRestAdapter(_rest_config(f"{base}/erp/vendor"))

    pulled = adapter.pull(VENDOR)

    values = {item.field_code: item.value for item in pulled}
    assert values == {"B.1": 4812500.0, "B.2": 1150000, "E.1": 64, "E.2": 9}
    assert all(item.source is ObservationSource.API for item in pulled)
    # Every observation names where it came from, down to the path inside the payload.
    assert all(item.source_ref.startswith(f"{base}/erp/vendor") for item in pulled)


def test_the_generic_adapter_passes_the_vendor_key_and_the_since_filter(
    stub: tuple[str, type[_Stub]],
) -> None:
    base, handler = stub
    handler.routes["/erp/1234567890"] = (200, "application/json", b'{"headcount":{"total":12}}')
    adapter = GenericRestAdapter(_rest_config(f"{base}/erp/{{vendor}}"))

    adapter.pull(VENDOR, since=None)

    assert handler.seen[0][0] == "/erp/1234567890"


def test_the_generic_adapter_prefers_the_external_ref_as_the_remote_key() -> None:
    """`external_ref` is the cross-system id of brief §2; the VÖEN is the fallback."""
    assert VENDOR.remote_key == "1234567890"
    with_ref = VendorRef(id=VENDOR.id, legal_name="x", voen="1234567890", external_ref="ERP-77")
    assert with_ref.remote_key == "ERP-77"


def test_a_bearer_credential_becomes_a_header_and_appears_nowhere_else(
    stub: tuple[str, type[_Stub]],
) -> None:
    base, handler = stub
    handler.routes["/erp/vendor"] = (200, "application/json", b'{"headcount":{"total":5}}')
    adapter = GenericRestAdapter(
        _rest_config(f"{base}/erp/vendor", auth_type="bearer", secret="s3cr3t-token")
    )

    adapter.pull(VENDOR)

    assert handler.seen[0][1]["authorization"] == "Bearer s3cr3t-token"
    # The stored secret never appears in what the API would return about the configuration.
    assert mask_secret("s3cr3t-token") == "••••••••"
    assert "s3cr3t" not in repr(adapter.config)


def test_an_unreachable_source_reports_that_it_could_not_reach_it() -> None:
    """Rule 1 of the interface: never a plausible value, always the failure."""
    adapter = GenericRestAdapter(_rest_config("http://127.0.0.1:9/erp"))

    with pytest.raises(AdapterUnreachableError) as caught:
        adapter.pull(VENDOR)

    assert caught.value.code == "source_unreachable"
    assert caught.value.message_az


def test_an_error_status_does_not_leak_the_remote_body(stub: tuple[str, type[_Stub]]) -> None:
    base, handler = stub
    handler.routes["/erp/vendor"] = (500, "text/plain", b"Authorization: Bearer leaked-token")
    adapter = GenericRestAdapter(_rest_config(f"{base}/erp/vendor", auth_type="bearer", secret="x"))

    with pytest.raises(AdapterUnreachableError) as caught:
        adapter.pull(VENDOR)

    assert "leaked-token" not in caught.value.message_en
    assert "HTTP 500" in caught.value.message_en


def test_an_unparsable_response_is_a_failure_not_an_empty_result(
    stub: tuple[str, type[_Stub]],
) -> None:
    base, handler = stub
    handler.routes["/erp/vendor"] = (200, "application/json", b"<html>not json</html>")
    adapter = GenericRestAdapter(_rest_config(f"{base}/erp/vendor"))

    with pytest.raises(AdapterUnreachableError) as caught:
        adapter.pull(VENDOR)

    assert caught.value.code == "source_unparsable"


def test_a_reachable_source_that_matched_nothing_says_so(stub: tuple[str, type[_Stub]]) -> None:
    base, handler = stub
    handler.routes["/erp/vendor"] = (200, "application/json", b'{"unrelated": 1}')
    adapter = GenericRestAdapter(_rest_config(f"{base}/erp/vendor"))

    pulled = adapter.pull(VENDOR)

    assert len(pulled) == 0
    assert [warning.code for warning in pulled.warnings] == ["unknown_field_code"]


def test_the_csv_adapter_reads_one_row_per_vendor(stub: tuple[str, type[_Stub]]) -> None:
    base, handler = stub
    handler.routes["/erp.csv"] = (
        200,
        "text/csv",
        b"turnover;equity\nignored\n",
    )
    handler.routes["/export.csv"] = (
        200,
        "text/csv",
        b"turnover,equity,staff\n1 250 000,320000,44\n",
    )
    adapter = CsvAdapter(
        AdapterConfig(
            adapter=AdapterKey.CSV,
            vendor_id=VENDOR.id,
            is_enabled=True,
            base_url=f"{base}/export.csv",
            field_map={"turnover": "B.1", "equity": "B.2", "staff": "E.1"},
        )
    )

    values = {item.field_code: item.value for item in adapter.pull(VENDOR)}

    assert values == {"B.1": 1250000.0, "B.2": 320000.0, "E.1": 44.0}


def test_a_half_configured_connector_refuses() -> None:
    """Enabled but with no endpoint, or no field map, is not a source — it is a 409."""
    no_url = AdapterConfig(adapter=AdapterKey.GENERIC_REST, is_enabled=True, field_map={"a": "B.1"})
    no_map = AdapterConfig(
        adapter=AdapterKey.GENERIC_REST, is_enabled=True, base_url="https://erp.example"
    )
    with pytest.raises(AdapterNotConfiguredError):
        GenericRestAdapter(no_url).pull(VENDOR)
    with pytest.raises(AdapterNotConfiguredError):
        GenericRestAdapter(no_map).pull(VENDOR)


# ── the mocked ERP families ─────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("adapter_class", "key", "voen"),
    [
        (Erp1CAdapter, AdapterKey.ERP_1C, "1000000001"),
        (ErpSapAdapter, AdapterKey.ERP_SAP, "1000000003"),
        (ErpOdooAdapter, AdapterKey.ERP_ODOO, "1000000004"),
    ],
)
def test_a_mocked_erp_is_indistinguishable_at_the_interface(
    adapter_class: type[GenericRestAdapter], key: AdapterKey, voen: str
) -> None:
    """Same class hierarchy, same configuration checks, same observations, same provenance."""
    adapter = adapter_class(AdapterConfig(adapter=key, is_enabled=True, base_url="mock://fixture"))
    vendor = VendorRef(id=uuid.uuid4(), legal_name="Fixture MMC", voen=voen)

    pulled = adapter.pull(vendor)

    values = {item.field_code: item.value for item in pulled}
    assert {"B.1", "B.2", "E.1", "E.2", "C.1", "C.2", "C.3"} <= set(values)
    assert isinstance(values["B.1"], float)  # "12 400 000.00" normalised like a spreadsheet cell
    assert all(item.source is ObservationSource.API for item in pulled)
    # The source ref says out loud that this was a mock.
    assert all(item.source_ref.startswith(f"mock:{key.value}/") for item in pulled)


def test_a_mocked_erp_does_not_invent_a_record_for_an_unknown_vendor() -> None:
    adapter = Erp1CAdapter(
        AdapterConfig(adapter=AdapterKey.ERP_1C, is_enabled=True, base_url="mock://fixture")
    )

    with pytest.raises(AdapterUnreachableError) as caught:
        adapter.pull(VENDOR)

    assert caught.value.code == "mock_record_not_found"


def test_the_only_difference_between_a_mock_and_the_live_connector_is_fetch() -> None:
    """The promise of "same interface, fixture responses": one overridden method.

    Everything else a family declares is data — the fixture name, the paths to its records
    and its identity field, the default field map — so making one of them live is deleting
    a ``_fetch`` and nothing else.
    """
    for adapter_class in (Erp1CAdapter, ErpSapAdapter, ErpOdooAdapter):
        assert issubclass(adapter_class, GenericRestAdapter)
    overridden = {
        name
        for name, member in MockedErpAdapter.__dict__.items()
        if callable(member) and not name.startswith("__")
    }
    assert overridden == {"_fetch"}
    assert all(
        not callable(member)
        for name, member in Erp1CAdapter.__dict__.items()
        if not name.startswith("__")
    )


# ── the registry stub ───────────────────────────────────────────────────────
def test_the_registry_adapter_never_returns_a_verification() -> None:
    """Registry is trust rank 1 and A.4 is a knock-out: a fabricated pass is unrecoverable."""
    adapter = RegistryAdapter(
        AdapterConfig(adapter=AdapterKey.REGISTRY, is_enabled=True, base_url="https://e-taxes")
    )

    with pytest.raises(AdapterNotConfiguredError) as caught:
        adapter.pull(VENDOR)

    assert caught.value.code == "registry_not_configured"
    assert "not configured" in caught.value.message_en


def test_the_registry_adapter_has_no_code_path_that_produces_an_observation() -> None:
    """Belt and braces: the class body must not contain an ``Observation`` construction."""
    source = Path(RegistryAdapter.__module__.replace(".", "/") + ".py")
    text = (REPO_ROOT / "apps/api" / source).read_text(encoding="utf-8")
    assert "PullResult.of(" not in text
    assert "Observation(" not in text


# ── the Excel adapter ───────────────────────────────────────────────────────
def test_the_excel_importer_is_an_adapter_like_any_other() -> None:
    adapter = ExcelAdapter(
        AdapterConfig(adapter=AdapterKey.EXCEL, is_enabled=True, base_url=str(WESA_FORM))
    )

    pulled = adapter.pull(VENDOR)

    assert len(pulled) > 80
    assert all(item.source is ObservationSource.EXCEL for item in pulled)
    assert {item.field_code for item in pulled} >= {"A.3", "B.1", "C.t1"}
    assert [warning.code for warning in pulled.warnings]


def test_the_excel_adapter_reports_a_missing_workbook() -> None:
    adapter = ExcelAdapter(
        AdapterConfig(adapter=AdapterKey.EXCEL, is_enabled=True, base_url="/no/such/file.xlsx")
    )

    with pytest.raises(AdapterUnreachableError) as caught:
        adapter.pull(VENDOR)

    assert caught.value.code == "workbook_not_found"


# ── mapping and transport ───────────────────────────────────────────────────
def test_a_dotted_path_walks_dicts_and_indexes_lists() -> None:
    payload = {"d": {"results": [{"Stceg": "1000000003"}]}}
    assert resolve_path(payload, "d.results.0.Stceg") == "1000000003"
    assert resolve_path(payload, "d.results.9.Stceg") is None
    assert resolve_path(payload, "d.missing.thing") is None


def test_values_are_normalised_the_way_a_spreadsheet_cell_is() -> None:
    assert coerce("B.1", "1 250 000") == 1250000.0
    assert coerce("B.1", "1250,50") == 1250.5
    assert coerce("F.1", "Var") is True
    assert coerce("F.1", "Yoxdur") is False
    assert coerce("A.5", "  Bakı  ") == "Bakı"


def test_an_unparsable_number_is_kept_and_reported_never_dropped() -> None:
    observations, warnings = observations_from(
        {"turnover": "USD 250,000 (Property)"},
        {"turnover": "B.1"},
        source=ObservationSource.API,
        source_ref="test",
    )
    assert observations[0].value == "USD 250,000 (Property)"
    assert [warning.code for warning in warnings] == ["unparsable_value"]


def test_an_absent_path_produces_no_observation_at_all() -> None:
    observations, warnings = observations_from(
        {"present": 1},
        {"absent": "B.1", "present": "B.2"},
        source=ObservationSource.API,
        source_ref="test",
    )
    assert [item.field_code for item in observations] == ["B.2"]
    assert warnings == []


def test_csv_parsing_takes_the_first_data_row() -> None:
    assert parse_csv("a,b\n1,2\n3,4\n") == {"a": "1", "b": "2"}
    assert parse_csv("a,b\n") == {}


def test_only_http_and_https_urls_are_accepted() -> None:
    """A configured ``file://`` would turn a text field into a file read (spec §13)."""
    assert validate_url("https://erp.example/api")
    for bad in ("file:///etc/passwd", "gopher://x/1", "ftp://host/x", "/relative", "https://"):
        with pytest.raises(TransportError):
            validate_url(bad)


def test_the_auth_header_covers_the_four_declared_types() -> None:
    assert auth_header("none", None, "secret") == {}
    assert auth_header("bearer", None, "t") == {"Authorization": "Bearer t"}
    assert auth_header("api_key", None, "k") == {"X-API-Key": "k"}
    assert auth_header("basic", "u", "p") == {"Authorization": "Basic dTpw"}
    # No secret means no header, whatever the type says.
    assert auth_header("bearer", None, None) == {}
