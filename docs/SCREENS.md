# The 34 screens — route map and screenshot inventory

**Status:** contract artefact, owned by the orchestrator. A worker may not rename a route or a
slug; it files a change request. Adding a *nested* view under a screen's own route is free.

Why this file exists: `docs/BUILD_BRIEF.md` §4.2 counts the screens per phase-2 task and
`docs/SPEC.md` §7–§8 describes their content, but neither fixes an address. Seven workers
building in parallel would otherwise produce seven URL conventions, and the phase-3 Playwright
run — which must land exactly 68 files in `docs/screens/` — would have nothing stable to aim at.

Conventions: TanStack Router paths, `$param` for a path parameter. The screenshot file is
`docs/screens/<slug>.<lang>.png`, `lang ∈ {az, en}`, giving 34 × 2 = 68 files.

## Authentication — public, outside the shell (task 1F)

| # | Slug | Route | Content |
|---|---|---|---|
| 1 | `auth-vendor-signin` | `/login` | E-mail → one-time code, two steps on one screen |
| 2 | `auth-staff-signin` | `/login/staff` | E-mail + password → TOTP, via `challenge_id` |
| 3 | `auth-vendor-register` | `/register` | Self-registration, fields per contract `VendorRegistration` |

## Vendor portal (task 2A) — spec §7

| # | Slug | Route | Content |
|---|---|---|---|
| 4 | `vendor-status` | `/portal` | Stepper, result + class once released, validity, next steps |
| 5 | `vendor-profile` | `/portal/profile` | A.1–A.10, contacts, legal form, categories, bank details |
| 6 | `vendor-form-a` | `/portal/application/A` | Section A — company profile |
| 7 | `vendor-form-b` | `/portal/application/B` | Section B — financial standing |
| 8 | `vendor-form-c` | `/portal/application/C` | Section C — technical experience (+ project tables) |
| 9 | `vendor-form-d` | `/portal/application/D` | Section D — facilities & equipment |
| 10 | `vendor-form-e` | `/portal/application/E` | Section E — human resources |
| 11 | `vendor-form-f` | `/portal/application/F` | Section F — HSE & quality |
| 12 | `vendor-form-g` | `/portal/application/G` | Section G — insurance & references |
| 13 | `vendor-documents` | `/portal/documents` | 38-item checklist, upload, expiry |
| 14 | `vendor-submit` | `/portal/submit` | Declaration, pre-submission check, submit |

`/portal/application` redirects to `/portal/application/A`.

## Manager — vendors & applications (task 2B) — spec §8

| # | Slug | Route | Content |
|---|---|---|---|
| 15 | `manager-overview` | `/` | KPI tiles, coverage, class distribution, attention list, activity |
| 16 | `vendor-register` | `/vendors` | Filterable table, search, Excel export |
| 17 | `vendor-detail` | `/vendors/$vendorId` | Profile, scorecard, history, documents, evaluations |
| 18 | `applications-queue` | `/applications` | Queue by cycle and status |
| 19 | `evaluation` | `/applications/$applicationId` | Per-criterion raw value, evidence, 0–3 rubric, live totals |
| 20 | `commission-summary` | `/applications/$applicationId/summary` | Sheet "5. Nəticə Xülasəsi" layout, xlsx + pdf export |

## Manager — cycles, projects, matching (task 2C) — spec §11

| # | Slug | Route | Content |
|---|---|---|---|
| 21 | `cycles` | `/cycles` | Cycles and invitations |
| 22 | `projects-list` | `/projects` | Value, package count, coverage %, go/no-go pill |
| 23 | `project-edit` | `/projects/$projectId/edit` | Project and its work packages; `/projects/new` creates |
| 24 | `project-matching` | `/projects/$projectId` | Per package: candidates, capacity fit, gaps, recommendation |

## Market intelligence and scoring models (task 2D) — spec §10, §12

| # | Slug | Route | Content |
|---|---|---|---|
| 25 | `market-intelligence` | `/market` | Coverage matrix, capacity, penetration, sources, expiry, gaps |
| 26 | `scoring-models` | `/scoring-models` | Version list, vendor type, state |
| 27 | `model-editor` | `/scoring-models/$version` | Criteria, bands, re-score test, publish |

## Integration layer (task 2E) — spec §6

| # | Slug | Route | Content |
|---|---|---|---|
| 28 | `data-sources` | `/integrations` | Adapters with status/record count/last sync; API keys, webhooks, event log as tabs |
| 29 | `excel-import` | `/integrations/excel-import` | Upload → mapping preview + anomaly warnings → write |
| 30 | `erp-connector` | `/integrations/adapters/$adapter` | Per-vendor connector configuration |

## Administration (task 2F) — spec §3, §13

| # | Slug | Route | Content |
|---|---|---|---|
| 31 | `admin-categories` | `/admin/categories` | Both taxonomies, AZ/EN names, parent |
| 32 | `admin-users` | `/admin/users` | Users, roles, the matrix from spec §3 |
| 33 | `admin-settings` | `/admin/settings` | Matching thresholds, validity, notifications, org/language |
| 34 | `admin-audit` | `/admin/audit` | Immutable log with Excel export |

## Rail and the gating operation

`apps/web/src/app/navigation.ts` carries the rail. Screens 17, 19, 20, 23, 24, 27, 29 and 30 are
reached from their parent screen and have no rail entry of their own; every other screen does.

Visibility is **not** a role table in the web app. Each rail item names the contract operation id
that gates its screen, and `navSectionsFor(permissions)` shows the item when `GET /api/auth/me`
lists that id (ADR-013). A management screen is gated on the operation that *is* the management,
not on a read operation a wider audience may call.

| Screen | Gated by | Who that admits today |
|---|---|---|
| `manager-overview` | `getIntelOverview` | officer, commission, manager, admin |
| `vendor-register` | `listVendors` | all staff |
| `applications-queue` | `listApplications` | all staff |
| `cycles` | `listCycles` | all staff — rail entry added by task 2C |
| `projects-list` | `listProjects` | all staff |
| `market-intelligence` | `getIntelCoverage` | all staff |
| `scoring-models` | `listScoringModels` | all staff |
| `data-sources` | `listAdapters` | officer, manager, admin |
| `admin-categories` | `createCategory` | admin — rail entry added by task 2F |
| `admin-users` | `listUsers` | admin — rail entry added by task 2F |
| `admin-settings` | `putSettings` | manager, admin — rail entry added by task 2F |
| `admin-audit` | `listAuditEvents` | manager, admin — rail entry added by task 2F |

Vendor rail: `vendor-status` → `listApplications`, `vendor-profile` → `getVendor`,
`vendor-form-*` → `getApplication`, `vendor-documents` → `listDocuments`, `vendor-submit` →
`submitApplication`.

"Who that admits today" is derived from `apps/api/vendoriq_api/security/permissions.py` and is
documentation, not a second source of truth — when the matrix changes, the rail follows it
without an edit here.
