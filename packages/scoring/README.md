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
3. **Certificates** — resolved against **the model the vendor was scored with**
   (`vendor["model_version"]`, not `vendor_type`), and a certificate that model has no
   criterion for is **not held** (ADR-009, ADR-011):

   | Requirement | `sub-4` | `sup-1` |
   |---|---|---|
   | `iso9001` | `C.4` ISO 9001 | `F.1` ISO 9001 |
   | `iso45001` | `F.2` ISO 14001 / 45001 | *no criterion* → never held |
   | anything else | *no criterion* → never held | *no criterion* → never held |

   The criterion is found by scanning the model's own criterion labels for the standard
   number (`_CERTIFICATE_STANDARDS`), not from a per-version table, so a version
   published through the model editor inherits the mapping with its criteria instead of
   silently evidencing nothing.

   Three behaviours of the original port are now rejected:

   * `C.4 > 0 or F.1 > 0` for everybody — `sub-4` F.1 is the *HSE policy* knock-out, so
     every subcontractor that cleared KO "held" ISO 9001 with C.4 at zero; `sup-1` C.4 is
     *product certificates* (CE, GOST, test reports) and `C.3` is manufacturer
     authorisation. Neither substitutes for a quality-management certificate.
   * inferring the model from `vendor_type` — a `both` vendor was checked against a
     rubric its score was never produced with.
   * **unknown certificate keys pass.** Passing a certificate nobody checked reports a
     verification that never happened. A false negative is visible (the gap says which
     certificate is missing and the manager can drop the requirement); a false positive
     quietly puts an unverified vendor on a shortlist, against spec §12's claim that the
     intelligence is honest about its own accuracy.

   `Candidate.missing_certs` and `PackageMatch.missing_certs` name the certificates
   behind a `certificate_missing` reason, so the screen prints *which* one. The `gap` and
   `reasons` vocabularies themselves are **unchanged** — no new i18n key comes out of
   this, only the certificate keys the package already listed in `required_certs`.
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
- `test_matching.py` (ADR-009 / ADR-011) — ISO 9001 read from each model's own criterion in
  both directions, a `both` vendor resolved by `model_version`, a supplier unable to
  evidence `iso45001`, an unknown key reported missing, and the seed's own packages
  unmoved by any of it.

---

## 6. Phase 1A — as built

Implemented, `pytest packages/scoring/tests` → **235 passed**, 98 % line coverage, ruff and
mypy strict clean. The 13/13 Rev4 gate holds with zero mismatches
(`tests/test_rev4_fixture.py`).

```
vendoriq_scoring/
  numbers.py    R1 / R0 / Number(v)||0 / year parsing — the coercion layer
  engine.py     score_criterion, classify, score
  derive.py     derive_raw and the Yes/No pre-fill tables
  matching.py   CLASS_RANK, match_package, match_project
  loader.py     load_model, model_from_dict
  cli.py        python -m vendoriq_scoring score|derive
```

```bash
python -m vendoriq_scoring score  --model sub-4 --raw raw.json
python -m vendoriq_scoring derive --answers answers.json --type sub | \
python -m vendoriq_scoring score  --model sub-4 --raw -
```

### Deviations from §1–§5, and why

| §  | Contract said | As built | Why |
|----|---------------|----------|-----|
| §3 | `derive_raw(answers, vendor_type)` | plus keyword-only `current_year: int \| None` | `A.2` needs a year and the function must stay pure. Defaults to `date.today().year`, so the documented call is unchanged; a re-score of a closed cycle pins the year and stays reproducible (spec §10.3). |
| §3 | KO answers `A.1`, `A.4`, `F.1` pre-filled | ten questions pre-filled (`YES_NO_PREFILL_SUB`) | The 1A brief gives the full table: `A.11→A.1`, `A.15→A.4`, `F.1→F.1`, `C.1→C.4`, `B.9→B.3`, `B.12→B.4`, `E.12→E.3`, `G.1→G.1`, `F.5`/`F.8→F.2`. A superset of §3; every entry is still an overridable pre-fill. |
| §3 | (silent on suppliers) | `YES_NO_PREFILL_SUP`, a deliberate subset | The A–G form is the *subcontractor* form. Only the questions whose supplier criterion means the same thing are mapped (ISO 9001 moves from `C.4` to `F.1`; references move from `G.2` to `G.1`). `sup-1` `C.3` (manufacturer authorisation, a KO) and `D.3` (lead time) have **no form question** — the officer enters them. |
| §4 | candidates = vendors in the category | same, but non-prequalified vendors stay in the list carrying `not_prequalified` | The reference drops them before scoring, so the UI can only say "nobody". Eligibility, strength and both verdicts are unchanged. |
| §4 | `gap ∈ {no_vendor_in_category, only_class_c, certificate_missing, capacity_too_small}` | adds `no_prequalified_vendor` and `too_few_strong` | Without them the seed's own data is mislabelled: TQS-238 pk5 (one rejected vendor) came out as `only_class_c`, and pk6 (a single class-A supplier) likewise. Both new keys need an `az`/`en` string. |
| §2 | `bands`: `v == 0` → `0` | `v == 0` → `spec["zero"]` | Identical for both shipped models (`zero` is 0) and it matches `BandsSpec` in `types.py`; it keeps the JSON self-describing. |
| §2 | `score(model, raw: RawIndicators)` | `raw: RawIndicatorsInput` (`Mapping`) | `dict` is invariant, so a caller's `dict[str, float]` — the natural shape coming out of observations — could not be passed without a cast. Widening only; `RawIndicators` is unchanged and is still what `derive_raw` returns. |

### Rulings applied after phase 1A

**ADR-008 — `E.2` excludes technicians and foremen.** `derive_raw` sums form rows
`E.4`…`E.8` (chief engineer, civil, architects, electrical, MEP). Form row `E.9` is
*technicians / foremen* (spec Appendix A, doc code `E-02`), who are not engineers, so it is
out. The 1A port summed `E.4`…`E.9` and flagged it; the orchestrator ruled `E.4`…`E.8`.
This does **not** move the Rev4 gate: `seed/vendors_seed.json` carries `E.2` as extracted
from the workbook and never passes through `derive_raw`, so all 13 totals and decisions are
unchanged. It does change the derived `E.2` of a *form* import — WESA goes from 12 to 8,
which scores the same 3.0 of 4 (both fall in the `< 16 → 75 %` band).

**ADR-009 — the ISO 9001 requirement is per model, not an "either".** `_certificate_held`
reads `C.4` for a subcontractor and `F.1` for a supplier, never both. The prototype's
`C.4 > 0 or F.1 > 0` was wrong in both directions — see §4 rule 3. (ADR-009 keyed this on
`vendor_type`; ADR-011 below re-keyed it on `model_version`, which is the same answer for
every vendor that is not `both`.) Pinned by
`test_a_subcontractors_hse_policy_is_not_an_iso_9001_certificate` and
`test_a_supplier_holds_iso_9001_through_f_1_even_with_c_4_empty`.

**ADR-011 — resolve against the scored model, and never pass what was not checked.** Two
rules, one principle: the engine may only claim what it verified.

*The model, not the type.* `_assess` already loads `vendor["model_version"]` to produce
the score; the certificate check now reads that same model. A `both` vendor is therefore
checked against whichever rubric actually measured it — a score and an eligibility claim
quoting different rubrics is a statement about a model the vendor never faced.

*No criterion, no certificate.* A required certificate the model has no criterion for is
reported missing, replacing the old "unknown key passes". The concrete consequence:
`sup-1` has no ISO 45001 row, so a supplier can never satisfy an `iso45001` requirement.
That is the intended answer — a supplier's ISO 45001 status is genuinely unrecorded —
and it is loud rather than silent.

*Blast radius on the seed: none.* `iso9001` is required on TQS-238 pk1 (facade) and
TQS-301 pk1 (steel); `iso45001` on TQS-238 pk3 (MEP). All three are work packages matched
against `sub-4`. No material package requires a certificate, so no supplier is affected,
and every package state, gap, eligible list and coverage figure for both seed projects is
byte-identical before and after. `test_no_material_package_in_the_seed_requires_a_certificate`
pins that, so the day a material package asks for ISO 45001 the test says so first.

### Facts worth knowing before touching this

**The 1.0 that four vendors score is `C.3`, not `A.2`.** `seed/README.md` attributes it to the
`bands` rule on years in operation. It is not: V02–V04 and V12 have *every* cell `None`, `A.2`
scores 0, and the single point is `ongoing`'s 25 %-for-zero rung on C.3 (1.0 of 4).
`tests/test_rev4_fixture.py::test_an_empty_application_still_scores_one` pins the real
mechanism. The seed README is worth correcting.

**Two certificate gaps belong to the models, not to the engine.** Both are recorded and
neither is fixed here, because a model version is immutable once used (spec §10.3):
`sub-4` is the frozen Rev4 model all 13 fixture vendors were scored with, and `sup-1` is
"proposed" until the commission freezes it (brief §1.3). Re-weighting either is the
commission's call through a new version.

* **`sup-1` has no ISO 45001 criterion.** Its F.2 is the *defect / return record*. Under
  ADR-011 a supplier therefore cannot evidence ISO 45001 at all and is reported missing
  it. No seed package asks a supplier for one, so nothing changes today.
* **`sub-4` F.2 conflates ISO 14001 with ISO 45001.** The criterion is literally labelled
  "ISO 14001 / 45001", so a subcontractor holding only ISO 14001 registers as holding
  ISO 45001. The engine cannot separate them from one 0–3 cell.
