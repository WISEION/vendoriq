"""Regenerate `seed/wesa_form.json` from the workbook it was parsed from.

The seed needs Wesa's real application answers, and the API image has no reason to carry
openpyxl or a 74 KB spreadsheet to get them. So the parse is done once, here, and the result
is committed. `apps/api/tests/test_seed_form.py` re-parses the workbook and asserts the two
still agree, which is what makes the frozen copy trustworthy rather than merely convenient.

    make seed-form
"""

from __future__ import annotations

import json
from pathlib import Path

from vendoriq_excel_import import parse_application_form

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = "seed/fixtures/98dfa150-WESA_Prekvalifikasiya_Muraciet_Formasi.xlsx"
TARGET = REPO_ROOT / "seed" / "wesa_form.json"
#: Wesa. The only one of the 13 whose filled-in application form Uni Ko still had.
VOEN = "1003915341"


def build() -> dict[str, object]:
    parsed = parse_application_form(REPO_ROOT / SOURCE)
    merged = {**parsed.answers, **parsed.tables}
    return {
        "_source": SOURCE,
        "_note": (
            "Wesa's real application form, parsed by packages/excel_import and frozen here so "
            "the seed can load it without shipping openpyxl or the workbook into the API "
            "image. Regenerate with: make seed-form. apps/api/tests/test_seed_form.py asserts "
            "it still matches the workbook."
        ),
        "voen": VOEN,
        # `None` is "the vendor left this blank", which is the same as not writing an
        # observation at all — and an observation of null would read as an answer.
        "answers": {code: value for code, value in sorted(merged.items()) if value is not None},
    }


if __name__ == "__main__":
    TARGET.write_text(
        json.dumps(build(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"{TARGET.relative_to(REPO_ROOT)}: {len(build()['answers'])} answers")  # type: ignore[arg-type]
