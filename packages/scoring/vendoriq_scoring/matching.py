"""Vendor ↔ package matching and the project go / no-go verdict (spec §11).

Port of ``CLS_RANK``, ``matchPackage`` and ``matchProject`` in ``docs/design/app.js``,
with one deliberate extension: the reference drops non-prequalified vendors before it
builds the candidate list, so the UI can only say "nobody". Here every vendor in the
category becomes a candidate and carries the ``reasons`` it failed, which lets the
matching screen print the specific gap ("class C, needs B") without recomputing
anything. Eligibility, strength, the package state and the project verdict are
unchanged — a non-prequalified vendor is never eligible either way.

Thresholds are arguments, not constants: the caller passes the values from the
``setting`` rows (spec §11.2) and the engine never reads settings itself.
"""

from __future__ import annotations

from .engine import score
from .loader import load_model
from .numbers import r0, to_number
from .types import (
    Candidate,
    CandidateInput,
    MatchParams,
    MatchStateName,
    PackageInput,
    PackageMatch,
    ProjectInput,
    ProjectMatch,
    RawIndicatorsInput,
    ScoreClassName,
    ScoringModel,
)

__all__ = ["CLASS_RANK", "STRONG_CLASSES", "match_package", "match_project"]

#: Ordering of the classes. ``KO`` and the "not scored" placeholder rank below ``F`` so a
#: package can never require a minimum they satisfy.
CLASS_RANK: dict[str, int] = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1, "KO": 0, "NA": 0}

#: A "strong" candidate is class A or B — the classes the commission invites outright.
STRONG_CLASSES: frozenset[ScoreClassName] = frozenset({"A", "B"})

#: Certificate key → the standard number as it is written in a criterion's label.
#: A model *carries* a certificate when one of its criteria names that number, so the
#: criterion code is never hard-coded per version: a new version published through the
#: model editor (spec §10.3) resolves the same way without a code change, and a version
#: that drops the criterion stops evidencing the certificate instead of silently
#: reading a neighbouring cell. A new certificate key needs an entry here *and* a
#: criterion in some model — one without the other means "not held" (ADR-011).
_CERTIFICATE_STANDARDS: dict[str, str] = {"iso9001": "9001", "iso45001": "45001"}

_REASON_NOT_PREQUALIFIED = "not_prequalified"
_REASON_KO_FAILED = "ko_failed"
_REASON_CLASS_BELOW_MIN = "class_below_min"
_REASON_CERTIFICATE_MISSING = "certificate_missing"
_REASON_CAPACITY_TOO_SMALL = "capacity_too_small"


def match_package(
    pkg: PackageInput,
    candidates: list[CandidateInput],
    params: MatchParams | None = None,
) -> PackageMatch:
    """Rank vendors for one work package and decide GO / CONDITIONAL / NO-GO (spec §11.1)."""
    settings = params or MatchParams()
    assessed = [
        _assess(vendor, pkg, settings)
        for vendor in candidates
        if pkg["category_code"] in vendor["category_codes"]
    ]
    assessed.sort(key=lambda candidate: candidate.score.total, reverse=True)

    eligible = [candidate for candidate in assessed if candidate.eligible]
    strong = [
        candidate
        for candidate in eligible
        if candidate.score.cls in STRONG_CLASSES and candidate.capacity_fit
    ]

    state: MatchStateName
    if len(strong) >= settings.strong_min:
        state = "go"
    elif eligible:
        state = "cond"
    else:
        state = "nogo"

    return PackageMatch(
        package_id=pkg["id"],
        state=state,
        candidates=assessed,
        eligible=eligible,
        strong=strong,
        gap=_gap(assessed, eligible, strong, state),
        missing_certs=sorted({cert for c in assessed for cert in c.missing_certs}),
    )


def match_project(
    project: ProjectInput,
    candidates: list[CandidateInput],
    params: MatchParams | None = None,
) -> ProjectMatch:
    """Aggregate the package results into a project verdict and coverage (spec §11.2).

    One un-fillable package sinks the whole project: a tender cannot be submitted with a
    hole in it. Coverage says how big the hole is, by value — the number the commission
    argues about when it decides to bid anyway.
    """
    settings = params or MatchParams()
    packages = project["packages"]
    results = [match_package(pkg, candidates, settings) for pkg in packages]
    by_id = {result.package_id: result for result in results}

    state: MatchStateName
    if any(result.state == "nogo" for result in results):
        state = "nogo"
    elif all(result.state == "go" for result in results):
        state = "go"  # vacuously true for a project with no packages, as in the reference
    else:
        state = "cond"

    total_value = sum(pkg["estimated_value"] for pkg in packages)
    covered = sum(pkg["estimated_value"] for pkg in packages if by_id[pkg["id"]].state != "nogo")
    # No packages, or packages with no value: nothing is uncovered.
    coverage = r0(covered / total_value * 100) if total_value else 100

    return ProjectMatch(
        project_id=project["id"],
        state=state,
        packages=results,
        coverage_pct=coverage,
        params=settings,
        recommendation_key=f"m_rec_{state}",
    )


def _assess(vendor: CandidateInput, pkg: PackageInput, settings: MatchParams) -> Candidate:
    """Score one vendor against one package and record every reason it falls short."""
    raw = vendor["raw"]
    # The model the vendor was *scored* with is also the model its certificates are read
    # from (ADR-011): a score and an eligibility claim that quote different rubrics are
    # a statement about a model the vendor was never measured against.
    model = load_model(vendor["model_version"])
    result = score(model, raw)

    capacity = _capacity_value(vendor, raw, settings)
    capacity_fit = capacity >= pkg["estimated_value"] * settings.capacity_ratio
    missing_certs = [
        cert for cert in pkg["required_certs"] if not _certificate_held(cert, raw, model)
    ]
    certs_ok = not missing_certs
    class_ok = CLASS_RANK.get(result.cls, 0) >= CLASS_RANK.get(pkg["min_class"], 0)

    reasons: list[str] = []
    if not vendor["is_prequalified"]:
        reasons.append(_REASON_NOT_PREQUALIFIED)
    if not result.ko:
        reasons.append(_REASON_KO_FAILED)
    if not class_ok:
        reasons.append(_REASON_CLASS_BELOW_MIN)
    if not certs_ok:
        reasons.append(_REASON_CERTIFICATE_MISSING)
    # Capacity does not block eligibility — it blocks *strength*. A small firm can still
    # be invited for part of the scope, which is exactly what CONDITIONAL means.
    if not capacity_fit:
        reasons.append(_REASON_CAPACITY_TOO_SMALL)

    return Candidate(
        vendor_id=vendor["id"],
        legal_name=vendor["legal_name"],
        score=result,
        capacity_value=capacity,
        capacity_fit=capacity_fit,
        certs_ok=certs_ok,
        eligible=vendor["is_prequalified"] and result.ko and class_ok and certs_ok,
        reasons=reasons,
        missing_certs=missing_certs,
    )


def _capacity_value(
    vendor: CandidateInput, raw: RawIndicatorsInput, settings: MatchParams
) -> float:
    """What the vendor has demonstrably delivered at once, in package-value terms.

    A subcontractor is measured by its largest completed project (C.2). A supplier has no
    "project", so its annual turnover is divided down to a comparable single-order size.
    """
    if vendor["vendor_type"] == "sub":
        return to_number(raw.get("C.2"))
    return to_number(raw.get("B.1")) / settings.supplier_turnover_divisor


def _certificate_criterion(cert: str, model: ScoringModel) -> str | None:
    """The criterion code that evidences ``cert`` in ``model``, or ``None`` if it has none.

    Resolved from the model's own labels rather than a per-version lookup table, so a
    version published through the model editor inherits the mapping with its criteria.
    As the two shipped models stand:

    ============ ============================= ==============================
    Certificate  ``sub-4`` (subcontractor)      ``sup-1`` (supplier)
    ============ ============================= ==============================
    ``iso9001``  ``C.4`` ISO 9001               ``F.1`` ISO 9001
    ``iso45001`` ``F.2`` ISO 14001 / 45001      none — the model has no such row
    ============ ============================= ==============================
    """
    standard = _CERTIFICATE_STANDARDS.get(cert)
    if standard is None:
        return None
    for criterion in model.criteria:
        if standard in criterion["name_en"] or standard in criterion["name_az"]:
            return criterion["code"]
    return None


def _certificate_held(cert: str, raw: RawIndicatorsInput, model: ScoringModel) -> bool:
    """Whether a required certificate is evidenced in the model the vendor was scored with.

    Two rules, both of them corrections of a port that was too generous (ADR-009,
    ADR-011):

    1. The certificate is read from **the criterion that carries it in this model**,
       never from "either position". The prototype's ``C.4 > 0 or F.1 > 0`` was wrong in
       both directions: in ``sub-4`` F.1 is the *HSE policy* knock-out, so every
       subcontractor that cleared KO "held" ISO 9001 with C.4 at zero; in ``sup-1`` C.4
       is *product certificates* (CE, GOST, test reports) and C.3 is manufacturer
       authorisation — neither is a quality-management certificate.
    2. A certificate the model has **no criterion for is not held**. Nothing in the
       vendor's file was ever checked against that standard, so the engine cannot
       evidence it, and saying "held" would report a verification that never happened.
       A false negative is visible — the manager reads the gap, sees which certificate
       is missing and can drop the requirement — while a false positive quietly puts an
       unverified vendor on a shortlist (spec §12).

    The concrete consequence today: ``sup-1`` has no ISO 45001 criterion, so a supplier
    can never satisfy an ``iso45001`` requirement. That is the intended answer, not a
    gap to paper over — a supplier's ISO 45001 status is genuinely unrecorded.

    **Two limitations of the models, recorded here, not fixed in the engine.** ``sub-4``
    F.2 is labelled "ISO 14001 / 45001", so a subcontractor holding only ISO 14001
    registers as holding ISO 45001. And ``sup-1`` carries no ISO 45001 criterion at all.
    Both are properties of frozen model versions — ``sub-4`` is the Rev4 model all 13
    fixture vendors were scored with, ``sup-1`` is "proposed" until the commission
    freezes it — and a model version is immutable once used (spec §10.3), so changing
    either is the commission's call through a new version, not the engine's.
    """
    code = _certificate_criterion(cert, model)
    if code is None:
        return False
    return to_number(raw.get(code)) > 0


def _gap(
    candidates: list[Candidate],
    eligible: list[Candidate],
    strong: list[Candidate],
    state: MatchStateName,
) -> str | None:
    """The single reason a package is not GO, for the UI to translate.

    Reported at package level so the matching screen can lead with the one thing that
    would change the verdict, instead of a list of per-vendor complaints.
    """
    if state == "go":
        return None
    if not candidates:
        return "no_vendor_in_category"

    if not eligible:
        # Which single change would put *somebody* over the line? Capacity is excluded:
        # it never blocks eligibility, only strength.
        blockers = [set(c.reasons) - {_REASON_CAPACITY_TOO_SMALL} for c in candidates]
        if any(reasons == {_REASON_CERTIFICATE_MISSING} for reasons in blockers):
            return "certificate_missing"
        if any(
            reasons <= {_REASON_CLASS_BELOW_MIN, _REASON_CERTIFICATE_MISSING}
            for reasons in blockers
        ):
            return "only_class_c"
        return "no_prequalified_vendor"

    # CONDITIONAL: there are eligible vendors, just not enough strong ones.
    strong_ids = {candidate.vendor_id for candidate in strong}
    weak = [candidate for candidate in eligible if candidate.vendor_id not in strong_ids]
    if any(_REASON_CAPACITY_TOO_SMALL in candidate.reasons for candidate in weak):
        return "capacity_too_small"
    if any(candidate.score.cls not in STRONG_CLASSES for candidate in weak):
        return "only_class_c"
    return "too_few_strong"
