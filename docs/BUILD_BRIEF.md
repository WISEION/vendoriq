# VendorIQ — One-Shot Build Brief

**Orchestrator:** Claude Fable · **Workers:** Claude Opus (architecture-critical), Claude Sonnet (well-specified implementation)
**Owner:** Gasimov (Zion Noiz) — operating context: "Uni Ko" QSC commercial department, construction tendering, Baku
**Outcome:** a deployable web application that replaces the Excel-based subcontractor prequalification cycle and grows into a vendor / market-intelligence platform. Built in one orchestrated run, verified, pushed to a GitHub repository, runnable with `docker compose up`.

---

## 0. Inputs the agents receive

| Artefact | What it is | Use |
|---|---|---|
| `VendorIQ_System_Design_Specification.docx` | 17-page system design (data model, workflows, both scoring models, matching rules, roadmap, field & document appendices) | Source of truth for behaviour |
| `dist.html` (prototype) | Working single-file prototype: vendor portal + manager dashboard, AZ/EN, Rev4 scoring engine in JS (`scoreSubcontractor`, `SUB_CRITERIA`, `SUP_CRITERIA`, `scoreGeneric`), matching engine (`matchPackage`, `matchProject`), i18n dictionaries, design tokens (CSS variables) | Port logic 1:1; reuse i18n strings and design tokens |
| `data.json` | Structured seed: 13 real vendors with raw indicators, WESA detail, form catalogue A–G, 38-document checklist, category taxonomy, 4 demo suppliers, 2 projects | Seed data + form definition |
| `vendors_seed.json` | Raw extraction from Rev4 sheet incl. `sheetTotal` / `sheetDecision` per vendor | Verification fixture (13/13 must match) |
| Wireframes canvas (34 artboards) | Every screen, in the prototype's colours | Screen inventory and layout |
| 4 Excel files | `Form Prekvalifikasiya_Muraciet_Formasi.xlsx` (blank 11-sheet application), `WESA …` (filled), `FORM Rev1 …` and `Rev4 Prekvalifikasiya TQS2026006.xlsx` (scoring workbooks) | Importer test fixtures; formula reference |

## 1. How the system works — facts established in the design session

1. **The Excel process is the ground truth.** Vendors receive an 11-sheet application (cover, instructions, sections A–G, document checklist with codes A-01…H-02, declaration), fill yellow cells, and return it with a ZIP of PDFs. Officers transcribe answers into the scoring workbook, verify documents, enter 0–3 rubric scores, and a summary sheet is signed by the commission chair and management.
2. **Scoring model Rev4 (sub-4)** — 7 groups, 24 criteria, 100 points. Rubric criteria: `round(score/3 × max, 1)`. Numeric criteria: threshold tables (turnover, equity, project counts/values, staff, engineers, references), bands (years), special curve for ongoing projects (0→25 %, ≤3→50 %, ≤6→100 %, >6→75 %). Knock-out: A.1 licence, A.4 tax clearance, F.1 HSE policy — raw value 0 ⇒ automatic reject. Pass 70. Classes: A 90+, B 80–89, C 70–79, D 60–69, F <60, KO. Group totals are rounded to one decimal after each addition (the workbook's behaviour). **The JS port in `dist.html` reproduces all 13 Rev4 totals and decisions exactly** — it is the reference implementation.
3. **Supplier model v1 (sup-1)** — proposal, same mechanics, re-weighted groups (Product & technical 25, Logistics 15 incl. inverse lead-time curve, Commercial 15). KO: registration, tax clearance, manufacturer authorisation/origin. Marked "proposed" in UI until the commission freezes it.
4. **Raw indicators are derived from the form**: B.1 = average of three annual turnovers; C.1 = count of completed projects table; C.2 = max project value; C.3 = count of ongoing table; E.1/E.2 from headcount rows; Yes/No answers on KO questions map to rubric 3/0 before officer review.
5. **Field provenance**: every value is an append-only *observation* (field code, value, source ∈ {registry, api, document, portal, excel, manual}, timestamp, actor). Current value = latest observation from highest-trust source. Freshness rules: financials 15 months, headcount 12, documents by expiry; A-05 tax clearance expires issue date + 3 months.
6. **Workflow states**: registered → invited → in_progress → submitted → under_review → (information_requested ⇄ under_review) → prequalified(A/B/C) | rejected(D/F/KO); suspended by manager. Prequalification valid 12 months. Submission freezes a raw-indicator snapshot.
7. **Matching**: per package — candidates = vendors with the category; eligible = prequalified ∧ KO pass ∧ class ≥ package minimum ∧ required certificates; capacity fit = largest completed project ≥ 40 % of package value (suppliers: turnover ÷ 4). Package GO if ≥2 A/B with capacity fit; CONDITIONAL if ≥1 eligible; NO-GO otherwise. Project GO if all GO; NO-GO if any NO-GO; else CONDITIONAL. Coverage = value share of non-NO-GO packages. All thresholds are settings.
8. **Market intelligence** = category × class matrix, capacity per category (turnover, engineers, vendor count), certification/insurance penetration among prequalified subcontractors, data-source split and stale-profile count, expiring documents (60 days), category gaps.
9. **Bilingual**: Azerbaijani default, English toggle; dictionaries exist in the prototype (`I18N.az`, `I18N.en`) and form/document catalogue carries AZ+EN labels.
10. **What is real vs. demo in the seed**: real = 13 vendors, their raw indicators, contacts, WESA detail, project "Gənclik Bahar Residence / TQS-238 / Uni Ko QSC / contact Əli Məmmədov", form & document catalogue. Demo (must be flagged `is_demo=true`, removable with one command) = category assignments of the 13 vendors, 4 suppliers, work-package breakdown, document expiry dates, activity feed, source labels.
11. **Known data quirks the importer must handle**: dates as text (`28.09.2020`) and as datetime; percentages as `0.95` and `85%`; multi-value cells (`1400915571 / 7200482051`); "Müddətsiz" (no expiry) in date fields; the methodology sheet says USD while data is AZN — the system stores AZN.

## 2. Fixed decisions (from the owner)

| Topic | Decision |
|---|---|
| Stack | **FastAPI (Python 3.12) + React 18/Vite/TypeScript + PostgreSQL 16 + MinIO**; SQLAlchemy 2 + Alembic; TanStack Query + Router; CSS variables from the prototype (no UI kit lock-in) |
| Scope | **Full: all 34 screens.** ERP connectors and government-registry checks are implemented as adapter interfaces with a working *generic REST/CSV* adapter and mocked 1C/SAP/Odoo adapters (same interface, fixture responses) |
| Deployment | **First run and all acceptance tests on localhost** (`docker compose` dev profile, `http://localhost`). Production profile for a VPS (`caddy` TLS) is prepared but deployed only after the owner's sign-off. Services: `api`, `web`, `db`, `minio`, `worker` (scheduled jobs). One `.env.example`. Code in a **GitHub monorepo** |
| Visual design | Owner and management approved the prototype's **dark "Blueprint" theme** as the baseline look. Final palette/element choice is made from the "VendorIQ Look & Feel" canvas before Phase 1F; tokens are copied from the chosen direction into `apps/web/src/theme/tokens.css`. Both light and dark themes ship regardless |
| Auth (pre-launch) | Vendors: e-mail + one-time code; staff: login/password + TOTP 2FA. **Until official launch: seeded test accounts, OTP/TOTP shown in server log and in a dev banner when `AUTH_MODE=test`.** Switching to `AUTH_MODE=live` enables real e-mail delivery and hides codes. SSO is an adapter stub |
| Language of code & docs | English identifiers, comments, docs; UI AZ/EN |
| Seed | Real data from Excel + demo layer flagged `is_demo` (`make seed`, `make seed-demo`, `make purge-demo`) |
| E-mail / files | SMTP from `.env`, fallback to log; MinIO (S3 API) for documents |
| Delivery | GitHub repo, CI green (lint, type-check, unit + integration + e2e), Playwright screenshots of all 34 screens in both languages attached to the final report |
| Future integrations | **API-first**: every UI action goes through the public REST API; OpenAPI 3.1 published; API keys with scopes for other products; outbound **webhooks** on domain events; event log table; stable IDs (UUID) and `external_ref` on vendor/project for cross-system mapping; no business logic in the frontend |

## 3. Repository layout

```
vendoriq/
  apps/api/            FastAPI: app/{core,auth,vendors,applications,scoring,matching,intel,imports,integrations,admin,notifications,events}
  apps/web/            React: src/{app,features/{auth,vendor,manager,admin},components,i18n,api(generated client),theme}
  apps/worker/         scheduled jobs (expiry reminders, adapter pulls, stale-profile scan)
  packages/scoring/    pure-Python scoring + matching engine (no framework deps) + fixtures
  packages/excel-import/  openpyxl parser for the 11-sheet form and the scoring workbook
  infra/               docker-compose.yml, Caddyfile, .env.example, backup script
  seed/                data.json, vendors_seed.json, Excel fixtures, seed CLI
  docs/                OpenAPI export, ADRs, runbook, integration guide (API keys, webhooks)
  .github/workflows/   ci.yml (lint, mypy, pytest, vitest, playwright, docker build)
```

## 4. Orchestration plan

### 4.1 Roles
- **Fable (orchestrator)** — owns the plan, contracts and gates. Writes the OpenAPI contract and DB schema first, assigns work, reviews every merge against acceptance criteria, resolves conflicts, runs the final verification, writes the report. Never implements feature code itself except contract files.
- **Opus workers** — architecture-critical, ambiguity-heavy: scoring/matching engine port + verification, Excel importer, data model & migrations, auth & permissions, integration layer (adapters, webhooks, API keys), final QA sweep.
- **Sonnet workers** — well-specified, high-volume: React screens from wireframes, CRUD endpoints against the contract, i18n wiring, seed CLI, Playwright e2e, docs, CI, Docker.

### 4.2 Phases and gates (sequential gates, parallel work inside a phase)

**Phase 0 — Contracts (Fable, ~1 agent-hour)**
Outputs: `docs/openapi.yaml` (all endpoints, schemas, error envelope), `apps/api/alembic/versions/0001_init.py` (schema from spec §5), `packages/scoring/README.md` (function signatures), design tokens file `apps/web/src/theme/tokens.css` copied from prototype, repo skeleton, CI skeleton, `CONTRIBUTING.md` (branch naming, commit rules, "no contract change without orchestrator").
Gate 0: repo builds empty; CI green; OpenAPI validates.

**Phase 1 — Core (parallel)**
| Task | Worker | Depends on | Acceptance |
|---|---|---|---|
| 1A Scoring & matching engine (Python) | Opus | 0 | `pytest` fixture: all 13 Rev4 vendors match `sheetTotal`/`sheetDecision`; supplier model tests; matching rules tests; property tests for rounding |
| 1B Data model, repositories, observations, audit | Opus | 0 | migrations apply/rollback; observation "current value" resolver tested; audit written on every mutation |
| 1C Auth: OTP, password+TOTP, roles, permissions, `AUTH_MODE=test` | Opus | 1B | permission matrix tests (spec §3); test accounts seeded |
| 1D Excel importer (application form + scoring workbook) | Opus | 1B | imports blank form (0 answers), WESA form (all fields + warnings listed in §1.11), Rev4 workbook (13 vendors) — exact expected JSON fixtures |
| 1E Seed CLI (real + demo, purge-demo) | Sonnet | 1B, 1D | `make seed` idempotent; `is_demo` rows removable |
| 1F Web app shell: routing, layout (rail/topbar), i18n, theme, API client generation, auth screens (3) | Sonnet | 0 | Storybook-free; screens match wireframes; AZ/EN toggle persists |
Gate 1: engine 13/13; importer fixtures pass; login works for all test accounts; CI green.

**Phase 2 — Features (parallel, contract-driven)**
| Task | Worker | Screens |
|---|---|---|
| 2A Vendor portal API + UI | Sonnet ×2 | Status, Profile, Form A–G (7), Documents (38 items, upload to MinIO, expiry auto-rules), Declaration & submit (pre-submission check, snapshot) |
| 2B Manager: vendors & applications | Sonnet | Overview, Vendor register (filters/export), Vendor detail, Applications queue, Evaluation (live scoring via API), Commission summary (Excel export in the layout of sheet "5. Nəticə Xülasəsi", PDF) |
| 2C Manager: cycles, projects, matching | Sonnet | Cycles & invitations, Projects list, Project create/edit (packages), Project matching & go/no-go |
| 2D Market intelligence + scoring models | Sonnet | Market intelligence, Scoring models, Model editor (versioning, re-score test, publish) |
| 2E Integration layer | Opus | Data sources, Excel import result (mapping preview → write), ERP connector config; adapter interface; generic REST/CSV adapter; mocked 1C/SAP/Odoo; registry-check stub; API keys with scopes; webhooks (vendor.prequalified, application.submitted, document.expiring, project.matched); event log; `docs/integration-guide.md` |
| 2F Admin | Sonnet | Categories, Users & roles, Settings (matching thresholds, validity, notifications, org/lang), Audit log |
| 2G Worker jobs + notifications | Sonnet | expiry reminders (30/7 days), stale-profile scan, adapter schedule, e-mail templates AZ/EN, SMTP/log switch |
Gate 2: every screen reachable; every endpoint covered by at least one integration test; no frontend business logic (lint rule: scoring/matching imports forbidden in `apps/web`).

**Phase 3 — Verification & hardening**
| Task | Worker |
|---|---|
| 3A Playwright e2e: full vendor journey (register → form → docs → submit) and manager journey (import WESA → evaluate → approve → project matching → export), both languages; screenshots of all 34 screens ×2 languages | Sonnet |
| 3B Adversarial review: security (authz per role, signed URLs, rate limits on OTP, file type validation), data integrity (snapshot immutability, model version immutability), i18n completeness (no untranslated keys) | Opus |
| 3C Docker Compose prod profile, Caddy TLS, backup/restore script, runbook | Sonnet |
| 3D Final report: what was built, deviations, known gaps, how to run, test accounts | Fable |
Gate 3: CI green on `main`; `docker compose --profile prod up` serves the app; report delivered.

### 4.3 Orchestrator rules
- Contract first: workers may not change `openapi.yaml` or migrations; they file a change request to Fable.
- One worker per directory at a time; merges via PR into `main` after Fable's review against the acceptance column.
- Every worker returns: files changed, tests added, how to verify, open questions. Fable answers questions from this brief, the spec, or the prototype before inventing anything; unresolved ambiguities go to `docs/DECISIONS.md` with the chosen default.
- Use the prototype as the reference for any UI or logic question not answered by the spec.
- No placeholder ("lorem", "TODO") in shipped UI; unknown real facts stay as empty fields, not invented values.

## 5. Functional requirements by module (condensed; spec §5–§12 is authoritative)

**Vendors** — CRUD, VÖEN unique (10 digits), type sub/sup/both, categories (two taxonomies), contacts, status machine, `external_ref`, `is_demo`. Register supports filter by type/category/class/status/region, search by name/VÖEN, Excel export.

**Applications** — cycle-bound; answers stored by field code (JSONB) with tables as arrays; derived raw indicators computed server-side; rubric scores 0–3 with evidence document code; per-criterion points, group totals, total, KO, class computed by `packages/scoring`; decisions with justification; second-evaluator optional; snapshot on submit; commission summary export.

**Documents** — codes A-01…H-02 from catalogue; PDF only; statuses uploaded/in_preparation/not_applicable/missing; issue/expiry; A-05 auto-expiry +3 months; signed download URLs; reminders.

**Scoring models** — versioned (`sub-4`, `sup-1` seeded); immutable once used; editor creates new version; re-score test against a cycle; class bands & pass mark per version.

**Projects & matching** — projects with packages (category, value, min class, certs); matching per rules §1.7; results persisted per run; recommendation text; export.

**Market intelligence** — endpoints returning the six views; computed from current observations; freshness metrics.

**Integrations** — adapter interface `pull(vendor, since) -> Observation[]`; adapters: generic REST/CSV (working), 1C/SAP/Odoo (mocked, same interface), registry checks (stub returning "not configured"); Excel importer as an adapter too; sync log; API keys (scoped read/write per module); webhooks with HMAC signature and retry; event log.

**Admin** — categories, users & roles (matrix from spec §3), settings (all thresholds), audit log with export.

**Auth** — roles: vendor, officer, commission, manager, admin. `AUTH_MODE=test|live`. Session cookies (httpOnly) + CSRF; API keys for machines.

**i18n** — AZ default, EN toggle; all strings in `apps/web/src/i18n/{az,en}.json` seeded from the prototype's dictionaries; server messages and e-mails bilingual.

## 6. Test accounts (seeded when `AUTH_MODE=test`)

| Role | Login | Password | 2FA/OTP |
|---|---|---|---|
| Admin | admin@vendoriq.test | Admin!2026 | TOTP secret printed at seed; code also shown in dev banner |
| Manager | manager@vendoriq.test | Manager!2026 | same |
| Commission | commission@vendoriq.test | Commission!2026 | same |
| Officer | officer@vendoriq.test | Officer!2026 | same |
| Vendor (Wesa) | habib.atakisiyev@wesa.az | — | OTP `000000` accepted in test mode |
| Vendor (Shield) | a.tabit@shield.az | — | same |
| Vendor (new, empty) | vendor.new@vendoriq.test | — | same |

Test mode must be impossible to leave on by accident: the app refuses to start with `AUTH_MODE=test` when `APP_ENV=production`.

## 7. Definition of done (checked by Fable, evidence in the final report)

1. `docker compose up` from a clean clone → app on `http://localhost` with seeded data; `--profile prod` with Caddy TLS instructions in runbook.
2. `pytest`: scoring fixture 13/13 Rev4 match; importer fixtures; matching rules; permissions matrix. Coverage ≥ 80 % on `packages/*` and `apps/api/app/{scoring,matching,imports,auth}`.
3. Playwright: both journeys pass; 68 screenshots (34 screens × AZ/EN) committed under `docs/screens/`.
4. OpenAPI served at `/api/docs`; `docs/integration-guide.md` explains API keys, webhooks, event log, `external_ref`, and how a future product subscribes.
5. No business logic in the frontend (lint rule enforced); no untranslated keys (i18n test).
6. `make purge-demo` leaves only real data; `make seed` is idempotent.
7. CI green on `main`; repository pushed; final report with deviations and known gaps.

## 8. Explicit non-goals for this run
Real 1C/SAP/Odoo connectivity, real registry APIs, SSO, WhatsApp channel, e-tendering/bid pricing, mobile apps. Each has an interface or stub so it can be added without refactoring.

## 9. Environment notes for this run (added by orchestrator)

- Build host: Linux sandbox. **No Docker daemon available** — write `infra/docker-compose.yml` and Dockerfiles, but run and test natively: PostgreSQL 16 is installed and running on `localhost:5432` (create role/db with `su postgres -c "psql -c ..."`), Python 3.11 (`uv` and `poetry` available), Node 22, Playwright + Chromium preinstalled (`PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`, do not run `playwright install`).
- Target Python version is therefore **3.11** (not 3.12).
- npm registry enforces a security policy: some packages return 403 (seen: `skills`, `@clack/prompts`). If an install fails with 403, pick an alternative package rather than retrying.
- Object storage: MinIO cannot run here; implement a storage interface with two backends — `local` (filesystem, used in tests and dev) and `s3` (boto3, used with MinIO in compose).
- Design tokens are final: `docs/design/tokens.css` (decision "A + D"). Copy verbatim into `apps/web/src/theme/tokens.css`.
- Reference material lives in `docs/`: `SPEC.md` (spec), `design/prototype.html` + `design/scoring.js` + `design/app.js` (reference logic and i18n), `skills/*` (React best practices, composition patterns, web design guidelines — read before writing frontend code). Seeds and Excel fixtures in `seed/`.
- GitHub is not reachable for pushing from this host; commit locally on `main`; the orchestrator delivers the repository as an archive.
