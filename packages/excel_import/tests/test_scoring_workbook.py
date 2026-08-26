"""The scoring workbook parser, against ``seed/vendors_seed.json``.

That file is the extraction the prototype was built from and the fixture phase 1A has to
reproduce 13/13. If the parser and the file ever disagree, one of them silently rewrote the
commission's record — so the test compares the whole list, not a sample.
"""

from __future__ import annotations

import json
from pathlib import Path

from conftest import VENDORS_SEED
from vendoriq_excel_import import RAW_INDICATOR_CODES, parse_scoring_workbook, to_seed_rows


def test_rev4_reproduces_vendors_seed(rev4_workbook: Path) -> None:
    vendors = parse_scoring_workbook(rev4_workbook)
    seed = json.loads(VENDORS_SEED.read_text(encoding="utf-8"))

    assert to_seed_rows(vendors) == seed


def test_rev4_has_thirteen_participants(rev4_workbook: Path) -> None:
    vendors = parse_scoring_workbook(rev4_workbook)

    assert len(vendors) == 13
    assert [v.name.strip() for v in vendors][:3] == [
        "İbrahimovs Group MMC",
        "Snek Group MMC",
        "Akabe İnşaat",
    ]
    # Every participant carries all 24 Rev4 criteria, even the ones nobody filled in.
    assert all(set(v.raw) == set(RAW_INDICATOR_CODES) for v in vendors)


def test_rev4_totals_and_decisions(rev4_workbook: Path) -> None:
    vendors = {v.name.strip(): v for v in parse_scoring_workbook(rev4_workbook)}

    assert vendors["Wesa"].sheet_total == 90.3
    assert vendors["Wesa"].sheet_decision == "A — Əla (DƏVƏT)"
    assert vendors["Shield"].sheet_total == 94.7
    assert vendors["Snek Group MMC"].sheet_ko == "RƏDD ✗"
    assert vendors["Snek Group MMC"].sheet_decision == "KO — RƏDD"
    # Group totals come off sheet 4 and must add up to the grand total the sheet printed.
    assert round(sum(vendors["Wesa"].groups.values()), 1) == 90.3


def test_rev4_reports_the_double_registration(rev4_workbook: Path) -> None:
    vendors = {v.name.strip(): v for v in parse_scoring_workbook(rev4_workbook)}
    gilan = vendors["Gilan (Kila Qrup)"]

    # Two companies merged into one participant. The cell keeps its original text — the seed
    # file records it that way — and the split values arrive next to a warning.
    assert gilan.voen == "1400915571 / 7200482051"
    assert gilan.voen_values == ["1400915571", "7200482051"]
    assert [w.code for w in gilan.warnings] == ["multi_value_cell"]


def test_rev1_template_has_no_participants(rev1_workbook: Path) -> None:
    # The Rev1 fixture is the empty workbook the officers copy per tender.
    assert parse_scoring_workbook(rev1_workbook) == []
    assert to_seed_rows(parse_scoring_workbook(rev1_workbook)) == []


def test_workbook_vendor_round_trips_to_json(rev4_workbook: Path) -> None:
    vendors = parse_scoring_workbook(rev4_workbook)

    dumped = json.dumps([v.as_dict() for v in vendors], ensure_ascii=False)
    assert json.loads(dumped)[4]["sheet_total"] == 90.3
