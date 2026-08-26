# VendorIQ — progress log (orchestrator)

Updated: 2026-08-26 · branch `claude/vendoriq-orchestration-7ls8e6`

## Gate 3 — PASSED

| Criterion (brief §7) | Evidence |
|---|---|
| 7.1 `docker compose up`; prod profile + Caddy TLS runbook | Config asserted by `test_compose_profiles.py` (production and live auth pinned, Caddy the only published service, refusal on a missing secret); `docs/RUNBOOK.md`. **Containers never started — no Docker daemon here.** |
| 7.2 pytest, coverage ≥ 80 % | **1102 passed, 0 xfailed**; Rev4 fixture 17/17; coverage **95 %** |
| 7.3 Playwright journeys + 68 screenshots | **80 passed**; 68 files, 34 slugs × AZ/EN, all distinct; journeys assert 90.3/A, 94.7/A, 96 % |
| 7.4 OpenAPI at `/api/docs`; integration guide | 200; contract served verbatim; 103/103 operations requested from a test |
| 7.5 No business logic in the frontend; no untranslated keys | lint rule mutation-tested; i18n test now compares to the contract, not dictionary-to-dictionary |
| 7.6 `make purge-demo`, `make seed` idempotent | 8 tests, third consecutive run changes nothing |
| 7.7 CI green; pushed; report | **All five checks green.** Pushed to the run's branch; merging to `main` is the owner's call. `docs/REPORT.md` complete. |

Phase 3 found more than phases 1 and 2 of my own checking did: 5 defects from 3A, 9 from 3B,
all fixed. The one that mattered most — two code namespaces sharing an alphabet — was
invisible to 1102 tests because every one of them agreed with the mistake.

Three of my own defects reached CI because a local check was *nearly* the CI check. `make ci`
now runs CI's steps in CI's order.

## Phase 3 — complete

| Task | Owner | State |
|---|---|---|
| 3A Playwright journeys + 68 screenshots | worker | done — 80 tests, 5 defects reported |
| 3B adversarial security / integrity / i18n review | worker (Opus) | done — 9 findings, all fixed |
| 3C production profile, backup and restore, runbook | orchestrator | done |
| 3D final report | orchestrator | done |

**3C found two real defects by reading rather than running.** The prod profile could be started
with every development default in place — `AUTH_MODE=test` on a public hostname seeds the
published accounts and reveals sign-in codes — so `infra/docker-compose.prod.yml` now pins the
production values and makes the rest `${VAR:?…}`, which stops `docker compose` from rendering a
configuration at all while one is missing (ADR-020). And a live stack had **no user who could
sign in**: `AUTH_MODE=live` seeds nothing, correctly, and every screen is behind the sign-in, so
there was no first move. `seed create-admin` is that move (ADR-019).

`docker compose config` parses and interpolates without a daemon, so both claims are asserted by
a test rather than described in the runbook. What the containers do when started is still
unverified, and `docs/RUNBOOK.md` opens by saying which parts those are.

## Gate 2 — PASSED

| Criterion (brief §4.2) | Evidence |
|---|---|
| All 34 screens reachable | 34/34, walked in a browser under a real staff session and a real vendor session — not inferred from the route table, which compiled green while the app rendered a blank page |
| Every endpoint covered by an integration test | 103/103 contract operations are requested from a test |
| No business logic in the frontend | `no-restricted-imports` blocks `packages/scoring` and any import leaving `apps/web`; mutation-tested. Its limit is written down: it cannot catch an inline reimplementation, and the report says so |
| Suite | 1015 pytest · 52 vitest · 6 Playwright · ruff, ruff format, mypy, eslint, tsc, build |
| CI | green on the PR head: Python, Web, OpenAPI contract, Docker build, Playwright |

102 of the 103 operations are served by a router; the one the counter calls missing is
`/health`, which is mounted at the root separately.

Two of the checks were wrong before the code was. The endpoint-coverage regex excluded the
quote inside an f-string interpolation and reported six project paths as untested when the
tests exercise all six; the screen walk called the sign-in screens unreachable for being under
200 characters, which is simply how long a sign-in form is. Both were fixed and the screens
re-verified by their controls — every input has a label, 1/1, 2/2 and 9/9.

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
