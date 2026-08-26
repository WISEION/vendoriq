"""The scoring engine — a faithful port of ``scoreSubcontractor`` / ``scoreGeneric``.

Reference: ``docs/design/scoring.js`` (``R1``, ``SUB_CRITERIA``, ``scoreCriterion``,
``scoreSubcontractor``) and ``docs/design/app.js`` (``SUP_CRITERIA``, ``scoreGeneric``,
which adds the ``leadtime`` kind). The criteria tables themselves are not code here —
they are the model JSON in ``vendoriq_scoring/models/`` (see CONTRIBUTING: a weight
change is a new version, never an edit).

Everything in this module is pure: no clock, no I/O, no database.
"""

from __future__ import annotations

from typing import cast

from .numbers import r1, to_number
from .types import (
    BandsSpec,
    Criterion,
    RawIndicatorsInput,
    ScoreClassName,
    ScoreResult,
    ScoringModel,
    ThreshSpec,
)

__all__ = ["classify", "score", "score_criterion"]


def score_criterion(criterion: Criterion, value: object) -> float:
    """Points for one criterion — the ``switch (kind)`` of the reference, rule for rule.

    The two asymmetries below are deliberate and load-bearing (README §2):

    * ``thresh`` compares with strict ``<``; ``bands`` / ``ongoing`` / ``leadtime`` use ``<=``.
    * ``ongoing`` scores 25 % for *zero* ongoing projects (idle capacity is available
      capacity), while ``leadtime`` scores 0 for an unknown lead time.

    ``bands`` points are literal — not scaled by ``max`` and not rounded. That is what
    makes a vendor who submitted nothing still score 1.0 overall (V02–V04, V12).
    """
    number = to_number(value)
    maximum = criterion["max"]
    kind = criterion["kind"]

    if kind == "rubric":
        return r1(number / 3 * maximum)

    if kind == "bands":
        bands = cast(BandsSpec, criterion["spec"])
        if number == 0:
            return bands["zero"]
        for limit, points in bands["bands"]:
            if number <= limit:
                return points
        return bands["top"]

    if kind == "thresh":
        cuts = cast(ThreshSpec, criterion["spec"])["cuts"]
        for limit, fraction in cuts:
            if number < limit:
                return r1(maximum * fraction)
        return maximum  # above every cut: the full weight, unrounded

    if kind == "ongoing":
        if number == 0:
            return r1(maximum * 0.25)
        if number <= 3:
            return r1(maximum * 0.5)
        if number <= 6:
            return maximum
        return r1(maximum * 0.75)

    if kind == "leadtime":
        if number == 0:
            return 0.0
        if number <= 3:
            return maximum
        if number <= 7:
            return r1(maximum * 0.75)
        if number <= 14:
            return r1(maximum * 0.5)
        if number <= 30:
            return r1(maximum * 0.25)
        return 0.0

    raise ValueError(f"unknown criterion kind {kind!r} on {criterion['code']}")


def classify(model: ScoringModel, total: float, ko_passed: bool) -> ScoreClassName:
    """Class band for a total, or ``KO`` when a knock-out criterion failed.

    ``KO`` is not a band: it *replaces* the class while the total stays visible, because
    the evaluation screen shows both (spec §10).
    """
    if not ko_passed:
        return "KO"
    for band in model.classes:
        if total >= band["min"]:
            return band["cls"]
    return "F"


def score(model: ScoringModel, raw: RawIndicatorsInput) -> ScoreResult:
    """Score one vendor against one model version.

    The rounding is the whole point of this function. ``R1`` is applied three times, and
    the middle one is the surprising one: the group total is re-rounded **after every
    addition**, not once at the end. That is the workbook's own behaviour, and dropping
    it costs a tenth of a point on several of the 13 Rev4 vendors.
    """
    per: dict[str, float] = {}
    # Every declared group is present even when all its criteria score 0 (README §2).
    groups: dict[str, float] = {group["group"]: 0.0 for group in model.groups}

    for criterion in model.criteria:
        points = score_criterion(criterion, raw.get(criterion["code"]))
        per[criterion["code"]] = points
        letter = criterion["group"]
        groups[letter] = r1(groups.get(letter, 0.0) + points)

    total = r1(sum(groups.values()))
    # KO is decided on the *raw* value, not on the points it earned.
    ko_passed = all(to_number(raw.get(c["code"])) > 0 for c in model.criteria if c["ko"])

    return ScoreResult(
        per=per,
        groups=groups,
        total=total,
        ko=ko_passed,
        cls=classify(model, total, ko_passed),
    )
