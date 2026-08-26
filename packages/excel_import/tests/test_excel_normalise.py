"""The normalisers, one quirk at a time.

Each case here was taken from a real cell in one of the four fixtures (brief §1.11) or is a
boundary next to one. They are unit tests so that a failure points at the rule rather than
at "the WESA fixture changed".
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from vendoriq_excel_import.normalise import (
    clean_text,
    months_between,
    normalise_bool,
    normalise_date,
    normalise_number,
    normalise_percent,
    percent_style,
    split_multi_value,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (1250.5, 1250.5),
        (0, 0.0),
        ("1250", 1250.0),
        ("1 250 000", 1250000.0),  # space as a thousands separator
        ("1\xa0250", 1250.0),  # non-breaking space, as Excel pastes it
        ("1,250", 1250.0),  # comma grouping a thousand
        ("1250,50", 1250.5),  # comma as a decimal point
        ("1,250.50", 1250.5),  # both separators: comma groups, dot decides
        ("", None),
        ("Yoxdur", None),
        ("USD 250,000 (Property)", None),
    ],
)
def test_normalise_number(raw: object, expected: float | None) -> None:
    assert normalise_number(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("Var", True), ("var", True), ("Yoxdur", False), ("YOX", False), ("", None), ("Bəli", True)],
)
def test_normalise_bool(raw: str, expected: bool | None) -> None:
    assert normalise_bool(raw) is expected


def test_normalise_percent_accepts_both_spellings_in_one_column() -> None:
    # C.t2 of the WESA form: row 1 is a 0%-formatted 0.95, row 2 is the text "85%".
    assert normalise_percent(0.95) == 95.0
    assert normalise_percent("85%") == 85.0
    assert percent_style(0.95) == "fraction"
    assert percent_style("85%") == "suffix"


def test_normalise_percent_leaves_a_real_percentage_alone() -> None:
    assert normalise_percent(85) == 85.0
    assert normalise_percent(1) == 100.0  # "1" in a completion column means finished


@pytest.mark.parametrize(
    ("raw", "expected", "status"),
    [
        (datetime(2020, 9, 28), "2020-09-28", "ok"),
        (date(2020, 9, 28), "2020-09-28", "ok"),
        ("28.09.2020", "2020-09-28", "ok"),
        ("28.04.2026 18.00", "2026-04-28", "ok"),  # a deadline carries a time
        ("2026-12-10", "2026-12-10", "ok"),
        ("Müddətsiz", None, "no_expiry"),
        ("Layihe esasli (40 gun)", None, "unparsable"),
        ("31.02.2020", None, "unparsable"),
        ("", None, "ok"),
    ],
)
def test_normalise_date(raw: object, expected: str | None, status: str) -> None:
    assert normalise_date(raw) == (expected, status)


def test_split_multi_value_only_splits_two_whole_numbers() -> None:
    assert split_multi_value("1400915571 / 7200482051") == ["1400915571", "7200482051"]
    assert split_multi_value("2006 / 2016") == ["2006", "2016"]
    # A licence number and a free-text insurance limit are single values that contain a slash.
    assert split_multi_value("3-21-2-2-1/2-28732/2026") is None
    assert split_multi_value("USD 250,000 (Property) / USD 65,000 (Bodily)") is None
    assert split_multi_value(1804034391) is None


def test_months_between_counts_whole_months() -> None:
    assert months_between(date(2020, 9, 28), date(2026, 4, 21)) == 66
    assert months_between(date(2026, 1, 28), date(2026, 4, 28)) == 3
    assert months_between(date(2026, 1, 28), date(2026, 4, 27)) == 2


def test_clean_text_collapses_the_whitespace_a_typed_cell_collects() -> None:
    assert clean_text("  Bakı  şəhəri \n Nəsimi ") == "Bakı şəhəri Nəsimi"
    assert clean_text("   ") is None
    assert clean_text(datetime(2020, 9, 28)) == "2020-09-28"
