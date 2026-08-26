"""openpyxl parser for the 11-sheet application form and the Rev4 scoring workbook.

Phase 0 ships the result shapes only; the parsers land in phase 1D. Fixtures live in
``seed/fixtures/`` — see ``seed/README.md``.

The importer is an *adapter* like any other (spec §6): it produces field observations with
``source = "excel"`` plus a list of warnings for the officer. It never writes to the
database itself — ``preview()`` returns a mapping the officer confirms, and only then does
the API persist it (endpoints ``POST /integrations/excel-import/preview`` and
``POST /integrations/excel-import/runs``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

__version__ = "0.1.0"

#: Warning codes the officer sees on the import preview screen (brief §1.11).
WARNING_CODES = (
    "stale_certificate",  # A.16 older than 3 months (WESA: 2020-09-28)
    "mixed_percent_format",  # completion given as 0.95 and as "85%"
    "multi_value_cell",  # "1400915571 / 7200482051"
    "no_expiry_literal",  # "Müddətsiz" in a date cell
    "mandatory_cell_empty",
    "currency_label_mismatch",  # sheet says USD, data is AZN
    "unknown_field_code",
    "unparsable_date",
)


@dataclass(frozen=True, slots=True)
class ImportWarning:
    """One anomaly, addressed to a human, in both languages."""

    code: str
    field_code: str | None
    sheet: str | None
    cell: str | None
    message_az: str
    message_en: str
    raw_value: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedField:
    """One answer cell resolved to its catalogue code."""

    field_code: str
    value: Any
    unit: str | None
    sheet: str
    cell: str


@dataclass(frozen=True, slots=True)
class ParsedDocumentStatus:
    """One row of the 38-item checklist sheet."""

    code: str
    status: Literal["uploaded", "in_preparation", "not_applicable", "missing"]
    note: str | None = None


@dataclass(frozen=True, slots=True)
class ApplicationFormResult:
    """What ``parse_application_form`` returns."""

    source_file: str
    fields: list[ParsedField] = field(default_factory=list)
    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    documents: list[ParsedDocumentStatus] = field(default_factory=list)
    warnings: list[ImportWarning] = field(default_factory=list)
    #: Raw indicators derived from the answers, ready for ``vendoriq_scoring.score``.
    derived_raw: dict[str, float | int | None] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WorkbookVendorRow:
    """One vendor column of the Rev4 scoring workbook."""

    name: str
    voen: str | None
    raw: dict[str, float | int | None]
    rubric: dict[str, int]
    sheet_total: float | None
    sheet_decision: str | None


@dataclass(frozen=True, slots=True)
class ScoringWorkbookResult:
    """What ``parse_scoring_workbook`` returns."""

    source_file: str
    model_version: str
    vendors: list[WorkbookVendorRow] = field(default_factory=list)
    warnings: list[ImportWarning] = field(default_factory=list)


def parse_application_form(path: Path | str) -> ApplicationFormResult:
    """Read the 11-sheet vendor application form.

    Cells are addressed by their **code in column B**, never by row number, so the parser
    survives row insertions (spec §6.1).

    Not implemented in phase 0 (contract only).
    """
    raise NotImplementedError("Implemented in phase 1D")


def parse_scoring_workbook(path: Path | str) -> ScoringWorkbookResult:
    """Read a Rev4-style scoring workbook, one column per vendor.

    Not implemented in phase 0 (contract only).
    """
    raise NotImplementedError("Implemented in phase 1D")


__all__ = [
    "WARNING_CODES",
    "ApplicationFormResult",
    "ImportWarning",
    "ParsedDocumentStatus",
    "ParsedField",
    "ScoringWorkbookResult",
    "WorkbookVendorRow",
    "__version__",
    "parse_application_form",
    "parse_scoring_workbook",
]
