"""Number coercion and the one rounding rule the whole engine depends on.

Two behaviours are ported verbatim from the reference JS (``docs/design/scoring.js``)
because the 13 Rev4 totals only reproduce when they match bit for bit:

* ``R1`` is ``Math.round(x * 10) / 10`` — **not** Python's :func:`round`, which is
  banker's rounding and turns 0.05 into 0.0 where the workbook produces 0.1.
* ``to_number`` is ``Number(v) || 0`` — every unusable value collapses to 0 rather
  than raising, so a half-filled application still scores.
"""

from __future__ import annotations

import math
from datetime import date, datetime

__all__ = ["parse_year", "r0", "r1", "to_number"]

#: Characters Excel exports leave in numeric cells: thin/non-breaking spaces, currency.
_STRIP_CHARS = " \t\r\n   "
_CURRENCY_TOKENS = ("azn", "usd", "eur", "man.", "₼", "$", "€")


def r1(x: float) -> float:
    """``Math.round(x * 10) / 10`` — one decimal, halves away from zero towards +∞.

    ``math.floor(y + 0.5)`` is exactly how ECMA-262 defines ``Math.round``, so this
    reproduces the reference for negative values too, even though every score is
    non-negative.
    """
    return math.floor(x * 10 + 0.5) / 10


def r0(x: float) -> int:
    """``Math.round(x)`` — used for the whole-percent coverage figure."""
    return math.floor(x + 0.5)


def to_number(value: object) -> float:
    """The engine's ``Number(v) || 0``.

    ``None``, ``""``, ``NaN`` and anything unparsable become ``0.0``. Booleans follow
    JavaScript (``true`` → 1). Strings are cleaned of the artefacts the Excel importer
    leaves behind (brief §1.11): a multi-value cell keeps its first value, a trailing
    ``%`` divides by 100, and thousands separators are dropped.
    """
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, int):
        return float(value)
    if isinstance(value, float):
        return 0.0 if math.isnan(value) else value
    if isinstance(value, str):
        return _number_from_string(value)
    return 0.0


def _number_from_string(text: str) -> float:
    """Parse the numeric shapes the workbooks actually contain."""
    cleaned = text.strip(_STRIP_CHARS)
    if not cleaned:
        return 0.0
    # Multi-value cell, e.g. the two VÖENs of Gilan: "1400915571 / 7200482051".
    if "/" in cleaned:
        cleaned = cleaned.split("/", 1)[0].strip(_STRIP_CHARS)
    lowered = cleaned.lower()
    for token in _CURRENCY_TOKENS:
        lowered = lowered.replace(token, "")
    lowered = lowered.strip(_STRIP_CHARS)
    percent = lowered.endswith("%")
    if percent:
        lowered = lowered[:-1].strip(_STRIP_CHARS)
    lowered = lowered.replace(" ", "").replace(" ", "")
    # "1,234,567.89" → comma is a thousands separator; "1234,56" → comma is the decimal.
    if "," in lowered and "." in lowered:
        lowered = lowered.replace(",", "")
    elif "," in lowered:
        lowered = lowered.replace(",", ".")
    try:
        number = float(lowered)
    except ValueError:
        return 0.0
    if math.isnan(number):
        return 0.0
    return number / 100 if percent else number


def parse_year(value: object) -> int | None:
    """Read a year out of a cell that may be a year, a date or a date written as text.

    Returns ``None`` when nothing year-like is there — the caller decides what a
    missing registration year means (``derive_raw`` leaves ``A.2`` at 0).
    """
    if isinstance(value, datetime | date):
        return value.year
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        year = int(value)
        return year if 1800 <= year <= 2200 else None
    if isinstance(value, str):
        text = value.strip(_STRIP_CHARS)
        if not text:
            return None
        for separator in (".", "-", "/"):
            if separator in text:
                parts = [p for p in text.split(separator) if p]
                for part in (parts[-1], parts[0]):  # dd.mm.yyyy and yyyy-mm-dd
                    candidate = _year_or_none(part)
                    if candidate is not None:
                        return candidate
                return None
        return _year_or_none(text)
    return None


def _year_or_none(text: str) -> int | None:
    try:
        year = int(float(text.strip(_STRIP_CHARS)))
    except ValueError:
        return None
    return year if 1800 <= year <= 2200 else None
