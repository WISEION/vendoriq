"""Wesa's real application form: the frozen copy, and what it agrees with.

`seed/wesa_form.json` is the workbook parsed once and committed, so the API image needs
neither openpyxl nor a 74 KB spreadsheet. A generated file that nothing checks is a file that
drifts, so the first test here re-parses the workbook and compares.

The rest is the more interesting half. Wesa is the only one of the 13 whose filled-in form
Uni Ko still had, which makes it the only vendor in the system where the *form* and the *Rev4
scoring sheet* describe the same company independently. Deriving indicators from one and
comparing them against the other is an end-to-end check of the whole bridge — `FIELD_CATALOG`
codes in, `derive_raw`, criterion codes out — against real data, and it had never been run.

Every indicator the form can produce matches the sheet exactly, except `E.2`. That is
recorded here rather than smoothed over: the point of the exercise is that the number the two
sources disagree about is visible.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from vendoriq_excel_import import parse_application_form
from vendoriq_scoring import derive_raw, score
from vendoriq_scoring.loader import load_model

REPO_ROOT = Path(__file__).resolve().parents[3]
FROZEN = REPO_ROOT / "seed" / "wesa_form.json"
WORKBOOK = REPO_ROOT / "seed" / "fixtures" / "98dfa150-WESA_Prekvalifikasiya_Muraciet_Formasi.xlsx"

#: Criteria no form question feeds: the officer scores them against the uploaded evidence
#: (`packages/scoring/derive.py` — "judgement criteria ... stay absent from the map").
JUDGEMENT_ONLY = {"A.3", "D.1", "D.2", "D.3", "E.4", "F.3"}


def _derived(frozen: dict[str, Any]) -> dict[str, float]:
    """The form's answers through the bridge, with the absent criteria dropped.

    `derive_raw` returns `None` for an indicator no answer feeds; those are the judgement
    criteria and comparing them against a number is not the question here.
    """
    raw = derive_raw(frozen["answers"], "sub")
    return {code: float(value) for code, value in raw.items() if value is not None}


@pytest.fixture(scope="module")
def frozen() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(FROZEN.read_text(encoding="utf-8"))
    return document


@pytest.fixture(scope="module")
def sheet_snapshot() -> dict[str, float]:
    """Wesa's Rev4 raw indicators, as `seed/data.json` records them from the workbook."""
    data = json.loads((REPO_ROOT / "seed" / "data.json").read_text(encoding="utf-8"))
    wesa = next(row for row in data["vendors"] if str(row.get("voen")) == "1003915341")
    return {code: float(value) for code, value in wesa["raw"].items()}


def test_the_frozen_form_still_matches_the_workbook(frozen: dict[str, Any]) -> None:
    """Otherwise the committed copy is just a file nobody can trust."""
    parsed = parse_application_form(WORKBOOK)
    merged = {
        code: value
        for code, value in {**parsed.answers, **parsed.tables}.items()
        if value is not None
    }
    assert frozen["answers"] == json.loads(json.dumps(merged, ensure_ascii=False)), (
        "seed/wesa_form.json is stale — regenerate it with `make seed-form`"
    )


def test_the_frozen_form_is_keyed_by_form_codes_not_criterion_codes(frozen: dict[str, Any]) -> None:
    """The distinction ADR-021 exists for. `A.1` here is a company name, not a licence score."""
    from vendoriq_excel_import.catalog import FIELD_CATALOG

    unknown = sorted(code for code in frozen["answers"] if code not in FIELD_CATALOG)
    assert not unknown, unknown
    assert frozen["answers"]["A.1"] == "VVESA MMC"


def test_the_form_reproduces_every_rev4_indicator_but_one(
    frozen: dict[str, Any], sheet_snapshot: dict[str, float]
) -> None:
    """The cross-validation: two independent records of the same company, one derivation."""
    derived = _derived(frozen)

    comparable = {code: value for code, value in derived.items() if code in sheet_snapshot}
    disagreements = {
        code: (value, sheet_snapshot[code])
        for code, value in comparable.items()
        # The sheet stores whole numbers; the form carries the cents behind them.
        if abs(value - sheet_snapshot[code]) >= 0.51
    }
    assert set(disagreements) == {"E.2"}, f"unexpected disagreements: {disagreements}"

    # Turnover, largest project, headcount, references: to the manat.
    assert comparable["B.1"] == pytest.approx(5_189_111.38)
    assert comparable["C.2"] == pytest.approx(6_140_000.0)
    assert comparable["E.1"] == 80.0
    assert comparable["G.2"] == 8.0

    # And the criteria no question feeds are exactly the ones the officer is meant to score.
    assert set(sheet_snapshot) - set(derived) == JUDGEMENT_ONLY


def test_the_one_disagreement_is_the_engineer_count_and_it_changes_no_score(
    frozen: dict[str, Any], sheet_snapshot: dict[str, float]
) -> None:
    """`E.2`, the ADR-008 question, with data at last — and it is score-neutral for Wesa.

    ADR-008 ruled that "engineers" is the sum of `E.4`…`E.8` and excludes `E.9`, the
    technicians and foremen, and recorded honestly that the Rev4 fixture could not confirm it
    because the seed never went through `derive_raw`. Now the form has been through it: the
    form's own rows sum to **8** and the Rev4 sheet recorded **10**. Uni Ko counted two
    engineers this system does not, and no single row of the form accounts for the difference
    (`E.9` is 4, not 2), so this is a discrepancy to surface rather than a rule to re-derive.

    It is worth knowing that it costs nothing: `E.2` scores identically at 8 and at 10, so
    Wesa's 90.3 and its class A are unaffected either way. The seed still stores the sheet's
    number, because the sheet is what the commission decided on.
    """
    derived = _derived(frozen)
    assert derived["E.2"] == 8.0
    assert sheet_snapshot["E.2"] == 10.0

    model = load_model("sub-4")
    at_eight = score(model, {**sheet_snapshot, "E.2": 8.0})
    at_ten = score(model, {**sheet_snapshot, "E.2": 10.0})
    assert at_eight.total == at_ten.total == 90.3
    assert at_eight.cls == at_ten.cls == "A"
