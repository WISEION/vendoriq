"""Domain event log and the immutable audit trail (brief §2, spec §13)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, JsonDict, uuid_pk

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .auth import User


class Event(Base):
    """Append-only domain event; the source of webhook deliveries and the activity feed."""

    __tablename__ = "event"
    __table_args__ = (Index("ix_event_entity", "entity_type", "entity_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    #: Dotted event name, e.g. ``vendor.prequalified``, ``document.expiring``.
    type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    payload: Mapped[JsonDict] = mapped_column(nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class AuditEvent(Base):
    """Who changed what, with the before / after images. Never updated or deleted."""

    __tablename__ = "audit_event"
    __table_args__ = (Index("ix_audit_event_entity", "entity_type", "entity_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    #: ``create`` | ``update`` | ``delete`` | ``decide`` | ``login`` | adapter action.
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    before: Mapped[JsonDict | None] = mapped_column(nullable=True)
    after: Mapped[JsonDict | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    actor: Mapped[User | None] = relationship()
