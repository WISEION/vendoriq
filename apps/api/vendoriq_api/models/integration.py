"""Outbound webhooks and adapter sync history (brief §5, spec §6)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, JsonDict, JsonList, TimestampMixin, pg_enum, uuid_pk
from .enums import SyncResult

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .vendor import Vendor


class Webhook(Base, TimestampMixin):
    """HTTP subscriber for domain events; payloads carry an HMAC signature."""

    __tablename__ = "webhook"

    id: Mapped[uuid.UUID] = uuid_pk()
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    #: Shared secret used for the ``X-VendorIQ-Signature`` HMAC.
    secret: Mapped[str] = mapped_column(String(255), nullable=False)
    #: e.g. ``["vendor.prequalified", "application.submitted"]``.
    events: Mapped[JsonList] = mapped_column(nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_delivery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class SyncLog(Base):
    """One adapter run against one vendor (or the whole register when ``vendor_id`` is NULL)."""

    __tablename__ = "sync_log"

    id: Mapped[uuid.UUID] = uuid_pk()
    #: Adapter key: ``generic_rest``, ``csv``, ``erp_1c``, ``erp_sap``, ``erp_odoo``,
    #: ``registry``, ``excel``.
    adapter: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vendor.id", ondelete="CASCADE"), nullable=True, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Number of field observations written by this run.
    fields_written: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: ``[{code, message_az, message_en, field_code}]``.
    warnings: Mapped[JsonList] = mapped_column(nullable=False, default=list)
    result: Mapped[SyncResult] = mapped_column(
        pg_enum(SyncResult, "sync_result"), nullable=False, default=SyncResult.SUCCESS
    )

    vendor: Mapped[Vendor | None] = relationship()


class AdapterConfig(Base, TimestampMixin):
    """How one adapter reaches one vendor's system (spec §6.3).

    A table rather than rows in ``setting``: this is per-vendor operational configuration
    with its own shape, and ``services/settings_store.py`` deliberately refuses keys outside
    its five declared groups — so configuration hidden there would be invisible to the admin
    settings screen and uneditable through it, while still being the thing that decides
    whether a nightly pull runs.
    """

    __tablename__ = "adapter_config"
    __table_args__ = (UniqueConstraint("adapter", "vendor_id", name="uq_adapter_config_target"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    #: Adapter key, as in ``SyncLog.adapter``.
    adapter: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    #: NULL configures the adapter for the whole register rather than one vendor.
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vendor.id", ondelete="CASCADE"), nullable=True, index=True
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    base_url: Mapped[str | None] = mapped_column(String(1024))
    #: ``none`` | ``basic`` | ``bearer`` | ``api_key``.
    auth_type: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    username: Mapped[str | None] = mapped_column(String(255))
    #: Token or password. Write-only through the API — never serialised back.
    secret: Mapped[str | None] = mapped_column(Text)
    #: ``{"remote_field": "field_code"}``.
    field_map: Mapped[JsonDict] = mapped_column(nullable=False, default=dict)
    schedule_cron: Mapped[str | None] = mapped_column(String(64))

    vendor: Mapped[Vendor | None] = relationship()


class ImportPreview(Base):
    """A parsed workbook awaiting the officer's confirmation (spec §6.1).

    Previews were held in process memory. That is correct for one process and silently wrong
    behind a load balancer: the confirmation can reach a different worker than the one that
    parsed the file, and the officer is told the preview expired. Parsing is the expensive
    half, so the parsed result is stored and the write step reads it back.
    """

    __tablename__ = "import_preview"

    id: Mapped[uuid.UUID] = uuid_pk()
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vendor.id", ondelete="CASCADE"), nullable=True, index=True
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: When this preview stops being confirmable; a background sweep removes expired rows.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: The full parsed result: answers, tables, derived indicators, document statuses.
    parsed: Mapped[JsonDict] = mapped_column(nullable=False, default=dict)
    #: ``[{code, severity, field_code, sheet, cell, raw_value, message_az, message_en}]``.
    warnings: Mapped[JsonList] = mapped_column(nullable=False, default=list)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    vendor: Mapped[Vendor | None] = relationship()
