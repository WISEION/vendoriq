"""The integration layer (contract tag ``integrations``, brief §4.2 task 2E, spec §6).

Everything a future product needs to build on VendorIQ is behind these fifteen operations:
the adapters that bring data in, the sync history that says what they did, the two-step Excel
import, the API keys another system authenticates with and the webhooks it subscribes to.

The handlers are thin on purpose. Adapter behaviour is ``vendoriq_api.adapters``, the writes
are ``adapters.runner``, signing and delivery are ``services.webhooks``, key lifecycle is
``services.api_keys`` and the import is ``services.imports`` — a router that decided any of
that would be a second place the rules live.

Authorisation is ``require("<operationId>")`` against the matrix in
``security/permissions.py``. Two entries there are worth reading twice: ``createApiKey`` and
every webhook operation have **no API-key scope at all**, so a key can never mint another key
or redirect the event stream to a new endpoint. That closure is in the matrix, not here.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, get_args

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from vendoriq_excel_import import ImportWarning as ParserWarning

from ..adapters import ADAPTERS, CONFIGURABLE, AdapterError, config_store, mask_secret
from ..adapters.runner import last_sync_times, record_counts, run_sync
from ..config import Settings, get_settings
from ..db import UnitOfWork
from ..errors import ApiError
from ..models import SyncLog as SyncLogRow
from ..models import Vendor
from ..models.enums import CONTRACT_ADAPTER_KEYS, AdapterKey, Scope, SyncResult
from ..schemas.integrations import (
    Adapter,
    AdapterConfig,
    AdapterConfigInput,
    ApiKey,
    ApiKeyCreated,
    ApiKeyInput,
    ApiKeyPatch,
    ExcelImportRunInput,
    ImportPreview,
    ImportPreviewDocument,
    ImportPreviewField,
    ImportWarning,
    ImportWarningCode,
    Severity,
    SyncLog,
    SyncLogPage,
    SyncRunInput,
    SyncWarning,
    SyncWarningCode,
    Webhook,
    WebhookCreated,
    WebhookDelivery,
    WebhookInput,
)
from ..schemas.vendors import Vendor as VendorSchema
from ..security import Principal, get_uow, require
from ..services import api_keys as api_keys_service
from ..services import audit
from ..services import imports as imports_service
from ..services import webhooks as webhooks_service

router = APIRouter(tags=["integrations"])

# The dispatcher is installed at import time, and this module is imported by ``main.py``
# through ``routers/__init__.py``. That is the whole wiring: ``services.events.emit`` calls
# whatever dispatcher is installed, so every event any feature emits — from any router —
# reaches the subscriptions without that feature knowing webhooks exist.
webhooks_service.install_dispatcher()


# ── helpers ─────────────────────────────────────────────────────────────────
def _adapter_key(adapter: str) -> AdapterKey:
    """Resolve a path segment to an adapter the contract actually publishes."""
    try:
        key = AdapterKey(adapter)
    except ValueError as exc:
        raise ApiError(404, "not_found", "No such adapter.", {"adapter": adapter}) from exc
    if key not in CONTRACT_ADAPTER_KEYS:
        raise ApiError(404, "not_found", "No such adapter.", {"adapter": adapter})
    return key


def _vendor(session: Session, vendor_id: uuid.UUID) -> Vendor:
    vendor = session.get(Vendor, vendor_id)
    if vendor is None:
        raise ApiError(404, "not_found", "No such vendor.")
    return vendor


#: Which model a stored warning belongs to, decided by its own ``code``.
_SYNC_CODES: frozenset[str] = frozenset(get_args(SyncWarningCode))
_IMPORT_CODES: frozenset[str] = frozenset(get_args(ImportWarningCode))


def _as_dict(payload: dict[str, Any] | ParserWarning) -> dict[str, Any]:
    return payload.as_dict() if isinstance(payload, ParserWarning) else payload


def _severity(data: dict[str, Any]) -> Severity:
    """Required by the contract. Every producer sets it; this guards a legacy JSONB row."""
    stored = data.get("severity")
    return stored if stored in ("error", "warning", "info") else "warning"


def _sync_warning(payload: dict[str, Any] | ParserWarning) -> SyncWarning:
    """One row of ``SyncLog.warnings``.

    A run's log carries both vocabularies — ``source_unreachable`` from a connector that could
    not be reached, and ``stale_certificate`` from an Excel import, which is an adapter run
    too — so ``SyncWarning`` spans both and keeps the location fields the parser half needs.
    An unrecognised stored code degrades to ``source_unparsable`` rather than failing the
    response: a sync log that cannot be read is worse than one row rendered vaguely.
    """
    data = _as_dict(payload)
    code = str(data.get("code", ""))
    return SyncWarning(
        code=code if code in _SYNC_CODES else "source_unparsable",  # type: ignore[arg-type]
        severity=_severity(data),
        field_code=data.get("field_code"),
        sheet=data.get("sheet"),
        cell=data.get("cell"),
        raw_value=data.get("raw_value"),
        message_az=str(data.get("message_az", "")),
        message_en=str(data.get("message_en", "")),
    )


def _warning(payload: dict[str, Any] | ParserWarning) -> ImportWarning:
    data = _as_dict(payload)
    return ImportWarning(
        # Narrowed against the parser vocabulary; an unrecognised code is reported as a
        # mapping problem rather than dropped.
        code=code if (code := str(data.get("code", ""))) in _IMPORT_CODES else "unknown_field_code",  # type: ignore[arg-type]
        field_code=data.get("field_code"),
        sheet=data.get("sheet"),
        cell=data.get("cell"),
        raw_value=data.get("raw_value"),
        message_az=str(data.get("message_az", "")),
        message_en=str(data.get("message_en", "")),
        severity=_severity(data),
    )


def _sync_log(row: SyncLogRow, vendor_name: str | None = None) -> SyncLog:
    return SyncLog(
        id=row.id,
        adapter=row.adapter,
        vendor_id=row.vendor_id,
        vendor_name=vendor_name,
        started_at=row.started_at,
        finished_at=row.finished_at,
        fields_written=row.fields_written,
        warnings=[_sync_warning(item) for item in row.warnings if isinstance(item, dict)],
        result=row.result,
    )


def _adapter_error(exc: AdapterError) -> ApiError:
    """An adapter's own words, in the contract's envelope. Never a credential."""
    return ApiError(
        exc.http_status,
        "conflict" if exc.http_status == 409 else "bad_request",
        exc.message_en,
        {"adapter_code": exc.code, "message_az": exc.message_az},
    )


# ── adapters ────────────────────────────────────────────────────────────────
@router.get("/integrations/adapters")
def list_adapters(
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("listAdapters")),
) -> list[Adapter]:
    """Every adapter with its status, what it has written and when it last ran."""
    counts = record_counts(uow.session)
    last = last_sync_times(uow.session)
    result: list[Adapter] = []
    for key, adapter_class in ADAPTERS.items():
        configured = (
            len(config_store.configured_vendor_ids(uow.session, key)) if key in CONFIGURABLE else 0
        )
        enabled = len(config_store.enabled_configs(uow.session, key)) if key in CONFIGURABLE else 0
        status = adapter_class.default_status
        if key in CONFIGURABLE:
            status = "active" if enabled else "needs_configuration"
        result.append(
            Adapter(
                key=key,
                name_az=adapter_class.name_az,
                name_en=adapter_class.name_en,
                description_az=adapter_class.description_az,
                description_en=adapter_class.description_en,
                status=status,
                record_count=counts.get(key.value, 0),
                last_sync_at=last.get(key.value),
                configured_vendor_count=configured,
            )
        )
    return result


@router.get("/integrations/adapters/{adapter}/vendors/{vendor_id}/config")
def get_adapter_config(
    adapter: str,
    vendor_id: uuid.UUID,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("getAdapterConfig")),
) -> AdapterConfig:
    """The stored configuration, with the credential masked (contract)."""
    key = _adapter_key(adapter)
    _vendor(uow.session, vendor_id)
    stored = config_store.load_or_empty(uow.session, key, vendor_id)
    return AdapterConfig(
        adapter=key,
        vendor_id=vendor_id,
        is_enabled=stored.is_enabled,
        base_url=stored.base_url,
        auth_type=stored.auth_type,
        username=stored.username,
        secret_masked=mask_secret(stored.secret),
        field_map=dict(stored.field_map),
        schedule_cron=stored.schedule_cron,
    )


@router.put("/integrations/adapters/{adapter}/vendors/{vendor_id}/config")
def put_adapter_config(
    adapter: str,
    vendor_id: uuid.UUID,
    payload: AdapterConfigInput,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("putAdapterConfig")),
) -> AdapterConfig:
    """Configure one connector for one vendor."""
    key = _adapter_key(adapter)
    if key not in CONFIGURABLE:
        raise ApiError(
            409,
            "conflict",
            "This adapter is not configured per vendor.",
            {"adapter": key.value},
        )
    _vendor(uow.session, vendor_id)
    patch = payload.model_dump(exclude_unset=True)
    stored = config_store.save(uow, key, vendor_id, patch)
    audit.record(
        uow,
        entity_type="adapter_config",
        entity_id=vendor_id,
        action="update",
        # ``audit_view`` reports whether a secret exists, never what it is.
        after=config_store.audit_view(stored),
    )
    return AdapterConfig(
        adapter=key,
        vendor_id=vendor_id,
        is_enabled=stored.is_enabled,
        base_url=stored.base_url,
        auth_type=stored.auth_type,
        username=stored.username,
        secret_masked=mask_secret(stored.secret),
        field_map=dict(stored.field_map),
        schedule_cron=stored.schedule_cron,
    )


@router.post("/integrations/adapters/{adapter}/sync", status_code=202)
def run_adapter_sync(
    adapter: str,
    payload: SyncRunInput | None = None,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("runSync")),
) -> SyncLog:
    """Run an adapter now. 409 when nothing is configured; a run that failed is still a run."""
    key = _adapter_key(adapter)
    body = payload or SyncRunInput()
    vendor_name: str | None = None
    if body.vendor_id is not None:
        vendor_name = _vendor(uow.session, body.vendor_id).legal_name
    try:
        row = run_sync(uow, key, vendor_id=body.vendor_id, since=body.since)
    except AdapterError as exc:
        raise _adapter_error(exc) from exc
    return _sync_log(row, vendor_name)


@router.get("/integrations/sync-log")
def list_sync_log(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 25,
    adapter: str | None = None,
    vendor_id: uuid.UUID | None = None,
    result: SyncResult | None = None,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("listSyncLog")),
) -> SyncLogPage:
    """Adapter run history, newest first."""
    query = select(SyncLogRow)
    if adapter:
        query = query.where(SyncLogRow.adapter == adapter)
    if vendor_id is not None:
        query = query.where(SyncLogRow.vendor_id == vendor_id)
    if result is not None:
        query = query.where(SyncLogRow.result == result)
    total = uow.session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = uow.session.scalars(
        query.order_by(SyncLogRow.started_at.desc(), SyncLogRow.id.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()
    return SyncLogPage(
        items=[_sync_log(row, row.vendor.legal_name if row.vendor else None) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


# ── Excel import ────────────────────────────────────────────────────────────
@router.post("/integrations/excel-import/preview")
async def preview_excel_import(
    file: Annotated[UploadFile, File()],
    kind: Annotated[str, Form()] = "application_form",
    vendor_id: Annotated[uuid.UUID | None, Form()] = None,
    uow: UnitOfWork = Depends(get_uow),
    settings: Settings = Depends(get_settings),
    principal: Principal = Depends(require("previewExcelImport")),
) -> ImportPreview:
    """Step one of two. **Writes nothing** — the officer confirms before anything is stored."""
    if kind not in ("application_form", "scoring_workbook"):
        raise ApiError(422, "validation_error", "Unknown import kind.", {"kind": kind})
    content = await file.read()
    filename = file.filename or ""
    imports_service.validate_upload(filename, content, file.content_type, settings.upload_max_bytes)

    if kind == "application_form":
        preview = imports_service.preview_application_form(
            uow, filename=filename, content=content, vendor_id=vendor_id
        )
    else:
        preview = imports_service.preview_scoring_workbook(
            uow, filename=filename, content=content, vendor_id=vendor_id
        )

    matched = uow.session.get(Vendor, preview.vendor_id) if preview.vendor_id else None
    return ImportPreview(
        preview_id=preview.preview_id,
        kind="application_form" if preview.kind == "application_form" else "scoring_workbook",
        source_filename=preview.source_filename,
        matched_vendor=VendorSchema.model_validate(matched, from_attributes=True)
        if matched is not None
        else None,
        fields=[
            ImportPreviewField(
                field_code=item.field_code,
                value=item.value,
                unit=item.unit,
                sheet=item.sheet,
                cell=item.cell,
                current_value=item.current_value,
                will_change=item.will_change,
            )
            for item in preview.fields
        ],
        tables=preview.tables,
        documents=[
            ImportPreviewDocument(code=code, status=status)
            for code, status in sorted(preview.documents.items())
        ],
        derived_raw=preview.derived,
        warnings=[_warning(item) for item in preview.warnings],
    )


@router.post("/integrations/excel-import/runs", status_code=201)
def create_excel_import_run(
    payload: ExcelImportRunInput,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("createExcelImportRun")),
) -> SyncLog:
    """Step two: write the confirmed preview as observations with source ``excel``."""
    row = imports_service.create_run(
        uow,
        preview_id=payload.preview_id,
        vendor_id=payload.vendor_id,
        accept_field_codes=payload.accept_field_codes,
    )
    return _sync_log(row, row.vendor.legal_name if row.vendor else None)


# ── API keys ────────────────────────────────────────────────────────────────
def _api_key(row: Any) -> ApiKey:
    return ApiKey(
        id=row.id,
        name=row.name,
        scopes=[Scope(str(scope)) for scope in row.scopes],
        prefix=row.prefix,
        created_by=row.created_by,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        is_active=row.is_active,
    )


@router.get("/integrations/api-keys")
def list_api_keys(
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("listApiKeys")),
) -> list[ApiKey]:
    """Keys, newest first. The key material is not here and cannot be."""
    return [_api_key(row) for row in api_keys_service.list_keys(uow.session)]


@router.post("/integrations/api-keys", status_code=201)
def create_api_key(
    payload: ApiKeyInput,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("createApiKey")),
) -> ApiKeyCreated:
    """Mint a key. The plaintext in this response is the caller's only copy."""
    row, plaintext = api_keys_service.create(
        uow, name=payload.name, scopes=payload.scopes, created_by=principal.user_id
    )
    return ApiKeyCreated(**_api_key(row).model_dump(), key=plaintext)


@router.patch("/integrations/api-keys/{api_key_id}")
def patch_api_key(
    api_key_id: uuid.UUID,
    payload: ApiKeyPatch,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("patchApiKey")),
) -> ApiKey:
    """Rename, re-scope or deactivate."""
    row = api_keys_service.update(
        uow,
        api_key_id,
        name=payload.name,
        scopes=payload.scopes,
        is_active=payload.is_active,
    )
    return _api_key(row)


@router.delete("/integrations/api-keys/{api_key_id}", status_code=204)
def revoke_api_key(
    api_key_id: uuid.UUID,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("revokeApiKey")),
) -> Response:
    """Revoke. The next request presenting this key is anonymous."""
    api_keys_service.revoke(uow, api_key_id)
    return Response(status_code=204)


# ── webhooks ────────────────────────────────────────────────────────────────
def _webhook(row: Any) -> Webhook:
    return Webhook(
        id=row.id,
        url=row.url,
        events=list(row.events),
        is_active=row.is_active,
        last_delivery_at=row.last_delivery_at,
        failure_count=row.failure_count,
    )


@router.get("/integrations/webhooks")
def list_webhooks(
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("listWebhooks")),
) -> list[Webhook]:
    """Subscriptions. The signing secret is absent, by construction."""
    return [_webhook(row) for row in webhooks_service.list_webhooks(uow.session)]


@router.post("/integrations/webhooks", status_code=201)
def create_webhook(
    payload: WebhookInput,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("createWebhook")),
) -> WebhookCreated:
    """Subscribe. The secret in this response is shown once and never returned again."""
    row, secret = webhooks_service.create(
        uow,
        url=payload.url,
        events=[event.value for event in payload.events],
        is_active=payload.is_active,
    )
    return WebhookCreated(**_webhook(row).model_dump(), secret=secret)


@router.patch("/integrations/webhooks/{webhook_id}")
def patch_webhook(
    webhook_id: uuid.UUID,
    payload: WebhookInput,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("patchWebhook")),
) -> Webhook:
    """Change the target or the events. The secret is not rotated and is not returned."""
    row = webhooks_service.update(
        uow,
        webhook_id,
        url=payload.url,
        events=[event.value for event in payload.events],
        is_active=payload.is_active,
    )
    return _webhook(row)


@router.delete("/integrations/webhooks/{webhook_id}", status_code=204)
def delete_webhook(
    webhook_id: uuid.UUID,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("deleteWebhook")),
) -> Response:
    webhooks_service.delete(uow, webhook_id)
    return Response(status_code=204)


@router.post("/integrations/webhooks/{webhook_id}/test")
def test_webhook(
    webhook_id: uuid.UUID,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("testWebhook")),
) -> WebhookDelivery:
    """Send one signed test delivery and report exactly what the endpoint answered."""
    result = webhooks_service.send_test(uow, webhook_id)
    return WebhookDelivery(
        delivered=result.delivered,
        status_code=result.status_code,
        duration_ms=result.duration_ms,
        error=result.error,
    )


__all__ = ["router"]
