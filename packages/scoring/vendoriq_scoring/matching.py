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
)

__all__ = ["CLASS_RANK", "STRONG_CLASSES", "match_package", "match_project"]

#: Ordering of the classes. ``KO`` and the "not scored" placeholder rank below ``F`` so a
#: package can never require a minimum they satisfy.
CLASS_RANK: dict[str, int] = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1, "KO": 0, "NA": 0}

#: A "strong" candidate is class A or B — the classes the commission invites outright.
STRONG_CLASSES: frozenset[ScoreClassName] = frozenset({"A", "B"})

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
    result = score(load_model(vendor["model_version"]), raw)

    capacity = _capacity_value(vendor, raw, settings)
    capacity_fit = capacity >= pkg["estimated_value"] * settings.capacity_ratio
    certs_ok = all(_certificate_held(cert, raw) for cert in pkg["required_certs"])
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


def _certificate_held(cert: str, raw: RawIndicatorsInput) -> bool:
    """Whether a required certificate is evidenced by a raw indicator.

    ISO 9001 sits at C.4 in the subcontractor model and at F.1 in the supplier model, so
    either satisfies the requirement. An unknown key passes: certificates the models have
    no criterion for are informational until one is added (README §4).
    """
    if cert == "iso9001":
        return to_number(raw.get("C.4")) > 0 or to_number(raw.get("F.1")) > 0
    if cert == "iso45001":
        return to_number(raw.get("F.2")) > 0
    return True


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
