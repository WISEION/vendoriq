"""The permission matrix (spec §3, brief §5) — every role against every protected group.

Two layers are checked. The **matrix itself** must cover every operation the contract
declares, with no strays and no gaps: a new endpoint cannot ship without a deliberate answer
to "who may call this". The **live routes** must then actually enforce it, per role, per
route group, so that a matrix entry nobody wired up is a failing test rather than an open
door.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from vendoriq_api.models.enums import UserRole
from vendoriq_api.openapi import OPENAPI_PATH
from vendoriq_api.security.permissions import (
    PERMISSIONS,
    PUBLIC_OPERATIONS,
    operations_for_role,
    permission_for,
)

ROLES = list(UserRole)


def contract_operations() -> set[str]:
    document = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    return {
        operation["operationId"]
        for item in document["paths"].values()
        for method, operation in item.items()
        if method in {"get", "post", "put", "patch", "delete"}
    }


# ── the matrix as data ──────────────────────────────────────────────────────
def test_every_contract_operation_has_a_permission_entry() -> None:
    """A gap here means an endpoint whose authorisation was never decided."""
    declared = contract_operations()
    covered = set(PERMISSIONS) | PUBLIC_OPERATIONS
    assert declared - covered == set(), f"no permission declared for: {sorted(declared - covered)}"


def test_the_matrix_declares_nothing_the_contract_does_not() -> None:
    """A stray entry is a leftover from a removed endpoint, or a typo in an operation id."""
    assert set(PERMISSIONS) | PUBLIC_OPERATIONS <= contract_operations()


def test_public_operations_are_only_the_ones_that_create_a_session() -> None:
    assert {
        "getHealth",
        "registerVendor",
        "requestOtp",
        "verifyOtp",
        "staffLogin",
        "verifyTotp",
        "logout",
    } == PUBLIC_OPERATIONS


def test_no_operation_grants_an_empty_role_set() -> None:
    """An entry nobody can call is a mistake — it renders the endpoint dead."""
    for operation, permission in PERMISSIONS.items():
        assert permission.roles, operation


def test_admin_can_call_at_least_as_much_as_every_other_role() -> None:
    """Spec §3: the administrator's remit contains everyone else's plus accounts."""
    admin = set(operations_for_role(UserRole.ADMIN))
    for role in ROLES:
        if role is UserRole.ADMIN:
            continue
        extra = set(operations_for_role(role)) - admin
        # The vendor's own-record operations are the deliberate exception: a vendor may
        # patch answers on its application, an admin does not do that on its behalf.
        assert extra <= {"patchAnswers", "submitApplication"}, (role, sorted(extra))


def test_a_vendor_cannot_reach_the_back_office() -> None:
    vendor = set(operations_for_role(UserRole.VENDOR))
    for operation in (
        "createVendor",
        "confirmVendorCategories",
        "createObservation",
        "inviteVendor",
        "suspendVendor",
        "getEvaluation",
        "putEvaluation",
        "decideApplication",
        "listUsers",
        "createUser",
        "putSettings",
        "listAuditEvents",
        "listEvents",
        "getIntelOverview",
        "listProjects",
    ):
        assert operation not in vendor, operation


def test_only_the_administrator_manages_accounts_keys_and_the_taxonomy() -> None:
    for operation in (
        "createUser",
        "patchUser",
        "deactivateUser",
        "putUserRole",
        "createApiKey",
        "revokeApiKey",
        "createWebhook",
        "createCategory",
        "patchCategory",
        "deleteCategory",
    ):
        assert permission_for(operation).roles == frozenset({UserRole.ADMIN}), operation


def test_only_a_manager_approves_or_suspends() -> None:
    """Spec §9: approval and suspension are the manager's, not the officer's."""
    assert permission_for("suspendVendor").roles == frozenset({UserRole.MANAGER, UserRole.ADMIN})
    assert UserRole.OFFICER not in permission_for("putSettings").roles


def test_an_officer_does_the_register_work_but_does_not_decide() -> None:
    assert UserRole.OFFICER in permission_for("createVendor").roles
    assert UserRole.OFFICER in permission_for("putEvaluation").roles
    assert UserRole.OFFICER not in permission_for("decideApplication").roles


def test_the_commission_decides_but_does_not_edit_the_register() -> None:
    """Spec §3: the commission "reviews evaluations and records the decision"."""
    assert UserRole.COMMISSION in permission_for("decideApplication").roles
    assert UserRole.COMMISSION not in permission_for("createVendor").roles
    assert UserRole.COMMISSION not in permission_for("putEvaluation").roles


def test_account_and_key_operations_are_closed_to_machines() -> None:
    """No API key scope may create an account or another key — that is privilege escalation."""
    for operation in (
        "createUser",
        "patchUser",
        "deactivateUser",
        "putUserRole",
        "listApiKeys",
        "createApiKey",
        "patchApiKey",
        "revokeApiKey",
        "listWebhooks",
        "createWebhook",
        "patchWebhook",
        "deleteWebhook",
        "testWebhook",
    ):
        assert permission_for(operation).scope is None, operation


def test_vendor_scoped_operations_are_exactly_the_own_record_ones() -> None:
    scoped = {op for op, perm in PERMISSIONS.items() if perm.vendor_scoped}
    assert scoped == {
        "listVendors",
        "getVendor",
        "patchVendor",
        "listVendorCategories",
        "setVendorCategories",
        "listContacts",
        "createContact",
        "patchContact",
        "deleteContact",
        "listObservations",
        "listDocuments",
        "initDocumentUpload",
        "completeDocumentUpload",
        "patchDocument",
        "getDocumentDownload",
        "listApplications",
        "getApplication",
        "patchAnswers",
        "submitApplication",
    }


# ── the live routes ─────────────────────────────────────────────────────────
#: One representative request per implemented route group. ``roles`` is who must succeed;
#: every other role must get 403.
ROUTE_GROUPS: list[tuple[str, str, str, set[UserRole], dict[str, Any] | None]] = [
    ("register:read", "GET", "/api/vendors", set(ROLES), None),
    (
        "register:write",
        "POST",
        "/api/vendors",
        {UserRole.OFFICER, UserRole.MANAGER, UserRole.ADMIN},
        {"legal_name": "Perm Probe MMC", "type": "sub"},
    ),
    (
        "observations:write",
        "POST",
        "/api/vendors/{vendor}/observations",
        {UserRole.OFFICER, UserRole.MANAGER, UserRole.ADMIN},
        {"field_code": "E.1", "value": 10, "reason": "permission probe"},
    ),
    (
        "categories:confirm",
        "POST",
        "/api/vendors/{vendor}/categories/confirm",
        {UserRole.OFFICER, UserRole.MANAGER, UserRole.ADMIN},
        {"category_codes": []},
    ),
    (
        "vendor:suspend",
        "POST",
        "/api/vendors/{vendor}/suspend",
        {UserRole.MANAGER, UserRole.ADMIN},
        {"suspended": True, "reason": "permission probe"},
    ),
    ("taxonomy:read", "GET", "/api/admin/categories", set(ROLES), None),
    (
        "taxonomy:write",
        "POST",
        "/api/admin/categories",
        {UserRole.ADMIN},
        {"code": "probe", "name_az": "P", "name_en": "P", "kind": "work"},
    ),
    (
        "users:read",
        "GET",
        "/api/admin/users",
        {UserRole.ADMIN},
        None,
    ),
    (
        "users:write",
        "POST",
        "/api/admin/users",
        {UserRole.ADMIN},
        {"email": "probe@vendoriq.test", "role": "officer", "password": "Probe!2026"},
    ),
    (
        "settings:read",
        "GET",
        "/api/admin/settings",
        {UserRole.OFFICER, UserRole.COMMISSION, UserRole.MANAGER, UserRole.ADMIN},
        None,
    ),
    (
        "settings:write",
        "PUT",
        "/api/admin/settings",
        {UserRole.MANAGER, UserRole.ADMIN},
        {"matching": {"strong_min": 2}},
    ),
    (
        "audit:read",
        "GET",
        "/api/admin/audit",
        {UserRole.MANAGER, UserRole.ADMIN},
        None,
    ),
    (
        "events:read",
        "GET",
        "/api/events",
        {UserRole.OFFICER, UserRole.COMMISSION, UserRole.MANAGER, UserRole.ADMIN},
        None,
    ),
]


@pytest.mark.parametrize(
    ("group", "method", "path", "allowed", "body"),
    ROUTE_GROUPS,
    ids=[case[0] for case in ROUTE_GROUPS],
)
@pytest.mark.parametrize("role", ROLES, ids=[role.value for role in ROLES])
def test_each_role_against_each_route_group(
    client: TestClient,
    make_user: Any,
    make_vendor: Any,
    login: Any,
    role: UserRole,
    group: str,
    method: str,
    path: str,
    allowed: set[UserRole],
    body: dict[str, Any] | None,
) -> None:
    """The whole matrix, exercised through the real dependency chain."""
    vendor = make_vendor()
    user = make_user(role, vendor=vendor if role is UserRole.VENDOR else None)
    login(user)

    url = path.replace("{vendor}", str(vendor.id))
    # Make the probe payload unique per role so a success does not collide with the next.
    payload = dict(body) if body else None
    if payload and "code" in payload:
        payload["code"] = f"probe-{role.value}"
    if payload and "email" in payload:
        payload["email"] = f"probe-{role.value}@vendoriq.test"
    if payload and "legal_name" in payload:
        payload["legal_name"] = f"Probe {role.value} MMC"

    response = client.request(method, url, json=payload)
    if role in allowed:
        assert response.status_code != 403, (group, role, response.text)
    else:
        assert response.status_code == 403, (group, role, response.status_code, response.text)


def test_an_anonymous_caller_is_unauthenticated_not_forbidden(client: TestClient) -> None:
    """401 and 403 answer different questions; a client retries only one of them."""
    assert client.get("/api/vendors").status_code == 401
    assert client.get("/api/admin/settings").status_code == 401
    assert client.get("/api/events").status_code == 401


def test_a_vendor_cannot_read_another_vendors_record(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    """404, not 403: existence of a VÖEN in the register is itself information (spec §13)."""
    mine, theirs = make_vendor(), make_vendor()
    login(make_user(UserRole.VENDOR, vendor=mine))
    assert client.get(f"/api/vendors/{mine.id}").status_code == 200
    assert client.get(f"/api/vendors/{theirs.id}").status_code == 404
    assert client.get(f"/api/vendors/{theirs.id}/documents").status_code == 404
    assert client.get(f"/api/vendors/{theirs.id}/contacts").status_code == 404
    assert client.get(f"/api/vendors/{theirs.id}/observations").status_code == 404


def test_a_vendor_listing_the_register_sees_only_itself(
    client: TestClient, make_vendor: Any, make_user: Any, login: Any
) -> None:
    mine = make_vendor()
    make_vendor()
    make_vendor()
    login(make_user(UserRole.VENDOR, vendor=mine))
    body = client.get("/api/vendors").json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(mine.id)


def test_an_unknown_vendor_id_is_not_found_for_staff(
    client: TestClient, make_user: Any, login: Any
) -> None:
    login(make_user(UserRole.OFFICER))
    assert client.get(f"/api/vendors/{uuid.uuid4()}").status_code == 404
