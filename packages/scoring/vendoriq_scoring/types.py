"""Contract types for the scoring and matching engine.

These declarations are the interface phase 1A implements; nothing here computes a
score. The runtime shapes mirror ``docs/design/scoring.js`` one-to-one so the ported
engine can be diffed against the reference implementation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

#: Criterion rule kinds, exactly as in the reference JS engine.
CriterionKind = Literal["rubric", "bands", "thresh", "ongoing", "leadtime"]

#: Result classes. ``KO`` is not a band — it overrides the total (spec §10).
ScoreClassName = Literal["A", "B", "C", "D", "F", "KO"]

#: Go / no-go state of a package or a project (spec §11).
MatchStateName = Literal["go", "cond", "nogo"]

#: What a vendor is scored as. ``both`` is scored with the subcontractor model.
VendorTypeName = Literal["sub", "sup", "both"]

#: Lifecycle of a model version (spec §10.3).
ModelStatusName = Literal["active", "proposed", "retired"]

#: Raw indicator map: criterion code -> numeric value. ``None`` means "not answered"
#: and is treated as 0 by the engine, matching ``Number(v) || 0`` in the reference.
RawIndicators = dict[str, float | int | None]

#: What the engine *reads*. Covariant, so a caller's ``dict[str, float]`` — the natural
#: shape when raw indicators come out of observations — is accepted without a cast. The
#: engine never mutates a raw map.
RawIndicatorsInput = Mapping[str, float | int | None]

#: Application answers as they reach ``derive_raw``: field code → whatever the form or
#: the importer produced (text, number, date, or a list of table rows).
AnswerMap = Mapping[str, object]


class BandsSpec(TypedDict):
    """``bands``: value 0 scores ``zero``; otherwise first ``[limit, points]`` with v <= limit."""

    zero: float
    bands: list[list[float]]
    top: float


class ThreshSpec(TypedDict, total=False):
    """``thresh``: first ``[limit, fraction]`` with v < limit wins; otherwise the full max.

    ``top`` appears in the reference data but is never read by the ``thresh`` branch —
    it is carried through verbatim so the JSON stays byte-comparable with the prototype.
    """

    cuts: list[list[float]]
    top: float


class Criterion(TypedDict):
    """One row of a scoring model — the JSON shape in ``vendoriq_scoring/models/*.json``."""

    code: str
    group: str
    max: float
    kind: CriterionKind
    spec: BandsSpec | ThreshSpec | None
    ko: bool
    name_az: str
    name_en: str
    unit: str | None
    evidence_doc: str | None


class ClassBand(TypedDict):
    cls: ScoreClassName
    min: float
    label_az: str
    label_en: str


class GroupDef(TypedDict):
    group: str
    name_az: str
    name_en: str
    max: float


@dataclass(frozen=True, slots=True)
class ScoringModel:
    """A loaded model version. Immutable — see spec §10.3."""

    version: str
    vendor_type: VendorTypeName
    name_az: str
    name_en: str
    status: ModelStatusName
    pass_mark: float
    validity_months: int
    currency: str
    total_max: float
    groups: list[GroupDef]
    criteria: list[Criterion]
    classes: list[ClassBand]
    source: str = ""


@dataclass(frozen=True, slots=True)
class ScoreResult:
    """Engine output. Field names match the JS return value ``{per, groups, total, ko, cls}``."""

    #: Points per criterion code, each rounded to one decimal.
    per: dict[str, float]
    #: Points per group letter, rounded to one decimal after every addition.
    groups: dict[str, float]
    #: Sum of the group totals, rounded to one decimal.
    total: float
    #: ``True`` when every knock-out criterion has a raw value > 0.
    ko: bool
    #: Class band, or ``"KO"`` when ``ko`` is ``False``.
    cls: ScoreClassName


@dataclass(frozen=True, slots=True)
class MatchParams:
    """Matching thresholds — settings, not code (spec §11.2)."""

    #: How many class A/B vendors with capacity fit make a package GO.
    strong_min: int = 2
    #: Largest completed project must be at least this share of the package value.
    capacity_ratio: float = 0.40
    #: Suppliers use annual turnover divided by this instead of a project value.
    supplier_turnover_divisor: float = 4.0


@dataclass(frozen=True, slots=True)
class Candidate:
    """A vendor considered for one package, with the reasons behind the verdict."""

    vendor_id: str
    legal_name: str
    score: ScoreResult
    #: Largest completed project value (subcontractor) or turnover ÷ divisor (supplier).
    capacity_value: float
    capacity_fit: bool
    certs_ok: bool
    eligible: bool
    #: Machine-readable reasons a candidate is not eligible, e.g. ``["class_below_min"]``.
    reasons: list[str] = field(default_factory=list)
    #: The required certificates this vendor could not evidence, in the order the package
    #: asked for them, e.g. ``["iso45001"]``. Empty whenever ``certs_ok`` is true. Names
    #: the certificate behind a ``certificate_missing`` reason so the screen can say which
    #: one without re-deriving it (ADR-011).
    missing_certs: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class PackageMatch:
    """Result for one work package."""

    package_id: str
    state: MatchStateName
    candidates: list[Candidate]
    eligible: list[Candidate]
    strong: list[Candidate]
    #: The one change that would move this package towards GO, as an i18n key:
    #: ``no_vendor_in_category`` (nobody carries the category), ``no_prequalified_vendor``
    #: (vendors exist, none is prequalified and KO-clean), ``certificate_missing``,
    #: ``only_class_c`` (the class floor is the binding constraint), ``capacity_too_small``,
    #: ``too_few_strong`` (eligible A/B vendors exist, fewer than ``strong_min``).
    #: ``None`` when the package is GO.
    gap: str | None = None
    #: Every required certificate that blocked at least one candidate, sorted. This is
    #: what a ``certificate_missing`` gap names. It is a roll-up over the candidate list,
    #: not a statement about the package: an eligible candidate contributes nothing, but
    #: a hopeless one drags its missing certificate in, so read it together with ``gap``.
    missing_certs: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ProjectMatch:
    """Aggregate of the package results (spec §11.2)."""

    project_id: str
    state: MatchStateName
    packages: list[PackageMatch]
    #: Value share of packages that are not NO-GO, rounded to a whole percent.
    coverage_pct: int
    params: MatchParams
    recommendation_key: str = ""


class PackageInput(TypedDict):
    """The package as the engine needs it — no ORM types cross this boundary."""

    id: str
    category_code: str
    estimated_value: float
    min_class: ScoreClassName
    required_certs: list[str]


class CandidateInput(TypedDict):
    """A vendor as the engine needs it."""

    id: str
    legal_name: str
    vendor_type: VendorTypeName
    category_codes: list[str]
    is_prequalified: bool
    raw: RawIndicators
    model_version: str


class ProjectInput(TypedDict):
    id: str
    packages: list[PackageInput]


#: Everything a raw-indicator map may carry beyond the criterion codes.
DerivedExtras = dict[str, Any]
