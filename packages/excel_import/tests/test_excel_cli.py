"""``python -m vendoriq_excel_import parse <file> --json``.

The CLI is how a file gets inspected before there is an API to POST it to, so it has to
recognise which of the two workbook shapes it was handed on its own.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from vendoriq_excel_import.__main__ import detect_kind, main


def test_detects_a_form_and_a_workbook(wesa_form: Path, rev4_workbook: Path) -> None:
    assert detect_kind(wesa_form) == "form"
    assert detect_kind(rev4_workbook) == "workbook"


def test_json_output_of_a_form(wesa_form: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["parse", str(wesa_form), "--json"]) == 0

    parsed = json.loads(capsys.readouterr().out)
    assert parsed["kind"] == "application_form"
    assert parsed["vendor"]["voen"] == "1003915341"
    assert len(parsed["tables"]["C.t1"]) == 10


def test_json_output_of_a_workbook(rev4_workbook: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["parse", str(rev4_workbook), "--json"]) == 0

    parsed = json.loads(capsys.readouterr().out)
    assert parsed["kind"] == "scoring_workbook"
    assert len(parsed["vendors"]) == 13
    assert parsed["seed_rows"][4]["sheetTotal"] == 90.3


def test_summary_output_names_the_warnings(
    wesa_form: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["parse", str(wesa_form)]) == 0

    out = capsys.readouterr().out
    assert "stale_certificate" in out
    assert "mixed_percent_format" in out


def test_missing_file_is_an_error_not_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["parse", str(tmp_path / "nope.xlsx")]) == 2
    assert "no such file" in capsys.readouterr().err
