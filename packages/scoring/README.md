# `vendoriq_scoring` — engine contract

Pure Python. **No framework dependencies** — this package must import with nothing but the
standard library, so it can be reused by the API, the worker, a CLI or a future service.

Phase 0 ships the interface and the criteria data. Phase 1A implements the four functions.
The reference implementation is `docs/design/scoring.js` (`scoreSubcontractor`,
`SUB_CRITERIA`) and `docs/design/app.js` (`scoreGeneric`, `SUP_CRITERIA`, `matchPackage`,
`matchProject`). **The port must be line-for-line faithful**: the acceptance test is that all
13 Rev4 vendors in `seed/vendors_seed.json` reproduce their `sheetTotal` and `sheetDecision`
exactly.

---

## 1. The criteria JSON is the contract

```
packages/scoring/vendoriq_scoring/models/sub-4.json   # Rev4 subcontractor model, 24 criteria, 100 pts
packages/scoring/vendoriq_scoring/models/sup-1.json   # Supplier model v1 (proposed), 23 criteria, 100 pts
```

Transcribed from the prototype arrays. Do not edit these files to "fix" a score — a weight,
threshold or KO flag change creates a **new version** through the model editor (spec §10.3).
Both files carry the AZ/EN criterion and group labels, units and the evidence document code,
so the evaluation screen and the model viewer read them instead of hard-coding strings.

One criterion:

```json
{
  "code": "B.1", "group": "B", "max": 8, "kind": "thresh",
  "spec": { "cuts": [[500000, 0], [1000000, 0.25], [5000000, 0.5], [10000000, 0.75]], "top": 1 },
  "ko": false,
  "name_az": "Orta illik dövriyyə (3 il)", "name_en": "Avg annual turnover (3y)",
  "unit": "AZN", "evidence_doc": "B-01"
}
```

`spec.top` is present on `thresh` rows because the prototype data carries it; the `thresh`
branch never reads it (a value above every cut scores the full `max`). It **is** read by
`bands`. Keep it, so the JSON stays comparable with the prototype.

Model-level fields: `version`, `vendor_type`, `name_az`/`name_en`, `status`
(`active` | `proposed`), `pass_mark` (70), `validity_months` (12), `currency` (`AZN` — the
Rev4 methodology sheet says USD, the data is AZN; spec §16), `total_max`, `groups[]`,
`criteria[]`, `classes[]`.

Class bands, highest first: A ≥ 90, B ≥ 80, C ≥ 70, D ≥ 60, F ≥ 0. `KO` is not a band; it
replaces the class when any knock-out criterion has a raw value of 0.

Knock-out criteria: `sub-4` → A.1 licence, A.4 tax clearance, F.1 HSE policy.
`sup-1` → A.1 registration, A.4 tax clearance, C.3 manufacturer authorisation / origin.

---

## 2. `score`

```python
def score(model: ScoringModel, raw: RawIndicators) -> ScoreResult: ...
#   RawIndicators = dict[str, float | int | None]     # criterion code -> value
#   ScoreResult(per: dict[str, float], groups: dict[str, float],
#               total: float, ko: bool, cls: ScoreClassName)
```

Pure function, no I/O, no clock, no database. Same inputs → same output.

**Coercion.** Every raw value goes through the equivalent of the reference's
`Number(v) || 0`: `None`, `""`, a non-numeric string and `NaN` all become `0`. A criterion
absent from `raw` is `0`, never an error.

**Rounding rule — reproduce exactly.** `R1(x) = round(x * 10) / 10`, applied at three points:

1. each criterion's points, after its rule is applied;
2. the group total, **after every addition** (`groups[g] = R1(groups[g] + s)`), not once at
   the end — this is the workbook's behaviour and it is what makes the 13 totals match;
3. the grand total, once, over the already-rounded group totals.

Python's `round()` is banker's rounding and will **not** reproduce `Math.round`. Implement
`R1` explicitly, e.g. `math.floor(x * 10 + 0.5) / 10` for non-negative values (all points
are non-negative), and cover it with a property test.

**Rule kinds.**

| `kind` | Rule |
|---|---|
| `rubric` | `R1(v / 3 * max)` — `v` is the officer's 0–3 cell |
| `bands` | `v == 0` → `0`; else first `[limit, points]` in `spec.bands` with `v <= limit`; else `spec.top`. Points are literal, **not** scaled by `max` and **not** rounded |
| `thresh` | first `[limit, fraction]` in `spec.cuts` with `v < limit` → `R1(max * fraction)`; if none matches → `max` (unrounded) |
| `ongoing` | `v == 0` → `R1(max * .25)`; `v <= 3` → `R1(max * .5)`; `v <= 6` → `max`; else `R1(max * .75)` |
| `leadtime` | `v == 0` → `0`; `v <= 3` → `max`; `v <= 7` → `R1(max * .75)`; `v <= 14` → `R1(max * .5)`; `v <= 30` → `R1(max * .25)`; else `0` (inverse curve, supplier D.3) |

Note the two asymmetries that are easy to get wrong and are deliberate: `thresh` uses strict
`<` against its cuts while `bands`/`ongoing`/`leadtime` use `<=`; and `ongoing` gives a
*non-zero* score (25 %) for zero ongoing projects, while `leadtime` gives 0 for an unknown
(0-day) lead time.

**Knock-out and class.**

```python
ko  = all(float(raw.get(c["code"]) or 0) > 0 for c in model.criteria if c["ko"])
cls = "KO" if not ko else first band whose `min` <= total
```

`ko` is computed from the **raw** value, not from the points. The total is still computed and
returned when `ko` is `False` — the evaluation screen shows both.

**Group totals** are keyed by the group letter and must contain every group in
`model.groups`, including groups where all criteria scored 0.

---

## 3. `derive_raw`

```python
def derive_raw(answers: dict[str, object], vendor_type: Literal["sub","sup","both"]) -> RawIndicators: ...
```

Maps application answers (keyed by the field catalogue codes of spec Appendix A, tables as
lists of dicts) onto the raw indicators `score` consumes. Rules from brief §1.4:

| Raw indicator (`sub-4`) | Derivation from answers |
|---|---|
| `A.2` years in operation | current year − `A.4` (year of registration) |
| `B.1` avg. 3-year turnover | mean of `B.1`, `B.2`, `B.3` (last three annual turnovers), ignoring blanks |
| `B.2` equity | `B.5` |
| `C.1` completed projects | row count of table `C.t1` |
| `C.2` largest project value | max `value` in table `C.t1` |
| `C.3` ongoing projects | row count of table `C.t2` |
| `E.1` permanent staff | `E.1` |
| `E.2` engineers | sum of `E.4`…`E.8` (chief, civil, architects, electrical, MEP) |
| `G.2` references | row count of table `G.t1` |
| KO answers `A.1`, `A.4`, `F.1` | Yes → `3`, No/blank → `0` (a rubric pre-fill the officer may lower after checking evidence) |

Everything else is a rubric criterion and stays absent from the derived map: it is filled by
the officer on the evaluation screen, not by the form.

Normalisation the importer already applies and `derive_raw` must tolerate (brief §1.11):
dates as text (`28.09.2020`) or datetime, percentages as `0.95` **or** `"85%"`, multi-value
cells (`"1400915571 / 7200482051"` — first value wins for VÖEN), `"Müddətsiz"` meaning "no
expiry", and amounts that are AZN even where the sheet says USD.

`derive_raw` is pure and must not reach the database: the caller resolves current
observations first and passes plain values.

---

## 4. `match_package` / `match_project`

```python
def match_package(pkg: PackageInput, candidates: list[CandidateInput],
                  params: MatchParams | None = None) -> PackageMatch: ...
def match_project(project: ProjectInput, candidates: list[CandidateInput],
                  params: MatchParams | None = None) -> ProjectMatch: ...
```

`MatchParams(strong_min=2, capacity_ratio=0.40, supplier_turnover_divisor=4.0)` — defaults
only; the caller passes the values from `setting` rows (spec §11.2), the engine never reads
settings itself.

Package rules (spec §11.1, brief §1.7), in order:

1. **Candidates** — vendors whose **confirmed** categories contain `pkg.category_code`.
2. **Capacity value** — subcontractor: raw `C.2` (largest completed project). Supplier: raw
   `B.1` (turnover) ÷ `supplier_turnover_divisor`.
   **Capacity fit** — `capacity_value >= pkg.estimated_value * capacity_ratio`.
3. **Certificates** — `iso9001` is satisfied by raw `C.4` > 0 (subcontractor ISO 9001) or
   raw `F.1` > 0 (supplier ISO 9001); `iso45001` by raw `F.2` > 0. Unknown certificate keys
   pass (they are informational until a criterion exists for them).
4. **Eligible** — prequalified **and** `score.ko` **and** `CLASS_RANK[cls] >= CLASS_RANK[pkg.min_class]`
   **and** certificates satisfied. Rank: `A 5, B 4, C 3, D 2, F 1, KO 0`.
5. **Strong** — eligible, class A or B, and capacity fit.
6. **State** — `go` when `len(strong) >= strong_min`; `cond` when at least one eligible
   candidate; otherwise `nogo`.

Candidates are returned sorted by `score.total` descending. Every candidate carries the
`reasons` it failed (`not_prequalified`, `ko_failed`, `class_below_min`, `certificate_missing`,
`capacity_too_small`) so the UI can print the specific gap without recomputing anything.

Project rules (spec §11.2): `nogo` if any package is `nogo`; `go` if every package is `go`;
otherwise `cond`. `coverage_pct = round(Σ value of non-NO-GO packages / Σ value of all
packages × 100)`. On the TQS-238 sample this yields NO-GO at 96 % coverage — that number is a
regression test, not a coincidence.

`recommendation_key` is an i18n key (`m_rec_go`, `m_rec_cond`, `m_rec_nogo`), never a
rendered sentence: the engine returns keys, the frontend translates.

---

## 5. Tests phase 1A must add

- `test_rev4_fixture.py` — all 13 vendors from `seed/vendors_seed.json`: `total == sheetTotal`
  and `cls`/`ko` agree with `sheetDecision`. 13/13, no tolerance.
- `test_rounding.py` — property test that `R1` matches `Math.round(x*10)/10` on a wide range,
  including `.05` boundaries where banker's rounding differs.
- `test_rules.py` — one case per rule kind per boundary (`<` vs `<=`), plus the two
  asymmetries called out above.
- `test_supplier_model.py` — `sup-1` group maxima sum to 100 and the lead-time curve.
- `test_matching.py` — the four package states, the capacity rule for both vendor types, the
  project aggregation, and the TQS-238 96 % coverage case.
