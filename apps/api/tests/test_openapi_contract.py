"""`docs/openapi.yaml` is the contract — it must stay valid and internally consistent."""

from __future__ import annotations

import re
from typing import Any

import pytest
from vendoriq_api.openapi import OPENAPI_PATH, load_contract

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return load_contract()


def test_is_openapi_31(contract: dict[str, Any]) -> None:
    assert contract["openapi"].startswith("3.1")


def test_operation_ids_are_unique(contract: dict[str, Any]) -> None:
    ids = [
        operation["operationId"]
        for item in contract["paths"].values()
        for method, operation in item.items()
        if method in HTTP_METHODS
    ]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    assert not duplicates, f"duplicate operationIds: {duplicates}"


def test_every_operation_is_tagged_and_summarised(contract: dict[str, Any]) -> None:
    known_tags = {tag["name"] for tag in contract["tags"]}
    for path, item in contract["paths"].items():
        for method, operation in item.items():
            if method not in HTTP_METHODS:
                continue
            where = f"{method.upper()} {path}"
            assert operation.get("summary"), f"{where} has no summary"
            assert operation.get("tags"), f"{where} has no tag"
            assert set(operation["tags"]) <= known_tags, where


def test_every_local_ref_resolves(contract: dict[str, Any]) -> None:
    text = OPENAPI_PATH.read_text(encoding="utf-8")
    for ref in sorted(set(re.findall(r'"#/([^"]+)"', text))):
        node: Any = contract
        for part in ref.split("/"):
            assert isinstance(node, dict) and part in node, f"unresolved $ref #/{ref}"
            node = node[part]


def test_no_orphan_schemas(contract: dict[str, Any]) -> None:
    """A schema nobody references is either dead weight or a forgotten wiring."""
    text = OPENAPI_PATH.read_text(encoding="utf-8")
    referenced = set(re.findall(r'"#/components/schemas/([^"]+)"', text))
    declared = set(contract["components"]["schemas"])
    assert declared - referenced == set()


def test_error_envelope_shape(contract: dict[str, Any]) -> None:
    envelope = contract["components"]["schemas"]["ErrorEnvelope"]["properties"]["error"]
    assert set(envelope["required"]) == {"code", "message", "details"}


def test_pagination_shape(contract: dict[str, Any]) -> None:
    meta = contract["components"]["schemas"]["PageMeta"]
    assert set(meta["required"]) == {"total", "page", "page_size"}
    pages = [name for name in contract["components"]["schemas"] if name.endswith("Page")]
    assert pages, "no paginated collections declared"
    for name in pages:
        variants = contract["components"]["schemas"][name]["allOf"]
        assert variants[0] == {"$ref": "#/components/schemas/PageMeta"}, name
        assert "items" in variants[1]["properties"], name


def test_spec_validates_against_the_openapi_31_metaschema(contract: dict[str, Any]) -> None:
    validator = pytest.importorskip(
        "openapi_spec_validator",
        reason="openapi-spec-validator is a dev dependency",
    )
    errors = list(validator.OpenAPIV31SpecValidator(contract).iter_errors())
    assert not errors, [f"{list(e.absolute_path)}: {e.message}" for e in errors[:5]]
