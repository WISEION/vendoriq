"""Outbound webhooks and adapter sync history (brief §5, spec §6)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, JsonList, TimestampMixin, pg_enum, uuid_pk
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
