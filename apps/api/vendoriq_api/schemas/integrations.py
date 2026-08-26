"""Adapters, sync log, Excel import, API keys and webhooks.

Contract tag ``integrations``. Shapes are transcribed from ``docs/openapi.yaml``; they do
not generate it (ADR-006).

``ImportWarning.severity`` is required, as the contract now declares it: an officer triaging
eight warnings has to know which one blocks the import, and a field that is sometimes absent
is a field every client has to guess about.

``ImportWarning.code`` stays a plain ``str`` rather than the contract's eleven-value enum,
and that is a reported divergence. The enum covers the *parser's* vocabulary, but the same
schema carries the warnings of an **adapter run** — ``source_unreachable``,
``registry_not_configured``, ``mock_record_not_found`` and the rest — through
``SyncLog.warnings``. Narrowing here would make a failed sync unserialisable, which is the
one case the sync log exists for. See the change request in this task's report.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from ..models.enums import AdapterKey, EventType, Scope, SyncResult
from .base import Model, PageMeta
from .vendors import Vendor

AuthType = Literal["none", "basic", "bearer", "api_key"]
AdapterStatus = Literal["active", "planned", "needs_configuration"]
ImportKind = Literal["application_form", "scoring_workbook"]


# ── adapters ────────────────────────────────────────────────────────────────
class Adapter(Model):
    """One data source on the data-sources screen (contract ``Adapter``)."""

    key: AdapterKey
    name_az: str
    name_en: str
    description_az: str
    description_en: str
    status: AdapterStatus
    record_count: int
    last_sync_at: datetime | None = None
    configured_vendor_count: int


class AdapterConfig(Model):
    """Per-vendor connector configuration. ``secret_masked`` is never the real secret."""

    adapter: AdapterKey
    vendor_id: uuid.UUID
    is_enabled: bool
    base_url: str | None = None
    auth_type: AuthType = "none"
    username: str | None = None
    secret_masked: str | None = None
    field_map: dict[str, str] = Field(default_factory=dict)
    schedule_cron: str | None = None


class AdapterConfigInput(Model):
    """A partial configuration. ``secret`` echoed back as the mask keeps what is stored."""

    is_enabled: bool | None = None
    base_url: str | None = None
    auth_type: AuthType | None = None
    username: str | None = None
    secret: str | None = None
    field_map: dict[str, str] | None = None
    schedule_cron: str | None = None


class SyncRunInput(Model):
    """Body of ``POST /integrations/adapters/{adapter}/sync`` — both fields optional."""

    vendor_id: uuid.UUID | None = None
    since: datetime | None = None


# ── sync log ────────────────────────────────────────────────────────────────
#: What the officer is meant to do about a warning. Clients branch on this, not on ``code``:
#: the two vocabularies below are disjoint and both will grow.
Severity = Literal["error", "warning", "info"]

#: Anomalies the workbook parser reports, addressed to a cell (contract ``ImportWarning``).
ImportWarningCode = Literal[
    "stale_certificate",
    "mixed_percent_format",
    "multi_value_cell",
    "no_expiry_literal",
    "mandatory_cell_empty",
    "currency_label_mismatch",
    "unknown_field_code",
    "unparsable_date",
    "unparsable_value",
    "document_status_missing",
    "missing_sheet",
]

#: What an adapter *run* can report (contract ``SyncWarning``) — a superset of the above,
#: because the Excel importer is an adapter and its run logs parser anomalies alongside any
#: transport failure.
SyncWarningCode = Literal[
    "stale_certificate",
    "mixed_percent_format",
    "multi_value_cell",
    "no_expiry_literal",
    "mandatory_cell_empty",
    "currency_label_mismatch",
    "unknown_field_code",
    "unparsable_date",
    "unparsable_value",
    "document_status_missing",
    "missing_sheet",
    "source_unreachable",
    "source_error_status",
    "source_unparsable",
    "adapter_not_configured",
    "adapter_disabled",
    "adapter_no_field_map",
    "registry_not_configured",
    "mock_record_not_found",
    "workbook_not_found",
    "workbook_unreadable",
]


class ImportWarning(Model):
    """One anomaly in a workbook, addressed to a human, in both languages."""

    code: ImportWarningCode
    severity: Severity
    field_code: str | None = None
    sheet: str | None = None
    cell: str | None = None
    raw_value: str | None = None
    message_az: str
    message_en: str


class SyncWarning(Model):
    """Anything an adapter run reports: a transport failure, or a parser anomaly.

    Wider than :class:`ImportWarning` rather than a sibling of it. The Excel importer is an
    adapter like any other, so its run records ``stale_certificate`` — which points at a sheet
    and a cell — in the same log a REST connector uses to record ``source_unreachable``, which
    points at nothing of the sort. The location fields are therefore optional.

    The narrower shape stays where it is true: a preview only ever parses, so
    ``ImportPreview.warnings`` cannot contain a transport code and says so.
    """

    code: SyncWarningCode
    severity: Severity
    field_code: str | None = None
    sheet: str | None = None
    cell: str | None = None
    raw_value: str | None = None
    message_az: str
    message_en: str


class SyncLog(Model):
    id: uuid.UUID
    adapter: str
    vendor_id: uuid.UUID | None = None
    vendor_name: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    fields_written: int
    #: ``SyncWarningCode`` spans both vocabularies on purpose: an Excel import is an adapter
    #: run too, so a row here carries ``stale_certificate`` as readily as ``source_unreachable``.
    warnings: list[SyncWarning] = Field(default_factory=list)
    result: SyncResult


class SyncLogPage(PageMeta):
    items: list[SyncLog]


# ── Excel import ────────────────────────────────────────────────────────────
class ImportPreviewField(Model):
    """One mapped cell, next to what the register currently holds for that field code."""

    field_code: str
    value: Any = None
    unit: str | None = None
    sheet: str
    cell: str
    current_value: Any = None
    will_change: bool


class ImportPreviewDocument(Model):
    code: str
    status: str


class ImportPreview(Model):
    """What ``previewExcelImport`` answers. Producing it writes nothing."""

    preview_id: uuid.UUID
    kind: ImportKind
    source_filename: str
    matched_vendor: Vendor | None = None
    fields: list[ImportPreviewField] = Field(default_factory=list)
    tables: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    documents: list[ImportPreviewDocument] = Field(default_factory=list)
    derived_raw: dict[str, float | None] = Field(default_factory=dict)
    warnings: list[ImportWarning] = Field(default_factory=list)


class ExcelImportRunInput(Model):
    preview_id: uuid.UUID
    vendor_id: uuid.UUID | None = None
    accept_field_codes: list[str] | None = None


# ── API keys ────────────────────────────────────────────────────────────────
class ApiKey(Model):
    id: uuid.UUID
    name: str
    scopes: list[Scope]
    prefix: str | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime
    last_used_at: datetime | None = None
    is_active: bool


class ApiKeyCreated(ApiKey):
    """The one response that carries key material. There is no second one."""

    key: str


class ApiKeyInput(Model):
    name: str
    scopes: list[Scope]


class ApiKeyPatch(Model):
    name: str | None = None
    scopes: list[Scope] | None = None
    is_active: bool | None = None


# ── webhooks ────────────────────────────────────────────────────────────────
class Webhook(Model):
    id: uuid.UUID
    url: str
    events: list[EventType]
    is_active: bool
    last_delivery_at: datetime | None = None
    failure_count: int


class WebhookInput(Model):
    url: str
    events: list[EventType]
    is_active: bool = True


class WebhookCreated(Webhook):
    """``secret`` appears here and nowhere else, ever again."""

    secret: str


class WebhookDelivery(Model):
    delivered: bool
    status_code: int | None = None
    duration_ms: int
    error: str | None = None
