"""VendorIQ scoring & matching engine — pure Python, no framework dependencies.

Four functions carry the whole engine:

* :func:`score` — a vendor's raw indicators against one model version, reproducing the
  Rev4 workbook to the tenth of a point (see ``tests/test_rev4_fixture.py``: 13 of 13).
* :func:`derive_raw` — application answers → the raw indicators :func:`score` consumes.
* :func:`match_package` / :func:`match_project` — which vendors can build a package, and
  whether the project can be bid at all.

Everything here is pure. No clock (except the optional ``current_year`` of
:func:`derive_raw`), no I/O beyond reading the shipped model JSON, no database — so the
API, the worker, the importer and the CLI all get identical answers.

    >>> from vendoriq_scoring import load_model, score
    >>> score(load_model("sub-4"), {"A.1": 3, "A.2": 9, "A.4": 3, "F.1": 3}).cls
    'F'
"""

from __future__ import annotations

from .derive import YES_NO_PREFILL_SUB, YES_NO_PREFILL_SUP, derive_raw, is_yes
from .engine import classify, score, score_criterion
from .loader import BUILTIN_MODEL_VERSIONS, MODELS_DIR, load_model, model_from_dict
from .matching import CLASS_RANK, STRONG_CLASSES, match_package, match_project
from .numbers import parse_year, r0, r1, to_number
from .types import (
    AnswerMap,
    BandsSpec,
    Candidate,
    CandidateInput,
    ClassBand,
    Criterion,
    CriterionKind,
    GroupDef,
    MatchParams,
    MatchStateName,
    ModelStatusName,
    PackageInput,
    PackageMatch,
    ProjectInput,
    ProjectMatch,
    RawIndicators,
    RawIndicatorsInput,
    ScoreClassName,
    ScoreResult,
    ScoringModel,
    ThreshSpec,
    VendorTypeName,
)

__version__ = "0.1.0"

__all__ = [
    "BUILTIN_MODEL_VERSIONS",
    "CLASS_RANK",
    "MODELS_DIR",
    "STRONG_CLASSES",
    "YES_NO_PREFILL_SUB",
    "YES_NO_PREFILL_SUP",
    "AnswerMap",
    "BandsSpec",
    "Candidate",
    "CandidateInput",
    "ClassBand",
    "Criterion",
    "CriterionKind",
    "GroupDef",
    "MatchParams",
    "MatchStateName",
    "ModelStatusName",
    "PackageInput",
    "PackageMatch",
    "ProjectInput",
    "ProjectMatch",
    "RawIndicators",
    "RawIndicatorsInput",
    "ScoreClassName",
    "ScoreResult",
    "ScoringModel",
    "ThreshSpec",
    "VendorTypeName",
    "__version__",
    "classify",
    "derive_raw",
    "is_yes",
    "load_model",
    "match_package",
    "match_project",
    "model_from_dict",
    "parse_year",
    "r0",
    "r1",
    "score",
    "score_criterion",
    "to_number",
]
