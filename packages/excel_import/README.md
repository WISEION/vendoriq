# `vendoriq_excel_import` — the Excel adapter

Two parsers, one for each side of the paper process the system replaces:

| Function | Reads | Returns |
|---|---|---|
| `parse_application_form(path)` | the 11-sheet vendor application (`Form Prekvalifikasiya_Muraciet_Formasi.xlsx`) | `ParsedApplication` |
| `parse_scoring_workbook(path)` | a Rev4-style scoring workbook, one column per participant | `list[WorkbookVendor]` |

Both are pure readers. Neither touches the database: the importer is an adapter (spec §6)
that produces observations and warnings, and the officer confirms the mapping before the
API writes anything.

```bash
python -m vendoriq_excel_import parse seed/fixtures/98dfa150-WESA_….xlsx
python -m vendoriq_excel_import parse seed/fixtures/3b699c4f-Rev4_….xlsx --json
```

---

## Two rules run through the whole package

**Cells are addressed by their code in column B**, never by row number. `A.1 … G.7` on the
section sheets, `A-01 … H-02` on the checklist, and the group letters / `KO` / `Σ` rows in
the workbook. A sheet that grows a row still parses (spec §6.1). Sheets themselves are
resolved by the number their name starts with, so a renamed sheet still parses too. Only
*columns* are positional — and section C is the one exception worth remembering: its three
answers sit in `G`/`I` rather than `E`/`F`, because that sheet is mostly a wide project
table. `catalog.py` holds that layout.

**Nothing reads the clock.** "Is this tax-clearance certificate stale?" is answered against
the date the form itself carries (`Forma Göndərilmə Tarixi`), and "how many years has this
company operated?" counts to that same year. That is both the honest reference — the
certificate had to be fresh when the vendor applied, not when an officer opened the file —
and the reason the committed fixtures still pass next year.

---

## `ParsedApplication`

```python
ParsedApplication(
    source_file="WESA ….xlsx",
    vendor={"name": "VVESA MMC", "voen": "1003915341", "reg_year": 2015, …},
    meta={"project_name": "Gənclik Bahar Residence", "project_code": "238",
          "issued_on": "2026-04-21", "due_on": "2026-04-28", …},
    answers={"A.3": "1003915341", "B.1": 7678681.31, "A.11": True, "A.16": "2020-09-28", …},
    tables={"C.t1": [ {name, client, start, end, duration_months, value, project_type}, … ],
            "C.t2": [ {…, completion_pct}, … ],
            "G.t1": [ {client, project, contact}, … ]},
    documents={"A-01": "uploaded", "E-04": "not_applicable", …},
    document_details=[…],          # the checklist row in full, with the vendor's file note
    derived={"A.2": 11, "B.1": 5189111.38, "C.1": 10, …},   # via vendoriq_scoring.derive_raw
    units={"B.1": "AZN", …},
    warnings=[ImportWarning(...), …],
)
```

`to_observations(source="excel", source_ref=…)` turns `answers` and `tables` into
`field_observation` rows (ADR-004): `{field_code, value: {"value": …}, unit, source,
source_ref}`. Scalars and tables are both wrapped, so they share one JSONB column. The
caller supplies `vendor_id`, `observed_at` and `entered_by` — the importer knows none of
those.

A **filled cell always produces a key**, even when it normalises to `None`: `"Müddətsiz"`
in an expiry field is an answer ("no expiry"), not a blank. An *unfilled* cell produces no
key at all, which is why the blank template parses to `answers == {}`.

The form's own `calc` cells (`B.4` three-year average, `B.8` current ratio) are ignored and
recomputed — a stale formula result is not evidence.

## `WorkbookVendor`

Profile values are copied **verbatim**, including the line breaks inside an address and the
integer-vs-string difference between one VÖEN and two. The workbook is the commission's
record and `seed/vendors_seed.json` is that record transcribed; tidying it here would
silently rewrite it. `to_seed_rows(vendors)` reproduces that file exactly — the test asserts
all 13 rows — and `voen_values` carries the split-out numbers next to the warning that
explains them.

Alongside `raw` (the officers' 24 transcribed indicators) each vendor carries `points`,
`groups`, `sheet_total`, `sheet_ko` and `sheet_decision` straight off the workbook's own
formulas, so the engine port can be checked criterion by criterion and not only on the
total.

---

## Normalisation (brief §1.11)

| In the cell | Stored |
|---|---|
| `28.09.2020`, a real datetime, `28.04.2026 18.00` | `"2020-09-28"`, `"2026-04-28"` — ISO date |
| `Müddətsiz` in a date field | `None` + `no_expiry_literal` |
| `0.95` in one row, `"85%"` in the next | `95.0`, `85.0` + `mixed_percent_format` |
| `1 250 000`, `1,250`, `1250,50` | `1250000.0`, `1250.0`, `1250.5` |
| `1400915571 / 7200482051` | `["1400915571", "7200482051"]` + `multi_value_cell` |
| `Var` / `Yoxdur` | `True` / `False` |
| `Hazır` / `Hazırlanır` / `Aidiyyatsız` / empty | `uploaded` / `in_preparation` / `not_applicable` / `missing` |

A slash only splits a cell when both sides are whole numbers, so the licence number
`3-21-2-2-1/2-28732/2026` and the free-text limit `USD 250,000 (Property) / USD 65,000
(Bodily)` stay whole; the latter is reported as `unparsable_value` and kept as text rather
than guessed at.

## Warnings

Every warning carries `code`, `message_en`, `message_az`, `severity`
(`error` | `warning` | `info`) and, where it applies, the field code, sheet and cell.
Codes are listed in `normalise.WARNING_CODES`. The WESA fixture produces eight, among them
the three the brief names: the tax-clearance certificate dated `2020-09-28` (66 months
before the application), the completion column written two ways, and the checklist that
declares 38 documents while only 29 are marked ready.

## Tests

`pytest packages/excel_import/tests` — 62 tests over all four fixtures:

* `test_excel_normalise.py` — one case per quirk, each taken from a real cell.
* `test_form_blank.py` — the empty template: no answers, no crash, every mandatory cell and
  document reported.
* `test_form_wesa.py` — the filled form against `tests/fixtures/wesa_expected.json`, plus
  the values that were checked against the workbook by hand (VÖEN, the three turnovers, 10
  completed and 2 ongoing projects, ISO 9001 `I1731076497Q`).
* `test_scoring_workbook.py` — Rev4 reproduces all 13 rows of `seed/vendors_seed.json`;
  the Rev1 template has no participants.
* `test_excel_cli.py` — form/workbook detection and both output modes.

Regenerate the expected parse after an intentional change, then read the diff before
committing it:

```bash
python - <<'PY'
import json
from vendoriq_excel_import import parse_application_form
parsed = parse_application_form("seed/fixtures/98dfa150-WESA_Prekvalifikasiya_Muraciet_Formasi.xlsx")
with open("packages/excel_import/tests/fixtures/wesa_expected.json", "w", encoding="utf-8") as fh:
    json.dump(parsed.as_dict(), fh, ensure_ascii=False, indent=2)
    fh.write("\n")
PY
```
