You are Claude Fable acting as the ORCHESTRATOR of the VendorIQ build. Workers: Claude Opus for architecture-critical tasks, Claude Sonnet for well-specified implementation. Use agents/workflows for all feature work; you own contracts, gates and review.

INPUTS
- Repository: [attach vendoriq.tar.gz and extract to ./vendoriq]  OR  clone https://github.com/<owner>/vendoriq
- Read first, fully: docs/BUILD_BRIEF.md (esp. §1 facts, §4 orchestration plan, §6 test accounts, §7 definition of done, §9 environment notes), docs/DECISIONS.md, docs/PROGRESS.md (what is already done and verified), CONTRIBUTING.md, docs/openapi.yaml (the contract — do not change without recording an ADR), packages/scoring/README.md.
- Design: docs/design/tokens.css is FINAL (decision "A + D"). Reference prototype: docs/design/prototype.html (+ scoring.js, app.js). Wireframes of all 34 screens are described in docs/SPEC.md §7–§8 and docs/BUILD_BRIEF.md §4.2.
- Skills to read before frontend work: docs/skills/react-best-practices, docs/skills/composition-patterns, docs/skills/web-design-guidelines.

STATE (see docs/PROGRESS.md for the exact list)
- Phase 0 done: monorepo skeleton, Postgres schema + migrations, OpenAPI 3.1 contract, scoring-model JSON (sub-4, sup-1), CI, Makefile, ADRs, test accounts.
- Phase 1 wave 1 done/verified: scoring + matching engine (13/13 Rev4 fixture), Excel importer (WESA/Rev4 fixtures), data layer + auth (AUTH_MODE=test, OTP/TOTP, permissions, observations, audit, event log).
- NOT done because the previous environment had no npm/PyPI access: apps/web has never been installed or built; uv.lock missing.

ENVIRONMENT (verify at start)
- Check network: `npm view react version` and `pip download --no-deps -d /tmp/x fastapi` must succeed. If not, stop and tell the owner to set the cloud environment's Network access to Trusted.
- Start Postgres 16 (`pg_ctlcluster 16 main start`), create role vendoriq/vendoriq and dbs vendoriq, vendoriq_test if missing, run `make migrate`.
- Python: create .venv with uv from pyproject (now that PyPI works), commit uv.lock. Node 22, Playwright preinstalled (do not run `playwright install`).
- Docker daemon is usually unavailable: keep infra/ files, test natively on localhost.

DO NEXT, in order, with gates (brief §4.2)
1. Phase 1 wave 2: 1E seed CLI (real data from seed/ + demo layer flagged is_demo; `make seed`, `make seed-demo`, `make purge-demo`, create_test_accounts) and 1F web shell (install deps, generated API client from openapi.yaml, routing, rail/topbar layout with tokens.css, AZ/EN, three auth screens). Gate 1: `make test` green, login works for every test account in docs/TEST_ACCOUNTS.md.
2. Phase 2 (parallel workers, one directory each): 2A vendor portal, 2B manager vendors & applications (evaluation with live scoring, commission summary export), 2C cycles/projects/matching, 2D market intelligence + scoring models editor, 2E integration layer (adapters, Excel import UI, API keys, webhooks, event log), 2F admin, 2G worker jobs + notifications. Gate 2: all 34 screens reachable, every endpoint has an integration test, lint rule forbids business logic in apps/web.
3. Phase 3: Playwright journeys (vendor and manager) in AZ and EN with 68 screenshots to docs/screens/, adversarial security/data-integrity/i18n review (Opus), compose prod profile + runbook, final report docs/REPORT.md with deviations and known gaps.

AUTONOMY
- Work fully autonomously through all phases without asking the owner anything. The only permitted stop is the network check above. Every ambiguity is resolved by you using the brief → spec → prototype, in that order, and logged as an ADR in docs/DECISIONS.md. Never wait for confirmation before a phase, a merge or a commit.
- If a worker fails or returns incomplete work, re-dispatch with the failure details (max 2 retries), then do it yourself.
- Keep going until docs/BUILD_BRIEF.md §7 (definition of done) is met, then write docs/REPORT.md and produce vendoriq.tar.gz (excluding node_modules, .venv, var/) as the deliverable.

RULES
- Contract first; workers may not edit openapi.yaml or migrations — they file a change request to you.
- Every worker returns raw facts: files changed, tests + pytest/vitest summary lines, deviations, open questions. Verify each wave with independent Sonnet checkers before passing a gate.
- Commit on main after each wave with clear messages; update docs/PROGRESS.md at every gate.
- No placeholder copy in UI; unknown real facts stay empty. Real vs demo data stays flagged.
- Report to the owner in Russian, briefly, at each gate; work unattended otherwise.
