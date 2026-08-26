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


def test_no_description_was_split_by_a_comma_in_a_flow_mapping() -> None:
    """An unquoted description containing a comma silently becomes two YAML entries.

    Inside a flow mapping — `foo: { type: string, description: A, B }` — an unquoted scalar
    ends at the first comma. The description is truncated at that point and its tail becomes
    a **property of the schema**, with a null value. Six of these were shipped before the
    check existed; one of them turned `PageMeta.total`'s "Rows matching the filter, not rows
    on this page." into "Rows matching the filter", which says the opposite of what it means
    to anyone implementing pagination against the published contract.

    Both halves of the damage are invisible to a schema validator: the truncated text is a
    valid description, and the orphan is a valid property. So this looks for the signature
    instead — a key that reads as prose and carries no value.
    """
    contract = load_contract()
    orphans: list[str] = []

    def walk(node: object, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(key, str) and " " in key and value is None:
                    orphans.append(f"{path}.{key!r}")
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(contract, "")

    assert not orphans, (
        "these read as the tail of a description that a comma split; quote the description: "
        + ", ".join(sorted(orphans))
    )
