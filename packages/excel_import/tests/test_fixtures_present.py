"""The importer's fixtures must stay in the repository — phase 1D asserts against them."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[3] / "seed" / "fixtures"

EXPECTED = [
    "55783af7-Form_Prekvalifikasiya_Muraciet_Formasi.xlsx",  # blank 11-sheet form
    "98dfa150-WESA_Prekvalifikasiya_Muraciet_Formasi.xlsx",  # filled form
    "e6396e67-FORM_Rev1_Prekvalifikasiya_TQS2026006.xlsx",  # Rev1 workbook
    "3b699c4f-Rev4_Prekvalifikasiya_TQS2026006.xlsx",  # Rev4 workbook, 13 vendors
]


@pytest.mark.parametrize("name", EXPECTED)
def test_fixture_exists(name: str) -> None:
    path = FIXTURES / name
    assert path.is_file(), f"missing importer fixture {path}"
    assert path.stat().st_size > 0
