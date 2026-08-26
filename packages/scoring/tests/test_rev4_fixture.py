"""The acceptance gate for phase 1A: all 13 Rev4 vendors, exactly.

``seed/vendors_seed.json`` is a raw extraction from the signed Rev4 workbook — per vendor
the 24 raw indicators plus the total and the decision the commission actually recorded.
The ported engine has to reproduce both. A mismatch on any row is a failed port, not a
rounding opinion: this fixture is the only proof that the group-total rounding rule was
copied and not "simplified".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from vendoriq_scoring import ScoringModel, load_model, score

#: repo root / seed / vendors_seed.json — the fixture lives with the seed, not the package.
FIXTURE = Path(__file__).resolve().parents[3] / "seed" / "vendors_seed.json"

#: The workbook prints its totals to one decimal; ±0.05 is "the same cell", nothing looser.
TOLERANCE = 0.05


def _vendors() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return rows


@pytest.fixture(scope="module")
def sub_four() -> ScoringModel:
    return load_model("sub-4")


def test_the_fixture_has_all_thirteen_vendors() -> None:
    """If the fixture shrinks, the gate quietly weakens — so assert its size too."""
    rows = _vendors()
    assert len(rows) == 13
    assert {row["id"] for row in rows} == {f"V{n:02d}" for n in range(1, 14)}


@pytest.mark.parametrize("vendor", _vendors(), ids=lambda v: str(v["id"]))
def test_rev4_total_and_class_match_the_workbook(
    vendor: dict[str, Any], sub_four: ScoringModel
) -> None:
    result = score(sub_four, vendor["raw"])
    expected_class = str(vendor["sheetDecision"]).split()[0]

    assert result.total == pytest.approx(vendor["sheetTotal"], abs=TOLERANCE), (
        f"{vendor['id']} {vendor['name']}: engine {result.total} vs sheet {vendor['sheetTotal']}"
    )
    assert result.cls == expected_class, f"{vendor['id']}: {result.cls} vs sheet {expected_class}"
    assert result.ko is (expected_class != "KO")


def test_all_thirteen_match_in_one_assertion(sub_four: ScoringModel) -> None:
    """The 13/13 statement itself — the parametrised test above localises a failure."""
    mismatches = [
        row["id"]
        for row in _vendors()
        if abs(score(sub_four, row["raw"]).total - row["sheetTotal"]) > TOLERANCE
        or score(sub_four, row["raw"]).cls != str(row["sheetDecision"]).split()[0]
    ]
    assert mismatches == []


def test_an_empty_application_still_scores_one(sub_four: ScoringModel) -> None:
    """V02–V04 and V12 submitted nothing at all and still score exactly 1.0.

    Every one of their 24 cells is ``None``, so the single point comes from ``C.3``
    (ongoing projects), whose ``ongoing`` curve pays 25 % of the weight — 1.0 of 4 — for
    *zero* ongoing work: idle capacity is available capacity. Every other kind scores 0
    on a blank cell.

    Reproducing that 1.0 is the cheapest proof the ``ongoing`` zero-case was ported and
    not "simplified" to 0 like the other kinds. (``seed/README.md`` attributes the 1 to
    the ``bands`` rule on A.2 — see the note in the phase-1A report; A.2 scores 0 here.)
    """
    silent = [row for row in _vendors() if row["sheetTotal"] == 1]
    assert {row["id"] for row in silent} == {"V02", "V03", "V04", "V12"}
    for row in silent:
        assert all(value is None for value in row["raw"].values()), row["id"]
        result = score(sub_four, row["raw"])
        assert result.total == 1.0
        assert result.cls == "KO"
        assert result.per["C.3"] == 1.0
        assert result.per["A.2"] == 0
        assert {code for code, points in result.per.items() if points} == {"C.3"}


def test_group_totals_sum_to_the_grand_total(sub_four: ScoringModel) -> None:
    """The grand total is the sum of the *rounded* group totals, re-rounded once."""
    for row in _vendors():
        result = score(sub_four, row["raw"])
        assert set(result.groups) == {g["group"] for g in sub_four.groups}
        assert result.total == pytest.approx(round(sum(result.groups.values()), 1), abs=1e-9)
