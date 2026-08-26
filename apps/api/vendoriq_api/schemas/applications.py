"""Applications, answers, submission (contract tag ``applications``).

Owned by phase-2 task 2A (the vendor portal): ``listApplications``, ``getApplication``,
``patchAnswers``, ``submitApplication``. Evaluation and decision shapes (``Evaluation``,
``RubricInput``, ``DecisionInput`` …) belong to task 2B and are added to this module by
that task, not here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from ..models.enums import ScoreClass
from .base import Model, PageMeta
from .vendors import Application

__all__ = [
    "AnswerPatch",
    "AnswerState",
    "ApplicationDetail",
    "ApplicationPage",
    "Declaration",
    "DeclarationInput",
    "ScoreResult",
    "SubmissionChecks",
]


class SubmissionChecks(Model):
    """The pre-submission checklist shown on the declaration screen (spec §7)."""

    mandatory_fields: bool
    mandatory_documents: bool
    knock_out_answers: bool
    missing_field_codes: list[str] = Field(default_factory=list)
    missing_document_codes: list[str] = Field(default_factory=list)


class AnswerPatch(Model):
    """Partial map keyed by field code (``A.1`` … ``G.7``, tables ``C.t1``, ``C.t2``, ``G.t1``)."""

    answers: dict[str, Any]


class AnswerState(Model):
    completion_pct: float = Field(ge=0, le=100)
    checks: SubmissionChecks
    computed_fields: dict[str, float | None] = Field(default_factory=dict)
    #: Excel-import-style anomaly warnings (``ImportWarning``, contract tag ``integrations``).
    #: The portal path never produces one today, so the shape is loose rather than importing
    #: a schema owned by another phase-2 task.
    warnings: list[dict[str, Any]] = Field(default_factory=list)


class Declaration(Model):
    signatory_name: str | None = None
    signatory_position: str | None = None
    agreed: bool = False
    signed_at: datetime | None = None
    stamp_file_key: str | None = None


class DeclarationInput(Model):
    signatory_name: str = Field(min_length=1)
    signatory_position: str = Field(min_length=1)
    agreed: Literal[True]


class ScoreResult(Model):
    """Engine output — the same shape ``packages/scoring`` returns."""

    per: dict[str, float] = Field(default_factory=dict)
    groups: dict[str, float] = Field(default_factory=dict)
    total: float = 0.0
    ko: bool = True
    cls: ScoreClass | None = None
    pass_mark: float | None = None
    model_version: str | None = None


class ApplicationPage(PageMeta):
    items: list[Application]


class ApplicationDetail(Application):
    scoring_model_version: str | None = None
    answers: dict[str, Any] = Field(default_factory=dict)
    raw_snapshot: dict[str, float | None] | None = None
    rubric_scores: dict[str, int] | None = None
    computed: ScoreResult | None = None
    declaration: Declaration | None = None
    justification: str | None = None
    checks: SubmissionChecks | None = None
    #: What `AnswerState` carries, so the form can read its own state without writing.
    #: `patchAnswers` returns the same two, and the form used to fetch them with an empty
    #: patch — which the server correctly refuses once the application is submitted, so a
    #: complete, prequalified application showed a completion meter of 0 % (3A, finding 4).
    completion_pct: float = 0.0
    computed_fields: dict[str, float | None] = Field(default_factory=dict)
    #: Vendors see the score breakdown only after the commission decision (spec §7).
    score_released: bool = False
