"""Post-award performance records — stored from phase 1, scored from phase 2 (spec §6.5)."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, uuid_pk


class PerformanceRecord(Base, TimestampMixin):
    """How a vendor actually performed on one project in one period."""

    __tablename__ = "performance_record"

    id: Mapped[uuid.UUID] = uuid_pk()
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vendor.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project.id", ondelete="SET NULL"), nullable=True, index=True
    )
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    #: Share of milestones delivered on time, 0–100.
    on_time_pct: Mapped[float | None] = mapped_column(Numeric(5, 2))
    quality_ncr_count: Mapped[int | None] = mapped_column(Integer)
    hse_incidents: Mapped[int | None] = mapped_column(Integer)
    payment_disputes: Mapped[int | None] = mapped_column(Integer)
    #: Overall 0–5 site rating.
    rating: Mapped[float | None] = mapped_column(Numeric(3, 1))
    recorded_by_name: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(nullable=False, default=False)
