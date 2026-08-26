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
