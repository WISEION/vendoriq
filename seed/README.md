# `seed/` — the data the system starts from

Two layers, deliberately separated. **Real** data comes from the TQS2026006 prequalification and
must survive; **demo** data is illustrative and must be removable with one command.

```bash
make seed         # real rows only, idempotent — running it twice changes nothing
make seed-demo    # adds the demo layer, every row flagged is_demo = true
make purge-demo   # deletes every is_demo row, leaving the real data untouched
```

Every table that can carry demo rows has an `is_demo` boolean. `purge-demo` is a delete by that
flag — not a truncate — which is why the flag is a column rather than a naming convention.

## Files

| File | What it is |
|---|---|
| `data.json` | The structured seed: 13 real vendors, 4 demo suppliers, 2 projects with their packages, the A–G form catalogue, the 30-row document checklist and the 15-category taxonomy. |
| `vendors_seed.json` | Raw extraction from the Rev4 sheet: per vendor the 24 raw indicators plus `sheetTotal`, `sheetKO` and `sheetDecision`. **This is the verification fixture, not seed input.** |
| `fixtures/*.xlsx` | The four Excel workbooks the importer is tested against. |

### `data.json`

| Key | Contents | Real or demo |
|---|---|---|
| `vendors` | 13 legal entities: name, VÖEN, registration year, address, contact, phone, e-mail, website, staff, engineers, `raw` indicators, `docs`, `cats` | **Real**, except `cats` (category assignments) and `docs` expiry dates, which are illustrative |
| `suppliers` | 4 material suppliers | **Demo** |
| `projects` | `TQS-238 Gənclik Bahar Residence` (Uni Ko QSC, contact Əli Məmmədov) and `TQS-301 Xəzər Logistics Park` | TQS-238 is **real**; its work-package breakdown and TQS-301 are **demo** |
| `form` | Sections A–G, each row `[code, question_az, question_en, type, document_code]` — spec Appendix A | **Real** |
| `docs` | 30 checklist rows `[code, name_az, name_en, mandatory]` — spec Appendix B | **Real** |
| `cats` | 15 categories, `{az, en}` per code; `m_` prefixed codes are material groups | Codes are **real**; the assignment of vendors to them is **demo** (spec §16) |

The vendor `raw` maps are keyed by criterion code (`A.1` … `G.2`), exactly what
`vendoriq_scoring.score` consumes — no transformation sits between the seed and the engine.

### `vendors_seed.json` — the 13/13 acceptance fixture

The ported engine must reproduce every one of these totals and decisions exactly. This table is
the gate for phase 1A; a mismatch on any row is a failed port, not a rounding opinion.

| Id | Vendor | `sheetTotal` | `sheetDecision` |
|---|---|---|---|
| V01 | İbrahimovs Group MMC | 39.1 | F — RƏDD |
| V02 | Snek Group MMC | 1 | KO — RƏDD |
| V03 | Akabe İnşaat | 1 | KO — RƏDD |
| V04 | Bianco Group MMC | 1 | KO — RƏDD |
| V05 | Wesa (VVESA MMC) | 90.3 | A — Əla (DƏVƏT) |
| V06 | Hasan Holding | 76.2 | C — Şərti DƏVƏT |
| V07 | Ranuni MMC (Parket House) | 38.3 | KO — RƏDD |
| V08 | Ray Group | 32.3 | KO — RƏDD |
| V09 | Shield | 94.7 | A — Əla (DƏVƏT) |
| V10 | Arti Qrup MMC | 84 | B — Yaxşı (DƏVƏT) |
| V11 | Gilan (Kila Qrup) | 73 | C — Şərti DƏVƏT |
| V12 | Golden ABA | 1 | KO — RƏDD |
| V13 | İNPROCON MMC | 83.5 | B — Yaxşı (DƏVƏT) |

Note V02–V04 and V12: a vendor that submitted nothing still scores 1, because A.2 (years in
operation) is a `bands` criterion whose points are literal rather than scaled. Reproducing that
1 is part of the test — it is the cheapest proof that the `bands` rule was ported correctly and
not "simplified".

### `fixtures/` — importer test files

| File | Role |
|---|---|
| `55783af7-Form_Prekvalifikasiya_Muraciet_Formasi.xlsx` | The blank 11-sheet application form — the importer must read it and report zero answers, not an error |
| `98dfa150-WESA_Prekvalifikasiya_Muraciet_Formasi.xlsx` | The same form, filled by WESA — all fields, plus the warnings below |
| `e6396e67-FORM_Rev1_Prekvalifikasiya_TQS2026006.xlsx` | The Rev1 scoring workbook |
| `3b699c4f-Rev4_Prekvalifikasiya_TQS2026006.xlsx` | The Rev4 scoring workbook, 13 vendors — the source of `vendors_seed.json` |

Anomalies these files contain on purpose, which the parser must flag rather than swallow
(brief §1.11):

* `A.16` certificate date `2020-09-28` in the WESA file — older than the three-month rule
  (`stale_certificate`).
* Dates as text (`28.09.2020`) **and** as real datetimes in the same column (`unparsable_date`
  when neither works).
* Completion percentages written as `0.95` and as `"85%"` (`mixed_percent_format`).
* Multi-value cells such as `1400915571 / 7200482051` for Gilan, which has two legal entities
  (`multi_value_cell` — the first value is used).
* `"Müddətsiz"` ("no expiry") in date fields (`no_expiry_literal` → `expiry_date = null`).
* The methodology sheet labels turnover USD while the data is AZN (`currency_label_mismatch`);
  the system stores AZN (ADR-007).

The names carry a hash prefix because that is how the files arrived; do not rename them —
`packages/excel_import/tests/test_fixtures_present.py` asserts the exact names.

## Seed CLI

`make seed` calls `python -m vendoriq_api.seed`, implemented in phase 1E. Contract for that
implementation:

* **Idempotent.** Re-running matches existing rows by natural key (VÖEN for vendors, `code` for
  categories and projects, `version` for scoring models) and updates instead of duplicating.
* **Ordered.** Scoring models and categories first, then vendors, contacts, documents,
  observations; projects and packages last.
* **Provenance.** Every seeded value is written as a `field_observation` with
  `source = "excel"` and `source_ref = "seed/data.json"`, never as a direct column write —
  the seed goes through the same door as any adapter (ADR-004).
* **Test accounts** are created only when `AUTH_MODE=test` (`docs/TEST_ACCOUNTS.md`).
