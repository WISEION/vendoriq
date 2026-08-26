"""Enumerations shared by the persistence layer and the OpenAPI contract.

Every value here is part of the published contract (`docs/openapi.yaml`); adding or
renaming a member is a contract change and needs the orchestrator's approval
(see CONTRIBUTING.md).
"""

from __future__ import annotations

from enum import StrEnum


class VendorType(StrEnum):
    """Which scoring family a vendor belongs to."""

    SUB = "sub"
    SUP = "sup"
    BOTH = "both"


class VendorStatus(StrEnum):
    """Vendor lifecycle, spec §9."""

    REGISTERED = "registered"
    INVITED = "invited"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    INFORMATION_REQUESTED = "information_requested"
    PREQUALIFIED = "prequalified"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class CategoryKind(StrEnum):
    """Two taxonomies: work packages and material groups (spec §5)."""

    WORK = "work"
    MATERIAL = "material"


class ObservationSource(StrEnum):
    """Provenance of a field observation, ordered by trust in ``SOURCE_TRUST_RANK``."""

    REGISTRY = "registry"
    API = "api"
    DOCUMENT = "document"
    PORTAL = "portal"
    EXCEL = "excel"
    MANUAL = "manual"


#: Trust ranking from spec §6.6 — 1 is the most trusted. The database mirrors this
#: table in the generated column ``field_observation.trust_rank``; keep both in sync.
SOURCE_TRUST_RANK: dict[ObservationSource, int] = {
    ObservationSource.REGISTRY: 1,
    ObservationSource.API: 2,
    ObservationSource.DOCUMENT: 3,
    ObservationSource.PORTAL: 4,
    ObservationSource.EXCEL: 4,
    ObservationSource.MANUAL: 5,
}


class ScoringModelStatus(StrEnum):
    """Publication state of a model version, spec §10.3.

    Distinct from ``ScoringModel.is_locked``: ``status`` is the commission's editorial
    judgement (brief §1.3 marks the supplier model "proposed" until the commission freezes
    it), while ``is_locked`` is the mechanical fact that an application has been scored with
    the version and it can no longer be edited. A model can be locked and still proposed.
    """

    DRAFT = "draft"
    PROPOSED = "proposed"
    ACTIVE = "active"
    RETIRED = "retired"


class CycleKind(StrEnum):
    TENDER = "tender"
    PERIODIC = "periodic"


class CycleStatus(StrEnum):
    DRAFT = "draft"
    OPEN = "open"
    CLOSED = "closed"
    ARCHIVED = "archived"


class ApplicationStatus(StrEnum):
    """Application lifecycle, spec §9. Mirrors the vendor states except ``suspended``."""

    INVITED = "invited"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    INFORMATION_REQUESTED = "information_requested"
    PREQUALIFIED = "prequalified"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class DecisionKind(StrEnum):
    """Commission / manager decision recorded on an application."""

    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_INFO = "request_info"


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    IN_PREPARATION = "in_preparation"
    NOT_APPLICABLE = "not_applicable"
    MISSING = "missing"


class ProjectStage(StrEnum):
    PIPELINE = "pipeline"
    GO_NOGO = "go_nogo"
    TENDER = "tender"
    EXECUTION = "execution"


class UserRole(StrEnum):
    """Permission matrix roles, spec §3."""

    VENDOR = "vendor"
    OFFICER = "officer"
    COMMISSION = "commission"
    MANAGER = "manager"
    ADMIN = "admin"


class SyncResult(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class MatchState(StrEnum):
    """Package / project go-no-go state (spec §11)."""

    GO = "go"
    COND = "cond"
    NOGO = "nogo"


class ScoreClass(StrEnum):
    """Result class bands (spec §10)."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"
    KO = "KO"


class AdapterKey(StrEnum):
    """Data-source adapters (spec §6).

    The contract's ``AdapterKey`` carries a single ``registry`` member. The registry work
    splits into two independent government checks with different cadences and different
    knock-out criteria, so the constants below name both. ``REGISTRY`` is kept as the
    contract-visible umbrella value until the orchestrator widens ``docs/openapi.yaml``.
    """

    GENERIC_REST = "generic_rest"
    CSV = "csv"
    ERP_1C = "erp_1c"
    ERP_SAP = "erp_sap"
    ERP_ODOO = "erp_odoo"
    #: Contract-visible umbrella key; the two below are what the adapters actually register as.
    REGISTRY = "registry"
    #: State Tax Service — A.4 tax clearance and VÖEN validity.
    REGISTRY_TAX = "registry_tax"
    #: Construction licence register — A.1 licence validity.
    REGISTRY_LICENCE = "registry_licence"
    EXCEL = "excel"


#: Adapter keys that `docs/openapi.yaml` accepts on the wire today.
CONTRACT_ADAPTER_KEYS: frozenset[AdapterKey] = frozenset(
    {
        AdapterKey.GENERIC_REST,
        AdapterKey.CSV,
        AdapterKey.ERP_1C,
        AdapterKey.ERP_SAP,
        AdapterKey.ERP_ODOO,
        AdapterKey.REGISTRY,
        AdapterKey.EXCEL,
    }
)


class EventType(StrEnum):
    """Domain events. The same stream webhooks deliver and ``GET /events`` pages."""

    VENDOR_REGISTERED = "vendor.registered"
    VENDOR_INVITED = "vendor.invited"
    VENDOR_PREQUALIFIED = "vendor.prequalified"
    VENDOR_REJECTED = "vendor.rejected"
    VENDOR_SUSPENDED = "vendor.suspended"
    APPLICATION_SUBMITTED = "application.submitted"
    APPLICATION_DECIDED = "application.decided"
    DOCUMENT_UPLOADED = "document.uploaded"
    DOCUMENT_EXPIRING = "document.expiring"
    PROJECT_MATCHED = "project.matched"
    MODEL_PUBLISHED = "model.published"
    SYNC_COMPLETED = "sync.completed"


class Scope(StrEnum):
    """API key scope, ``<module>:<read|write>`` (brief §2, "API-first")."""

    VENDORS_READ = "vendors:read"
    VENDORS_WRITE = "vendors:write"
    APPLICATIONS_READ = "applications:read"
    APPLICATIONS_WRITE = "applications:write"
    PROJECTS_READ = "projects:read"
    PROJECTS_WRITE = "projects:write"
    INTEL_READ = "intel:read"
    INTEGRATIONS_READ = "integrations:read"
    INTEGRATIONS_WRITE = "integrations:write"
    ADMIN_READ = "admin:read"
    ADMIN_WRITE = "admin:write"


class DocumentExpiryState(StrEnum):
    """Derived from ``Document.status`` and ``expiry_date`` — never stored.

    ``perm`` is the "Müddətsiz" case of brief §1.11: a document that is on file and never
    expires. It is a separate state from ``valid`` because the reminder jobs must skip it.
    """

    MISSING = "missing"
    PERM = "perm"
    VALID = "valid"
    EXPIRING = "expiring"
    EXPIRED = "expired"
