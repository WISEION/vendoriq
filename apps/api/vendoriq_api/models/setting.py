"""Organisation settings — matching thresholds, validity, notifications (spec §11.2)."""

from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, JsonDict, TimestampMixin


class Setting(Base, TimestampMixin):
    """A single key/value pair. Values are JSON so a threshold set fits in one row."""

    __tablename__ = "setting"

    #: e.g. ``matching.capacity_ratio``, ``matching.strong_min``,
    #: ``qualification.validity_months``, ``notifications.expiry_days``.
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[JsonDict] = mapped_column(nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
