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
