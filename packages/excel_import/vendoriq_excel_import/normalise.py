"""Turning what people actually typed into values the system can store.

Every quirk handled here was seen in the four fixture workbooks (brief §1.11): dates as
``28.09.2020`` text next to real datetime cells, a percentage entered as ``0.95`` in one row
and ``"85%"`` in the next, ``"Müddətsiz"`` ("no expiry") in a date field, two VÖENs in one
cell, and thousands separators that are sometimes spaces and sometimes commas.

The functions are pure and return ``(value, warnings)`` — nothing here reads a clock or a
file, so a fixture parses to the same JSON on every machine and in every year.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

Severity = Literal["error", "warning", "info"]

#: Warning codes the officer sees on the import preview screen (brief §1.11, spec §6.1).
WARNING_CODES: tuple[str, ...] = (
    "stale_certificate",  # A.16 older than three months at submission (WESA: 2020-09-28)
    "mixed_percent_format",  # completion given as 0.95 in one row and "85%" in the next
    "multi_value_cell",  # "1400915571 / 7200482051"
    "no_expiry_literal",  # "Müddətsiz" in a date cell
    "mandatory_cell_empty",
    "currency_label_mismatch",  # the sheet header says USD, the data is AZN
    "unknown_field_code",
    "unparsable_date",
    "unparsable_value",  # "USD 250,000 (Property) / USD 65,000 (Bodily)" in an AZN cell
    "document_status_missing",
    "missing_sheet",
)


@dataclass(frozen=True, slots=True)
class ImportWarning:
    """One anomaly, addressed to a human, in both languages."""

    code: str
    message_en: str
    message_az: str
    severity: Severity = "warning"
    field_code: str | None = None
    sheet: str | None = None
    cell: str | None = None
    raw_value: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message_en": self.message_en,
            "message_az": self.message_az,
            "severity": self.severity,
            "field_code": self.field_code,
            "sheet": self.sheet,
            "cell": self.cell,
            "raw_value": self.raw_value,
        }


@dataclass(slots=True)
class Warnings:
    """Accumulator threaded through the parsers so warnings keep their sheet and cell."""

    items: list[ImportWarning] = field(default_factory=list)

    def add(
        self,
        code: str,
        *,
        message_en: str,
        message_az: str,
        severity: Severity = "warning",
        field_code: str | None = None,
        sheet: str | None = None,
        cell: str | None = None,
        raw_value: object = None,
    ) -> None:
        self.items.append(
            ImportWarning(
                code=code,
                message_en=message_en,
                message_az=message_az,
                severity=severity,
                field_code=field_code,
                sheet=sheet,
                cell=cell,
                raw_value=None if raw_value is None else str(raw_value),
            )
        )


# --------------------------------------------------------------------------------------
# Scalars
# --------------------------------------------------------------------------------------

#: Words the form uses for "no expiry" in a date cell.
NO_EXPIRY_WORDS = frozenset({"müddətsiz", "muddetsiz", "müddətsizdir", "sürəsiz"})

_TRUE_WORDS = frozenset({"var", "bəli", "beli", "hə", "he", "yes", "y", "true", "1"})
_FALSE_WORDS = frozenset({"yoxdur", "yox", "xeyr", "no", "n", "false", "0"})

_DATE_RE = re.compile(r"^(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})")
_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
#: Two whole values separated by a slash, as in "1400915571 / 7200482051" or "2006 / 2016".
_MULTI_VALUE_RE = re.compile(r"^\s*([^/|;]+?)\s*[/|;]\s*([^/|;]+?)\s*$")
_NUMERIC_RE = re.compile(r"^-?\d+(\.\d+)?$")


def is_blank(value: object) -> bool:
    """An unfilled cell. ``0`` counts as blank only where the caller says so."""
    return value is None or (isinstance(value, str) and not value.strip())


def clean_text(value: object) -> str | None:
    """Collapse the whitespace a hand-filled cell collects; ``None`` when nothing is left."""
    if value is None:
        return None
    if isinstance(value, str):
        text = " ".join(value.split())
        return text or None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def normalise_number(value: object) -> float | None:
    """``"1 250,50"``, ``"1,250.50"`` and ``1250.5`` all become ``1250.5``.

    A comma is a decimal separator only when it is the sole comma and no dot follows it —
    otherwise it is a thousands separator, which is how these sheets use it.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("\xa0", "").replace(" ", "")
    if "," in text and "." in text:
        text = text.replace(",", "")
    elif text.count(",") == 1:
        # "1250,50" is a decimal; "1,250" is a thousands group.
        head, _, tail = text.partition(",")
        text = f"{head}.{tail}" if len(tail) != 3 else f"{head}{tail}"
    else:
        text = text.replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def normalise_bool(value: object) -> bool | None:
    """``Var`` / ``Yoxdur`` (and the English and numeric spellings) to a real boolean."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    word = str(value).strip().casefold()
    if not word:
        return None
    if word in _TRUE_WORDS:
        return True
    if word in _FALSE_WORDS:
        return False
    return None


def normalise_percent(value: object) -> float | None:
    """A completion percentage as a number out of 100.

    The same column carries ``0.95`` (a number in a ``0%``-formatted cell) and ``"85%"``.
    A bare fraction of one or less is read as a fraction; anything else is already a
    percentage. ``1`` is therefore 100 %, which is what "1" in a completion column means.
    """
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("%"):
            number = normalise_number(text[:-1])
            return None if number is None else number
        value = text
    number = normalise_number(value)
    if number is None:
        return None
    return number * 100.0 if 0.0 < number <= 1.0 else number


def percent_style(value: object) -> Literal["fraction", "suffix", "plain"] | None:
    """How the author wrote a percentage, so mixed styles in one column can be reported."""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        return "suffix" if text.endswith("%") else "plain"
    number = normalise_number(value)
    if number is None:
        return None
    return "fraction" if 0.0 < number <= 1.0 else "plain"


def normalise_date(value: object) -> tuple[str | None, Literal["ok", "no_expiry", "unparsable"]]:
    """A date cell to an ISO date.

    Accepts real datetime cells, ``dd.mm.yyyy`` text (with or without a trailing time as in
    ``"28.04.2026 18.00"``) and ISO text. ``"Müddətsiz"`` is a legitimate answer meaning
    "no expiry" and yields ``None`` with its own flag rather than an error.
    """
    if value is None:
        return None, "ok"
    if isinstance(value, datetime):
        return value.date().isoformat(), "ok"
    if isinstance(value, date):
        return value.isoformat(), "ok"
    text = str(value).strip()
    if not text:
        return None, "ok"
    if text.casefold() in NO_EXPIRY_WORDS:
        return None, "no_expiry"
    iso = _ISO_RE.match(text)
    if iso:
        return _safe_date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
    dmy = _DATE_RE.match(text)
    if dmy:
        return _safe_date(int(dmy.group(3)), int(dmy.group(2)), int(dmy.group(1)))
    return None, "unparsable"


def _safe_date(year: int, month: int, day: int) -> tuple[str | None, Literal["ok", "unparsable"]]:
    try:
        return date(year, month, day).isoformat(), "ok"
    except ValueError:
        return None, "unparsable"


def split_multi_value(value: object) -> list[str] | None:
    """``"1400915571 / 7200482051"`` -> both values; ``None`` when the cell holds just one.

    Only a slash between two otherwise whole values counts. A licence number such as
    ``3-21-2-2-1/2-28732/2026`` and a free-text insurance limit are left alone, because
    splitting those would invent data rather than recover it.
    """
    if not isinstance(value, str):
        return None
    match = _MULTI_VALUE_RE.match(value)
    if match is None:
        return None
    parts = [match.group(1).strip(), match.group(2).strip()]
    if not all(_NUMERIC_RE.match(part.replace(" ", "")) for part in parts):
        return None
    return parts


def months_between(earlier: date, later: date) -> int:
    """Whole months from ``earlier`` to ``later`` — the unit the tax-clearance rule uses."""
    months = (later.year - earlier.year) * 12 + (later.month - earlier.month)
    if later.day < earlier.day:
        months -= 1
    return months


def parse_iso(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
