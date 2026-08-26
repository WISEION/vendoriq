"""Reading and writing a connector's per-vendor configuration.

Backed by the ``adapter_config`` table (migration ``0004``). It was `setting` rows under a
namespaced key while no table existed; ``services/settings_store.py`` refuses every key
outside its five declared groups, so configuration parked there was invisible to the admin
settings screen and uneditable through it, while still deciding whether a scheduled pull
runs. ``test_adapter_configuration_never_writes_a_setting_row`` is what keeps it out.

The public surface did not change when the table arrived — :func:`load` and :func:`save`
have the signatures they had — because nothing outside this module ever knew where the rows
lived. That was the point of routing every read and write through here.

The stored ``secret`` is a live credential for an outbound call and therefore has to be
recoverable, exactly like the webhook signing secret. It is never returned by the API
(``secret_masked``), never written to a log line, and never put in an audit row: see
:func:`audit_view`.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import UnitOfWork
from ..models import AdapterConfig as AdapterConfigRow
from ..models.enums import AdapterKey
from .base import MASKED_SENTINEL, AdapterConfig, AuthType

_AUTH_TYPES: frozenset[str] = frozenset({"none", "basic", "bearer", "api_key"})


def _as_auth_type(value: Any) -> AuthType:
    text = str(value or "none")
    if text not in _AUTH_TYPES:
        return "none"
    # The membership test above is the narrowing; mypy cannot see through a frozenset.
    return text  # type: ignore[return-value]


def _row(session: Session, adapter: AdapterKey, vendor_id: uuid.UUID) -> AdapterConfigRow | None:
    return session.scalars(
        select(AdapterConfigRow).where(
            AdapterConfigRow.adapter == adapter.value,
            AdapterConfigRow.vendor_id == vendor_id,
        )
    ).first()


def _to_config(row: AdapterConfigRow) -> AdapterConfig:
    field_map = row.field_map if isinstance(row.field_map, dict) else {}
    return AdapterConfig(
        adapter=AdapterKey(row.adapter),
        vendor_id=row.vendor_id,
        is_enabled=bool(row.is_enabled),
        base_url=row.base_url or None,
        auth_type=_as_auth_type(row.auth_type),
        username=row.username or None,
        secret=row.secret or None,
        field_map={str(key): str(value) for key, value in field_map.items()},
        schedule_cron=row.schedule_cron or None,
    )


def load(session: Session, adapter: AdapterKey, vendor_id: uuid.UUID) -> AdapterConfig | None:
    """The stored configuration, or ``None`` when this vendor was never configured."""
    row = _row(session, adapter, vendor_id)
    return None if row is None else _to_config(row)


def load_or_empty(session: Session, adapter: AdapterKey, vendor_id: uuid.UUID) -> AdapterConfig:
    """What ``GET .../config`` answers for a vendor with no row: disabled and empty."""
    return load(session, adapter, vendor_id) or AdapterConfig(adapter=adapter, vendor_id=vendor_id)


def save(
    uow: UnitOfWork,
    adapter: AdapterKey,
    vendor_id: uuid.UUID,
    patch: dict[str, Any],
) -> AdapterConfig:
    """Apply a partial ``AdapterConfigInput``.

    The masked sentinel sent back in ``secret`` means "keep what is stored" (contract), and
    an omitted ``secret`` means the same. Only an explicit new value replaces it, and an
    explicit empty string clears it — so a screen that renders the mask into its password
    field and posts the form unchanged cannot silently wipe a working credential.
    """
    row = _row(uow.session, adapter, vendor_id)
    if row is None:
        row = AdapterConfigRow(
            adapter=adapter.value,
            vendor_id=vendor_id,
            is_enabled=False,
            auth_type="none",
            field_map={},
        )
        uow.session.add(row)

    if "secret" in patch:
        submitted = patch["secret"]
        if submitted == MASKED_SENTINEL:
            pass  # the client echoed the mask: leave the stored credential alone
        elif submitted in (None, ""):
            row.secret = None
        else:
            row.secret = str(submitted)

    if "is_enabled" in patch:
        row.is_enabled = bool(patch["is_enabled"])
    if "base_url" in patch:
        row.base_url = patch["base_url"] or None
    if "auth_type" in patch:
        row.auth_type = _as_auth_type(patch["auth_type"])
    if "username" in patch:
        row.username = patch["username"] or None
    if "schedule_cron" in patch:
        row.schedule_cron = patch["schedule_cron"] or None
    if "field_map" in patch:
        submitted_map = patch["field_map"] or {}
        # Reassign rather than mutate: SQLAlchemy does not track in-place JSONB edits.
        row.field_map = {str(key): str(value) for key, value in dict(submitted_map).items()}

    uow.flush()
    return _to_config(row)


def delete(uow: UnitOfWork, adapter: AdapterKey, vendor_id: uuid.UUID) -> None:
    row = _row(uow.session, adapter, vendor_id)
    if row is not None:
        uow.session.delete(row)
        uow.flush()


def configured_vendor_ids(session: Session, adapter: AdapterKey) -> list[uuid.UUID]:
    """Vendors with a row for this adapter, enabled or not — the screen's connector count."""
    return [
        vendor_id
        for vendor_id in session.scalars(
            select(AdapterConfigRow.vendor_id).where(AdapterConfigRow.adapter == adapter.value)
        )
        if vendor_id is not None
    ]


def enabled_configs(session: Session, adapter: AdapterKey) -> list[AdapterConfig]:
    """Every enabled configuration for one adapter — what "run for every vendor" means."""
    return [
        _to_config(row)
        for row in session.scalars(
            select(AdapterConfigRow).where(
                AdapterConfigRow.adapter == adapter.value,
                AdapterConfigRow.is_enabled.is_(True),
            )
        )
    ]


def audit_view(config: AdapterConfig) -> dict[str, Any]:
    """The configuration as it may appear in an audit row: everything except the secret.

    ``has_secret`` rather than the secret, because the audit log is exportable for committee
    minutes (spec §13) and a credential in a spreadsheet attachment is a credential leak.
    """
    return {
        "adapter": config.adapter.value,
        "vendor_id": str(config.vendor_id) if config.vendor_id else None,
        "is_enabled": config.is_enabled,
        "base_url": config.base_url,
        "auth_type": config.auth_type,
        "username": config.username,
        "has_secret": config.secret is not None,
        "field_map": dict(config.field_map),
        "schedule_cron": config.schedule_cron,
    }
