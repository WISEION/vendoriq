# VendorIQ

Vendor management and market intelligence for construction tendering. It replaces the
Excel-based subcontractor prequalification cycle (the TQS2026006 workbooks) with a permanent,
queryable vendor base, and answers the question a tender actually poses: *can the market supply
these work packages, from whom, at what class of reliability, and with what gaps?*

Context: Uni Ko QSC commercial department, Baku. Interface Azerbaijani with an English toggle;
code and documentation English.

## Where things are

| Path | What it is |
|---|---|
| `docs/openapi.yaml` | **The contract.** Every endpoint the 34 screens need. Served at `/api/docs`. |
| `docs/SPEC.md` | The system design specification — behaviour is decided here. |
| `docs/BUILD_BRIEF.md` | The delivery plan, phases and acceptance criteria. |
| `docs/DECISIONS.md` | ADR log: why the system is shaped the way it is. |
| `docs/TEST_ACCOUNTS.md` | Seeded accounts and what `AUTH_MODE` does. |
| `docs/design/` | The approved prototype: reference scoring engine, i18n dictionaries, design tokens. |
| `apps/api/` | FastAPI backend, SQLAlchemy 2 models, Alembic migrations. |
| `apps/web/` | React 18 + Vite single-page app (manager dashboard and vendor portal). |
| `apps/worker/` | APScheduler jobs — expiry reminders, adapter pulls, stale-profile scan. |
| `packages/scoring/` | Pure-Python scoring and matching engine, plus the criteria JSON. |
| `packages/excel_import/` | openpyxl parsers for the 11-sheet form and the scoring workbook. |
| `infra/` | docker compose (dev and prod profiles), Dockerfiles, Caddyfile, `.env.example`. |
| `seed/` | Real and demo seed data, and the four Excel fixtures. |

## Run it locally

Prerequisites: Python 3.11, [uv](https://docs.astral.sh/uv/), Node 22, PostgreSQL 16 on
`localhost:5432`. Docker is optional.

```bash
make setup          # Python workspace + web dependencies
make db-up          # role vendoriq, databases vendoriq and vendoriq_test
make migrate        # apply migrations to both
cp infra/.env.example .env
make api            # http://localhost:8000/health · http://localhost:8000/api/docs
make web            # http://localhost:5173
```

`make help` lists every target. `CONTRIBUTING.md` has the full native setup, the branching rules
and the one rule that matters: **no contract change without the orchestrator**.

## Three things worth knowing before reading the code

1. **The scoring engine is a pure function and its rounding is load-bearing.** Group totals are
   rounded to one decimal *after every addition*, because that is what the workbook does. The
   acceptance test is all 13 Rev4 vendors reproducing their sheet total and decision exactly.
   See `packages/scoring/README.md`.
2. **There is no `vendor.turnover` column.** Every value is an append-only observation with a
   source and a timestamp, and the current value is the one from the highest-trust source
   (ADR-004). This is what makes "accurate and current" measurable instead of aspirational.
3. **The frontend holds no business logic.** Scoring, matching and eligibility live on the
   server; the evaluation screen recomputes by calling the API. An ESLint rule enforces it.

## Status

Phase 0 (contracts and skeleton) is complete: repository layout, database schema and migration
0001, the OpenAPI 3.1 contract, the engine interface and criteria data, the app shell, CI and
the infrastructure files. Business logic — scoring, importer, endpoints, screens — is phase 1
onward, per `docs/BUILD_BRIEF.md` §4.
