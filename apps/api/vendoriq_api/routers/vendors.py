"""The vendor register (contract ``/vendors/*``, spec §5, §7, §8).

Every handler follows the same three steps: authorise the operation, narrow to the vendor
the caller is allowed to see, then call a service. No SQL and no business rule lives here —
CONTRIBUTING, "repositories own the queries".
"""

from __future__ import annotations

import io
import uuid
from collections import OrderedDict
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from ..catalog import days_to_expiry
from ..config import Settings, get_settings
from ..db import UnitOfWork
from ..errors import ApiError
from ..models import Vendor as VendorRow
from ..models.enums import (
    DocumentStatus,
    ObservationSource,
    ScoreClass,
    VendorStatus,
    VendorType,
)
from ..schemas import (
    Application,
    CategoryCodes,
    CategoryConfirmation,
    Contact,
    ContactInput,
    Document,
    DocumentPatch,
    DownloadTicket,
    EvaluationSummary,
    FieldObservation,
    FieldObservationPage,
    InviteInput,
    ObservationInput,
    SuspendInput,
    UploadCompletion,
    UploadInit,
    UploadTicket,
    Vendor,
    VendorCategory,
    VendorCreate,
    VendorDetail,
    VendorPage,
    VendorPatch,
)
from ..security import Principal, get_uow, require, scope_to_vendor
from ..services import (
    applications as applications_service,
)
from ..services import (
    auth as auth_service,
)
from ..services import (
    categories as categories_service,
)
from ..services import (
    contacts as contacts_service,
)
from ..services import (
    documents as documents_service,
)
from ..services import (
    evaluation as evaluation_service,
)
from ..services import (
    exports as exports_service,
)
from ..services import (
    observations as observations_service,
)
from ..services import (
    settings_store,
)
from ..services import (
    vendors as vendors_service,
)
from ..storage import Storage, get_storage
from .admin import category_payload

router = APIRouter(tags=["vendors"])

#: ``upload_id`` → signed ticket. Process-local and as short-lived as the ticket it holds;
#: a multi-node deployment moves it onto the ``document`` row (phase 2A).
#:
#: Bounded, because an abandoned ``upload-init`` never reaches ``upload-complete`` and an
#: unbounded dict of them is a slow memory leak that only shows up in production. The ticket
#: itself carries its own expiry, so evicting the oldest entry costs a vendor at most a retry.
_UPLOAD_TICKET_LIMIT = 512
_UPLOAD_TICKETS: OrderedDict[uuid.UUID, str] = OrderedDict()


def _remember_ticket(upload_id: uuid.UUID, token: str) -> None:
    _UPLOAD_TICKETS[upload_id] = token
    while len(_UPLOAD_TICKETS) > _UPLOAD_TICKET_LIMIT:
        _UPLOAD_TICKETS.popitem(last=False)


# ── serialisers ─────────────────────────────────────────────────────────────
def vendor_payload(uow: UnitOfWork, vendor: VendorRow) -> Vendor:
    latest = vendors_service.latest_result(uow.session, vendor.id)
    return Vendor(
        id=vendor.id,
        legal_name=vendor.legal_name,
        voen=vendor.voen,
        type=vendor.type,
        legal_form=vendor.legal_form,
        registration_year=vendor.registration_year,
        address=vendor.address,
        region=vendor.region,
        website=vendor.website,
        status=vendor.status,
        external_ref=vendor.external_ref,
        is_demo=vendor.is_demo,
        latest_score=latest.total,
        latest_class=latest.cls,
        prequalified_until=latest.prequalified_until,
        primary_source=vendors_service.primary_source(uow.session, vendor.id),
        created_at=vendor.created_at,
        updated_at=vendor.updated_at,
    )


def contact_payload(uow: UnitOfWork, contact: Any) -> Contact:
    return Contact(
        id=contact.id,
        vendor_id=contact.vendor_id,
        name=contact.name,
        position=contact.position,
        phone=contact.phone,
        email=contact.email,
        is_primary=contact.is_primary,
        has_portal_account=contacts_service.has_portal_account(uow.session, contact),
    )


def vendor_category_payload(uow: UnitOfWork, row: Any) -> VendorCategory:
    return VendorCategory(
        category=category_payload(uow, row.category),
        confirmed=row.confirmed,
        confirmed_at=row.updated_at if row.confirmed else None,
    )


def document_payload(row: documents_service.ChecklistRow, vendor_id: uuid.UUID) -> Document:
    document = row.document
    return Document(
        id=document.id if document else None,
        vendor_id=vendor_id,
        code=row.code,
        name_az=row.definition.name_az,
        name_en=row.definition.name_en,
        mandatory=row.definition.mandatory,
        status=row.status,
        filename=document.filename if document else None,
        file_key=document.file_key if document else None,
        issue_date=document.issue_date if document else None,
        expiry_date=row.expiry_date,
        days_to_expiry=row.days_left(),
        verified_by=document.verified_by if document else None,
        verified_at=document.verified_at if document else None,
    )


def evaluation_summary_payload(row: evaluation_service.VendorHistoryRow) -> EvaluationSummary:
    computed = row.computed or {}
    cls_value = computed.get("cls")
    return EvaluationSummary(
        application_id=row.application_id,
        cycle_name=row.cycle_name,
        model_version=row.model_version,
        total=computed.get("total"),
        cls=ScoreClass(cls_value) if cls_value in set(ScoreClass) else None,
        decision=row.decision.value if row.decision else None,
        decided_at=row.decided_at,
    )


def observation_payload(row: Any, current: set[uuid.UUID]) -> FieldObservation:
    return FieldObservation(
        id=row.id,
        vendor_id=row.vendor_id,
        field_code=row.field_code,
        value=observations_service.unwrap(row.value),
        unit=row.unit,
        source=row.source,
        source_ref=row.source_ref,
        observed_at=row.observed_at,
        entered_by=row.entered_by,
        trust_rank=row.trust_rank,
        is_current=row.id in current,
    )


def _load(uow: UnitOfWork, principal: Principal, vendor_id: uuid.UUID, operation: str) -> VendorRow:
    scope_to_vendor(principal, vendor_id, operation)
    return vendors_service.get(uow.session, vendor_id)


# ── register ────────────────────────────────────────────────────────────────
@router.get("/vendors")
def list_vendors(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 25,
    type: VendorType | None = None,
    category: Annotated[list[str] | None, Query()] = None,
    cls: Annotated[list[ScoreClass] | None, Query(alias="class")] = None,
    status_filter: Annotated[list[VendorStatus] | None, Query(alias="status")] = None,
    region: str | None = None,
    q: str | None = None,
    include_demo: bool = True,
    sort: str = "legal_name",
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("listVendors")),
) -> VendorPage:
    """The register. A vendor caller sees exactly one row — its own."""
    filters = vendors_service.VendorFilters(
        type=type,
        categories=category or (),
        classes=cls or (),
        statuses=status_filter or (),
        region=region,
        q=q,
        include_demo=include_demo,
        sort=sort,
    )
    rows, total = vendors_service.list_page(
        uow.session,
        filters,
        page=page,
        page_size=page_size,
        principal_vendor_id=principal.vendor_id if principal.is_vendor else None,
    )
    return VendorPage(
        items=[vendor_payload(uow, row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/vendors", status_code=status.HTTP_201_CREATED)
def create_vendor(
    body: VendorCreate,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("createVendor")),
) -> Vendor:
    vendor = vendors_service.create(
        uow,
        legal_name=body.legal_name,
        type=body.type,
        voen=body.voen,
        is_demo=body.is_demo,
        legal_form=body.legal_form,
        registration_year=body.registration_year,
        address=body.address,
        region=body.region,
        website=body.website,
        external_ref=body.external_ref,
    )
    return vendor_payload(uow, vendor)


@router.get("/vendors/export.xlsx")
def export_vendors(
    type: VendorType | None = None,
    category: Annotated[list[str] | None, Query()] = None,
    cls: Annotated[list[ScoreClass] | None, Query(alias="class")] = None,
    status_filter: Annotated[list[VendorStatus] | None, Query(alias="status")] = None,
    region: str | None = None,
    q: str | None = None,
    locale: Literal["az", "en"] = "az",
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("exportVendors")),
) -> Response:
    """The filtered register as an Excel workbook — the same filters ``listVendors`` takes.

    Registered before ``/vendors/{vendor_id}`` (as the contract itself orders the two paths):
    a dynamic ``{vendor_id}`` segment matches any literal string at the routing layer, type
    coercion happens only afterwards, so ``export.xlsx`` must be matched first or it would
    never reach this handler.
    """
    filters = vendors_service.VendorFilters(
        type=type,
        categories=category or (),
        classes=cls or (),
        statuses=status_filter or (),
        region=region,
        q=q,
    )
    workbook = exports_service.build_vendor_register_workbook(
        uow.session,
        filters,
        principal_vendor_id=principal.vendor_id if principal.is_vendor else None,
        locale=locale,
    )
    buffer = io.BytesIO()
    workbook.save(buffer)
    return Response(
        content=buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="vendors.xlsx"'},
    )


@router.get("/vendors/{vendor_id}")
def get_vendor(
    vendor_id: uuid.UUID,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("getVendor")),
) -> VendorDetail:
    """Detail: contacts, categories, the resolved current profile and the checklist."""
    vendor = _load(uow, principal, vendor_id, "getVendor")
    profile = observations_service.current_profile(uow.session, vendor.id)
    windows = settings_store.freshness_windows(uow.session)
    return VendorDetail(
        **vendor_payload(uow, vendor).model_dump(),
        contacts=[
            contact_payload(uow, row) for row in contacts_service.list_for(uow.session, vendor.id)
        ],
        categories=[
            vendor_category_payload(uow, row)
            for row in categories_service.list_for_vendor(uow.session, vendor.id)
        ],
        current_fields=profile,
        raw_indicators=_raw_indicators(uow.session, vendor, profile),
        documents=[
            document_payload(row, vendor.id)
            for row in documents_service.checklist(uow.session, vendor)
        ],
        evaluations=[
            evaluation_summary_payload(row)
            for row in evaluation_service.vendor_history(uow.session, vendor.id)
        ],
        stale_fields=observations_service.stale_field_codes(
            uow.session, vendor.id, windows=windows
        ),
    )


def _raw_indicators(
    session: Session, vendor: VendorRow, profile: dict[str, Any]
) -> dict[str, float | None]:
    """The scoring inputs for this vendor: the frozen snapshot if there is one, else derived.

    The engine is the only place that knows how an answer becomes an indicator, so the
    derivation is a call into it, not a reimplementation.

    The snapshot comes first, which is the precedence `services/evaluation.py`,
    `services/intel.py` and `services/matching.py` already use and this screen did not. The
    difference is not cosmetic for the 13 Rev4 vendors: they were scored from a spreadsheet
    and have no form answers at all (ADR-021), so deriving from their empty profile reports
    a register full of zeroes for vendors whose real indicators are sitting in the
    application the commission decided.
    """
    from vendoriq_scoring import derive_raw

    application = applications_service.decided_application(session, vendor.id)
    if application is not None and application.raw_snapshot is not None:
        derived: dict[str, Any] = dict(application.raw_snapshot)
    else:
        kind = "sup" if vendor.type is VendorType.SUP else "sub"
        derived = dict(derive_raw(profile, kind))  # type: ignore[arg-type]
    return {
        code: (float(value) if isinstance(value, int | float) else None)
        for code, value in derived.items()
    }


@router.patch("/vendors/{vendor_id}")
def patch_vendor(
    vendor_id: uuid.UUID,
    body: VendorPatch,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("patchVendor")),
) -> Vendor:
    """Each changed field becomes a ``manual`` observation and an audit row (spec §6.5)."""
    vendor = _load(uow, principal, vendor_id, "patchVendor")
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    reason = changes.pop("reason", None)
    vendors_service.patch(uow, vendor, changes, role=principal.role, reason=reason)
    return vendor_payload(uow, vendor)


# ── categories ──────────────────────────────────────────────────────────────
@router.get("/vendors/{vendor_id}/categories")
def list_vendor_categories(
    vendor_id: uuid.UUID,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("listVendorCategories")),
) -> list[VendorCategory]:
    _load(uow, principal, vendor_id, "listVendorCategories")
    return [
        vendor_category_payload(uow, row)
        for row in categories_service.list_for_vendor(uow.session, vendor_id)
    ]


@router.put("/vendors/{vendor_id}/categories")
def set_vendor_categories(
    vendor_id: uuid.UUID,
    body: CategoryCodes,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("setVendorCategories")),
) -> list[VendorCategory]:
    """The vendor selects; the selection arrives unconfirmed (contract)."""
    _load(uow, principal, vendor_id, "setVendorCategories")
    rows = categories_service.set_for_vendor(uow, vendor_id, body.category_codes)
    return [vendor_category_payload(uow, row) for row in rows]


@router.post("/vendors/{vendor_id}/categories/confirm")
def confirm_vendor_categories(
    vendor_id: uuid.UUID,
    body: CategoryConfirmation,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("confirmVendorCategories")),
) -> list[VendorCategory]:
    vendors_service.get(uow.session, vendor_id)
    rows = categories_service.confirm_for_vendor(
        uow, vendor_id, body.category_codes, confirmed=body.confirmed
    )
    return [vendor_category_payload(uow, row) for row in rows]


# ── contacts ────────────────────────────────────────────────────────────────
@router.get("/vendors/{vendor_id}/contacts")
def list_contacts(
    vendor_id: uuid.UUID,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("listContacts")),
) -> list[Contact]:
    _load(uow, principal, vendor_id, "listContacts")
    return [contact_payload(uow, row) for row in contacts_service.list_for(uow.session, vendor_id)]


@router.post("/vendors/{vendor_id}/contacts", status_code=status.HTTP_201_CREATED)
def create_contact(
    vendor_id: uuid.UUID,
    body: ContactInput,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("createContact")),
) -> Contact:
    _load(uow, principal, vendor_id, "createContact")
    contact = contacts_service.create(uow, vendor_id, body.model_dump())
    return contact_payload(uow, contact)


@router.patch("/vendors/{vendor_id}/contacts/{contact_id}")
def patch_contact(
    vendor_id: uuid.UUID,
    contact_id: uuid.UUID,
    body: ContactInput,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("patchContact")),
) -> Contact:
    _load(uow, principal, vendor_id, "patchContact")
    contact = contacts_service.get(uow.session, vendor_id, contact_id)
    contacts_service.patch(uow, contact, body.model_dump(exclude_unset=True))
    return contact_payload(uow, contact)


@router.delete("/vendors/{vendor_id}/contacts/{contact_id}", status_code=204)
def delete_contact(
    vendor_id: uuid.UUID,
    contact_id: uuid.UUID,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("deleteContact")),
) -> None:
    _load(uow, principal, vendor_id, "deleteContact")
    contacts_service.delete(uow, contacts_service.get(uow.session, vendor_id, contact_id))


# ── observations ────────────────────────────────────────────────────────────
@router.get("/vendors/{vendor_id}/observations")
def list_observations(
    vendor_id: uuid.UUID,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 25,
    field_code: Annotated[list[str] | None, Query()] = None,
    source: Annotated[list[ObservationSource] | None, Query()] = None,
    current_only: bool = False,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("listObservations")),
) -> FieldObservationPage:
    """Provenance history, newest first; ``current_only`` returns the resolver's winners."""
    _load(uow, principal, vendor_id, "listObservations")
    current = observations_service.current_ids(uow.session, vendor_id)
    if current_only:
        rows = observations_service.current_observations(uow.session, vendor_id)
        if field_code:
            rows = [row for row in rows if row.field_code in set(field_code)]
        if source:
            rows = [row for row in rows if row.source in set(source)]
        total = len(rows)
        window = rows[(page - 1) * page_size : page * page_size]
    else:
        window, total = observations_service.history(
            uow.session,
            vendor_id,
            field_codes=field_code,
            sources=source,
            limit=page_size,
            offset=(page - 1) * page_size,
        )
    return FieldObservationPage(
        items=[observation_payload(row, current) for row in window],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/vendors/{vendor_id}/observations", status_code=status.HTTP_201_CREATED)
def create_observation(
    vendor_id: uuid.UUID,
    body: ObservationInput,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("createObservation")),
) -> FieldObservation:
    """Manual entry or correction; the reason is mandatory (spec §6.5)."""
    vendors_service.get(uow.session, vendor_id)
    row = observations_service.record(
        uow,
        vendor_id,
        body.field_code,
        body.value,
        source=ObservationSource.MANUAL,
        unit=body.unit,
        observed_at=body.observed_at,
        reason=body.reason,
    )
    return observation_payload(row, observations_service.current_ids(uow.session, vendor_id))


# ── documents ───────────────────────────────────────────────────────────────
@router.get("/vendors/{vendor_id}/documents")
def list_documents(
    vendor_id: uuid.UUID,
    status_filter: Annotated[list[DocumentStatus] | None, Query(alias="status")] = None,
    expiring_within_days: Annotated[int | None, Query(ge=0)] = None,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("listDocuments")),
) -> list[Document]:
    """Always every catalogue code, including the ones with status ``missing`` (contract)."""
    vendor = _load(uow, principal, vendor_id, "listDocuments")
    rows = documents_service.checklist(uow.session, vendor)
    if status_filter:
        wanted = set(status_filter)
        rows = [row for row in rows if row.status in wanted]
    if expiring_within_days is not None:
        window = expiring_within_days
        rows = [
            row
            for row in rows
            if (left := days_to_expiry(row.expiry_date)) is not None and 0 <= left <= window
        ]
    return [document_payload(row, vendor_id) for row in rows]


@router.post("/vendors/{vendor_id}/documents/upload-init")
def init_document_upload(
    vendor_id: uuid.UUID,
    body: UploadInit,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("initDocumentUpload")),
    settings: Settings = Depends(get_settings),
    storage: Storage = Depends(get_storage),
) -> UploadTicket:
    """A pre-signed S3 target, or the local equivalent — the client cannot tell (ADR-002)."""
    vendor = _load(uow, principal, vendor_id, "initDocumentUpload")
    ttl = settings.storage_url_ttl_minutes * 60
    upload_id, ticket, token = documents_service.start_upload(
        uow,
        vendor,
        storage,
        code=body.code,
        filename=body.filename,
        content_type=body.content_type,
        size=body.size,
        max_bytes=settings.upload_max_bytes,
        ttl_seconds=ttl,
        secret=settings.session_secret,
    )
    # The signed ticket stays server-side; the contract's body carries only the UUID that
    # stands for it, so nothing bearer-shaped travels through the client.
    _remember_ticket(upload_id, token)
    return UploadTicket(
        upload_id=upload_id,
        url=ticket.url,
        method=ticket.method,
        headers=ticket.headers,
        expires_at=ticket.expires_at,
    )


@router.post("/vendors/{vendor_id}/documents/upload-complete")
def complete_document_upload(
    vendor_id: uuid.UUID,
    body: UploadCompletion,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("completeDocumentUpload")),
    settings: Settings = Depends(get_settings),
    storage: Storage = Depends(get_storage),
) -> Document:
    """Record the document. For ``A-05`` the expiry is forced to issue + 3 months (spec §7)."""
    vendor = _load(uow, principal, vendor_id, "completeDocumentUpload")
    token = _UPLOAD_TICKETS.pop(body.upload_id, None)
    if token is None:
        raise ApiError(409, "conflict", "Unknown or already-used upload ticket.")
    document = documents_service.complete_upload(
        uow,
        vendor,
        storage,
        upload_token=token,
        code=body.code,
        issue_date=body.issue_date,
        expiry_date=body.expiry_date,
        secret=settings.session_secret,
    )
    return _one_document(uow, vendor, document.code)


def _one_document(uow: UnitOfWork, vendor: VendorRow, code: str) -> Document:
    for row in documents_service.checklist(uow.session, vendor):
        if row.code == code:
            return document_payload(row, vendor.id)
    raise ApiError(404, "not_found", "No such document code for this vendor.")


@router.patch("/vendors/{vendor_id}/documents/{document_id}")
def patch_document(
    vendor_id: uuid.UUID,
    document_id: uuid.UUID,
    body: DocumentPatch,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("patchDocument")),
) -> Document:
    vendor = _load(uow, principal, vendor_id, "patchDocument")
    document = documents_service.get(uow.session, vendor_id, document_id)
    documents_service.patch(
        uow,
        document,
        body.model_dump(exclude_unset=True),
        role=principal.role,
        actor_id=principal.user_id,
    )
    return _one_document(uow, vendor, document.code)


@router.get("/vendors/{vendor_id}/documents/{document_id}")
def get_document_download(
    vendor_id: uuid.UUID,
    document_id: uuid.UUID,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("getDocumentDownload")),
    settings: Settings = Depends(get_settings),
    storage: Storage = Depends(get_storage),
) -> DownloadTicket:
    """A signed, expiring link (spec §13) — never the object key itself."""
    _load(uow, principal, vendor_id, "getDocumentDownload")
    document = documents_service.get(uow.session, vendor_id, document_id)
    url, expires_at, filename = documents_service.download_ticket(
        storage, document, ttl_seconds=settings.storage_url_ttl_minutes * 60
    )
    return DownloadTicket(url=url, expires_at=expires_at, filename=filename)


# ── lifecycle ───────────────────────────────────────────────────────────────
@router.post("/vendors/{vendor_id}/suspend")
def suspend_vendor(
    vendor_id: uuid.UUID,
    body: SuspendInput,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("suspendVendor")),
) -> Vendor:
    """Manager suspends or lifts, with a mandatory reason (spec §9)."""
    vendor = vendors_service.get(uow.session, vendor_id)
    vendors_service.suspend(uow, vendor, suspended=body.suspended, reason=body.reason)
    return vendor_payload(uow, vendor)


@router.post("/vendors/{vendor_id}/invite", status_code=status.HTTP_201_CREATED)
def invite_vendor(
    vendor_id: uuid.UUID,
    body: InviteInput,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("inviteVendor")),
    settings: Settings = Depends(get_settings),
) -> Application:
    """Move the vendor to ``invited``, open its application and e-mail the contact."""
    vendor = vendors_service.get(uow.session, vendor_id)
    application = applications_service.invite(uow, vendor, cycle_id=body.cycle_id)
    auth_service.notify_invitation(
        uow, settings, vendor, message_az=body.message_az, message_en=body.message_en
    )
    return applications_service.payload(uow.session, application)


__all__ = ["router"]
