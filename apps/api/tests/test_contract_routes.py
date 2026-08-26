"""The implemented routes against ``docs/openapi.yaml`` (ADR-006).

The contract is the source of truth and is served verbatim; these tests keep the code honest
about it. Phase 1B/1C implements a subset — health, auth, vendors, admin and events — so the
check is directional: every route this process serves must exist in the contract, at the same
path and method. The reverse (every contract operation has a route) becomes an equality once
phase 2 lands, and the list of what is still missing is asserted explicitly so it shrinks
deliberately rather than by accident.
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from vendoriq_api.openapi import OPENAPI_PATH
from vendoriq_api.schemas import Health, Settings, Vendor

METHODS = {"get", "post", "put", "patch", "delete"}

#: Groups phase 2 implements. Listed by tag so a new endpoint inside an implemented group
#: cannot hide here.
UNIMPLEMENTED_TAGS = {
    "applications",
    "cycles",
    "scoring-models",
    "projects",
    "intel",
    "integrations",
}

#: Individually deferred operations inside groups that are otherwise implemented.
DEFERRED_OPERATIONS = {
    # Excel export of the register — the exporter lands with the importer's workbook writer.
    "exportVendors",
    "exportAuditLog",
}


def contract() -> dict[str, Any]:
    document = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def contract_index() -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (method.upper(), path): operation
        for path, item in contract()["paths"].items()
        for method, operation in item.items()
        if method in METHODS
    }


def _walk(app: Any) -> Any:
    """Yield every route object, flattening FastAPI's lazily-included routers.

    ``include_router`` does not copy routes onto ``app.routes`` in FastAPI 0.14x; it appends
    one ``_IncludedRouter`` placeholder that resolves its children at request time. Anything
    that inspects the route table — this test, a permission audit, a URL map — has to expand
    it, so the expansion lives here once.
    """
    for route in app.routes:
        contexts = getattr(route, "effective_route_contexts", None)
        if callable(contexts):
            yield from contexts()
        else:
            yield route


def served_routes(app: Any) -> set[tuple[str, str]]:
    """(method, contract path) for every documented route the process serves."""
    routes: set[tuple[str, str]] = set()
    for route in _walk(app):
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        if not getattr(route, "include_in_schema", True):
            continue
        if not path.startswith("/api/"):
            continue
        trimmed = path[len("/api") :]
        for method in methods:
            if method.lower() in METHODS:
                routes.add((method, trimmed))
    return routes


def test_the_route_walker_actually_finds_routes(app: Any) -> None:
    """Guards the test above: an empty walk would make every assertion vacuously pass."""
    assert len(served_routes(app)) > 30


def test_every_served_route_is_in_the_contract(app: Any) -> None:
    """A route the contract does not declare is an undocumented public API."""
    documented = set(contract_index())
    served = served_routes(app)
    # /openapi.json, /openapi.yaml, /docs and /redoc are the contract's own delivery and are
    # excluded from the schema; anything else that is served must be declared.
    stray = served - documented
    assert stray == set(), f"served but not in the contract: {sorted(stray)}"


def test_the_implemented_groups_are_complete(app: Any) -> None:
    """Inside an implemented tag, every contract operation must have a live route."""
    served = served_routes(app)
    missing: list[str] = []
    for (method, path), operation in contract_index().items():
        tag = operation["tags"][0]
        if tag in UNIMPLEMENTED_TAGS or operation["operationId"] in DEFERRED_OPERATIONS:
            continue
        if (method, path) not in served:
            missing.append(f"{operation['operationId']} {method} {path}")
    assert missing == [], f"declared but not served: {sorted(missing)}"


def test_the_deferred_list_only_names_real_operations() -> None:
    """A stale entry here would silently excuse an endpoint that no longer exists."""
    declared = {operation["operationId"] for operation in contract_index().values()}
    assert declared >= DEFERRED_OPERATIONS


# ── response shapes ─────────────────────────────────────────────────────────
def _schema(name: str) -> dict[str, Any]:
    schema = contract()["components"]["schemas"][name]
    assert isinstance(schema, dict)
    return schema


def _required(name: str) -> set[str]:
    return set(_schema(name).get("required", []))


@pytest.mark.parametrize(
    ("model", "schema_name"),
    [(Health, "Health"), (Vendor, "Vendor"), (Settings, "Settings")],
)
def test_the_models_carry_every_required_contract_field(model: Any, schema_name: str) -> None:
    assert _required(schema_name) <= set(model.model_fields)


def test_the_health_response_matches_the_contract(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert _required("Health") <= set(body)


def test_the_vendor_page_uses_the_collection_envelope(
    client: TestClient, make_user: Any, login: Any
) -> None:
    """Contract convention: collections are always `{items, total, page, page_size}`."""
    login(
        make_user(__import__("vendoriq_api.models.enums", fromlist=["UserRole"]).UserRole.OFFICER)
    )
    body = client.get("/api/vendors").json()
    assert set(body) == {"items", "total", "page", "page_size"}


def test_errors_use_the_one_envelope(client: TestClient) -> None:
    """Contract convention: `{"error": {code, message, details}}`, always."""
    body = client.get("/api/vendors").json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] in set(
        _schema("ErrorEnvelope")["properties"]["error"]["properties"]["code"]["enum"]
    )


def test_the_enums_the_api_serialises_match_the_contract() -> None:
    """A value the code can emit but the contract does not list breaks every client."""
    from vendoriq_api.models import enums

    pairs = [
        (enums.VendorType, "VendorType"),
        (enums.VendorStatus, "VendorStatus"),
        (enums.ApplicationStatus, "ApplicationStatus"),
        (enums.ScoreClass, "ScoreClass"),
        (enums.CategoryKind, "CategoryKind"),
        (enums.ObservationSource, "ObservationSource"),
        (enums.DocumentStatus, "DocumentStatus"),
        (enums.UserRole, "UserRole"),
        (enums.EventType, "EventType"),
        (enums.Scope, "Scope"),
    ]
    for enum_cls, schema_name in pairs:
        assert {member.value for member in enum_cls} == set(_schema(schema_name)["enum"]), (
            schema_name
        )


def test_the_adapter_key_enum_is_a_documented_superset() -> None:
    """The registry split (``registry_tax`` / ``registry_licence``) is not yet in the contract.

    Phase 1B was told to add the constants only. This test states the divergence rather than
    letting it be discovered later: everything the contract lists exists in the enum, and the
    two extra members are exactly the split.
    """
    from vendoriq_api.models.enums import CONTRACT_ADAPTER_KEYS, AdapterKey

    contract_values = set(_schema("AdapterKey")["enum"])
    assert {key.value for key in CONTRACT_ADAPTER_KEYS} == contract_values
    assert {key.value for key in AdapterKey} - contract_values == {
        "registry_tax",
        "registry_licence",
    }
