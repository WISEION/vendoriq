"""Paths to the four Excel fixtures every importer test reads."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = REPO_ROOT / "seed" / "fixtures"
EXPECTED = Path(__file__).resolve().parent / "fixtures"

BLANK_FORM = FIXTURES / "55783af7-Form_Prekvalifikasiya_Muraciet_Formasi.xlsx"
WESA_FORM = FIXTURES / "98dfa150-WESA_Prekvalifikasiya_Muraciet_Formasi.xlsx"
REV1_WORKBOOK = FIXTURES / "e6396e67-FORM_Rev1_Prekvalifikasiya_TQS2026006.xlsx"
REV4_WORKBOOK = FIXTURES / "3b699c4f-Rev4_Prekvalifikasiya_TQS2026006.xlsx"

VENDORS_SEED = REPO_ROOT / "seed" / "vendors_seed.json"
WESA_EXPECTED = EXPECTED / "wesa_expected.json"


@pytest.fixture(scope="session")
def wesa_expected() -> dict[str, Any]:
    """The reviewed expected parse of the WESA form, as committed."""
    return json.loads(WESA_EXPECTED.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


@pytest.fixture(scope="session")
def blank_form() -> Path:
    return BLANK_FORM


@pytest.fixture(scope="session")
def wesa_form() -> Path:
    return WESA_FORM


@pytest.fixture(scope="session")
def rev1_workbook() -> Path:
    return REV1_WORKBOOK


@pytest.fixture(scope="session")
def rev4_workbook() -> Path:
    return REV4_WORKBOOK
