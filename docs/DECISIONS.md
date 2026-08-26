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
