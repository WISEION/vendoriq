"""The 38-slot document package: uploads, expiry rules and verification (spec §7, §13).

Two rules carry the weight here. **A-05 expires three months after issue** whatever the
client sends, because the tax clearance certificate does not print an expiry and the vendor
is guessing. And **the checklist is complete by construction**: ``GET`` returns every
catalogue code, with status ``missing`` where nothing was uploaded, so the portal's checklist
and the officer's verification list are the same list.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..catalog import (
    DEFAULT_EXPIRING_WINDOW_DAYS,
    DOCUMENT_CATALOG,
    DocumentDef,
    checklist_for,
    days_to_expiry,
    expiry_state,
    resolve_expiry,
)
from ..db import UnitOfWork
from ..errors import ApiError
from ..models import Document, Vendor
from ..models.enums import DocumentExpiryState, DocumentStatus, EventType, UserRole
from ..security.tokens import TokenError, sign, unsign
from ..storage import Storage, document_key
from . import audit, events

#: Only PDFs (spec §7). The importer's .xlsx originals go through the import run, not here.
ALLOWED_CONTENT_TYPES = frozenset({"application/pdf"})

#: What a vendor may set on its own documents. Verification is the officer's stamp.
VENDOR_SETTABLE_STATUSES = frozenset({DocumentStatus.IN_PREPARATION, DocumentStatus.NOT_APPLICABLE})

FIELDS = ("code", "status", "filename", "file_key", "issue_date", "expiry_date", "verified_at")


@dataclass(frozen=True, slots=True)
class ChecklistRow:
    """One catalogue slot, whether or not a file has been uploaded into it."""

    definition: DocumentDef
    document: Document | None

    @property
    def code(self) -> str:
        return self.definition.code

    @property
    def status(self) -> DocumentStatus:
        return self.document.status if self.document else DocumentStatus.MISSING

    @property
    def expiry_date(self) -> date | None:
        return self.document.expiry_date if self.document else None

    def state(
        self, *, today: date | None = None, window_days: int = DEFAULT_EXPIRING_WINDOW_DAYS
    ) -> DocumentExpiryState:
        return expiry_state(self.status, self.expiry_date, today=today, window_days=window_days)

    def days_left(self, *, today: date | None = None) -> int | None:
        return days_to_expiry(self.expiry_date, today=today)


def stored(session: Session, vendor_id: uuid.UUID) -> dict[str, Document]:
    """The rows that exist, keyed by code. At most one document per code per vendor."""
    rows = session.scalars(select(Document).where(Document.vendor_id == vendor_id)).all()
    return {row.code: row for row in rows}


def checklist(session: Session, vendor: Vendor) -> list[ChecklistRow]:
    """Every catalogue code for this vendor type, in code order (contract: always all)."""
    existing = stored(session, vendor.id)
    return [
        ChecklistRow(definition=definition, document=existing.get(definition.code))
        for definition in checklist_for(vendor.type)
    ]


def get(session: Session, vendor_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    document = session.get(Document, document_id)
    if document is None or document.vendor_id != vendor_id:
        raise ApiError(404, "not_found", "No such document for this vendor.")
    return document


def _require_catalogue_code(code: str) -> DocumentDef:
    definition = DOCUMENT_CATALOG.get(code)
    if definition is None:
        raise ApiError(
            422,
            "validation_error",
            f"{code!r} is not a document checklist code (spec Appendix B).",
            {"code": code},
        )
    return definition


# ── upload ──────────────────────────────────────────────────────────────────
def start_upload(
    uow: UnitOfWork,
    vendor: Vendor,
    storage: Storage,
    *,
    code: str,
    filename: str,
    content_type: str,
    size: int,
    max_bytes: int,
    ttl_seconds: int,
    secret: str,
) -> tuple[uuid.UUID, Any, str]:
    """Reserve a key and hand back a signed target.

    Returns ``(upload_id, SignedUrl, key)``. The ``upload_id`` is itself a signed token
    binding the key, the vendor and the code, so ``upload-complete`` cannot be talked into
    attaching someone else's object to this vendor's checklist.
    """
    _require_catalogue_code(code)
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ApiError(
            415,
            "unsupported_media_type",
            "Only application/pdf is accepted for vendor documents (spec §7).",
            {"content_type": content_type},
        )
    if size <= 0 or size > max_bytes:
        raise ApiError(
            413,
            "payload_too_large",
            f"The document exceeds the {max_bytes} byte limit.",
            {"size": size, "max_bytes": max_bytes},
        )
    key = document_key(vendor.id, code, filename)
    upload_id = uuid.uuid4()
    ticket = storage.upload_url(key, content_type=content_type, ttl_seconds=ttl_seconds)
    token = sign(
        {
            "uid": str(upload_id),
            "vendor": str(vendor.id),
            "code": code,
            "key": key,
            "filename": filename,
        },
        secret,
        ttl_seconds=ttl_seconds,
    )
    return upload_id, ticket, token


def complete_upload(
    uow: UnitOfWork,
    vendor: Vendor,
    storage: Storage,
    *,
    upload_token: str,
    code: str,
    issue_date: date | None,
    expiry_date: date | None,
    secret: str,
) -> Document:
    """Record the document once the bytes are in the store."""
    try:
        payload = unsign(upload_token, secret)
    except TokenError as exc:
        raise ApiError(409, "conflict", "The upload ticket is invalid or has expired.") from exc
    if payload.get("vendor") != str(vendor.id) or payload.get("code") != code:
        raise ApiError(409, "conflict", "The upload ticket does not match this vendor and code.")
    key = str(payload["key"])
    if not storage.exists(key):
        raise ApiError(409, "conflict", "No file was uploaded against this ticket.", {"code": code})

    definition = _require_catalogue_code(code)
    existing = stored(uow.session, vendor.id).get(code)
    before = audit.snapshot(existing, FIELDS) if existing else None
    document = existing or Document(vendor_id=vendor.id, code=code)
    # Replacing a document leaves the previous object orphaned rather than deleting it: the
    # audit row names the old key, and an accidental overwrite has to be recoverable.
    document.file_key = key
    document.filename = str(payload.get("filename") or definition.code)
    document.issue_date = issue_date
    document.expiry_date = resolve_expiry(code, issue_date, expiry_date)
    document.status = DocumentStatus.UPLOADED
    document.verified_by = None
    document.verified_at = None
    if existing is None:
        uow.session.add(document)
    uow.flush()
    audit.record(
        uow,
        entity_type="document",
        entity_id=document.id,
        action="upload",
        before=before,
        after=audit.snapshot(document, FIELDS),
    )
    events.emit(
        uow,
        EventType.DOCUMENT_UPLOADED,
        entity_type="document",
        entity_id=document.id,
        payload={
            "vendor_id": str(vendor.id),
            "code": code,
            "expiry_date": document.expiry_date.isoformat() if document.expiry_date else None,
        },
    )
    return document


def patch(
    uow: UnitOfWork,
    document: Document,
    data: dict[str, Any],
    *,
    role: UserRole | None,
    actor_id: uuid.UUID | None,
) -> Document:
    """Status, dates and verification. Vendors get a strict subset (contract)."""
    is_vendor = role is UserRole.VENDOR
    before = audit.snapshot(document, FIELDS)

    if "status" in data and data["status"] is not None:
        target = DocumentStatus(data["status"])
        if is_vendor and target not in VENDOR_SETTABLE_STATUSES:
            raise ApiError(
                403,
                "forbidden",
                "A vendor may only set in_preparation or not_applicable here; "
                "uploaded comes from an upload and missing is the absence of one.",
                {"status": target.value},
            )
        document.status = target
        if target is not DocumentStatus.UPLOADED:
            document.verified_by = None
            document.verified_at = None

    if "issue_date" in data:
        document.issue_date = data["issue_date"]
    if "issue_date" in data or "expiry_date" in data:
        document.expiry_date = resolve_expiry(
            document.code,
            document.issue_date,
            data.get("expiry_date", document.expiry_date),
        )

    if data.get("verified") is not None:
        if is_vendor:
            raise ApiError(403, "forbidden", "Only an officer verifies a document (spec §3).")
        if data["verified"]:
            document.verified_by = actor_id
            document.verified_at = datetime.now(UTC)
        else:
            document.verified_by = None
            document.verified_at = None

    uow.flush()
    after = audit.snapshot(document, FIELDS)
    audit.record(
        uow,
        entity_type="document",
        entity_id=document.id,
        action="update",
        before={key: before[key] for key in audit.diff(before, after)},
        after=audit.diff(before, after),
    )
    return document


def download_ticket(
    storage: Storage, document: Document, *, ttl_seconds: int
) -> tuple[str, datetime, str]:
    """A signed, expiring link (spec §13). Both backends produce one; only the shape differs."""
    if not document.file_key:
        raise ApiError(404, "not_found", "This checklist slot holds no file.")
    signed = storage.download_url(
        document.file_key, filename=document.filename, ttl_seconds=ttl_seconds
    )
    return signed.url, signed.expires_at, document.filename or document.code


def missing_mandatory(session: Session, vendor: Vendor) -> list[str]:
    """Mandatory codes without an uploaded, unexpired file — the pre-submission check."""
    today = datetime.now(UTC).date()
    missing: list[str] = []
    for row in checklist(session, vendor):
        if not row.definition.mandatory:
            continue
        if row.state(today=today) in {DocumentExpiryState.MISSING, DocumentExpiryState.EXPIRED}:
            missing.append(row.code)
    return missing


def expiring(
    session: Session, *, within_days: int = DEFAULT_EXPIRING_WINDOW_DAYS, today: date | None = None
) -> list[Document]:
    """Every uploaded document expiring inside the window — reminders and intel (spec §12)."""
    reference = today or datetime.now(UTC).date()
    rows = session.scalars(
        select(Document)
        .where(
            Document.status == DocumentStatus.UPLOADED,
            Document.expiry_date.is_not(None),
        )
        .order_by(Document.expiry_date.asc())
    ).all()
    return [
        row
        for row in rows
        if row.expiry_date is not None and 0 <= (row.expiry_date - reference).days <= within_days
    ]
