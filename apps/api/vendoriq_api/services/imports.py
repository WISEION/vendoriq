"""The two-step Excel import: parse and show, then write what the officer confirmed.

Spec §6.1 and the contract are explicit that these are two operations, and the reason is the
data: the four fixture workbooks carry dates as text *and* as datetimes, percentages as
``0.95`` *and* as ``"85%"``, two VÖENs in one cell, ``"Müddətsiz"`` where a date belongs, and
a methodology sheet that says USD over figures that are AZN (brief §1.11). A human has to
look at that before it becomes the register's truth.

So ``preview`` **writes nothing into the register**. It parses, resolves the vendor, computes
what would change against the current observations, and returns the parser's anomaly list.
No ``field_observation`` and no ``sync_log`` row exists until ``create_run`` is called with
the ``preview_id`` — and then only for the field codes the officer accepted.

What preview *does* write is one ``import_preview`` row (migration ``0004``). Previews used
to live in this process's memory, which is correct for one process and silently wrong behind
a load balancer: the confirmation can reach a different worker than the one that parsed the
file, and the officer is told their upload expired. Parsing is the expensive half, so the
parsed result is stored and the write step reads it back by id.

``consumed_at`` is what makes a confirmation single-use. Without it a double-clicked button
appends every observation twice, and because observations are append-only (ADR-004) there is
nothing to undo — the duplicate is simply part of the vendor's history from then on.

Parsing is ``packages/excel_import``; the importer is an adapter like any other
(``adapters/excel.py``), so an import run writes observations with ``source = excel`` and
produces the same :class:`SyncLog` row an ERP pull does.
"""

from __future__ import annotations

import tempfile
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from vendoriq_excel_import import (
    ImportWarning,
    ParsedApplication,
    Severity,
    WorkbookVendor,
    parse_application_form,
    parse_scoring_workbook,
)

from ..adapters import observations_from_parsed
from ..adapters.base import Observation
from ..adapters.runner import record_run
from ..db import UnitOfWork
from ..errors import ApiError
from ..models import ImportPreview as ImportPreviewRow
from ..models import SyncLog, Vendor
from ..models.enums import AdapterKey, ObservationSource, SyncResult
from ..services import observations

#: How long a preview may be confirmed for (contract: "Valid for one hour").
PREVIEW_TTL = timedelta(hours=1)

#: The only extension accepted. Spec §13 and the contract's 415 response.
ALLOWED_EXTENSION = ".xlsx"
#: Content types a browser or a script legitimately sends for an .xlsx.
ALLOWED_CONTENT_TYPES = frozenset(
    {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
        "application/octet-stream",
        "application/zip",
        "",
    }
)
#: An OOXML workbook is a ZIP; a ZIP always starts with this and an .xlsx always has this entry.
_ZIP_MAGIC = b"PK\x03\x04"
_WORKBOOK_ENTRY = "xl/workbook.xml"


# ── upload validation ───────────────────────────────────────────────────────
def validate_upload(
    filename: str, content: bytes, content_type: str | None, max_bytes: int
) -> None:
    """Refuse anything that is not an .xlsx workbook, before openpyxl sees it (spec §13).

    Three checks, because each one alone is bypassable: the extension is what the officer
    sees, the declared content type is what the client claims, and the ZIP structure is what
    the bytes actually are. A renamed PDF, a .docx and a ZIP bomb's outer wrapper all fail
    the third.
    """
    if not filename or not filename.lower().endswith(ALLOWED_EXTENSION):
        raise ApiError(
            415,
            "unsupported_media_type",
            "Only .xlsx workbooks are accepted.",
            {"filename": filename},
        )
    if (content_type or "").split(";")[0].strip().lower() not in ALLOWED_CONTENT_TYPES:
        raise ApiError(
            415,
            "unsupported_media_type",
            "Only .xlsx workbooks are accepted.",
            {"content_type": content_type},
        )
    if not content:
        raise ApiError(422, "validation_error", "The uploaded file is empty.")
    if len(content) > max_bytes:
        raise ApiError(
            413,
            "payload_too_large",
            "The workbook is larger than the upload limit.",
            {"max_bytes": max_bytes},
        )
    if not content.startswith(_ZIP_MAGIC):
        raise ApiError(
            415,
            "unsupported_media_type",
            "The file is not an .xlsx workbook.",
            {"reason": "magic"},
        )
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile as exc:
        raise ApiError(
            415,
            "unsupported_media_type",
            "The file is not a readable .xlsx workbook.",
            {"reason": "archive"},
        ) from exc
    if _WORKBOOK_ENTRY not in names:
        raise ApiError(
            415,
            "unsupported_media_type",
            "The archive is not a spreadsheet workbook.",
            {"reason": "no_workbook_part"},
        )


# ── the preview ─────────────────────────────────────────────────────────────
@dataclass(slots=True)
class PreviewField:
    """One mapped cell, next to what the register currently holds for that code."""

    field_code: str
    value: Any
    unit: str | None
    sheet: str
    cell: str
    current_value: Any
    will_change: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "field_code": self.field_code,
            "value": self.value,
            "unit": self.unit,
            "sheet": self.sheet,
            "cell": self.cell,
            "current_value": self.current_value,
            "will_change": self.will_change,
        }


@dataclass(slots=True)
class Preview:
    """Everything ``previewExcelImport`` answers with, and everything the run needs later."""

    preview_id: uuid.UUID
    kind: str
    source_filename: str
    vendor_id: uuid.UUID | None
    fields: list[PreviewField]
    tables: dict[str, list[dict[str, Any]]]
    documents: dict[str, str]
    derived: dict[str, float | None]
    warnings: list[ImportWarning]
    #: The observations a confirmed run would append, held so the run re-parses nothing.
    observations: list[Observation] = field(default_factory=list)
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC) + PREVIEW_TTL)


def _observation_payload(pulled: list[Observation]) -> list[dict[str, Any]]:
    """The observations, flattened for JSONB. Values are already plain JSON from the parser."""
    return [
        {"field_code": item.field_code, "value": item.value, "unit": item.unit} for item in pulled
    ]


def _store(
    uow: UnitOfWork,
    preview: Preview,
    *,
    kind: str,
) -> Preview:
    """Persist the parsed result and hand back the preview carrying its row id."""
    row = ImportPreviewRow(
        vendor_id=preview.vendor_id,
        filename=preview.source_filename,
        created_by=uow.actor_id if isinstance(uow.actor_id, uuid.UUID) else None,
        created_at=datetime.now(UTC),
        expires_at=preview.expires_at,
        parsed={
            "kind": kind,
            "fields": [item.as_dict() for item in preview.fields],
            "tables": preview.tables,
            "documents": preview.documents,
            "derived": preview.derived,
            "observations": _observation_payload(preview.observations),
        },
        warnings=[warning.as_dict() for warning in preview.warnings],
    )
    uow.session.add(row)
    uow.flush()
    preview.preview_id = row.id
    return preview


def purge_expired(uow: UnitOfWork, *, now: datetime | None = None) -> int:
    """Drop previews nobody confirmed. Called by the scheduled jobs; safe to call anywhere."""
    moment = now or datetime.now(UTC)
    stale = list(
        uow.session.scalars(select(ImportPreviewRow).where(ImportPreviewRow.expires_at <= moment))
    )
    for row in stale:
        uow.session.delete(row)
    uow.flush()
    return len(stale)


def _match_vendor(
    session: Session, parsed_voen: str | None, vendor_id: uuid.UUID | None
) -> Vendor | None:
    if vendor_id is not None:
        return session.get(Vendor, vendor_id)
    if not parsed_voen:
        return None
    return session.scalars(select(Vendor).where(Vendor.voen == parsed_voen)).first()


def _cell_index(parsed: ParsedApplication, code: str) -> tuple[str, str]:
    """Where a warning saw this code, when the parser recorded a location for it.

    The parser reports sheet and cell on warnings rather than on every answer, so a field
    with no anomaly has no location. Empty strings, not invented coordinates.
    """
    for warning in parsed.warnings:
        if warning.field_code == code and warning.sheet:
            return warning.sheet, warning.cell or ""
    return "", ""


def preview_application_form(
    uow: UnitOfWork,
    *,
    filename: str,
    content: bytes,
    vendor_id: uuid.UUID | None,
) -> Preview:
    """Parse an eleven-sheet application form and show what it would change."""
    parsed = _parse_form(filename, content)
    vendor = _match_vendor(uow.session, parsed.vendor.get("voen"), vendor_id)
    current = observations.current_profile(uow.session, vendor.id) if vendor is not None else {}

    fields: list[PreviewField] = []
    for code, value in parsed.answers.items():
        sheet, cell = _cell_index(parsed, code)
        fields.append(
            PreviewField(
                field_code=code,
                value=value,
                unit=parsed.units.get(code),
                sheet=sheet,
                cell=cell,
                current_value=current.get(code),
                will_change=current.get(code) != value,
            )
        )
    fields.sort(key=lambda item: item.field_code)

    preview = Preview(
        preview_id=uuid.uuid4(),
        kind="application_form",
        source_filename=filename,
        vendor_id=vendor.id if vendor is not None else None,
        fields=fields,
        tables=dict(parsed.tables),
        documents=dict(parsed.documents),
        derived=dict(parsed.derived),
        warnings=list(parsed.warnings),
        observations=observations_from_parsed(parsed, filename),
    )
    return _store(uow, preview, kind="application_form")


def preview_scoring_workbook(
    uow: UnitOfWork,
    *,
    filename: str,
    content: bytes,
    vendor_id: uuid.UUID | None,
) -> Preview:
    """Parse a Rev4-style workbook column and show the officers' raw indicators.

    A workbook holds every participant of a cycle. Which one this import is about is
    therefore a question, not a guess: with a single participant it is that one, otherwise
    the caller names the vendor and the participant is matched on VÖEN.
    """
    participants = _parse_workbook(filename, content)
    if not participants:
        raise ApiError(
            422, "validation_error", "The workbook has no participant columns.", {"file": filename}
        )
    vendor = uow.session.get(Vendor, vendor_id) if vendor_id is not None else None
    participant = _select_participant(participants, vendor, filename)
    if vendor is None:
        vendor = _match_vendor(uow.session, _voen_of(participant), None)

    current = observations.current_profile(uow.session, vendor.id) if vendor is not None else {}
    fields = [
        PreviewField(
            field_code=code,
            value=value,
            unit=None,
            sheet="3. Cavablar",
            cell="",
            current_value=current.get(code),
            will_change=current.get(code) != value,
        )
        for code, value in sorted(participant.raw.items())
        if value is not None
    ]
    pulled = [
        Observation(
            field_code=item.field_code,
            value=item.value,
            source=ObservationSource.EXCEL,
            source_ref=f"{filename}#{participant.name}",
        )
        for item in fields
    ]
    preview = Preview(
        preview_id=uuid.uuid4(),
        kind="scoring_workbook",
        source_filename=filename,
        vendor_id=vendor.id if vendor is not None else None,
        fields=fields,
        tables={},
        documents={},
        derived={},
        warnings=list(participant.warnings),
        observations=pulled,
    )
    return _store(uow, preview, kind="scoring_workbook")


def _voen_of(participant: WorkbookVendor) -> str | None:
    if participant.voen_values:
        return participant.voen_values[0]
    return str(participant.voen) if participant.voen is not None else None


def _select_participant(
    participants: list[WorkbookVendor], vendor: Vendor | None, filename: str
) -> WorkbookVendor:
    if vendor is not None and vendor.voen:
        for participant in participants:
            if _voen_of(participant) == vendor.voen:
                return participant
        raise ApiError(
            422,
            "validation_error",
            "The workbook has no column for this vendor's VÖEN.",
            {"voen": vendor.voen, "file": filename},
        )
    if len(participants) == 1:
        return participants[0]
    raise ApiError(
        422,
        "validation_error",
        "The workbook holds several participants; name the vendor to import.",
        {"participants": [participant.name for participant in participants]},
    )


def _parse_form(filename: str, content: bytes) -> ParsedApplication:
    with SpooledWorkbook(content) as path:
        try:
            return parse_application_form(path)
        except ApiError:
            raise
        except Exception as exc:  # openpyxl raises a family of unrelated errors
            raise ApiError(
                422,
                "validation_error",
                "The workbook could not be read as an application form.",
                {"file": filename},
            ) from exc


def _parse_workbook(filename: str, content: bytes) -> list[WorkbookVendor]:
    with SpooledWorkbook(content) as path:
        try:
            return list(parse_scoring_workbook(path))
        except ApiError:
            raise
        except Exception as exc:
            raise ApiError(
                422,
                "validation_error",
                "The workbook could not be read as a scoring workbook.",
                {"file": filename},
            ) from exc


class SpooledWorkbook:
    """openpyxl wants a path; an upload is bytes. A temporary file, removed on exit."""

    def __init__(self, content: bytes) -> None:
        self._content = content
        self._path: Path | None = None

    def __enter__(self) -> Path:
        handle = tempfile.NamedTemporaryFile(suffix=ALLOWED_EXTENSION, delete=False)
        try:
            handle.write(self._content)
        finally:
            handle.close()
        self._path = Path(handle.name)
        return self._path

    def __exit__(self, *_: object) -> None:
        if self._path is not None:
            self._path.unlink(missing_ok=True)


# ── the run ─────────────────────────────────────────────────────────────────
def _claim(uow: UnitOfWork, preview_id: uuid.UUID) -> ImportPreviewRow:
    """Fetch a preview that may still be applied, and mark it applied.

    Three ways a preview is unusable, and the officer is told which: it never existed, it
    expired, or it was already written. All three answer 404 because
    ``createExcelImportRun`` declares only 201 and 404 in the contract; ``details.reason``
    carries the distinction.

    The row is locked, not merely read. A double-clicked confirm is two requests in two
    transactions, and without the lock both read ``consumed_at IS NULL`` and both write the
    whole workbook. Observations are append-only (ADR-004), so that duplicate cannot be
    taken back afterwards — the second request has to block here and then find the preview
    consumed.
    """
    row = uow.session.get(ImportPreviewRow, preview_id, with_for_update=True)
    if row is None:
        raise ApiError(
            404,
            "not_found",
            "No such import preview.",
            {"preview_id": str(preview_id), "reason": "unknown"},
        )
    if row.consumed_at is not None:
        raise ApiError(
            404,
            "not_found",
            "This preview has already been written into the register.",
            {
                "preview_id": str(preview_id),
                "reason": "consumed",
                "consumed_at": row.consumed_at.isoformat(),
            },
        )
    expires_at = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        raise ApiError(
            404,
            "not_found",
            "This import preview has expired; upload the workbook again.",
            {"preview_id": str(preview_id), "reason": "expired"},
        )
    return row


def create_run(
    uow: UnitOfWork,
    *,
    preview_id: uuid.UUID,
    vendor_id: uuid.UUID | None = None,
    accept_field_codes: list[str] | None = None,
) -> SyncLog:
    """Write a confirmed preview. This is the only function in this module that writes
    observations."""
    row = _claim(uow, preview_id)
    target = vendor_id or row.vendor_id
    if target is None:
        raise ApiError(
            404,
            "not_found",
            "The workbook did not match a vendor in the register; name one to import into.",
            {"reason": "no_vendor"},
        )
    vendor = uow.session.get(Vendor, target)
    if vendor is None:
        raise ApiError(404, "not_found", "No such vendor.", {"reason": "no_vendor"})

    accepted = set(accept_field_codes) if accept_field_codes else None
    started = datetime.now(UTC)
    parsed = row.parsed if isinstance(row.parsed, dict) else {}
    pulled = parsed.get("observations") or []
    written = 0
    for item in pulled:
        if not isinstance(item, dict):  # pragma: no cover - a hand-edited row
            continue
        code = str(item.get("field_code", ""))
        if not code or (accepted is not None and code not in accepted):
            continue
        observations.record(
            uow,
            vendor.id,
            code,
            item.get("value"),
            source=ObservationSource.EXCEL,
            unit=item.get("unit"),
            source_ref=f"{row.filename}#{row.id}",
            observed_at=started,
            write_audit=False,
        )
        written += 1

    # Stamped before the sync log so a failure anywhere below rolls the claim back with it:
    # a preview is consumed exactly when its observations land, never independently.
    row.consumed_at = started
    uow.flush()

    return record_run(
        uow,
        AdapterKey.EXCEL,
        vendor_id=vendor.id,
        started_at=started,
        fields_written=written,
        warnings=[_warning_from(item) for item in row.warnings if isinstance(item, dict)],
        result=SyncResult.SUCCESS if written else SyncResult.PARTIAL,
    )


def _warning_from(payload: dict[str, Any]) -> ImportWarning:
    """Rebuild the parser's own warning from stored JSON, to hand to ``record_run``.

    This is the internal dataclass, not the response model: ``record_run`` serialises it back
    into ``sync_log.warnings`` JSONB, and the router builds the ``SyncWarning`` a client sees.
    """
    severity: Severity = "warning"
    stored = payload.get("severity")
    if stored in ("error", "warning", "info"):
        severity = stored
    return ImportWarning(
        code=str(payload.get("code", "unknown_field_code")),
        message_en=str(payload.get("message_en", "")),
        message_az=str(payload.get("message_az", "")),
        severity=severity,
        field_code=payload.get("field_code"),
        sheet=payload.get("sheet"),
        cell=payload.get("cell"),
        raw_value=payload.get("raw_value"),
    )
