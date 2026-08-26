"""Request and response shapes, transcribed from ``docs/openapi.yaml``.

These models do **not** generate the published schema (ADR-006 — the hand-written contract
is served verbatim). They exist so the handlers parse and serialise exactly what the
contract declares, and ``tests/test_contract_shapes.py`` checks the two against each other.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from .models.enums import (
    ApplicationStatus,
    CategoryKind,
    DocumentStatus,
    ObservationSource,
    ScoreClass,
    UserRole,
    VendorStatus,
    VendorType,
)

#: ``format: email`` from the contract. ``email-validator`` is a PyPI-only dependency and
#: PyPI is blocked on the build host (ADR-005), so the shape is enforced by pattern instead:
#: one ``@``, a dot in the domain, no whitespace. Addresses are lower-cased on the way in so
#: ``Habib@wesa.az`` and ``habib@wesa.az`` are one account.
EmailStr = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        max_length=255,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    ),
]


class Model(BaseModel):
    """Base: reject unknown keys, so a client typo is a 422 rather than a silent no-op."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class PageMeta(Model):
    total: int
    page: int
    page_size: int


# ── health & auth ───────────────────────────────────────────────────────────
class Health(Model):
    status: Literal["ok"]
    version: str
    app_env: Literal["development", "staging", "production"]
    auth_mode: Literal["test", "live"]
    storage_backend: Literal["local", "s3"]


class VendorRegistration(Model):
    legal_name: str = Field(min_length=2)
    voen: str = Field(pattern=r"^[0-9]{10}$")
    type: VendorType
    contact_name: str
    position: str | None = None
    phone: str | None = None
    email: EmailStr
    locale: Literal["az", "en"] = "az"


class OtpRequest(Model):
    email: EmailStr


class OtpChallenge(Model):
    email: str
    expires_at: datetime
    debug_code: str | None = None


class OtpVerification(Model):
    email: EmailStr
    code: str = Field(pattern=r"^[0-9]{6}$")


class StaffLogin(Model):
    email: EmailStr
    password: str


class TotpChallenge(Model):
    challenge_id: uuid.UUID
    totp_required: bool
    debug_code: str | None = None


class TotpVerification(Model):
    challenge_id: uuid.UUID
    code: str = Field(pattern=r"^[0-9]{6}$")


class User(Model):
    id: uuid.UUID
    email: str
    full_name: str | None = None
    role: UserRole
    vendor_id: uuid.UUID | None = None
    vendor_name: str | None = None
    locale: Literal["az", "en"] = "az"
    is_active: bool
    has_totp: bool = False
    last_login_at: datetime | None = None


class UserCreated(User):
    totp_provisioning_uri: str | None = None


class UserPage(PageMeta):
    items: list[User]


class UserInput(Model):
    email: EmailStr
    full_name: str | None = None
    role: UserRole
    vendor_id: uuid.UUID | None = None
    locale: Literal["az", "en"] | None = None
    is_active: bool | None = None
    password: str | None = None


class UserRoleInput(Model):
    role: UserRole


class Session(Model):
    user: User
    expires_at: datetime
    csrf_token: str | None = None


class Me(User):
    permissions: list[str] = Field(default_factory=list)
    auth_mode: Literal["test", "live"] = "test"


# ── vendors ─────────────────────────────────────────────────────────────────
class Vendor(Model):
    id: uuid.UUID
    legal_name: str
    voen: str | None = None
    type: VendorType
    legal_form: str | None = None
    registration_year: int | None = None
    address: str | None = None
    region: str | None = None
    website: str | None = None
    status: VendorStatus
    external_ref: str | None = None
    is_demo: bool
    latest_score: float | None = None
    latest_class: ScoreClass | None = None
    prequalified_until: date | None = None
    primary_source: ObservationSource | None = None
    created_at: datetime
    updated_at: datetime


class VendorCreate(Model):
    legal_name: str
    voen: str | None = Field(default=None, pattern=r"^[0-9]{10}$")
    type: VendorType
    legal_form: str | None = None
    registration_year: int | None = None
    address: str | None = None
    region: str | None = None
    website: str | None = None
    external_ref: str | None = None
    is_demo: bool = False


class VendorPatch(Model):
    legal_name: str | None = None
    voen: str | None = Field(default=None, pattern=r"^[0-9]{10}$")
    type: VendorType | None = None
    legal_form: str | None = None
    registration_year: int | None = None
    address: str | None = None
    region: str | None = None
    website: str | None = None
    external_ref: str | None = None
    status: VendorStatus | None = None
    reason: str | None = None


class Category(Model):
    id: uuid.UUID
    code: str
    name_az: str
    name_en: str
    kind: CategoryKind
    parent_id: uuid.UUID | None = None
    is_active: bool = True
    vendor_count: int = 0
    prequalified_count: int = 0


class CategoryInput(Model):
    code: str
    name_az: str
    name_en: str
    kind: CategoryKind
    parent_id: uuid.UUID | None = None
    is_active: bool = True


class VendorCategory(Model):
    category: Category
    confirmed: bool
    confirmed_at: datetime | None = None


class CategoryCodes(Model):
    category_codes: list[str]


class CategoryConfirmation(Model):
    category_codes: list[str]
    confirmed: bool = True


class Contact(Model):
    id: uuid.UUID
    vendor_id: uuid.UUID
    name: str
    position: str | None = None
    phone: str | None = None
    email: str | None = None
    is_primary: bool
    has_portal_account: bool = False


class ContactInput(Model):
    name: str
    position: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    is_primary: bool = False


class FieldObservation(Model):
    id: uuid.UUID
    vendor_id: uuid.UUID
    field_code: str
    value: Any
    unit: str | None = None
    source: ObservationSource
    source_ref: str | None = None
    observed_at: datetime
    entered_by: uuid.UUID | None = None
    trust_rank: int
    is_current: bool = False


class ObservationInput(Model):
    field_code: str
    value: Any = None
    unit: str | None = None
    observed_at: datetime | None = None
    reason: str = Field(min_length=3)


class FieldObservationPage(PageMeta):
    items: list[FieldObservation]


class VendorPage(PageMeta):
    items: list[Vendor]


class EvaluationSummary(Model):
    application_id: uuid.UUID
    cycle_name: str | None = None
    model_version: str | None = None
    total: float | None = None
    cls: ScoreClass | None = None
    decision: str | None = None
    decided_at: datetime | None = None


class VendorDetail(Vendor):
    contacts: list[Contact] = Field(default_factory=list)
    categories: list[VendorCategory] = Field(default_factory=list)
    current_fields: dict[str, Any] = Field(default_factory=dict)
    raw_indicators: dict[str, float | None] = Field(default_factory=dict)
    documents: list[Document] = Field(default_factory=list)
    evaluations: list[EvaluationSummary] = Field(default_factory=list)
    stale_fields: list[str] = Field(default_factory=list)


class Document(Model):
    id: uuid.UUID | None = None
    vendor_id: uuid.UUID
    code: str
    name_az: str
    name_en: str
    mandatory: bool
    status: DocumentStatus
    filename: str | None = None
    file_key: str | None = None
    issue_date: date | None = None
    expiry_date: date | None = None
    days_to_expiry: int | None = None
    verified_by: uuid.UUID | None = None
    verified_at: datetime | None = None


class DocumentPatch(Model):
    status: DocumentStatus | None = None
    issue_date: date | None = None
    expiry_date: date | None = None
    verified: bool | None = None


class UploadInit(Model):
    code: str
    filename: str
    content_type: Literal["application/pdf"]
    size: int = Field(gt=0)


class UploadTicket(Model):
    upload_id: uuid.UUID
    url: str
    method: Literal["PUT", "POST"]
    headers: dict[str, str] = Field(default_factory=dict)
    expires_at: datetime


class UploadCompletion(Model):
    upload_id: uuid.UUID
    code: str
    issue_date: date | None = None
    expiry_date: date | None = None


class DownloadTicket(Model):
    url: str
    expires_at: datetime
    filename: str | None = None


class InviteInput(Model):
    cycle_id: uuid.UUID
    message_az: str | None = None
    message_en: str | None = None


class SuspendInput(Model):
    suspended: bool
    reason: str = Field(min_length=3)


class Application(Model):
    id: uuid.UUID
    vendor_id: uuid.UUID
    vendor_name: str | None = None
    cycle_id: uuid.UUID
    cycle_name: str | None = None
    status: ApplicationStatus
    submitted_at: datetime | None = None
    total: float | None = None
    cls: ScoreClass | None = None
    decision: str | None = None
    decided_at: datetime | None = None
    evaluator_name: str | None = None
    is_demo: bool = False


# ── admin & events ──────────────────────────────────────────────────────────
class MatchingSettings(Model):
    strong_min: int
    capacity_ratio: float
    supplier_turnover_divisor: float
    default_min_class: ScoreClass


class QualificationSettings(Model):
    validity_months: int
    pass_mark: float
    tax_clearance_validity_months: int


class FreshnessSettings(Model):
    financials_months: int
    headcount_months: int
    stale_profile_days: int


class NotificationSettings(Model):
    expiry_reminder_days: list[int]
    expiring_window_days: int
    email_enabled: bool


class OrganisationSettings(Model):
    name: str
    default_locale: Literal["az", "en"]
    currency: Literal["AZN"]


class Settings(Model):
    matching: MatchingSettings
    qualification: QualificationSettings
    freshness: FreshnessSettings
    notifications: NotificationSettings
    organisation: OrganisationSettings


class AuditEvent(Model):
    id: uuid.UUID
    actor_id: uuid.UUID | None = None
    actor_email: str | None = None
    entity_type: str
    entity_id: uuid.UUID | None = None
    action: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    created_at: datetime


class AuditEventPage(PageMeta):
    items: list[AuditEvent]


class Event(Model):
    id: uuid.UUID
    type: str
    entity_type: str
    entity_id: uuid.UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class EventPage(PageMeta):
    items: list[Event]


# Forward references: VendorDetail names Document before it is declared.
VendorDetail.model_rebuild()
