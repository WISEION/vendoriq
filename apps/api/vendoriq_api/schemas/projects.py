"""Projects, work packages and matching runs.

Contract tag ``projects``. Owned by phase-2 task 2C.

``MatchRun``, ``PackageMatch`` and ``MatchCandidate`` mirror the JSON the matching engine
(``packages/scoring``) produces almost field-for-field — see
``vendoriq_scoring.types.ProjectMatch`` / ``PackageMatch`` / ``Candidate``. ``gap`` and
``reasons`` are i18n keys, never rendered sentences (packages/scoring/README.md §4); the
frontend is the only place they are translated.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import Field

from ..models.enums import MatchState, ProjectStage, ScoreClass
from .base import Model, PageMeta
from .vendors import Category


class Project(Model):
    id: uuid.UUID
    code: str
    name: str
    client: str | None = None
    stage: ProjectStage
    estimated_value: float | None = None
    deadline: date | None = None
    external_ref: str | None = None
    is_demo: bool = False
    package_count: int = 0
    coverage_pct: int | None = None
    match_state: MatchState | None = None
    last_matched_at: datetime | None = None


class ProjectInput(Model):
    code: str
    name: str
    client: str | None = None
    stage: ProjectStage = ProjectStage.PIPELINE
    estimated_value: float | None = None
    deadline: date | None = None
    external_ref: str | None = None
    is_demo: bool = False


class MatchParams(Model):
    strong_min: int | None = None
    capacity_ratio: float | None = None
    supplier_turnover_divisor: float | None = None


class WorkPackage(Model):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str | None = None
    category: Category
    estimated_value: float
    min_class: ScoreClass
    required_certs: list[str] = Field(default_factory=list)
    notes: str | None = None
    is_demo: bool = False


class WorkPackageInput(Model):
    name: str | None = None
    category_code: str
    estimated_value: float = Field(ge=0)
    min_class: ScoreClass = ScoreClass.C
    required_certs: list[str] = Field(default_factory=list)
    notes: str | None = None


class MatchCandidate(Model):
    vendor_id: uuid.UUID
    legal_name: str
    total: float
    cls: ScoreClass
    capacity_value: float = 0
    capacity_fit: bool = False
    certs_ok: bool = True
    eligible: bool
    reasons: list[str] = Field(default_factory=list)
    missing_certs: list[str] = Field(default_factory=list)


class PackageMatch(Model):
    package_id: uuid.UUID
    state: MatchState
    gap: str | None = None
    candidates: list[MatchCandidate] = Field(default_factory=list)
    missing_certs: list[str] = Field(default_factory=list)
    eligible_count: int = 0
    strong_count: int = 0


class MatchRun(Model):
    id: uuid.UUID
    project_id: uuid.UUID
    ran_at: datetime
    params: MatchParams
    state: MatchState
    coverage_pct: int
    recommendation_key: str
    packages: list[PackageMatch] = Field(default_factory=list)


class ProjectDetail(Project):
    packages: list[WorkPackage] = Field(default_factory=list)
    latest_match: MatchRun | None = None


class ProjectPage(PageMeta):
    items: list[Project]


__all__ = [
    "MatchCandidate",
    "MatchParams",
    "MatchRun",
    "PackageMatch",
    "Project",
    "ProjectDetail",
    "ProjectInput",
    "ProjectPage",
    "WorkPackage",
    "WorkPackageInput",
]
