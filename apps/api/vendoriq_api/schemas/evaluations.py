"""The officer's rubric, live scoring, decisions and the commission exports.

Contract tag ``applications`` — the half of it phase-2 task 2B owns (``routers/evaluations.py``
serves it; ``routers/portal.py``, task 2A, owns the vendor's own half — see that router's
docstring). Everything the two operations sets have in common (``Application``,
``EvaluationSummary``, ``ApplicationDetail``, ``ScoreResult``) already lives in
``schemas/vendors.py`` and ``schemas/applications.py`` (task 2A); nothing here repeats it.
``ScoreResult`` and ``ApplicationDetail`` are re-exported from here purely so this module's own
classes (``Evaluation``, ``SecondEvaluation``) and ``routers/evaluations.py`` can reference them
with one import — there is exactly one Python class per contract schema (ADR discussion, final
report round 2): a second one is how the two drift.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import Field, field_validator

from ..models.enums import DecisionKind, ObservationSource
from .applications import ApplicationDetail, ScoreResult
from .base import Model

#: Mirrors ``vendoriq_scoring.types.CriterionKind`` — kept local so this module has no
#: import-time dependency on the engine package beyond what the service layer already needs.
CriterionKind = Literal["rubric", "bands", "thresh", "ongoing", "leadtime"]


class EvaluationRow(Model):
    code: str
    group: str
    name_az: str = ""
    name_en: str = ""
    kind: CriterionKind
    max: float
    ko: bool = False
    unit: str | None = None
    evidence_doc: str | None = None
    raw_value: float | None = None
    raw_source: ObservationSource | None = None
    rubric_score: int | None = Field(default=None, ge=0, le=3)
    points: float = 0.0


class Evaluation(Model):
    application_id: uuid.UUID
    model_version: str
    rows: list[EvaluationRow]
    computed: ScoreResult
    can_approve: bool = False
    evaluator_name: str | None = None


class RubricInput(Model):
    rubric_scores: dict[str, int]
    evidence: dict[str, str] | None = None

    @field_validator("rubric_scores")
    @classmethod
    def _cells_are_0_to_3(cls, value: dict[str, int]) -> dict[str, int]:
        for code, cell in value.items():
            if not isinstance(cell, int) or isinstance(cell, bool) or not (0 <= cell <= 3):
                raise ValueError(f"rubric cell {code!r} must be an integer 0-3, got {cell!r}")
        return value


class ComputeRequest(Model):
    rubric_scores: dict[str, int] | None = None
    raw_overrides: dict[str, float | None] | None = None
    model_version: str | None = None


class Divergence(Model):
    code: str
    first: int
    second: int


class SecondEvaluation(Model):
    computed: ScoreResult
    divergences: list[Divergence]


class DecisionInput(Model):
    decision: DecisionKind
    justification: str | None = None
    valid_months: int | None = Field(default=None, gt=0)


__all__ = [
    "ApplicationDetail",
    "ComputeRequest",
    "CriterionKind",
    "DecisionInput",
    "Divergence",
    "Evaluation",
    "EvaluationRow",
    "RubricInput",
    "ScoreResult",
    "SecondEvaluation",
]
