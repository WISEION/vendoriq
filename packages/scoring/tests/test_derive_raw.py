"""`derive_raw` — application answers to raw indicators (brief §1.4).

Two things this file is really testing: that the derivations match the workbook's own
formulas, and that a half-filled, quirk-ridden form (brief §1.11) still produces a
scoreable map instead of an exception.
"""

from __future__ import annotations

from datetime import date

import pytest
from vendoriq_scoring import YES_NO_PREFILL_SUB, derive_raw, is_yes, load_model, score

WESA_ANSWERS: dict[str, object] = {
    "A.4": 2015,  # year of registration
    "A.11": "Bəli",  # construction licence  → A.1 (KO)
    "A.15": "Bəli",  # tax clearance         → A.4 (KO)
    "B.1": 7_678_681.31,
    "B.2": 5_275_759.15,
    "B.3": 2_612_893.68,
    "B.5": 1_208_443.06,  # equity            → raw B.2
    "B.9": "Bəli",  # credit line           → B.3
    "B.12": "Bəli",  # audited               → B.4
    "C.1": "Bəli",  # ISO 9001              → C.4
    "C.t1": [
        {"name": "Nizami Mall", "value": 3_015_079.84},
        {"name": "Park Akademiya", "value": 1_816_000},
        {"name": "Central Towers", "value": 3_352_934.80},
        {"name": "Ravy Tower", "value": 3_430_153.40},
        {"name": "Heat Exchanger and Air Coolers", "value": 6_140_000},
        {"name": "Flue Gas Stack HAOR", "value": 1_500_000},
        {"name": "Sevinc AVM", "value": 1_000_000},
        {"name": "Hidravlik test qurğusu", "value": 948_000},
        {"name": "Steel Structure Fabrication", "value": 640_000},
        {"name": "DTX Elevator Building", "value": 491_213},
    ],
    "C.t2": [
        {"name": "Air Cooler", "value": 6_120_000},
        {"name": "The Ritz-Carlton Fasad", "value": 211_000},
    ],
    "E.1": 80,  # permanent staff
    "E.4": 1, "E.5": 4, "E.6": 2, "E.7": 1, "E.8": 1, "E.9": 1,  # engineering rows
    "E.12": "Bəli",  # HSE specialist        → E.3
    "F.1": "Bəli",  # HSE policy            → F.1 (KO)
    "F.5": "Xeyr",  # ISO 14001             ┐
    "F.8": "Bəli",  # ISO 45001             ┘ → F.2, better answer wins
    "G.1": "Bəli",  # liability insurance   → G.1
    "G.t1": [{"client": "Delta"}, {"client": "Prokon"}, {"client": "SOCAR"}],
}  # fmt: skip


@pytest.fixture
def wesa() -> dict[str, float | int | None]:
    return derive_raw(WESA_ANSWERS, "sub", current_year=2026)


# ------------------------------------------------------------------ numeric derivations


def test_years_in_operation_is_current_year_minus_registration(
    wesa: dict[str, float | int | None],
) -> None:
    assert wesa["A.2"] == 11  # 2026 − 2015


def test_years_in_operation_defaults_to_today_but_can_be_pinned() -> None:
    """A re-score of a closed cycle must not drift as the calendar moves (spec §10.3)."""
    assert derive_raw({"A.4": 2000}, "sub", current_year=2026)["A.2"] == 26
    assert derive_raw({"A.4": 2000}, "sub")["A.2"] == date.today().year - 2000


def test_a_registration_year_written_as_a_date_still_parses() -> None:
    """Brief §1.11: the same column holds ``28.09.2020``, a datetime and a bare year."""
    assert derive_raw({"A.4": "28.09.2020"}, "sub", current_year=2026)["A.2"] == 6
    assert derive_raw({"A.4": "2020-09-28"}, "sub", current_year=2026)["A.2"] == 6
    assert derive_raw({"A.4": date(2020, 9, 28)}, "sub", current_year=2026)["A.2"] == 6


def test_a_missing_registration_year_leaves_a_2_absent() -> None:
    """Absent, not a negative number — the officer sees an empty cell, not "−2026 years"."""
    assert "A.2" not in derive_raw({}, "sub")
    assert "A.2" not in derive_raw({"A.4": "Müddətsiz"}, "sub")
    assert "A.2" not in derive_raw({"A.4": ""}, "sub")
    assert "A.2" not in derive_raw({"A.4": True}, "sub")  # a Yes/No cell in the wrong column
    assert "A.2" not in derive_raw({"A.4": 42}, "sub")  # not a plausible year
    assert "A.2" not in derive_raw({"A.4": "12.13"}, "sub")  # neither part is a year


def test_a_registration_year_in_the_future_does_not_go_negative() -> None:
    """A typo (2062 for 2026) must not produce a negative "years in operation"."""
    assert derive_raw({"A.4": 2062}, "sub", current_year=2026)["A.2"] == 0


def test_turnover_is_the_mean_of_the_three_declared_years(
    wesa: dict[str, float | int | None],
) -> None:
    expected = (7_678_681.31 + 5_275_759.15 + 2_612_893.68) / 3
    assert wesa["B.1"] == pytest.approx(expected)


def test_turnover_ignores_blank_years_rather_than_averaging_them_as_zero() -> None:
    """A young company that has two years of trading is not a company with a bad third."""
    raw = derive_raw({"B.1": 900_000, "B.2": 700_000, "B.3": None}, "sub")
    assert raw["B.1"] == pytest.approx(800_000)
    assert "B.1" not in derive_raw({}, "sub")


def test_equity_comes_from_form_b_5(wesa: dict[str, float | int | None]) -> None:
    assert wesa["B.2"] == pytest.approx(1_208_443.06)


def test_project_tables_become_counts_and_a_maximum(
    wesa: dict[str, float | int | None],
) -> None:
    assert wesa["C.1"] == 10  # completed rows
    assert wesa["C.2"] == pytest.approx(6_140_000)  # largest completed project
    assert wesa["C.3"] == 2  # ongoing rows
    assert wesa["G.2"] == 3  # references


def test_empty_table_rows_are_not_counted() -> None:
    """Spreadsheets carry blank rows; counting them would inflate C.1 and G.2."""
    answers = {"C.t1": [{"name": "Real", "value": 100}, {"name": "", "value": None}, {}]}
    assert derive_raw(answers, "sub")["C.1"] == 1


def test_missing_tables_derive_to_zero_not_an_error() -> None:
    raw = derive_raw({}, "sub")
    assert raw["C.1"] == 0
    assert raw["C.2"] == 0
    assert raw["C.3"] == 0
    assert raw["G.2"] == 0


def test_a_table_that_is_not_a_table_is_ignored() -> None:
    """The importer can hand back a string for a table it failed to parse."""
    assert derive_raw({"C.t1": "see attachment", "C.t2": None}, "sub")["C.1"] == 0


def test_positional_project_rows_are_understood_too() -> None:
    """The seed carries project rows as lists, not dicts:
    ``[name, client, start_year, end_year, value, type]``. The value is the largest
    number that is not a year — years never reach a project's price, and a price never
    falls inside 1800–2200 in AZN.
    """
    answers = {
        "C.t1": [
            ["Nizami Mall", "Delta MMC", 2023, 2024, 3_015_079.84, "facade"],
            ["Sevinc AVM", "Xəzər-2016", 2022, 2023, 1_000_000, "facade"],
        ]
    }
    raw = derive_raw(answers, "sub")
    assert raw["C.1"] == 2
    assert raw["C.2"] == pytest.approx(3_015_079.84)


def test_a_project_row_with_no_recognisable_value_counts_but_scores_zero() -> None:
    """Counting the row is right — the vendor did the job; its value is simply unknown."""
    answers = {"C.t1": [{"name": "Unnamed price", "client": "X"}]}
    raw = derive_raw(answers, "sub")
    assert raw["C.1"] == 1
    assert raw["C.2"] == 0


def test_the_value_column_is_found_under_any_of_its_names() -> None:
    for key in ("value", "amount", "dəyər", "məbləğ"):
        raw = derive_raw({"C.t1": [{"name": "P", key: 250_000}]}, "sub")
        assert raw["C.2"] == 250_000, key


def test_engineers_are_the_sum_of_the_technical_staff_rows(
    wesa: dict[str, float | int | None],
) -> None:
    assert wesa["E.1"] == 80
    assert wesa["E.2"] == 10  # 1 + 4 + 2 + 1 + 1 + 1, form rows E.4…E.9


def test_headcount_stays_absent_when_the_section_is_blank() -> None:
    raw = derive_raw({"A.4": 2015}, "sub")
    assert "E.1" not in raw
    assert "E.2" not in raw


# ------------------------------------------------------------------ Yes/No pre-fills


@pytest.mark.parametrize(
    ("answer", "expected"),
    [("Bəli", True), ("bəli", True), ("Yes", True), ("YES", True), ("var", True),
     ("hə", True), (True, True), (1, True), ("1", True), ("✓", True),
     ("Xeyr", False), ("No", False), (False, False), (0, False), ("", False),
     (None, False), ("bilmirəm", False)],
)  # fmt: skip
def test_is_yes_reads_both_languages(answer: object, expected: bool) -> None:
    assert is_yes(answer) is expected


def test_yes_no_answers_pre_fill_the_rubric_at_three(
    wesa: dict[str, float | int | None],
) -> None:
    for criterion in ("A.1", "A.4", "F.1", "C.4", "B.3", "B.4", "E.3", "G.1"):
        assert wesa[criterion] == 3.0, criterion


def test_a_no_pre_fills_zero_rather_than_staying_absent() -> None:
    """0 and absent score the same, but 0 is a statement the officer can see and override."""
    raw = derive_raw({"A.11": "Xeyr", "F.1": "Xeyr"}, "sub")
    assert raw["A.1"] == 0.0
    assert raw["F.1"] == 0.0


def test_an_unasked_question_leaves_its_criterion_absent() -> None:
    assert "A.1" not in derive_raw({"A.4": 2015}, "sub")


def test_iso_14001_and_45001_both_feed_f_2_and_the_better_answer_wins(
    wesa: dict[str, float | int | None],
) -> None:
    """Criterion F.2 is literally "ISO 14001 / 45001" — one of the two satisfies it."""
    assert YES_NO_PREFILL_SUB["F.5"] == "F.2"
    assert YES_NO_PREFILL_SUB["F.8"] == "F.2"
    assert wesa["F.2"] == 3.0  # F.5 is "Xeyr", F.8 is "Bəli"
    assert derive_raw({"F.5": "Xeyr", "F.8": "Xeyr"}, "sub")["F.2"] == 0.0
    assert derive_raw({"F.5": "Bəli", "F.8": "Xeyr"}, "sub")["F.2"] == 3.0


def test_judgement_criteria_stay_out_of_the_derived_map(
    wesa: dict[str, float | int | None],
) -> None:
    """The form cannot answer "equipment & tools" — the officer scores it from evidence."""
    for officer_only in ("A.3", "D.1", "D.2", "D.3", "E.4", "F.3"):
        assert officer_only not in wesa, officer_only


# ------------------------------------------------------------------------- end to end


def test_the_derived_wesa_map_scores_in_the_right_neighbourhood(
    wesa: dict[str, float | int | None],
) -> None:
    """The form alone cannot reach the sheet's 90.3 — six judgement criteria are missing.

    What it must do is put WESA above the pass mark on the strength of the facts it does
    state, with no KO. The remaining 15 points are the officer's to award.
    """
    result = score(load_model("sub-4"), wesa)
    assert result.ko is True
    assert result.total >= 70
    assert result.cls in {"A", "B", "C"}
    missing = [c["code"] for c in load_model("sub-4").criteria if c["code"] not in wesa]
    assert missing == ["A.3", "D.1", "D.2", "D.3", "E.4", "F.3"]


# -------------------------------------------------------------------------- suppliers


def test_the_supplier_derivation_puts_references_in_g_1_and_iso_in_f_1() -> None:
    """The supplier model counts references in G.1 and holds ISO 9001 in F.1."""
    answers = {
        "A.4": 2012,
        "A.11": "Bəli",
        "A.15": "Bəli",
        "B.1": 20_000_000,
        "B.2": 24_000_000,
        "B.3": 22_000_000,
        "B.5": 6_500_000,
        "C.1": "Bəli",
        "G.t1": [{"client": "a"}, {"client": "b"}, {"client": "c"}, {"client": "d"}],
    }
    raw = derive_raw(answers, "sup", current_year=2026)
    assert raw["A.2"] == 14
    assert raw["G.1"] == 4
    assert raw["F.1"] == 3.0
    assert raw["B.1"] == pytest.approx(22_000_000)
    assert raw["B.2"] == pytest.approx(6_500_000)
    # A supplier has no project table, so the subcontractor-only indicators stay absent.
    for subcontractor_only in ("C.1", "C.2", "C.3", "E.1", "E.2", "G.2"):
        assert subcontractor_only not in raw, subcontractor_only


def test_both_is_derived_as_a_subcontractor() -> None:
    """A vendor that supplies *and* builds is prequalified on the stricter model."""
    answers = {"A.4": 2015, "G.t1": [{"client": "a"}]}
    assert derive_raw(answers, "both", current_year=2026)["G.2"] == 1
