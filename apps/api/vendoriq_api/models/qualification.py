"""Qualification cycles and applications (spec §5, §9, §10)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, JsonDict, TimestampMixin, pg_enum, uuid_pk
from .enums import ApplicationStatus, CycleKind, CycleStatus, DecisionKind

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .project import Project
    from .scoring_model import ScoringModel
    from .vendor import Vendor


class QualificationCycle(Base, TimestampMixin):
    """Groups applications — one TQS tender round or one periodic re-qualification."""

    __tablename__ = "qualification_cycle"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[CycleKind] = mapped_column(pg_enum(CycleKind, "cycle_kind"), nullable=False)
    #: Version of the scoring model every application in this cycle is scored with.
    scoring_model_version: Mapped[str] = mapped_column(
        ForeignKey("scoring_model.version", ondelete="RESTRICT"), nullable=False
    )
    opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[CycleStatus] = mapped_column(
        pg_enum(CycleStatus, "cycle_status"), nullable=False, default=CycleStatus.DRAFT
    )
    is_demo: Mapped[bool] = mapped_column(nullable=False, default=False)

    scoring_model: Mapped[ScoringModel] = relationship()
    project: Mapped[Project | None] = relationship()
    applications: Mapped[list[Application]] = relationship(back_populates="cycle")


class Application(Base, TimestampMixin):
    """A vendor's participation in one cycle, with its frozen snapshot and scores."""

    __tablename__ = "application"
    __table_args__ = (UniqueConstraint("vendor_id", "cycle_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vendor.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cycle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("qualification_cycle.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        pg_enum(ApplicationStatus, "application_status"),
        nullable=False,
        default=ApplicationStatus.INVITED,
        index=True,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Answers by field code plus signatory / stamp of the signed declaration.
    declaration: Mapped[JsonDict | None] = mapped_column(nullable=True)
    #: Raw indicators frozen at submission so a later profile edit cannot move a past score.
    raw_snapshot: Mapped[JsonDict | None] = mapped_column(nullable=True)
    #: Officer's 0–3 rubric cells, keyed by criterion code, with the evidence document code.
    rubric_scores: Mapped[JsonDict | None] = mapped_column(nullable=True)
    #: Engine output: ``{"per": {...}, "groups": {...}, "total": 0.0, "ko": true, "cls": "A"}``.
    computed: Mapped[JsonDict | None] = mapped_column(nullable=True)
    decision: Mapped[DecisionKind | None] = mapped_column(
        pg_enum(DecisionKind, "decision_kind"), nullable=True
    )
    justification: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Optional second evaluator's rubric set (spec §10.3).
    second_rubric: Mapped[JsonDict | None] = mapped_column(nullable=True)
    is_demo: Mapped[bool] = mapped_column(nullable=False, default=False)

    vendor: Mapped[Vendor] = relationship(back_populates="applications")
    cycle: Mapped[QualificationCycle] = relationship(back_populates="applications")
