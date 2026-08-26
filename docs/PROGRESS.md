# VendorIQ — progress log (orchestrator)

Updated: 2026-08-26 · branch `main`

## Done and verified
| Phase | Item | Evidence |
|---|---|---|
| 0 | Monorepo skeleton, Makefile, CI, CONTRIBUTING, ADR-001…007, test accounts doc | commit 5e0a5d9 |
| 0 | Postgres schema: 21 entities, Alembic 0001 (+0002 Evaluation table) | `alembic check` clean on vendoriq / vendoriq_test |
| 0 | OpenAPI 3.1 contract `docs/openapi.yaml` — 75 paths / 103 ops / 117 schemas | openapi-spec-validator 0 errors |
| 0 | Scoring model JSON `packages/scoring/vendoriq_scoring/models/{sub-4,sup-1}.json` | sums to 100, KO sets A.1/A.4/F.1 and A.1/A.4/C.3 |
| 1A | `packages/scoring` — score, derive_raw, match_package, match_project, CLI | 220 passed; Rev4 fixture 13/13; 98% cov |
| 1D | `packages/excel_import` — application form + scoring workbook parsers, CLI | 62 passed; WESA expected fixture; Rev4 → vendors_seed.json 0 mismatches |
| 1B+1C | `apps/api` — config (AUTH_MODE guard), UoW, observations resolver, documents + expiry, state machine, audit, event log, storage local/s3, auth (OTP, password+TOTP, sessions+CSRF, API keys), permissions matrix, routers: auth, vendors, admin (users/settings/categories/audit), events, storage | 359 passed, 95% cov; independent checker: login/OTP/TOTP/403 flows OK; production guard refuses AUTH_MODE=test |
| 1B | `apps/worker` — APScheduler skeleton, 3 jobs registered, stale-profile scan | tests pass |

## Not done (needs npm/PyPI access — blocked in the previous environment)
- 1E seed CLI (`vendoriq_api.seed` referenced by Makefile does not exist yet). `create_test_accounts()` exists in `services/accounts.py`.
- 1F web shell: `apps/web` sources/config exist, **never installed or built**; `apps/web/preview/` is a dependency-free stand-in.
- `uv.lock` missing; `.venv` was assembled by git-cloning package sources (ADR-005) — rebuild it with `uv sync` once PyPI is reachable. `pytest-cov`/`coverage` in `.venv` are hand-installed; `mypy` is not in `.venv` (use `mypy --python-executable .venv/bin/python .` or reinstall).
- Phases 2 and 3 entirely.

## Orchestrator rulings on open questions
- Engineers count `E.2` = sum of **E.4…E.8** (E.9 technicians/foremen excluded). `packages/scoring/vendoriq_scoring/derive.py` currently sums E.4…E.9 — change it and its test (1 line each). ADR-008.
- ISO 9001 certificate rule for subcontractors: require `C.4 > 0` only (drop the `F.1` fallback ported from the prototype); suppliers use `F.1`. ADR-009.
- New matching gap keys `no_prequalified_vendor`, `too_few_strong` need AZ/EN strings in `apps/web/src/i18n`.
- `seed/README.md` explanation of why empty vendors score 1.0 is wrong (it is C.3's 25% floor, not A.2) — fix the text.
- API routes live under `/api/...`; staff login is two-step (`/api/auth/login` → `/api/auth/totp/verify`). Web client must follow the contract.
- Real vs demo data: see BUILD_BRIEF §1.10; keep `is_demo` on every demo row.
