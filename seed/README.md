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

Note V02–V04 and V12: a vendor that submitted nothing still scores 1, and it is **not** because
of A.2. A.2 (years in operation) is a `bands` criterion whose `zero` value is 0 — at a raw value
of 0 it contributes nothing. The 1.0 comes from C.3 (ongoing projects), an `ongoing` criterion
whose curve gives a **25 % floor even at zero** (`0 → 25 %, ≤3 → 50 %, ≤6 → 100 %, >6 → 75 %` —
brief §1.2): `R1(4 × 0.25) = 1.0`, and every other criterion on an empty submission is 0.
Reproducing that 1 is part of the test — it is the cheapest proof that the `ongoing` curve's
zero-floor was ported correctly and not "simplified" to zero like every other empty answer.

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

`make seed` / `make seed-demo` / `make purge-demo` call `python -m vendoriq_api.seed`
(`apps/api/vendoriq_api/seed/`, phase 1E). What it actually does:

* **Idempotent.** Re-running matches existing rows by natural key and updates instead of
  duplicating: `external_ref` for vendors and projects (VÖEN cannot serve — four of the
  thirteen real vendors have none, brief §1.10), `code` for categories, `version` for
  scoring models, `(vendor_id, cycle_id)` for applications. A `field_observation` is matched
  on `(vendor_id, field_code, source, source_ref)` — the same value re-appearing on a second
  run is not a new fact, so it is not appended again.
* **Ordered.** Scoring models and categories first, then the 13 vendors (contacts,
  observations), then the real project and the qualification cycle (`load --real`); category
  assignments, demo suppliers, work packages and document expiry rows last (`load --demo`,
  which requires `load --real` to have already run).
* **Provenance is split, not uniform.** ADR-004 ("no `vendor.turnover` column") is about
  *scoring* fields — there genuinely is no such column. Vendor identity — legal name, VÖEN,
  registration year, address, region, website — **is** a `Vendor` column (`models/vendor.py`),
  and brief §1.10 lists it separately from "raw indicators". The seed writes identity as
  columns and the 24 Rev4 raw indicators (`A.1` … `G.2`) as append-only `field_observation`
  rows, `source = excel`, `source_ref` naming the Rev4 workbook — never the reverse.
* **The 13 Rev4 totals are re-verified, not trusted.** Each vendor's `raw` map is recomputed
  with `packages/scoring` before its application is written; a mismatch against `sheetTotal`
  raises and the whole `load --real` transaction rolls back rather than storing a wrong score.
* **Test accounts** are created only when `AUTH_MODE=test` (`services/accounts.py`,
  `docs/TEST_ACCOUNTS.md`), after the 13 vendors — so `habib.atakisiyev@wesa.az` and
  `a.tabit@shield.az` link to the real Wesa/Shield rows instead of getting a placeholder.
* **`purge-demo`'s scope is the real/demo axis above** — every `is_demo=True` row in
  `vendor`, `contact`, `category`, `vendor_category`, `document`, `project`, `work_package`,
  `qualification_cycle`, `application`, `performance_record`. `app_user` also carries
  `is_demo`, but that flags a *test account* (gated by `AUTH_MODE`, its own lifecycle in
  `services/accounts.py`), a different axis — `purge-demo` leaves it alone.
* **`purge-demo` never takes a login with it.** `vendor.new@vendoriq.test` — the one seeded
  account with no real vendor — gets a placeholder `Vendor` that genuinely **is**
  `is_demo=True` real/demo-axis data, and `app_user.vendor_id` is `ON DELETE CASCADE`
  (`models/auth.py`). Deleting that placeholder by the letter of "every `is_demo` row" would
  therefore delete the account too, and the seven logins `docs/TEST_ACCOUNTS.md` promises
  would quietly become six. `purge-demo` excludes any vendor a live `app_user` still points
  at from every delete, so it does not — while `AUTH_MODE=test`, the guarantee that all seven
  accounts work is a guarantee about the *mode*, not about the demo layer, and a demo-data
  command is not where an account's lifecycle gets decided. Removing `vendor.new` for good is
  `AUTH_MODE=live` and `services.accounts.purge_test_accounts`, same as the rest of the
  test-account layer.
