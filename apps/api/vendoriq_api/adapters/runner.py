"""Running an adapter and recording what happened.

The adapters read; this module is the only thing that writes. It appends the observations a
pull returned (ADR-004 — appended, never updated), writes the :class:`SyncLog` row the data
sources screen reads, emits ``sync.completed`` for the event log and webhooks, and leaves an
audit trail entry for spec §13's "immutable log of every integration write".

Two failure modes are kept apart, because they mean different things to an officer:

* **Nothing was configured** — no endpoint, no enabled vendor, or the registry adapter,
  which is never configured. Nothing ran, so nothing is logged; the contract answers 409.
* **It ran and failed** — the source refused, timed out or answered unusably. That is a run
  with a result, so it *is* logged, with ``result = failed``, ``fields_written = 0`` and the
  reason as a warning. The count of what a failed pull would have written is never guessed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from vendoriq_excel_import import ImportWarning

from ..db import UnitOfWork
from ..models import SyncLog, Vendor
from ..models.enums import AdapterKey, EventType, SyncResult
from ..services import audit, events, observations
from . import CONFIGURABLE, build, config_store
from .base import AdapterError, AdapterNotConfiguredError, Observation, PullResult, VendorRef


def vendor_ref(vendor: Vendor) -> VendorRef:
    """What an adapter is told about a vendor — never the ORM row itself (see ``base``)."""
    return VendorRef(
        id=vendor.id,
        legal_name=vendor.legal_name,
        voen=vendor.voen,
        external_ref=vendor.external_ref,
    )


def targets(session: Session, key: AdapterKey, vendor_id: uuid.UUID | None) -> list[Vendor]:
    """Which vendors this run covers. Empty means "nothing is configured", not "no work"."""
    if vendor_id is not None:
        vendor = session.get(Vendor, vendor_id)
        return [vendor] if vendor is not None else []
    if key not in CONFIGURABLE:
        return []
    ids = [config.vendor_id for config in config_store.enabled_configs(session, key)]
    if not ids:
        return []
    return list(
        session.scalars(select(Vendor).where(Vendor.id.in_([i for i in ids if i is not None])))
    )


def write_observations(
    uow: UnitOfWork,
    vendor_id: uuid.UUID,
    pulled: PullResult | list[Observation],
    *,
    observed_at: datetime,
) -> int:
    """Append every observation a pull returned. Returns how many rows were written."""
    written = 0
    for observation in pulled:
        observations.record(
            uow,
            vendor_id,
            observation.field_code,
            observation.value,
            source=observation.source,
            unit=observation.unit,
            source_ref=observation.source_ref,
            observed_at=observation.observed_at or observed_at,
            write_audit=False,
        )
        written += 1
    return written


def run_sync(
    uow: UnitOfWork,
    key: AdapterKey,
    *,
    vendor_id: uuid.UUID | None = None,
    since: datetime | None = None,
) -> SyncLog:
    """Run one adapter now, over one vendor or over every vendor it is configured for.

    Raises :class:`AdapterNotConfiguredError` when there is nothing to run at all — the contract's
    409 on ``POST /integrations/adapters/{adapter}/sync``.
    """
    started = datetime.now(UTC)
    vendors = targets(uow.session, key, vendor_id)
    if not vendors:
        # Ask the adapter itself for the reason, so the registry stub explains itself in its
        # own words rather than through a generic "not configured" from here.
        build(key).pull(VendorRef(id=uuid.uuid4(), legal_name="—"), since)
        raise AdapterNotConfiguredError(  # pragma: no cover - an adapter that pulls with no config
            "adapter_not_configured",
            f"The {key.value} adapter is not configured for any vendor.",
            f"{key.value} adapteri heç bir təchizatçı üçün konfiqurasiya edilməyib.",
        )

    warnings: list[ImportWarning] = []
    written = 0
    succeeded = 0
    failed = 0
    unconfigured: list[AdapterNotConfiguredError] = []
    for vendor in vendors:
        config = (
            config_store.load_or_empty(uow.session, key, vendor.id) if key in CONFIGURABLE else None
        )
        adapter = build(key, config)
        try:
            pulled = adapter.pull(vendor_ref(vendor), since)
        except AdapterNotConfiguredError as exc:
            # Nothing was attempted for this vendor: that is a configuration answer, not a
            # run. Kept apart from a failure so the contract's 409 stays meaningful.
            unconfigured.append(exc)
            warnings.append(exc.as_warning())
            continue
        except AdapterError as exc:
            failed += 1
            warnings.append(exc.as_warning())
            continue
        succeeded += 1
        warnings.extend(pulled.warnings)
        written += write_observations(uow, vendor.id, pulled, observed_at=started)

    if unconfigured and succeeded == 0 and failed == 0:
        # Not one vendor was even attempted. There is no run to log — the contract's 409.
        raise unconfigured[0]
    failed += len(unconfigured)

    result = (
        SyncResult.SUCCESS
        if failed == 0
        else SyncResult.FAILED
        if succeeded == 0
        else SyncResult.PARTIAL
    )
    return record_run(
        uow,
        key,
        vendor_id=vendors[0].id if len(vendors) == 1 else None,
        started_at=started,
        fields_written=written,
        warnings=warnings,
        result=result,
    )


def record_run(
    uow: UnitOfWork,
    key: AdapterKey,
    *,
    vendor_id: uuid.UUID | None,
    started_at: datetime,
    fields_written: int,
    warnings: list[ImportWarning],
    result: SyncResult,
) -> SyncLog:
    """Write the sync-log row, the audit row and the ``sync.completed`` event.

    Shared with the Excel import run, which is an adapter run that happens to have started
    with an upload rather than a schedule (spec §6, "the importer is an adapter too").
    """
    row = SyncLog(
        adapter=key.value,
        vendor_id=vendor_id,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        fields_written=fields_written,
        warnings=[warning.as_dict() for warning in warnings],
        result=result,
    )
    uow.session.add(row)
    uow.flush()
    audit.record(
        uow,
        entity_type="sync_log",
        entity_id=row.id,
        action="sync",
        after={
            "adapter": key.value,
            "vendor_id": vendor_id,
            "fields_written": fields_written,
            "result": result.value,
            "warning_codes": sorted({warning.code for warning in warnings}),
        },
    )
    events.emit(
        uow,
        EventType.SYNC_COMPLETED,
        entity_type="sync_log",
        entity_id=row.id,
        payload={
            "adapter": key.value,
            "vendor_id": str(vendor_id) if vendor_id else None,
            "fields_written": fields_written,
            "result": result.value,
            "warning_count": len(warnings),
        },
    )
    return row


def record_counts(session: Session) -> dict[str, int]:
    """``{adapter key: fields written across every run}`` — the screen's record count."""
    rows = session.execute(
        select(SyncLog.adapter, func.coalesce(func.sum(SyncLog.fields_written), 0)).group_by(
            SyncLog.adapter
        )
    ).all()
    return {str(adapter): int(total) for adapter, total in rows}


def last_sync_times(session: Session) -> dict[str, datetime]:
    """``{adapter key: newest run start}``. An adapter with no runs is simply absent."""
    rows = session.execute(
        select(SyncLog.adapter, func.max(SyncLog.started_at)).group_by(SyncLog.adapter)
    ).all()
    return {str(adapter): moment for adapter, moment in rows if moment is not None}
