"""The filled WESA application, against a committed expected parse.

``fixtures/wesa_expected.json`` was produced by this parser and then read line by line
against the workbook itself, so it is a *reviewed* snapshot rather than a rubber stamp. The
value assertions below repeat the numbers that were checked by hand, so that a regression
says which fact broke instead of only "the JSON differs".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vendoriq_excel_import import ImportWarning, ParsedApplication, parse_application_form


def test_wesa_matches_the_expected_parse(wesa_form: Path, wesa_expected: dict[str, Any]) -> None:
    parsed = parse_application_form(wesa_form)

    assert parsed.as_dict() == wesa_expected


def test_wesa_vendor_identity(wesa_form: Path) -> None:
    parsed = parse_application_form(wesa_form)

    assert parsed.vendor["voen"] == "1003915341"
    assert parsed.vendor["name"] == "VVESA MMC"
    assert parsed.vendor["reg_year"] == 2015
    assert parsed.vendor["email"] == "habib.atakisiyev@wesa.az"
    assert parsed.meta["project_name"] == "Gənclik Bahar Residence"
    assert parsed.meta["project_code"] == "238"


def test_wesa_financials(wesa_form: Path) -> None:
    parsed = parse_application_form(wesa_form)

    assert parsed.answers["B.1"] == 7678681.31
    assert parsed.answers["B.2"] == 5275759.15
    assert parsed.answers["B.3"] == 2612893.68
    # The form's own average cell is a formula and is ignored; the importer recomputes it.
    assert "B.4" not in parsed.answers
    assert parsed.derived["B.1"] == 5189111.38


def test_wesa_project_tables(wesa_form: Path) -> None:
    parsed = parse_application_form(wesa_form)

    assert len(parsed.tables["C.t1"]) == 10
    assert len(parsed.tables["C.t2"]) == 2
    assert len(parsed.tables["G.t1"]) == 8
    assert parsed.derived["C.1"] == 10
    assert parsed.derived["C.3"] == 2
    assert parsed.derived["C.2"] == 6140000.0  # largest completed project
    assert parsed.tables["C.t1"][4]["name"] == "Heat Exchanger and Air Coolers / RFP"


def test_wesa_iso_certificate(wesa_form: Path) -> None:
    parsed = parse_application_form(wesa_form)

    assert parsed.answers["C.1"] is True
    assert parsed.answers["C.2"] == "I1731076497Q"
    assert parsed.answers["C.3"] == "2026-12-10"


def test_wesa_open_ended_licence_is_a_null_answer_not_a_blank(wesa_form: Path) -> None:
    # A.14 reads "Müddətsiz" — the licence never expires. The key exists with a null value
    # so a reader can tell "no expiry" apart from "not answered".
    parsed = parse_application_form(wesa_form)

    assert "A.14" in parsed.answers
    assert parsed.answers["A.14"] is None
    assert _warning(parsed, "no_expiry_literal").field_code == "A.14"


def test_wesa_reports_the_stale_tax_clearance(wesa_form: Path) -> None:
    parsed = parse_application_form(wesa_form)
    warning = _warning(parsed, "stale_certificate")

    assert warning.field_code == "A.16"
    assert warning.severity == "error"
    assert warning.raw_value == "2020-09-28"
    # Measured against the form's own date (2026-04-21), never against today's clock.
    assert "2026-04-21" in warning.message_en
    assert "2020-09-28" in warning.message_az


def test_wesa_reports_the_mixed_percentage_column(wesa_form: Path) -> None:
    parsed = parse_application_form(wesa_form)
    warning = _warning(parsed, "mixed_percent_format")

    assert warning.field_code == "C.t2"
    assert [row["completion_pct"] for row in parsed.tables["C.t2"]] == [95.0, 85.0]


def test_wesa_reports_the_incomplete_document_checklist(wesa_form: Path) -> None:
    parsed = parse_application_form(wesa_form)
    warning = _warning(parsed, "document_status_missing")

    # The sheet says 29 of 38; the checklist only lists 30 codes, so nine statuses are
    # unaccounted for and the officer has to be told.
    assert warning.raw_value == "29 / 38"
    assert parsed.documents["E-04"] == "not_applicable"
    assert sum(1 for s in parsed.documents.values() if s == "uploaded") == 29


def test_wesa_reports_the_free_text_insurance_limits(wesa_form: Path) -> None:
    parsed = parse_application_form(wesa_form)
    codes = {w.field_code for w in parsed.warnings if w.code == "unparsable_value"}

    assert codes == {"G.4", "G.7"}
    assert parsed.answers["G.4"] == "USD 250,000 (Property) / USD 65,000 (Bodily)"


def test_wesa_observations_carry_source_and_unit(wesa_form: Path) -> None:
    parsed = parse_application_form(wesa_form)
    observations = parsed.to_observations(source="excel", source_ref=parsed.source_file)
    by_code = {row["field_code"]: row for row in observations}

    assert len(observations) == len(parsed.answers) + len(parsed.tables)
    assert by_code["B.1"] == {
        "field_code": "B.1",
        "value": {"value": 7678681.31},
        "unit": "AZN",
        "source": "excel",
        "source_ref": parsed.source_file,
    }
    assert by_code["C.t1"]["value"]["value"] == parsed.tables["C.t1"]
    assert {row["source"] for row in observations} == {"excel"}


def test_wesa_derives_the_knock_out_prefills(wesa_form: Path) -> None:
    # Form A.11 / A.15 / F.1 are the three "Var?" questions; they pre-fill raw indicators
    # A.1 / A.4 / F.1 with the rubric value 3 (brief §1.4).
    parsed = parse_application_form(wesa_form)

    assert parsed.derived["A.1"] == 3
    assert parsed.derived["A.4"] == 3
    assert parsed.derived["F.1"] == 3
    # Years in operation count to the year printed on the form, not to today, so this
    # assertion is still true in 2030.
    assert parsed.derived["A.2"] == 11  # 2026 form year − 2015 registration


def _warning(parsed: ParsedApplication, code: str) -> ImportWarning:
    matches = [w for w in parsed.warnings if w.code == code]
    assert len(matches) == 1, f"expected exactly one {code} warning, got {len(matches)}"
    return matches[0]
