# Contributing to VendorIQ

Read this before the first commit. It is short because only a few rules matter.

## The one rule: no contract change without the orchestrator

Three files are **contracts**. They are written and changed by the orchestrator (Fable) only:

| File | What it fixes |
|---|---|
| `docs/openapi.yaml` | Every endpoint, payload, error code and pagination shape |
| `apps/api/alembic/versions/*` and `apps/api/vendoriq_api/models/*` | The database schema |
| `packages/scoring/vendoriq_scoring/models/*.json` | The scoring criteria, weights, thresholds and KO flags |

If your task cannot be done without changing one of them, **stop and file a change request**:
open an issue titled `contract: <what and why>` describing the endpoint or column you need, what
you tried, and what breaks without it. Do not "just add a field" — the frontend, the importer,
the engine and any external consumer are all written against these files, and a silent change
turns into four silent breakages.

Two rules follow from this:

* **Never** run `alembic revision --autogenerate` and commit the result on a feature branch. A
  migration arrives with the contract change that motivated it.
* **Never** edit a published scoring model version. Weights change by creating a **new version**
  through the model editor (spec §10.3); applications already scored keep theirs.

## Branching

```
main                     always green, always deployable
feat/<area>-<slug>       new behaviour        feat/vendors-register-filters
fix/<area>-<slug>        bug fix              fix/scoring-rounding-boundary
chore/<slug>             tooling, deps, docs  chore/ci-playwright-cache
contract/<slug>          orchestrator only    contract/add-second-evaluator
```

`<area>` is the directory you work in: `api`, `web`, `worker`, `scoring`, `excel`, `infra`, `docs`.

**One worker per directory at a time.** Merges go into `main` through a pull request that the
orchestrator reviews against the acceptance criteria in the build brief. No direct pushes to
`main`.

## Commits

Conventional Commits, imperative mood, English:

```
feat(vendors): filter the register by category and class
fix(scoring): round group totals after every addition, not once at the end
test(excel): assert the WESA fixture reports the A.16 stale-certificate warning
chore(ci): run pytest against a postgres service
docs(adr): record the storage backend decision
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`, `build`, `ci`.
The body explains **why**, not what — the diff already says what. Reference the brief or spec
section when a rule comes from there (`spec §11.1`, `brief §1.4`).

A pull request answers four questions, and the description is expected to contain them: files
changed, tests added, how to verify, open questions.

## Definition of done for a task

1. `make lint` and `make test` pass locally.
2. New behaviour has a test that fails without the change.
3. No business logic in `apps/web` — scoring, matching and eligibility are server-side. The
   ESLint rule in `apps/web/eslint.config.js` blocks the import; do not disable it.
4. No placeholder text in shipped UI. An unknown real value stays an empty field; it is never
   invented, and it is never "TODO" or "lorem".
5. Every user-facing string exists in **both** `apps/web/src/i18n/az.json` and `en.json`. The
   i18n test fails when they drift.
6. Every mutation writes an audit event.

## Running locally, natively, without Docker

Docker is optional. Everything below runs on the host.

**Prerequisites:** Python 3.11, [uv](https://docs.astral.sh/uv/), Node 22, PostgreSQL 16
running on `localhost:5432`.

```bash
# 1. Dependencies (Python workspace + web packages)
make setup

# 2. Database: creates the vendoriq role and the vendoriq / vendoriq_test databases
make db-up
make migrate

# 3. Environment
cp infra/.env.example .env      # the defaults are already correct for a local run

# 4. Seed data — real rows, then the removable demo layer
make seed
make seed-demo                  # make purge-demo takes it back out

# 5. Two processes, two terminals
make api                        # http://localhost:8000/health · /api/docs
make web                        # http://localhost:5173
make worker                     # optional: the scheduled jobs
```

The web dev server proxies `/api` to the API process, so the browser sees one origin and the
session cookie works exactly as it does behind Caddy in production.

**Tests.**

```bash
make test          # pytest (against vendoriq_test) + vitest
make e2e           # Playwright, needs make api and make web running
make lint          # ruff, mypy, eslint, tsc
make openapi-validate
```

**If `make db-up` cannot reach PostgreSQL**, create the role and databases by hand:

```bash
sudo -u postgres psql -c "CREATE ROLE vendoriq LOGIN PASSWORD 'vendoriq' CREATEDB"
sudo -u postgres psql -c "CREATE DATABASE vendoriq OWNER vendoriq"
sudo -u postgres psql -c "CREATE DATABASE vendoriq_test OWNER vendoriq"
```

**Docker**, when you want it, is `docker compose -f infra/docker-compose.yml --profile dev up`
after copying `infra/.env.example` to `infra/.env`.

## Code style

* **Python** — ruff (lint + format, 100 columns) and mypy in strict mode. Type every signature;
  `Any` needs a comment saying why. Comments explain intent and the non-obvious, never the
  syntax.
* **TypeScript** — ESLint + Prettier, `strict` with `noUncheckedIndexedAccess`. Prefer
  composition over configuration flags; see `docs/skills/composition-patterns`.
* **Identifiers, comments and docs are English.** The UI is Azerbaijani and English — that
  distinction is deliberate and permanent.
* **SQL** — no raw SQL in route handlers; repositories own the queries.

## Where things live

```
apps/api/          FastAPI: routers, repositories, services, alembic
apps/web/          React SPA: app shell, features, i18n, theme, generated API client
apps/worker/       APScheduler jobs; imports vendoriq_api, never duplicates its rules
packages/scoring/  Pure-Python scoring + matching engine and the criteria JSON
packages/excel_import/  openpyxl parsers for the 11-sheet form and the scoring workbook
infra/             compose, Dockerfiles, Caddyfile, .env.example
seed/              real and demo seed data, Excel fixtures
docs/              the contract, ADRs, spec, test accounts, screens
```
