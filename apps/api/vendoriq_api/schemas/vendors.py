"""The vendor register: vendors, contacts, categories, documents, observations.

Contract tag ``vendors``.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field

from ..models.enums import (
    ApplicationStatus,
    CategoryKind,
    DocumentStatus,
    ObservationSource,
    ScoreClass,
    VendorStatus,
    VendorType,
)
from .base import EmailStr, Model, PageMeta


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


# `VendorDetail` names `Document` above the line that declares it, so the reference stays a
# string until the module is fully executed.
VendorDetail.model_rebuild()
