"""Projects, work packages and persisted match runs (spec §5, §11)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, JsonDict, JsonList, TimestampMixin, pg_enum, uuid_pk
from .enums import ProjectStage, ScoreClass

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .catalog import Category


class Project(Base, TimestampMixin):
    """The demand side: a tender or pipeline opportunity made of work packages."""

    __tablename__ = "project"

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    client: Mapped[str | None] = mapped_column(String(255))
    stage: Mapped[ProjectStage] = mapped_column(
        pg_enum(ProjectStage, "project_stage"), nullable=False, default=ProjectStage.PIPELINE
    )
    estimated_value: Mapped[float | None] = mapped_column(Numeric(18, 2))
    deadline: Mapped[date | None] = mapped_column(Date)
    external_ref: Mapped[str | None] = mapped_column(String(128), index=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    packages: Mapped[list[WorkPackage]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    match_runs: Mapped[list[MatchRun]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class WorkPackage(Base, TimestampMixin):
    """One package of a project; each is matched independently (spec §11.1)."""

    __tablename__ = "work_package"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("category.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str | None] = mapped_column(String(255))
    estimated_value: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    min_class: Mapped[ScoreClass] = mapped_column(
        pg_enum(ScoreClass, "score_class"), nullable=False, default=ScoreClass.C
    )
    #: e.g. ``["iso9001", "iso45001"]``.
    required_certs: Mapped[JsonList] = mapped_column(nullable=False, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    project: Mapped[Project] = relationship(back_populates="packages")
    category: Mapped[Category] = relationship()


class MatchRun(Base):
    """A persisted matching result — one row per execution, never mutated."""

    __tablename__ = "match_run"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ran_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    #: Thresholds in effect for this run (``strong_min``, ``capacity_ratio``, …).
    params: Mapped[JsonDict] = mapped_column(nullable=False, default=dict)
    #: ``{"state": "cond", "coverage_pct": 96, "packages": [...]}``.
    result: Mapped[JsonDict] = mapped_column(nullable=False, default=dict)
    ran_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )

    project: Mapped[Project] = relationship(back_populates="match_runs")
