"""VendorIQ scoring & matching engine — pure Python, no framework dependencies.

Phase 0 ships the *contract*: the model JSON (``models/sub-4.json``, ``models/sup-1.json``),
the loader, and the exact signatures phase 1A implements. The four functions below raise
``NotImplementedError`` on purpose — see ``packages/scoring/README.md`` for the rules and
the rounding behaviour they must reproduce.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal, cast

from .types import (
    BandsSpec,
    Candidate,
    CandidateInput,
    ClassBand,
    Criterion,
    CriterionKind,
    GroupDef,
    MatchParams,
    MatchStateName,
    PackageInput,
    PackageMatch,
    ProjectInput,
    ProjectMatch,
    RawIndicators,
    ScoreClassName,
    ScoreResult,
    ScoringModel,
    ThreshSpec,
)

__version__ = "0.1.0"

MODELS_DIR = Path(__file__).parent / "models"

#: Versions shipped with the system. New versions are created through the model editor.
BUILTIN_MODEL_VERSIONS = ("sub-4", "sup-1")

__all__ = [
    "BUILTIN_MODEL_VERSIONS",
    "MODELS_DIR",
    "BandsSpec",
    "Candidate",
    "CandidateInput",
    "ClassBand",
    "Criterion",
    "CriterionKind",
    "GroupDef",
    "MatchParams",
    "MatchStateName",
    "PackageInput",
    "PackageMatch",
    "ProjectInput",
    "ProjectMatch",
    "RawIndicators",
    "ScoreClassName",
    "ScoreResult",
    "ScoringModel",
    "ThreshSpec",
    "__version__",
    "derive_raw",
    "load_model",
    "match_package",
    "match_project",
    "score",
]


@lru_cache
def load_model(version: str) -> ScoringModel:
    """Load a built-in model version from ``vendoriq_scoring/models/<version>.json``.

    Raises ``FileNotFoundError`` for an unknown version. Models stored in the database
    (created by the model editor) are built with ``ScoringModel(**row)`` instead.
    """
    path = MODELS_DIR / f"{version}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    return ScoringModel(
        version=document["version"],
        vendor_type=document["vendor_type"],
        name_az=document["name_az"],
        name_en=document["name_en"],
        status=document["status"],
        pass_mark=document["pass_mark"],
        validity_months=document["validity_months"],
        currency=document["currency"],
        total_max=document["total_max"],
        groups=cast(list[GroupDef], document["groups"]),
        criteria=cast(list[Criterion], document["criteria"]),
        classes=cast(list[ClassBand], document["classes"]),
        source=document.get("source", ""),
    )


def score(model: ScoringModel, raw: RawIndicators) -> ScoreResult:
    """Score one vendor against one model version.

    Pure function: same model + same raw indicators always yield the same result.
    Rounding is load-bearing — see README §"Rounding rule".

    Not implemented in phase 0 (contract only).
    """
    raise NotImplementedError("Implemented in phase 1A — see packages/scoring/README.md")


def derive_raw(
    answers: dict[str, object],
    vendor_type: Literal["sub", "sup", "both"],
) -> RawIndicators:
    """Turn application answers (by field code) into the raw indicators ``score`` expects.

    Rules are in brief §1.4 and README §"derive_raw".

    Not implemented in phase 0 (contract only).
    """
    raise NotImplementedError("Implemented in phase 1A — see packages/scoring/README.md")


def match_package(
    pkg: PackageInput,
    candidates: list[CandidateInput],
    params: MatchParams | None = None,
) -> PackageMatch:
    """Rank vendors for one work package and decide GO / CONDITIONAL / NO-GO (spec §11.1).

    Not implemented in phase 0 (contract only).
    """
    raise NotImplementedError("Implemented in phase 1A — see packages/scoring/README.md")


def match_project(
    project: ProjectInput,
    candidates: list[CandidateInput],
    params: MatchParams | None = None,
) -> ProjectMatch:
    """Aggregate package results into a project verdict and coverage (spec §11.2).

    Not implemented in phase 0 (contract only).
    """
    raise NotImplementedError("Implemented in phase 1A — see packages/scoring/README.md")
