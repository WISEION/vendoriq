"""The blank template must parse to nothing at all, without raising.

An officer will drop the empty template into the importer by accident, and a parser that
throws on it is a parser that cannot be trusted with a half-filled one either.
"""

from __future__ import annotations

from pathlib import Path

from vendoriq_excel_import import MANDATORY_FIELD_CODES, parse_application_form
from vendoriq_excel_import.catalog import DOCUMENT_CATALOG


def test_blank_template_has_no_answers(blank_form: Path) -> None:
    parsed = parse_application_form(blank_form)

    assert parsed.answers == {}
    assert parsed.derived == {}
    assert parsed.tables == {"C.t1": [], "C.t2": [], "G.t1": []}
    assert parsed.to_observations() == [
        {
            "field_code": code,
            "value": {"value": []},
            "unit": None,
            "source": "excel",
            "source_ref": parsed.source_file,
        }
        for code in ("C.t1", "C.t2", "G.t1")
    ]


def test_blank_template_keeps_the_cycle_metadata(blank_form: Path) -> None:
    # The cycle is printed on the template before it is sent out; only the vendor block
    # is empty, and there it is empty as a formula result of 0 rather than a blank cell.
    parsed = parse_application_form(blank_form)

    assert parsed.meta["project_name"] == "Gənclik Bahar Residence"
    assert parsed.meta["project_code"] == "238"
    assert parsed.meta["issued_on"] == "2026-04-21"
    assert parsed.vendor == {}
    assert parsed.meta["participant_code"] is None


def test_blank_template_reports_every_missing_mandatory_cell(blank_form: Path) -> None:
    parsed = parse_application_form(blank_form)
    empty = {w.field_code for w in parsed.warnings if w.code == "mandatory_cell_empty"}

    assert empty == set(MANDATORY_FIELD_CODES) == {"A.11", "A.15", "F.1"}


def test_blank_template_reports_every_document_as_missing(blank_form: Path) -> None:
    parsed = parse_application_form(blank_form)

    assert set(parsed.documents) == set(DOCUMENT_CATALOG)
    assert set(parsed.documents.values()) == {"missing"}
    # Mandatory documents are errors, optional ones only warnings.
    severities = {
        w.field_code: w.severity for w in parsed.warnings if w.code == "document_status_missing"
    }
    assert severities["A-05"] == "error"
    assert severities["A-06"] == "warning"
