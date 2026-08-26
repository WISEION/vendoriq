"""The permission matrix — spec §3, brief §5.

Keyed by **operation id**, because that is the unit the contract names and the unit
``GET /auth/me`` returns: the frontend hides what a role cannot call, the server refuses it.
Every operation in ``docs/openapi.yaml`` has an entry, including the ones later phases
implement; a test asserts the two sets are equal, so a new endpoint cannot ship without a
deliberate decision about who may call it.

Two axes:

* **roles** — which of ``vendor|officer|commission|manager|admin`` may call the operation.
  ``vendor`` is always additionally confined to its own vendor record (``vendor_scoped``).
* **scope** — the API-key scope a machine client needs. ``None`` means no API key can call
  the operation at all: the auth endpoints and anything a person must be accountable for.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models.enums import Scope, UserRole

VENDOR = UserRole.VENDOR
OFFICER = UserRole.OFFICER
COMMISSION = UserRole.COMMISSION
MANAGER = UserRole.MANAGER
ADMIN = UserRole.ADMIN

#: Read-only staff: everybody who is not a vendor. Used for register and intel reads.
STAFF = frozenset({OFFICER, COMMISSION, MANAGER, ADMIN})
#: Who may change the register and the evaluation.
BACK_OFFICE = frozenset({OFFICER, MANAGER, ADMIN})
#: Who may run the taxonomy, the accounts and the integration credentials.
ADMINISTRATION = frozenset({ADMIN})
#: Everyone with an account, including vendors.
EVERYONE = frozenset({VENDOR, OFFICER, COMMISSION, MANAGER, ADMIN})


@dataclass(frozen=True, slots=True)
class Permission:
    """Who may call one operation, and with which API-key scope."""

    roles: frozenset[UserRole]
    scope: Scope | None = None
    #: True when a ``vendor`` caller is confined to its own ``vendor_id``.
    vendor_scoped: bool = False


def _p(
    roles: frozenset[UserRole] | set[UserRole],
    scope: Scope | None = None,
    *,
    vendor_scoped: bool = False,
) -> Permission:
    return Permission(frozenset(roles), scope, vendor_scoped)


#: Operations any caller may reach without a session — they *are* how a session is obtained.
PUBLIC_OPERATIONS: frozenset[str] = frozenset(
    {
        "getHealth",
        "registerVendor",
        "requestOtp",
        "verifyOtp",
        "staffLogin",
        "verifyTotp",
        "logout",
    }
)

PERMISSIONS: dict[str, Permission] = {
    # ── auth ────────────────────────────────────────────────────────────────
    "getMe": _p(EVERYONE),
    # ── vendors ─────────────────────────────────────────────────────────────
    # A vendor may list, but the repository narrows the result to its own row: the
    # register screen and the portal share one endpoint (brief §2, API-first).
    "listVendors": _p(EVERYONE, Scope.VENDORS_READ, vendor_scoped=True),
    "createVendor": _p(BACK_OFFICE, Scope.VENDORS_WRITE),
    "exportVendors": _p(STAFF, Scope.VENDORS_READ),
    "getVendor": _p(EVERYONE, Scope.VENDORS_READ, vendor_scoped=True),
    "patchVendor": _p(EVERYONE, Scope.VENDORS_WRITE, vendor_scoped=True),
    "listVendorCategories": _p(EVERYONE, Scope.VENDORS_READ, vendor_scoped=True),
    "setVendorCategories": _p(EVERYONE, Scope.VENDORS_WRITE, vendor_scoped=True),
    # Confirmation is the officer's judgement — it is what makes a vendor a match candidate.
    "confirmVendorCategories": _p(BACK_OFFICE, Scope.VENDORS_WRITE),
    "listContacts": _p(EVERYONE, Scope.VENDORS_READ, vendor_scoped=True),
    "createContact": _p(EVERYONE, Scope.VENDORS_WRITE, vendor_scoped=True),
    "patchContact": _p(EVERYONE, Scope.VENDORS_WRITE, vendor_scoped=True),
    "deleteContact": _p(EVERYONE, Scope.VENDORS_WRITE, vendor_scoped=True),
    "listObservations": _p(EVERYONE, Scope.VENDORS_READ, vendor_scoped=True),
    # Manual entry needs a reason and an accountable person (spec §6.5) — staff only.
    "createObservation": _p(BACK_OFFICE, Scope.VENDORS_WRITE),
    "listDocuments": _p(EVERYONE, Scope.VENDORS_READ, vendor_scoped=True),
    "initDocumentUpload": _p(EVERYONE, Scope.VENDORS_WRITE, vendor_scoped=True),
    "completeDocumentUpload": _p(EVERYONE, Scope.VENDORS_WRITE, vendor_scoped=True),
    # Vendors may only set in_preparation / not_applicable here; verification is officer-only
    # and the service enforces that split.
    "patchDocument": _p(EVERYONE, Scope.VENDORS_WRITE, vendor_scoped=True),
    "getDocumentDownload": _p(EVERYONE, Scope.VENDORS_READ, vendor_scoped=True),
    "inviteVendor": _p(BACK_OFFICE, Scope.VENDORS_WRITE),
    "suspendVendor": _p(frozenset({MANAGER, ADMIN}), Scope.VENDORS_WRITE),
    # ── applications ────────────────────────────────────────────────────────
    "listApplications": _p(EVERYONE, Scope.APPLICATIONS_READ, vendor_scoped=True),
    "getApplication": _p(EVERYONE, Scope.APPLICATIONS_READ, vendor_scoped=True),
    "patchAnswers": _p(frozenset({VENDOR, OFFICER}), Scope.APPLICATIONS_WRITE, vendor_scoped=True),
    "submitApplication": _p(
        frozenset({VENDOR, OFFICER}), Scope.APPLICATIONS_WRITE, vendor_scoped=True
    ),
    "getEvaluation": _p(STAFF, Scope.APPLICATIONS_READ),
    "putEvaluation": _p(frozenset({OFFICER, MANAGER, ADMIN}), Scope.APPLICATIONS_WRITE),
    "computeScore": _p(STAFF, Scope.APPLICATIONS_READ),
    "decideApplication": _p(frozenset({COMMISSION, MANAGER, ADMIN}), Scope.APPLICATIONS_WRITE),
    "putSecondEvaluation": _p(
        frozenset({OFFICER, COMMISSION, MANAGER, ADMIN}), Scope.APPLICATIONS_WRITE
    ),
    "exportCommissionSummaryXlsx": _p(STAFF, Scope.APPLICATIONS_READ),
    "exportCommissionSummaryPdf": _p(STAFF, Scope.APPLICATIONS_READ),
    # ── cycles ──────────────────────────────────────────────────────────────
    "listCycles": _p(STAFF, Scope.APPLICATIONS_READ),
    "createCycle": _p(BACK_OFFICE, Scope.APPLICATIONS_WRITE),
    "getCycle": _p(STAFF, Scope.APPLICATIONS_READ),
    "patchCycle": _p(BACK_OFFICE, Scope.APPLICATIONS_WRITE),
    "deleteCycle": _p(frozenset({MANAGER, ADMIN}), Scope.APPLICATIONS_WRITE),
    "inviteToCycle": _p(BACK_OFFICE, Scope.APPLICATIONS_WRITE),
    # ── scoring models ──────────────────────────────────────────────────────
    # Vendors see the class bands of the version they were scored with (spec §10.3).
    "listScoringModels": _p(EVERYONE, Scope.APPLICATIONS_READ),
    "getScoringModel": _p(EVERYONE, Scope.APPLICATIONS_READ),
    "createScoringModelDraft": _p(frozenset({MANAGER, ADMIN}), Scope.ADMIN_WRITE),
    "patchScoringModelDraft": _p(frozenset({MANAGER, ADMIN}), Scope.ADMIN_WRITE),
    "testRescore": _p(frozenset({MANAGER, ADMIN}), Scope.ADMIN_READ),
    "publishScoringModel": _p(frozenset({MANAGER, ADMIN}), Scope.ADMIN_WRITE),
    # ── projects & matching ─────────────────────────────────────────────────
    "listProjects": _p(STAFF, Scope.PROJECTS_READ),
    "createProject": _p(BACK_OFFICE, Scope.PROJECTS_WRITE),
    "getProject": _p(STAFF, Scope.PROJECTS_READ),
    "patchProject": _p(BACK_OFFICE, Scope.PROJECTS_WRITE),
    "deleteProject": _p(frozenset({MANAGER, ADMIN}), Scope.PROJECTS_WRITE),
    "listPackages": _p(STAFF, Scope.PROJECTS_READ),
    "createPackage": _p(BACK_OFFICE, Scope.PROJECTS_WRITE),
    "patchPackage": _p(BACK_OFFICE, Scope.PROJECTS_WRITE),
    "deletePackage": _p(BACK_OFFICE, Scope.PROJECTS_WRITE),
    "runMatch": _p(STAFF, Scope.PROJECTS_WRITE),
    "getLatestMatch": _p(STAFF, Scope.PROJECTS_READ),
    "exportProject": _p(STAFF, Scope.PROJECTS_READ),
    # ── market intelligence ─────────────────────────────────────────────────
    "getIntelOverview": _p(STAFF, Scope.INTEL_READ),
    "getIntelCoverage": _p(STAFF, Scope.INTEL_READ),
    "getClassDistribution": _p(STAFF, Scope.INTEL_READ),
    "getIntelCapacity": _p(STAFF, Scope.INTEL_READ),
    "getIntelCertification": _p(STAFF, Scope.INTEL_READ),
    "getIntelSources": _p(STAFF, Scope.INTEL_READ),
    "getExpiringDocuments": _p(STAFF, Scope.INTEL_READ),
    "getMarketGaps": _p(STAFF, Scope.INTEL_READ),
    "getAttentionList": _p(STAFF, Scope.INTEL_READ),
    # ── integrations ────────────────────────────────────────────────────────
    "listAdapters": _p(frozenset({OFFICER, MANAGER, ADMIN}), Scope.INTEGRATIONS_READ),
    "getAdapterConfig": _p(frozenset({OFFICER, MANAGER, ADMIN}), Scope.INTEGRATIONS_READ),
    "putAdapterConfig": _p(ADMINISTRATION, Scope.INTEGRATIONS_WRITE),
    "runSync": _p(frozenset({OFFICER, ADMIN}), Scope.INTEGRATIONS_WRITE),
    "listSyncLog": _p(frozenset({OFFICER, MANAGER, ADMIN}), Scope.INTEGRATIONS_READ),
    "previewExcelImport": _p(BACK_OFFICE, Scope.INTEGRATIONS_WRITE),
    "createExcelImportRun": _p(BACK_OFFICE, Scope.INTEGRATIONS_WRITE),
    # An API key must never be able to mint another API key.
    "listApiKeys": _p(ADMINISTRATION),
    "createApiKey": _p(ADMINISTRATION),
    "patchApiKey": _p(ADMINISTRATION),
    "revokeApiKey": _p(ADMINISTRATION),
    "listWebhooks": _p(ADMINISTRATION),
    "createWebhook": _p(ADMINISTRATION),
    "patchWebhook": _p(ADMINISTRATION),
    "deleteWebhook": _p(ADMINISTRATION),
    "testWebhook": _p(ADMINISTRATION),
    # ── admin ───────────────────────────────────────────────────────────────
    # The taxonomy is readable by everyone: a vendor picks its categories from it.
    "listCategories": _p(EVERYONE, Scope.ADMIN_READ),
    "createCategory": _p(ADMINISTRATION, Scope.ADMIN_WRITE),
    "patchCategory": _p(ADMINISTRATION, Scope.ADMIN_WRITE),
    "deleteCategory": _p(ADMINISTRATION, Scope.ADMIN_WRITE),
    "listUsers": _p(ADMINISTRATION, Scope.ADMIN_READ),
    "createUser": _p(ADMINISTRATION),
    "patchUser": _p(ADMINISTRATION),
    "deactivateUser": _p(ADMINISTRATION),
    "putUserRole": _p(ADMINISTRATION),
    "getSettings": _p(STAFF, Scope.ADMIN_READ),
    "putSettings": _p(frozenset({MANAGER, ADMIN}), Scope.ADMIN_WRITE),
    "listAuditEvents": _p(frozenset({MANAGER, ADMIN}), Scope.ADMIN_READ),
    "exportAuditLog": _p(frozenset({MANAGER, ADMIN}), Scope.ADMIN_READ),
    # ── events ──────────────────────────────────────────────────────────────
    # The stream a future product polls instead of subscribing to webhooks (brief §2).
    "listEvents": _p(STAFF, Scope.INTEGRATIONS_READ),
}


def permission_for(operation_id: str) -> Permission:
    """Look up one operation. A missing entry is a programming error, not a 403."""
    try:
        return PERMISSIONS[operation_id]
    except KeyError as exc:  # pragma: no cover - guarded by test_permission_matrix
        raise KeyError(f"no permission declared for operation {operation_id!r}") from exc


def operations_for_role(role: UserRole) -> list[str]:
    """Operation ids this role may call — the list ``GET /auth/me`` returns."""
    allowed = [op for op, perm in PERMISSIONS.items() if role in perm.roles]
    return sorted(allowed + list(PUBLIC_OPERATIONS))


def operations_for_scopes(scopes: frozenset[str]) -> list[str]:
    """Operation ids an API key with ``scopes`` may call."""
    return sorted(
        op for op, perm in PERMISSIONS.items() if perm.scope is not None and perm.scope in scopes
    )
