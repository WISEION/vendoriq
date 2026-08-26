# Architecture decision log

One entry per decision that would be expensive to reverse or that a future reader would
otherwise have to reconstruct from the code. Newest last. An unresolved ambiguity gets an entry
with the chosen default, so the default is visible rather than buried (build brief §4.3).

Status values: **Accepted**, **Superseded by ADR-xxx**, **Proposed**.

---

## ADR-001 — Stack

**Status:** Accepted (phase 0) · **Decided by:** owner, build brief §2

FastAPI on Python 3.11, React 18 + Vite + TypeScript, PostgreSQL 16, SQLAlchemy 2 + Alembic,
TanStack Query + TanStack Router, MinIO (S3 API) for documents, uv for Python dependency
management, npm for the frontend.

**Why.** One language carries the two pieces of logic that matter — the scoring engine and the
Excel importer (openpyxl) — so the port of `docs/design/scoring.js` and the parser live in the
same test suite as the API. PostgreSQL's JSONB holds the form answers keyed by field code
without a table per section. React with plain CSS variables (the prototype's tokens) avoids a UI
kit that would have to be fought when the design changes.

**Consequences.** Python 3.11, not the 3.12 named in the brief: the build host ships 3.11 and
pinning to the host avoids a version the CI image would have to install separately
(`requires-python = ">=3.11,<3.12"` everywhere). The scoring package declares **no** dependencies
at all, so it can be lifted into any other runtime later.

---

## ADR-002 — Two storage backends: `local` and `s3`

**Status:** Accepted (phase 0) · **Decided by:** orchestrator, brief §9

Document storage is an interface with two implementations, selected by `STORAGE_BACKEND`:

* `local` — files under `STORAGE_LOCAL_DIR`; used for native development and by **every** test.
* `s3` — boto3 against any S3 API; MinIO in compose, a cloud bucket in production.

**Why.** MinIO cannot run on the build host, and tests that need a running object store are
tests that fail for reasons unrelated to the code. A filesystem backend also makes the fixtures
inspectable.

**Consequences.** Signed download URLs must exist in both worlds: `s3` issues a real pre-signed
URL, `local` issues a short-lived token the API validates itself. Both go through
`GET /vendors/{id}/documents/{id}`, so the frontend never learns which backend is in use.
`boto3` is an **optional** dependency (`vendoriq-api[s3]`) — a local install stays small.

---

## ADR-003 — `AUTH_MODE=test` and `AUTH_MODE=live`

**Status:** Accepted (phase 0) · **Decided by:** owner, brief §2, §6

Until launch the system runs with `AUTH_MODE=test`: seeded accounts
(`docs/TEST_ACCOUNTS.md`), one-time codes written to the server log and returned in `debug_code`,
a permanent banner in the web shell, and the vendor code `000000` always accepted.
`AUTH_MODE=live` enables SMTP delivery and hides every code.

**Why.** The owner has to be able to click through both journeys without an e-mail server, and
the demo has to be honest about the fact that it is not secure yet.

**Consequences.** The mode is a loaded gun, so it is bolted shut: `Settings` raises when
`AUTH_MODE=test` meets `APP_ENV=production`, which happens at import time — the process refuses
to open a port. `debug_code` is part of the published contract with an explicit "always null in
live mode" note, so a client cannot accidentally depend on it.

---

## ADR-004 — Field values are append-only observations

**Status:** Accepted (phase 0) · **Decided by:** spec §4, §6.6

There is no `vendor.turnover` column. Every value a source produces is a row in
`field_observation` (`vendor_id`, `field_code`, `value` JSONB, `unit`, `source`, `source_ref`,
`observed_at`, `entered_by`). The current value of a field is the observation with the best trust
rank and, within that rank, the newest `observed_at`.

**Why.** The requirement is not "store vendor data", it is "know how current and how trustworthy
each number is". A mutable column answers "what is the turnover"; observations answer "what is
the turnover, who said so, when, and should we believe it more than the registry".

**Consequences.**

* `trust_rank` is a **generated column** in PostgreSQL (`registry` 1, `api` 2, `document` 3,
  `portal`/`excel` 4, `manual` 5), so "current value" is one indexed query rather than
  application logic that each caller could get wrong. `enums.SOURCE_TRUST_RANK` mirrors it and
  a test asserts both exist; changing one means changing both.
* The generated expression compares enum to enum (`source = 'registry'::observation_source`)
  rather than casting to text: a cast from enum to text is only `STABLE`, and PostgreSQL requires
  an `IMMUTABLE` expression in a generated column.
* Scalars are wrapped (`{"value": …}`) so that tables (`C.t1`, `C.t2`, `G.t1`) can be stored in
  the same column as numbers and Yes/No answers.
* Reads cost a join and a window function. At the target scale (1 000 vendors, spec §13) this is
  well inside the one-second budget; if it ever is not, a materialised "current value" view is
  the escape hatch, not a schema change.
* Freshness becomes measurable, which is what makes the market-intelligence screens honest about
  their own accuracy.

---

## ADR-005 — Dependencies on this build host: npm and PyPI are blocked

**Status:** Accepted (phase 0) · **Decided by:** orchestrator, build environment

The brief anticipated occasional 403s from the npm registry. In fact **the egress policy of this
sandbox blocks `registry.npmjs.org`, `pypi.org`, `files.pythonhosted.org` and every CDN
outright** — every package fetch returns 403 "Host not in allowlist". `github.com` over HTTPS
git *is* reachable.

The manifests are therefore written as they must be in a normal environment
(`pyproject.toml` with FastAPI, SQLAlchemy, Alembic, psycopg, APScheduler; `package.json` with
React 18, Vite, TanStack Query/Router, vitest, Playwright), and for **local verification only**
the Python dependencies were obtained by `git clone` of the upstream repositories at pinned tags
and placed in `.venv` (which is git-ignored):

| Package | Source | Version |
|---|---|---|
| fastapi | `github.com/fastapi/fastapi` | 0.141.1 |
| annotated-doc | `github.com/fastapi/annotated-doc` | (fastapi runtime dependency) |
| sqlalchemy | `github.com/sqlalchemy/sqlalchemy` | `rel_2_0_36` |
| alembic | `github.com/sqlalchemy/alembic` | `rel_1_14_0` |
| mako | `github.com/sqlalchemy/mako` | `rel_1_3_6` |
| psycopg | `github.com/psycopg/psycopg` | `3.2.3`, pure-Python `pq` implementation over `libpq.so.5` |
| apscheduler | `github.com/agronholm/apscheduler` | `3.11.0` |
| openapi-spec-validator | `github.com/python-openapi/openapi-spec-validator` | contract validation |

**Consequences.**

* `psycopg` runs in pure-Python mode here (no `psycopg-binary` wheel, no `libpq` headers to
  compile against). The manifest still asks for `psycopg[binary]`, which is what a normal
  install gets; nothing in the code depends on which implementation is loaded.
* **`apps/web` could not be installed or built on this host.** The source, the configs and the
  dependency pins are complete and correct, but `vite build`, `vitest` and Playwright have not
  been executed. They run in CI, where the registry is reachable.
* `make web` therefore has a fallback (`scripts/web-dev.sh`): with no `node_modules` and no
  registry it serves `apps/web/preview/`, a dependency-free rendering of the same shell that
  imports the **real** `src/theme/global.css` and the **real** `src/i18n/*.json`. It exists so
  the layout can be seen and reviewed here; it is excluded from lint, typecheck and the bundle,
  and it disappears the moment `npm install` succeeds.
* **`uv.lock` is absent.** Locking requires resolving against PyPI, which is blocked here.
  The Dockerfiles glob `uv.lock*` so its absence is not an error, and the first `uv sync`
  in a connected environment produces it. Commit that lock file in the same PR as the
  first phase-1 dependency change.
* The contract was validated with `openapi-spec-validator` (Python) rather than
  `@redocly/cli` (npm, blocked). CI runs the Python validator; adding Redocly later is a
  one-line change.

---

## ADR-006 — The hand-written OpenAPI file is the source of truth

**Status:** Accepted (phase 0) · **Decided by:** orchestrator, brief §4.3

`docs/openapi.yaml` is written by hand and served verbatim: `apps/api` sets
`app.openapi = load_contract` and disables FastAPI's generated schema.

**Why.** With generated schemas the contract is whatever the code happens to do, which makes
"contract first" unenforceable and lets a worker change the public API by editing a signature.
Here the contract is a reviewable artefact that changes only through the orchestrator, and the
route handlers are checked against it.

**Consequences.** A route whose implementation drifts from the document is a bug in the route.
`apps/api/tests/test_openapi_contract.py` keeps the file valid, its operation ids unique, every
`$ref` resolvable and every schema referenced; phase 1+ adds a test that every declared operation
has a live route and vice versa. `/api/docs` and `/api/redoc` load Swagger UI / ReDoc from a CDN,
so on a host without internet access the raw contract at `/api/openapi.yaml` is the fallback.

---

## ADR-007 — Currency is AZN everywhere

**Status:** Accepted (phase 0) · **Decided by:** spec §16

The Rev4 methodology sheet labels turnover thresholds "USD", but the vendor data and the
thresholds are Azerbaijani manat. The system stores and displays AZN, the model JSON carries
`"currency": "AZN"`, and the model description corrects the label.

**Consequences.** No currency conversion exists anywhere in the code. If a second currency is
ever needed it is a new model version with converted thresholds, not a runtime conversion —
otherwise historical scores would silently move with an exchange rate.

---

## ADR-010 — The 34 screens have fixed addresses, recorded in `docs/SCREENS.md`

**Status:** Accepted (phase 1, wave 2) · **Decided by:** orchestrator

`docs/BUILD_BRIEF.md` §4.2 counts the screens per phase-2 task and `docs/SPEC.md` §7–§8
describes what each one contains, but nothing said where a screen *lives*. `docs/SCREENS.md`
now fixes, for all 34: a stable slug, a TanStack Router path, and the task that owns it. It is
a contract artefact — a worker may not rename a route or a slug, it files a change request.

**Why.** Phase 2 runs seven workers in parallel. Without a fixed map each invents its own URL
shape (`/vendors/:id` vs `/vendor/:id` vs `/vendors/detail?id=`), the rail and the deep links
disagree, and the phase-3 Playwright run — which must produce exactly 68 files, 34 screens ×
AZ/EN — has no stable target to aim at. Fixing the addresses before the work starts costs one
document; fixing them afterwards costs seven refactors and a re-run of every screenshot.

**Consequences.** The screenshot file name is derived from the slug (`<slug>.<lang>.png`), so
the phase-3 suite is a table-driven walk over `docs/SCREENS.md` rather than 68 hand-written
cases. Gate 2's "every screen reachable" is checked against this list. Seven of the 34 are
reached from a parent screen and deliberately have no rail entry; the file says which.

---

## ADR-008 — `E.2` engineers excludes technicians and foremen

**Status:** Accepted (phase 1, wave 2) · **Decided by:** orchestrator · **Supersedes** the
phase-1A behaviour of `derive_raw`

The subcontractor model scores `E.2` "Engineers" against the thresholds `< 3 → 0, ≤ 7 → 40 %,
≤ 15 → 75 %, else 100 %` (spec §10.1). The application form has no `E.2` cell for engineers —
its own `E.2` is "Temporary / contract" headcount — so the value is derived from the technical
staff block. `derive_raw` summed **E.4…E.9**. It now sums **E.4…E.8**.

**Why.** The form's own labels settle it. E.4 chief engineer / technical director, E.5 civil
engineers, E.6 architects, E.7 electrical engineers, E.8 MEP / HVAC engineers — then E.9
"Texniklər (usta, texnik)" / "Technicians / foremen", who are not engineers. Counting E.9
inflated every vendor's engineer count by its technician headcount and made a threshold that
distinguishes an engineering department from a site crew read the wrong quantity.

**Verification.** The Rev4 fixture is unchanged: 13/13 totals and decisions still match
`sheetTotal` / `sheetDecision`. It cannot move, and that is worth stating plainly rather than
claiming as evidence — `seed/vendors_seed.json` carries `E.2` as extracted from the workbook
and feeds it straight to `score()`, so `derive_raw` is not on that path at all. The fixture
neither confirms nor refutes this ruling; the form's labels do.

**Consequences.** WESA's derived `E.2` moves 12 → 8 (E.4…E.8 = 1+5+1+0+1, E.9 = 4), which is
the single value that changed in `packages/excel_import/tests/fixtures/wesa_expected.json`.
No score moves with it: `sub-4`'s cuts are `[[3,0],[8,0.4],[16,0.75]]`, so 8 and 12 sit in the
same `< 16 → 75 %` band and both score 3.0 of 4. A vendor whose technicians outnumber its
engineers can now fall below a band it used to clear — which is the point.

---

## ADR-009 — ISO 9001 is read from each model's own criterion

**Status:** Accepted (phase 1, wave 2) · **Decided by:** orchestrator

Matching's `_certificate_held` resolved an `iso9001` package requirement as
`C.4 > 0 or F.1 > 0`, for every vendor, regardless of type. The `or` was ported from the
prototype. It is now resolved per model: **`C.4` in `sub-4`, `F.1` in `sup-1`.**

**Why.** The two codes mean different things in the two models, and the `or` was wrong in both
directions. In `sub-4`, `C.4` is ISO 9001 and `F.1` is the HSE policy — a knock-out criterion
unrelated to quality management — so a subcontractor with an HSE policy and no certificate
satisfied an ISO 9001 requirement. In `sup-1`, `F.1` is ISO 9001 while `C.4` is product
certificates and `C.3` is manufacturer authorisation. A criterion code is only meaningful
inside the model that defines it.

**Consequences.** Shortlists get shorter and truer. See ADR-011 for how the model is chosen
for a vendor of type `both`, and for the two model gaps this work exposed.

---

## ADR-011 — A required certificate is resolved against the model the vendor was scored with

**Status:** Accepted (phase 1, wave 2) · **Decided by:** orchestrator

Two rules, both in matching's certificate check:

1. **Which model.** The model is `vendor["model_version"]` — the one that actually produced
   the vendor's score — not an inference from `vendor_type`. This settles type `both`, which
   the type-based split could only guess at. The score and the certificate check must read the
   same rubric, or eligibility is being claimed against a model the vendor was never measured
   with.
2. **A certificate with no criterion is not held.** The former rule was "an unknown key
   passes". A required certificate that the vendor's model has no criterion for cannot be
   evidenced, so the vendor is not eligible and the gap text names the certificate.

**Why rule 2.** Passing a certificate nobody checked is the system claiming a verification
that never happened — the same class of error as the `C.4 or F.1` bug in ADR-009, and the
worse direction to fail in. A false negative is visible on the matching screen: the gap says
which certificate is missing and the manager can drop the requirement. A false positive
silently puts an unqualified vendor on a shortlist. Spec §12's claim for the intelligence
views is that they are honest about their own accuracy.

**Blast radius, checked before ruling.** In `seed/data.json` only TQS-238 pk3 (MEP) requires
`iso45001` and TQS-238 pk1 / TQS-301 pk1 require `iso9001` — all three are work packages. No
material package requires any certificate, so no supplier in the seed changes state.

**Two model gaps this exposed. Both recorded, neither fixed** — model versions are immutable
once an application has been scored with them (spec §10.3), and `sup-1` is marked "proposed"
until the commission freezes it (brief §1.3), so re-weighting either is the commission's
decision, not the build's:

* **`sup-1` has no ISO 45001 criterion at all.** Its `F.2` is "Defect / return record". Under
  rule 2 a supplier is therefore never eligible for a package requiring ISO 45001. That is the
  honest answer while the model has no such criterion; the alternative was crediting a clean
  returns record as a safety certificate.
* **`sub-4`'s `F.2` conflates ISO 14001 with ISO 45001** ("ISO 14001 / 45001", one rubric cell).
  A subcontractor holding only ISO 14001 registers as holding ISO 45001. `sub-4` is the frozen
  Rev4 model all 13 fixture vendors were scored with, so this is a limitation of the model, not
  of the engine.

Both go into `docs/REPORT.md` as known gaps for the commission.

---

## ADR-012 — Argon2id is the password algorithm, not the aspiration

**Status:** Accepted (phase 1, wave 2) · **Decided by:** orchestrator · **Amends** ADR-005

ADR-005 recorded that `argon2-cffi` could not be installed on the previous build host and that
`security/hashing.py` therefore degraded to PBKDF2-HMAC-SHA256. This environment reaches PyPI,
`uv sync` installs `argon2-cffi` 25.1.0, and every deployment and test now takes the Argon2id
path. The module's docstring said the opposite and its live branches were marked
`# pragma: no cover - not reachable on the build host`, which would have hidden the real
algorithm from the coverage report that brief §7.2 requires.

Fixing the two type errors this file carried also removed `except (VerifyMismatchError,
Exception)`. That clause caught everything, which hid a real defect: a stored string that is
not an argon2 hash raises `InvalidHashError`, a `ValueError` rather than an `Argon2Error`, so
the two rejection paths do not share a base class. Both now mean "does not verify" and are
caught by name; anything else propagates instead of being silently reported as a bad password.
`apps/api/tests/test_auth.py::test_verify_password_handles_a_missing_hash` is what caught it.

**Consequences.** PBKDF2 stays as the documented fallback for a host that cannot build the C
extension, and `verify_password` still reads both encodings, so moving between them re-hashes
on the next successful login rather than invalidating every password.

---

## ADR-013 — The rail is built from `Me.permissions`, never from a role table in the web app

**Status:** Accepted (phase 1, wave 2) · **Decided by:** orchestrator

Each rail item names the **operation id** that gates its screen; the rail shows the item when
`GET /api/auth/me` lists that id in `permissions`. `navSectionsFor(permissions)` replaces
`navSectionsForRole(role)`, and `docs/SCREENS.md` records the gating operation for all 34.

**Why.** Phase 1F shipped a hand-written role table in `navigation.ts`, sourced honestly from
the role prose in `docs/TEST_ACCOUNTS.md` — the worker flagged it as a judgment call and asked
for confirmation, which was the right instinct, because the table was a second copy of the
permission matrix and it had already drifted from the first. Checked against
`security/permissions.py` it was wrong in both directions: it hid `/market` and `/projects`
from officers and commission although `getIntelCoverage` and `listProjects` admit them, and it
showed `/integrations` to admin but not manager although `listAdapters` admits manager and not
commission. A rail that lies in the permissive direction is a support ticket ("the button does
nothing"); one that lies in the restrictive direction hides work a role is paid to do.

There is only one permission matrix and it is on the server. The frontend hides, the server
enforces — so the frontend must ask the server what to hide.

**A management screen is gated on the operation that *is* the management.** `/admin/categories`
is gated on `createCategory` (admin only), not on the `listCategories` every vendor may call to
populate a category picker. Gating an editing screen on its read operation is how a taxonomy
editor ends up in a vendor's rail.

**Contract change.** `Me.permissions` and `Me.auth_mode` were optional. They are now
`required`. An omitted `permissions` is indistinguishable from "may call nothing" and renders
an empty rail, and the dev banner keys off `auth_mode`; a client must never have to guess
either. Verified against a live manager session: 82 operation ids, all seven manager rail
gates present.

**Consequences.** An empty or absent `permissions` list yields an **empty rail**, never a
default — "we do not know what you may do" must not render as "all of it". Phase 2 tasks add
their own rail entries with the gating operation named: 2C adds `/cycles` (`listCycles`) and
2F the four `/admin/*` screens. They were left out of the rail here rather than added blind,
because a rail entry pointing at a route that does not exist yet does not type-check against
the router's registry.

---

## ADR-014 — `scoring_model` carries what the contract requires; `currency` and `total_max` stay out

**Status:** Accepted (phase 1, wave 2) · **Decided by:** orchestrator · Migration `0003`

The `scoring_model` table could not serve the contract's `ScoringModel`. Three fields the
contract lists as **required** had no column — `name_az` and `name_en`
(`ScoringModelSummary.required`) and `groups` (`ScoringModel.required`) — and the declared
`status` had none either. The phase-1E seed worked around it by putting `name_az` in a single
`name` column and the rest into the free-form `notes` JSONB, then flagged the gap instead of
filing a migration. That was the right call: migrations are the orchestrator's, and the
workaround would otherwise have become the design.

Migration `0003` renames `name` → `name_az`, adds `name_en` (backfilled from `name_az`, so the
`NOT NULL` lands without inventing a translation), adds `groups`, and adds `status` as a new
`scoring_model_status` enum.

**`status` is not `is_locked`.** `status` is the commission's editorial judgement — brief §1.3
requires the supplier model to read "proposed" until the commission freezes it. `is_locked` is
the mechanical fact that an application has been scored with the version, after which spec
§10.3 makes it immutable. A version can be locked and still proposed. With one column the two
could not both be said, and the supplier model's "proposed" label — a requirement, not a nicety
— had nowhere to live. It now reads `proposed` in the database.

**Deliberately not columns.** `currency`: ADR-007 fixes it at AZN and states that no conversion
exists anywhere in the code, so a column whose only legal value is `AZN` would advertise a
capability the system does not have. It is served as the constant it is. `total_max`: it is the
sum of the criteria maxima. Stored separately it can drift from them, and then two numbers both
claim to be the total — the failure mode the append-only observation model (ADR-004) exists to
avoid elsewhere.

**Consequences.** `notes` returns to what its docstring always said it was: a free-form note
about what changed between versions, not an overflow bucket. The phase-2D model editor can
create a version with a bilingual name, a status and its group headings without a schema change.
`alembic check` reports no drift; the migration was applied, rolled back and re-applied.

---

## ADR-015 — The dependency licence position, and why `fpdf2` is acceptable

**Status:** Accepted (phase 2) · **Decided by:** orchestrator

Task 2B added `fpdf2` (PDF commission summary), `openpyxl` (already transitive, now declared
directly) and `fonts-dejavu-core` to the API image. `fpdf2` is **LGPL-3.0-only**, the first
copyleft dependency anyone deliberately chose, so it was worth checking before accepting.

A sweep of all 75 installed distributions puts it in context:

| Licence | Packages |
|---|---|
| LGPL-3.0-only | **`psycopg`**, `psycopg-binary`, `fpdf2` |
| MPL-2.0 | `certifi`, `pathspec` |
| MIT / BSD / Apache-2.0 | everything else |

`psycopg` is the PostgreSQL driver, fixed by ADR-001 and unavoidable — psycopg2 and psycopg3
are both LGPL, and no permissive driver exists for this stack. **The project therefore already
carries LGPL-3.0 for the one component it cannot run without.** `fpdf2` adds no obligation that
was not already there.

All five are used as unmodified libraries, imported at runtime and installed from PyPI by the
resolver: exactly the use LGPL §4 and MPL §3.3 permit, and the recipient can replace any of
them (`uv remove fpdf2`) without touching VendorIQ's own code. Nothing here is statically
linked or vendored.

**The DejaVu font is not incidental.** PDF core fonts are Latin-1; Azerbaijani needs ə, ğ, ş,
ı, ö, ü, ç. Without an embedded Unicode font the commission summary — the sheet the commission
chair signs — renders vendor names wrongly in the language the document is written in.

**Consequences.** `docs/REPORT.md` states this position so the owner's counsel sees the whole
copyleft surface in one place rather than discovering `fpdf2` alone. Should the owner's policy
forbid LGPL outright, the conclusion is not "swap `fpdf2`" but "change the database driver",
which is an ADR-001 decision — and that is precisely why the position is recorded rather than
left implicit.

**Process note, not a decision.** Task 2B edited `apps/api/pyproject.toml`, `uv.lock` and
`infra/Dockerfile.api` — none of which it owns — instead of filing a change request as briefed.
The dependency itself is the right call and is kept; the rule stands, and the worker was told.

---

## ADR-016 — The post-prequalification change request is refused, not implemented

**Status:** Accepted (phase 2) · **Decided by:** orchestrator

Spec §7 says a vendor's profile edit after prequalification "creates a change request the
officer confirms". No contract operation, table or screen exists for that queue, and task 2A
correctly filed it as a change request instead of inventing one.

**Ruling: the refusal stays; the workflow is out of scope for this run.**

What already exists is the safe half, built in phase 1B: `services/vendors.py` refuses a
vendor's edit of a prequalified profile outright, with a message saying it goes through a
change request. The reason is in that module's own comment and it is the right one — silently
accepting the edit would let a prequalified vendor rewrite the basis of its own score after
the commission signed it.

What does not exist is the queue an officer works. Building it means a table, at least two
contract operations, and a screen — and `docs/SCREENS.md` has **34 screens, none of which is a
change-request queue**. The brief §4.2 screen inventory is the scope of this run; adding a
thirty-fifth screen on the strength of one clause is exactly the quiet widening the
orchestrator is supposed to refuse.

**Consequences.** A prequalified vendor that needs a correction contacts the officer, who has
`patchVendor` with a mandatory reason (spec §6.5) and writes a `manual` observation — the audit
trail the change-request queue would have produced, without the queue. The portal must say so
plainly rather than showing a dead control: a bare 409 tells the vendor "no" with no path.
This goes into `docs/REPORT.md` as a known gap with the shape the endpoint should take.

---

## ADR-017 — `is_locked` freezes a model's definition, not its use

**Status:** Accepted (phase 2) · **Decided by:** orchestrator · **Corrects** the task 2B brief

Task 2B was briefed to "refuse on a locked model version" when saving an evaluation. It
declined, implemented the refusal on `ScoringModelStatus.RETIRED` instead, and asked for
confirmation. **It was right and the brief was wrong.**

Spec §10.3 says "every model version is immutable once an application has been scored with
it". That is a statement about the model's **definition** — its criteria, thresholds, class
bands and pass mark — not about whether the model may still score anything. `is_locked` is set
the moment the first application is scored, so `sub-4` is locked from the seed onward. A
`putEvaluation` that refused on `is_locked` would refuse every evaluation in the system,
including the 13 real Rev4 applications the acceptance check is built on. The brief conflated
"frozen definition" with "unusable".

**The rule, in one line each:**

* `is_locked` gates **editing the model** — `patchScoringModelDraft` must refuse it. That is
  task 2D's operation, and it is where spec §10.3 actually bites: changing a weight creates a
  new version, it never rewrites a version an application was scored with.
* `status = retired` gates **scoring with the model** — a version the commission has taken out
  of service accepts no new evaluations, while every historic application keeps its own.

The two are orthogonal on purpose (ADR-014): a version can be locked and active, locked and
retired, or — briefly, as a draft — neither.

**Consequences.** Task 2D's brief carries the `is_locked` half explicitly, so the rule is
enforced in the one place it belongs rather than in the place the original brief guessed.
`services/evaluation.py` documents the distinction at the top of the module, and
`test_put_evaluation_refuses_a_retired_model_version` pins it.

---

## ADR-018 — The demo layer must produce a system that demonstrates something

**Status:** Accepted (phase 2) · **Decided by:** orchestrator

Task 2C was asked to run TQS-238 through its own endpoints and compare with spec §11.2, and
**to report a disagreement rather than adjust the engine or the seed to match the prose**. It
found one, traced it, and reported it. The finding is correct and it matters more than the
number.

**What it found.** On a database built by `make seed && make seed-demo`, matching returns
nothing at all: every package comes back `no_vendor_in_category` and the project is NO-GO at
0 % coverage. Two causes, both in the seed:

1. **All 29 demo category assignments are written `confirmed = false`.** A vendor is only a
   candidate for a package once an officer has confirmed its category. `seed/common.py`
   defaults to unconfirmed for a good reason on the real and import paths — nothing should
   silently confirm a judgement an officer is accountable for — but the demo layer is
   fabricated data whose entire purpose is to show the system working.
2. **The four demo suppliers never reach `prequalified`.** They get raw indicators and
   categories but no `Application`, so `Vendor.status` stays `registered`. `seed/data.json`
   declares `"status": "prequalified"` for two of them and **nothing consumes that field** — a
   field that is written and then ignored is worse than no field, because it reads as a fact.

**Why the discrepancy was invisible until now.** `packages/scoring/tests/test_matching.py`
asserts the spec's 96 % — but `_seed_candidates()` builds its candidates by reading
`row["status"] == "prequalified"` straight out of `seed/data.json`, never from the database.
It is a sound unit test of the engine and a **worthless** end-to-end claim, and its name and
spec reference made it read as the latter. The engine was right the whole time; the seed was
never checked against it.

**The arithmetic settles which number is correct.** TQS-238 totals 14.7 M, flooring is 0.6 M.
Only-flooring NO-GO gives 95.9 % → **96 %**, exactly spec §11.2. Flooring plus both material
packages gives **76 %**, exactly what 2C measured. So the spec is right and the seeded system
is incomplete — not the reverse.

**Ruling.** In the **demo layer only**, and removable by `make purge-demo` like everything else
in it:

* demo category assignments are created confirmed, because an unconfirmed demo assignment
  demonstrates nothing;
* the four demo suppliers are driven through qualification against `sup-1` so their status is
  earned rather than asserted, and `seed/data.json`'s `status` field is either consumed or
  deleted.

Real data is untouched: the 13 vendors keep the Rev4 outcomes they actually received.

**Consequences.** Brief §7.1 promises that a clean start serves the app "with seeded data";
three of the 34 screens were going to show an empty market on first run. After the fix the
live system must reproduce 96 % through the API — and that assertion belongs in
`test_projects.py` against the database, with the engine fixture relabelled as the
engine-level test it actually is.

## ADR-019 — A production stack starts with no users, so it needs a way to get its first one

**Context.** `AUTH_MODE=live` seeds nothing. That is right and was decided early:
`create_test_accounts` raises `TestModeRequiredError` outside test mode, precisely so a live
system can never quietly grow an `admin@vendoriq.test` whose password is printed in
`docs/TEST_ACCOUNTS.md`.

The consequence had not been followed through. A stack deployed with `--profile prod` comes up
with an empty `app_user` table, and **every** screen is behind a sign-in — including the one
that creates users. There is no first move. The system is not misconfigured, it is
unreachable, and nothing in the build would have shown this, because every test and every
development run is in test mode where the accounts are already there.

**Ruling.** `python -m vendoriq_api.seed create-admin --email … --name … [--role …]`, run once
from the API container by whoever deploys.

* The password is read from a prompt or from `VENDORIQ_ADMIN_PASSWORD`, never from a flag —
  a command line is readable by every process on the host through `ps`, and it lands in the
  deploying operator's shell history.
* It **refuses** an address that already exists rather than resetting its password. A command
  that silently takes over an existing account is a privilege-escalation tool for anybody who
  can reach the container, and the convenience is not worth it: the admin screens can change
  a password once somebody is in.
* The TOTP secret is generated here and printed once. It is not retrievable afterwards, which
  is a property of the design rather than an oversight, so the runbook says to enrol the
  authenticator before closing the terminal.
* `is_demo=False`, so `make purge-demo` does not delete the administrator — which is the sort
  of thing that only shows up the day somebody runs it.

**Consequences.** `docs/RUNBOOK.md` §3.4 is now a sequence that ends with someone logged in.
The alternative — documenting a manual `INSERT` with an Argon2 hash produced by hand — is not
a procedure anyone should follow at the end of a deployment.

## ADR-020 — The production overlay makes the development defaults impossible, not merely wrong

**Context.** `infra/docker-compose.yml` is written for a laptop: `APP_ENV` defaults to
development, `AUTH_MODE` to test, and every password to a word printed in this repository. In
test mode the API seeds the published accounts and reveals sign-in codes. A stack that reached
a public hostname still carrying those defaults would not be a misconfiguration to fix later;
it would be open on the first request.

Brief §7.1 asks for `--profile prod` "with Caddy TLS instructions in runbook". A runbook that
lists variables to set is exactly the artefact that gets half-followed at 2 a.m.

**Ruling.** `infra/docker-compose.prod.yml`, layered over the base file, replaces each unsafe
default with either a fixed production value (`APP_ENV: production`, `AUTH_MODE: live`,
`STORAGE_BACKEND: s3`) or the `${VAR:?…}` form, which makes `docker compose` refuse to render a
configuration at all while the variable is unset. The failure mode moves from *starts and is
insecure* to *does not start and names the variable*.

This pairs with the guard already in `config.py`: the overlay guarantees `APP_ENV=production`
reaches the container, and the container then refuses `AUTH_MODE=test` under it. Neither half
is sufficient alone — the guard never fires if `APP_ENV` is left at its default, which is
exactly what a forgotten `.env` produces.

**Verification.** `apps/api/tests/test_compose_profiles.py` renders the overlay with
`docker compose config` and asserts the result: production and live on `api` and `worker`,
Caddy the only service publishing a port, and a refusal when `SESSION_SECRET` is absent. The
YAML-level assertions run without a Docker CLI, so CI checks them too. This matters more than
usual: the guarantee is one careless `:-` away from evaporating, and nothing about the running
system would look any different afterwards.

**What is still unverified.** No Docker daemon exists on the build host (brief §9), so the
images have never been built and the stack has never been started. `docs/RUNBOOK.md` says so
in its first paragraph rather than in a footnote.

## ADR-021 — Two code namespaces share one alphabet, and the seed was writing into the wrong one

**Context.** Found by task 3A while cross-checking the vendor portal against the API, not by
any test — and this is the most serious defect in the build.

Spec Appendix A gives the application **form** 92 field codes. `sub-4` gives its 24 **scoring
criteria** codes drawn from the same alphabet. They are different questions:

| code | form (Appendix A) | criterion (`sub-4`) |
|---|---|---|
| `A.1` | Full legal name | Construction licence |
| `A.2` | Trade register number | Years in operation |
| `C.1` | ISO 9001 held? | Similar projects (5y) |
| `F.1` | HSE policy document? | HSE policy & plan |

The namespaces do not merely differ, they **cross**: `derive_raw` is the bridge between them
and maps form `C.1` onto criterion `C.4`. So no single code is a reliable clue about which
namespace a value belongs to.

`field_observation` holds the **form** namespace. The portal's autosave writes into it
(`services/answers.py`, keyed from `FIELD_CATALOG`), and every reader interprets it that way
— `derive_raw(current_profile, …)` in matching, in submission, in the vendor register.

The seed wrote the Rev4 workbook's **criterion-coded raw indicators** into it, for all 13 real
vendors and all 4 demo suppliers. At the time this was found, **all 404 observations in the
seeded database were criterion-coded and not one of the 92 form codes had ever been written.**

**What it actually did.** The vendor portal showed, for a real prequalified vendor,
"Full legal name: 3", "Trade register number: 11", "Year of registration: 3". And more quietly:
`derive_raw` went looking for form `A.11` ("construction licence held?") in a profile that had
no form codes at all, found nothing, and returned near-empty indicators — so every path that
falls back to the live profile silently reported almost nothing. No error, no wrong type, no
failing test. A namespace collision cannot announce itself.

**Ruling.**

1. `observations_service.record` **refuses** a code that is not in `FIELD_CATALOG`. This is
   the actual fix; everything else follows from it. A convention that two namespaces must not
   be confused is worth nothing when both are strings that look alike — it needs a check at
   the one place every write passes through.
2. The seed no longer writes `row["raw"]` as field observations. Nothing is lost: those
   values are stored unchanged as the application's `raw_snapshot`, which is where
   `services/evaluation.py`, `services/intel.py` and `services/matching.py` already prefer to
   read them.
3. `GET /vendors/{id}` now prefers that snapshot too. It was the one reader that always
   derived from the live profile, so with the profile correctly empty it would have reported a
   register full of zeroes for vendors whose real indicators were sitting on a decided
   application. The shared `applications_service.decided_application` replaces what had become
   four copies of the same query, one of which had drifted.

**Consequences.** The 13 real vendors now have **no form answers at all**, and that is the
truth: Uni Ko scored them from a spreadsheet and never collected an Appendix A form from any
of them. Brief §1.10 — "unknown real facts stay empty" — is the rule, and this is the case it
was written for. No score, class, total or coverage figure changes: every one of them is
computed from `raw_snapshot`, and the 13/13 Rev4 sheet match and TQS-238's 96 % both still
hold.

The cost is that the vendor form screens have nothing to show for a real vendor. The demo
layer answers that, per ADR-018 — a demo application filled with genuine, form-coded answers,
which is also the only data in the system that exercises `derive_raw` end to end.

**What let it live this long.** `docs/DECISIONS.md` ADR-008 already recorded the symptom —
"the Rev4 fixture does not confirm this, because `vendors_seed.json` bypasses `derive_raw`" —
and stopped there. The observation that the seed never goes through the bridge between the two
namespaces was the whole bug, written down and not followed.

## ADR-022 — Logging out withdraws the token, not just the browser's copy of it

**Context.** 3B, finding 3. The session cookie is a stateless HMAC signature carrying `sub`,
`role` and `exp`, and `POST /auth/logout` cleared cookies and nothing else. The comment in
`security/tokens.py` said so plainly: "the session is stateless so that a horizontally-scaled
deployment needs no shared session store, and revocation rides on `User.is_active`".

That reasoning is sound about scaling and wrong about revocation. Clearing a cookie makes the
*browser* forget the token; the token itself keeps verifying until `exp`, eight hours by
default. A copy captured beforehand — a shared machine, a session left open, anything that
read the cookie once — went on authenticating for the rest of that window. And
`User.is_active` is not a substitute: deactivating the account is not what a person asks for
when they click "Log out".

**Ruling.** A `jti` claim in the token, and a `revoked_session` table holding one row per
logout (migration `0005`).

* **Per token, not per user.** Keying on `user_id` would have been simpler and would have
  made every logout a global one. Users experience that as being mysteriously signed out of
  the desktop because they signed out of the phone. There is a test for it specifically, and
  it fails under exactly that "simplification".
* **The statelessness that mattered is kept.** Nothing is read to *establish* a session — the
  signature still does that alone. The database is consulted only to ask whether a particular
  session has been withdrawn early: one primary-key lookup against a table sized by
  concurrent sessions, not by logouts ever performed, since each row is deleted once its
  token would have expired anyway. A scaled deployment still needs no shared session store,
  because these rows are self-expiring rather than authoritative.
* **Logout cannot fail.** A missing, malformed, expired or already-revoked cookie revokes
  nothing and still returns 204. The endpoint requires no authentication, deliberately: a
  caller can only revoke a session they already hold the cookie for, and an endpoint that can
  refuse to log you out is worse than one that occasionally revokes nothing.
* Sessions minted before this change carry no `jti` and cannot be revoked individually.
  Clearing the cookie is all logout can do for them and they expire within the TTL.

**Consequences.** `is_active` keeps its meaning — it revokes every session a user has at once
— and logout revokes exactly one. Both are now true statements rather than one standing in
for the other.

## ADR-023 — Wesa's real application form is loaded, and it validates the whole bridge

**Context.** ADR-021 stopped the seed writing criterion-coded indicators into the form-answer
store and concluded: "the 13 real vendors now have no form answers at all, and that is the
truth: Uni Ko scored them from a spreadsheet and never collected an Appendix A form from any
of them."

**That conclusion was wrong for one vendor, and I should have checked before writing it.**
`seed/fixtures/` contains `98dfa150-WESA_Prekvalifikasiya_Muraciet_Formasi.xlsx` — Wesa's
filled-in application form. `packages/excel_import` has parsed it since phase 1 and
`test_form_wesa.py` asserts its contents in detail. The seed simply never loaded it.

**What loading it showed.** Wesa is the only vendor in the system where two independent
records describe the same company: its own form, and the Rev4 scoring sheet. Running the
first through `derive_raw` and comparing with the second is an end-to-end check of the entire
bridge — Appendix A codes in, criterion codes out — against real data. Nobody had run it.

| | form → `derive_raw` | Rev4 sheet |
|---|---|---|
| B.1 avg turnover | 5,189,111.38 | 5,189,111 |
| C.1 similar projects | 10 | 10 |
| C.2 largest project | 6,140,000 | 6,140,000 |
| C.3 ongoing | 2 | 2 |
| E.1 permanent staff | 80 | 80 |
| G.2 references | 8 | 8 |
| **E.2 engineers** | **8** | **10** |
| A.3, D.1–D.3, E.4, F.3 | *absent* | present |

Seventeen of eighteen agree to the manat. The six absent ones are exactly the judgement
criteria `derive.py` says the officer scores against evidence — so the map's own account of
itself is accurate too.

**E.2 is the one disagreement, and it is ADR-008's open question with data at last.** ADR-008
ruled that "engineers" sums `E.4`…`E.8` and excludes `E.9`, the technicians and foremen, and
recorded honestly that the Rev4 fixture could not confirm it because the seed never went
through `derive_raw`. It does now: the form's rows sum to **8**, the sheet says **10**, and no
single row explains the gap (`E.9` is 4, not 2). Uni Ko counted two engineers this system does
not. It is **score-neutral** — `E.2` scores identically at 8 and 10, so Wesa's 90.3 and its
class A are unaffected — and it is left as a recorded discrepancy rather than a rule to
re-derive, because a difference between two human records is exactly the thing this product
exists to surface.

**Ruling.** The real seed loads Wesa's form as field observations, source `excel`,
`source_ref` the workbook. Frozen to `seed/wesa_form.json` by `scripts/freeze-wesa-form.py`
(`make seed-form`) so the API image needs neither openpyxl nor a spreadsheet; a test re-parses
the workbook and refuses a stale copy. The seed still stores the *sheet's* `E.2`, because the
sheet is what the commission decided on.

**Consequences.** Wesa's application is 98.9 % complete, so the vendor portal demonstrates a
real filled form instead of an empty one — with real data, which is better than the demo
application ADR-021 proposed and better than fabricating answers for a vendor. The other
twelve keep empty forms, correctly. And ADR-021's sentence about all thirteen should be read
as it now stands: twelve were scored from a spreadsheet alone; the thirteenth was not.
