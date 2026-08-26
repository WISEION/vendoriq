"""Scoring model versions, criteria, class bands and the editor (contract tag
``scoring-models``, spec §10.3).

Shapes are transcribed from ``docs/openapi.yaml``; the criteria/groups/classes payloads are
exactly the JSON shape ``packages/scoring/vendoriq_scoring/models/*.json`` ships, per that
package's README §1 — the model editor and the engine agree on one document format.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from pydantic import Field

from ..models.enums import ScoreClass, VendorType
from .base import Model

#: Mirrors ``vendoriq_scoring.types.CriterionKind`` — kept local so this module has no
#: dependency on the engine package, same as ``schemas/evaluations.py``'s own copy.
CriterionKind = Literal["rubric", "bands", "thresh", "ongoing", "leadtime"]


class GroupDef(Model):
    group: str
    name_az: str
    name_en: str
    max: float


class CriterionSpec(Model):
    """Threshold cuts or a band table (``packages/scoring`` §1) — never both."""

    cuts: list[list[float]] | None = None
    bands: list[list[float]] | None = None
    zero: float | None = None
    top: float | None = None


class Criterion(Model):
    code: str
    group: str
    max: float
    kind: CriterionKind
    spec: CriterionSpec | None = None
    ko: bool = False
    name_az: str = ""
    name_en: str = ""
    unit: str | None = None
    evidence_doc: str | None = None


class ClassBand(Model):
    cls: ScoreClass
    min: float
    label_az: str = ""
    label_en: str = ""


class ScoringModelSummary(Model):
    version: str
    vendor_type: VendorType
    name_az: str
    name_en: str
    status: str
    pass_mark: float
    validity_months: int
    effective_from: date | None = None
    is_locked: bool
    application_count: int = 0


class ScoringModel(ScoringModelSummary):
    currency: str = "AZN"
    total_max: float
    groups: list[GroupDef]
    criteria: list[Criterion]
    classes: list[ClassBand]


class ScoringModelPatch(Model):
    name_az: str | None = None
    name_en: str | None = None
    pass_mark: float | None = None
    validity_months: int | None = None
    criteria: list[Criterion] | None = None
    classes: list[ClassBand] | None = None


class CreateDraftInput(Model):
    from_version: str
    version: str
    name_az: str | None = None
    name_en: str | None = None
    note: str | None = None


class PublishInput(Model):
    effective_from: date | None = None


class RescoreInput(Model):
    cycle_id: uuid.UUID


class RescoreRow(Model):
    vendor_id: uuid.UUID
    vendor_name: str
    old_total: float | None = None
    new_total: float | None = None
    old_class: ScoreClass | None = None
    new_class: ScoreClass | None = None
    changed: bool = False


class RescoreSummary(Model):
    changed_count: int = 0
    class_changes: int = 0


class RescoreReport(Model):
    cycle_id: uuid.UUID
    from_version: str
    to_version: str
    rows: list[RescoreRow]
    summary: RescoreSummary = Field(default_factory=RescoreSummary)


__all__ = [
    "ClassBand",
    "CreateDraftInput",
    "Criterion",
    "CriterionSpec",
    "GroupDef",
    "PublishInput",
    "RescoreInput",
    "RescoreReport",
    "RescoreRow",
    "RescoreSummary",
    "ScoringModel",
    "ScoringModelPatch",
    "ScoringModelSummary",
]
