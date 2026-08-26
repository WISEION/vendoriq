"""Evaluations — one rubric set per evaluator per application (spec §10.3).

Replaces ``application.second_rubric``: the "optional second evaluator" is not a second
column, it is a second row. That keeps a third evaluator, an audit of who scored what and
the divergence report from needing another schema change.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, JsonDict, uuid_pk

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .auth import User
    from .qualification import Application


class Evaluation(Base):
    """One evaluator's 0–3 rubric cells and the engine output they produced.

    ``is_primary`` marks the set the application's decision is taken from; every other row
    is a cross-check whose divergences the evaluation screen flags (spec §10.3).
    """

    __tablename__ = "evaluation"
    __table_args__ = (
        UniqueConstraint("application_id", "evaluator_id"),
        Index("ix_evaluation_application_primary", "application_id", "is_primary"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("application.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: NULL when the evaluator's account was later removed — the row itself is evidence.
    evaluator_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    #: ``{"<criterion code>": 0..3}`` plus an optional ``evidence`` note per criterion.
    rubric: Mapped[JsonDict] = mapped_column(nullable=False, default=dict)
    #: Engine output for this rubric set: ``{"per", "groups", "total", "ko", "cls"}``.
    computed: Mapped[JsonDict | None] = mapped_column(nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    application: Mapped[Application] = relationship(back_populates="evaluations")
    evaluator: Mapped[User | None] = relationship()
