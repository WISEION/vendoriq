# VendorIQ — progress log (orchestrator)

Updated: 2026-08-26 · branch `claude/vendoriq-orchestration-7ls8e6`

## Gate 1 — PASSED

Evidence, all re-run by the orchestrator rather than taken from worker reports:

| Criterion (brief §4.2) | Evidence |
|---|---|
| `make test` green | `701 passed` — three consecutive full runs, no flakiness |
| Login works for every account in `docs/TEST_ACCOUNTS.md` | 10/10 auth paths on a database dropped and rebuilt from scratch, after `make seed` → `make seed-demo` → `make purge-demo`. Staff password+TOTP ×4, vendor OTP ×3 with both a fresh code and `000000` |
| Engine 13/13 | Rev4 fixture unchanged through ADR-008 and ADR-011 |
| Lint / types | `ruff check`, `ruff format --check`, `mypy .` (120 files) all clean |
| Coverage | 94.42%, floor of 80% now enforced in CI (`--cov-fail-under=80`) |

## Environment — resolved

npm and PyPI are reachable in this environment, which unblocks everything the previous run
could not do. `uv.lock` and `apps/web/package-lock.json` are committed. `argon2-cffi` installs,
so passwords are Argon2id rather than the PBKDF2 fallback (ADR-012). Postgres 16 local, both
databases migrated to `0003`.

**GitHub push is blocked** — `403: Claude doesn't have GitHub access to WISEION/vendoriq for
your organization`. Not transient, not fixable from here: it needs the Claude GitHub App
installed for the organisation. Commits accumulate locally on the branch; `BUILD_BRIEF` §9's
documented fallback (deliver the repository as an archive) applies until that is done.

## Done and verified

| Phase | Item | Evidence |
|---|---|---|
| 0 | Skeleton, Makefile, CI, ADR-001…007, test accounts | commit `5e0a5d9` |
| 0 | Schema, Alembic `0001`+`0002`, OpenAPI 3.1 (75 paths / 103 ops) | `alembic check` clean |
| 1A | `packages/scoring` — score, derive_raw, matching, CLI | 235 passed; Rev4 13/13 |
| 1D | `packages/excel_import` — form + workbook parsers | fixtures pass |
| 1B+1C | `apps/api` — data layer, observations, auth, permissions, audit, events | 42 of 103 operations live |
| 1E | Seed CLI — `load --real`, `load --demo`, `purge-demo` | idempotent; 68 demo rows removed; 13 Rev4 totals re-verified on load |
| 1F | Web shell, generated TS client, three auth screens | typecheck / eslint / vitest 17 / build clean |

## Rulings made in wave 2 (all in `docs/DECISIONS.md`)

- **ADR-008** `E.2` engineers = E.4…E.8; E.9 is technicians and foremen. The Rev4 fixture does
  **not** confirm this — `vendors_seed.json` bypasses `derive_raw` — the form's own labels do.
- **ADR-009** ISO 9001 read per model: `C.4` in `sub-4`, `F.1` in `sup-1`. The previous
  `C.4 or F.1` let a subcontractor satisfy ISO 9001 with an HSE policy.
- **ADR-010** `docs/SCREENS.md` fixes the address of all 34 screens.
- **ADR-011** A certificate resolves against the model the vendor was scored with; one with no
  criterion in that model is **not held**.
- **ADR-012** Argon2id is the password algorithm, not the aspiration.
- **ADR-013** The rail is built from `Me.permissions`, never a role table in the web app.
- **ADR-014** `scoring_model` gains `name_az`/`name_en`/`status`/`groups` (migration `0003`);
  `currency` and `total_max` stay out on purpose.

## Known gaps carried into `docs/REPORT.md`

- `sup-1` has **no ISO 45001 criterion**; under ADR-011 a supplier is never eligible for a
  package requiring it. Adding one is the commission's call — published models are immutable.
- `sub-4`'s `F.2` conflates ISO 14001 with ISO 45001, so a vendor holding only 14001 registers
  as holding 45001. `sub-4` is the frozen Rev4 model; a limitation of the model, not the engine.

## Next — phase 2

Seven tasks, disjoint file sets, `docs/SCREENS.md` fixes every route. 61 of 103 contract
operations remain. Shared files (`main.py`, `routers/__init__.py`, `navigation.ts`,
`routes.tsx`, the i18n dictionaries, migrations) are the orchestrator's — workers file change
requests rather than edit them.
