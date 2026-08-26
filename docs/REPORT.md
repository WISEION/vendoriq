# VendorIQ — build report

**Status: complete.** The known gaps and deviations were written as they were decided rather
than reconstructed at the end, so the reasoning is contemporaneous. Nothing here is a claim
about work that has not happened — where something is unverified, it says so, and §1.5 is the
list of what that covers.

45 commits · 23 ADRs · 1102 pytest · 52 vitest · 80 Playwright · CI green on all five checks.

---

## 1. Known gaps

Things a reader should know before trusting the system. Each is a deliberate decision with its
reasoning, not an oversight discovered late.

### 1.1 Two defects in the scoring models themselves — recorded, not fixed

* **`sup-1` has no ISO 45001 criterion at all.** Its `F.2` is "Defect / return record". Under
  ADR-011 a required certificate with no criterion in the vendor's model cannot be evidenced,
  so **a supplier is never eligible for a package requiring ISO 45001**. That is the honest
  answer while the model has no such criterion; the alternative was crediting a clean returns
  record as a safety certificate.
* **`sub-4`'s `F.2` conflates ISO 14001 with ISO 45001** — one rubric cell reads
  "ISO 14001 / 45001", so a subcontractor holding only 14001 registers as holding 45001.

Neither is fixed, and that is the point: spec §10.3 makes a model version immutable once an
application has been scored with it, `sub-4` is the frozen Rev4 model all 13 real vendors were
scored with, and brief §1.3 marks `sup-1` "proposed" until the commission freezes it. Changing
either is the commission's decision, and it takes the form of a **new version**, not an edit.
The model editor (task 2D) is where that happens.

### 1.2 The post-prequalification change request is refused, not implemented

Spec §7 says a vendor's profile edit after prequalification "creates a change request the
officer confirms". The refusal exists and is correct — accepting the edit would let a
prequalified vendor rewrite the basis of a score the commission has signed. The **queue an
officer works** does not exist: it needs a table, two contract operations and a screen, and
`docs/SCREENS.md` has 34 screens, none of which is that queue.

Today a prequalified vendor needing a correction contacts the officer, who has `patchVendor`
with a mandatory reason (spec §6.5) — the same audit trail the queue would have produced.
ADR-016.

### 1.3 What the "no business logic in the frontend" lint rule does and does not prove

Brief §7.5's wording is "lint rule: scoring/matching imports forbidden in `apps/web`", and that
is enforced and **mutation-tested** — a component importing `packages/scoring` is rejected, as
is any import climbing out of `apps/web` at all.

It cannot catch someone re-implementing the class bands inline in a component. Nothing
mechanical can. The actual guarantee is architectural — every score, class, coverage figure and
eligibility verdict arrives computed from the API — and it rests on review, not on the rule.

### 1.4 One copyleft dependency, and it was already there

`fpdf2` (PDF commission summary) is LGPL-3.0. So is **`psycopg`**, the PostgreSQL driver fixed
by ADR-001, for which no permissive equivalent exists on this stack. The project already
carried LGPL-3.0 for the one component it cannot run without, so `fpdf2` adds no new
obligation. `certifi` and `pathspec` are MPL-2.0; everything else among the 75 installed
distributions is MIT, BSD or Apache-2.0.

All are imported as unmodified libraries installed from PyPI — the use LGPL §4 and MPL §3.3
permit — and any of them can be removed without touching VendorIQ's own code. If the owner's
policy forbids LGPL outright, the conclusion is not "replace `fpdf2`" but "change the database
driver", which is an ADR-001 decision. ADR-015.

### 1.5 Not verifiable on this host

* **`docker compose up` has never been run.** No Docker daemon exists here (brief §9). What
  could be checked without one was: the rendered configuration (`docker compose config` parses
  and interpolates locally, so `test_compose_profiles.py` asserts what the production stack
  actually comes out as — pinned to production and live auth, Caddy the only service
  publishing a port, and a refusal when a secret is missing), the images' contents by reading,
  and the restore script's refusals. Three real defects were found that way: the stack came up
  with an empty database, the API image did not contain the file the seed reads, and a live
  stack had no user who could sign in (ADR-019). Whether the containers **start** remains
  unverified, and so do `pg_restore`, `mc mirror` and ACME issuance. `docs/RUNBOOK.md` opens
  by saying so.
* **Real 1C / SAP / Odoo connectivity, real government registries, SSO, WhatsApp,
  e-tendering** — explicit non-goals (brief §8). Each has an interface or a stub.

---

## 2. Deviations from the brief

### 2.1 Corrections to the brief's own instructions

* **"Refuse an evaluation on a locked model version"** was wrong and was not followed.
  `is_locked` is set the moment the first application is scored, so `sub-4` is locked from the
  seed onward — refusing on it would refuse every evaluation in the system, including the 13
  real ones. Spec §10.3's immutability is about the model's *definition*: `is_locked` gates
  *editing* it, retirement gates *scoring with* it. The worker declined the instruction and
  asked; it was right. ADR-017.

### 2.2 A claim of mine that was wrong, and how it was caught

ADR-021 concluded that none of the 13 vendors had form answers because Uni Ko scored them from
a spreadsheet. `seed/fixtures/` contains Wesa's filled-in application form; `packages/excel_import`
had parsed it since phase 1. I asserted something about the source data without checking the
source data, and wrote it into an ADR and into a report to the owner.

Loading it turned out to be worth more than the correction: Wesa is the only vendor with two
independent records of the same company, so deriving indicators from its form and comparing
them against the Rev4 sheet checks the whole Appendix-A-to-criterion bridge on real data.
Seventeen of eighteen agree to the manat; the six absent ones are exactly the judgement
criteria the officer is supposed to score. The one disagreement is `E.2` — the form's rows sum
to 8 engineers, the sheet recorded 10 — which is ADR-008's open question finally answered with
data, and it is score-neutral. ADR-023.

### 2.3 Three defects that reached CI because a check here was not the check there

Worth stating plainly because it is one mistake made three times:

* `ruff` resolved from `PATH` (0.15.8) instead of the pinned 0.16.4, so "format clean" was
  measured with the wrong binary. **Two workers reported the file CI rejected and I dismissed
  them both.** They were right.
* `tsc --noEmit` instead of `tsc --build`, which is what `npm run typecheck` and the web image
  run. It accepted a duplicate `const session` that CI rejected.
* `alembic check` — CI's "migrations match the models" step — never run locally at all. My
  `RevokedSession` model drifted from its own migration in two places.

`make ci` now runs exactly what CI runs, in CI's order, copied from `.github/workflows`. The
lesson is not "be more careful"; it is that a local gate which is *nearly* the CI gate is
worse than no local gate, because it produces confidence rather than doubt.

A fourth, related: a test I wrote for the `SESSION_SECRET` guard passed locally and asserted
**nothing** in CI, because `_env_file=None` suppresses the `.env` file and not the process
environment, and the workflow exports `SESSION_SECRET`. It was green exactly where it mattered
least. Settings tests now `delenv`, and the guard is mutation-tested under CI's own
environment.

### 2.4 Where the spec and the system disagreed, and who won

* **TQS-238 coverage.** Spec §11.2 states 96 % with flooring the only NO-GO. The system
  returned 76 %. The spec was right: the demo seed wrote all category assignments unconfirmed
  and never qualified the demo suppliers, so nothing was a match candidate. Fixed in the demo
  layer; the system now returns 96 % and **nothing was tuned to reach it**. ADR-018.
* The test that had "verified" that 96 % was reading a status label out of `seed/data.json`
  instead of scoring anyone, so it agreed with the spec while the product contradicted it. It
  now derives qualification from the score, which is the question the seed asks.

### 2.5 The nine security findings, all fixed

`docs/security-review.md` has the full report. Ranked as 3B ranked them:

1. **Any staff role could type `status=prequalified` onto a vendor** — no application, no
   score, no commission decision — and `services/matching.py` reads exactly that column to
   build the eligible-candidate pool. Now refused for every role: an outcome is decided, not
   typed. The fix is stricter than the finding proposed, because the reason it may not be
   typed is not that the typist is too junior.
2. **A model version never locked.** `is_locked` was set in one place, the seed, so
   `patch_draft`'s refusal never fired for anything the editor created. Demonstrated chain:
   application refused at 5.7 points → pass mark of the live version patched 70 → 1 → same
   application approved. `save_evaluation` now locks, and `patch_draft` checks the fact rather
   than only the flag.
3. **Logout did not revoke the session.** A captured cookie kept authenticating for the rest
   of its eight hours. Per-token `jti` and a self-expiring `revoked_session` table — per
   token, not per user, so a phone logout leaves the desktop signed in (ADR-022).
4. **The information-request loop could not correct a number.** `raw_snapshot` froze at
   submission and the only edge back never passed through `submit`, so the officer scored the
   figure the vendor had been asked to replace. Live while in `information_requested`,
   re-frozen when the review resumes.
5. **A commission member could rewrite the register** (legal name, VÖEN) while also being the
   only role that may decide. `patchVendor` no longer admits the commission.
6. **A wrong OTP never burnt an attempt** — the increment was flushed and then rolled back by
   the raise, so `OTP_MAX_ATTEMPTS` counted nothing.
7. **Five of eight application statuses rendered as raw identifiers**, in Azerbaijani as well
   as English. `test_i18n_contract` could not see it: it compares the two dictionaries to each
   other, and a key missing from both is perfectly consistent. The new test compares them to
   the contract.
8. **`withdrawn` and `suspended` were both labelled "Rejected"** — a false statement rather
   than a missing string.
9. **Production accepted the placeholder `SESSION_SECRET`.** Only `AUTH_MODE` was guarded.

What 3B attacked and found sound is in its report and is the more reassuring half: vendor
isolation across ten cross-tenant paths, score confidentiality before decision, the
server-side pass mark and KO gate, API-key handling, upload containment, audit atomicity,
CSRF and cookie flags.

---

## 3. Decisions

Twenty-three ADRs in `docs/DECISIONS.md`. The ones that change behaviour a reader would
notice:

* **ADR-021** — two code namespaces share one alphabet and *cross*, and the seed was writing
  into the wrong one. The most serious defect in the build.
* **ADR-023** — Wesa's real form is loaded, which corrects ADR-021 and cross-validates the
  scoring bridge; `E.2` is the one number the form and the sheet disagree about.
* **ADR-009 / ADR-011** — certificates resolve against the model the vendor was scored with,
  and one with no criterion in that model is *not held*.
* **ADR-013** — the navigation rail is built from `Me.permissions`, never from a role table
  copied into the browser.
* **ADR-014 / ADR-017** — `status` and `is_locked` answer different questions; ADR-017
  corrects an instruction in the brief itself.
* **ADR-018** — the demo layer has to demonstrate something.
* **ADR-019 / ADR-020** — a production stack starts with no users and needs a way to get its
  first one; its compose overlay makes the development defaults impossible rather than merely
  discouraged.
* **ADR-022** — logging out withdraws the token, not just the browser's copy of it.

---

## 4. How to run it

```bash
cp infra/.env.example infra/.env
make up                 # docker compose --profile dev up --build → http://localhost, seeded
```

Natively, which is how everything here was actually verified:

```bash
make setup && make db-up && make migrate && make seed && make seed-demo
make api                # http://localhost:8000  (/health, /api/docs)
make web                # http://localhost:5173
```

Production is `docs/RUNBOOK.md`: `make prod-up` with the overlay that makes the development
defaults impossible, Caddy for TLS, `make create-admin` for the first user, `make backup`.

`make ci` runs exactly what CI runs, in CI's order. Use it before pushing — three defects
reached CI green-locally because a check here was not the check there (§2.3).

## 5. Test accounts

`docs/TEST_ACCOUNTS.md`. Four staff accounts (admin, manager, commission, officer) with
password + TOTP, and three vendor accounts that sign in with a one-time code — `000000` is
accepted while `AUTH_MODE=test`, and the real code is printed in the server log. The seed
prints each TOTP secret once when it creates the account.

None of it exists outside test mode: `create_test_accounts` raises rather than run under
`AUTH_MODE=live`, the API refuses to start with `AUTH_MODE=test` under `APP_ENV=production`,
and the production compose overlay pins both. A live stack starts with no users at all, which
is why `make create-admin` exists (ADR-019).

## 6. Verification evidence

Against brief §7, item by item.

| § | Requirement | Evidence |
|---|---|---|
| 7.1 | `docker compose up` → seeded app; `--profile prod` with Caddy TLS in a runbook | Compose **config** verified by `test_compose_profiles.py` — production and live auth pinned, Caddy the only service publishing a port, a refusal when a secret is missing. `docs/RUNBOOK.md` covers TLS, first user, backup, upgrade, rollback. **The containers have never been started** (§1.5). |
| 7.2 | pytest: 13/13 Rev4, importer fixtures, matching rules, permission matrix; coverage ≥ 80 % | **1102 passed**, 0 xfailed. `test_rev4_fixture.py` 17/17. Coverage **95 %** on `packages/*` and the named API modules (80 % required). |
| 7.3 | Playwright: both journeys; 68 screenshots | **80 passed.** Both journeys assert real facts — Wesa 90.3 / class A, Shield 94.7 / A, TQS-238 96 % with flooring the only NO-GO. 68 files in `docs/screens/`, 34 slugs × AZ/EN, all distinct. |
| 7.4 | OpenAPI at `/api/docs`; integration guide | `/api/docs` 200, `/api/openapi.yaml` serves the hand-written contract verbatim (ADR-006). `docs/integration-guide.md` covers API keys, webhooks, the event log, `external_ref` and how a future product subscribes. 103/103 operations are requested from a test. |
| 7.5 | No business logic in the frontend (lint rule); no untranslated keys | `no-restricted-imports` blocks `packages/scoring` and any import leaving `apps/web`; mutation-tested. Its limit is written down in §1.3. i18n: every contract enum reaching a screen has a translation, and every application status now has its own label — a gap the original test could not see (§2.4). |
| 7.6 | `make purge-demo` leaves only real data; `make seed` idempotent | 8 tests, including a third consecutive run changing nothing and a purge leaving the real 13 referentially valid. |
| 7.7 | CI green; repository pushed; final report | All five checks green on the PR head. Pushed to `claude/vendoriq-orchestration-7ls8e6`; **merging to `main` is the owner's call** — the branch instruction for this run forbids pushing anywhere else. This document is the report. |

### 6.1 What the two review tasks found

Phase 3 ran two adversarial workers, and between them they found more than the preceding two
phases of my own checking did. That is the finding worth recording.

**3A (Playwright)** was told to assert real facts and to report discrepancies rather than
adjust assertions to match. It found five defects, one of which — the code-namespace
collision of ADR-021 — was the most serious in the build and had been invisible to 1102 tests,
because every one of them agreed with the mistake.

**3B (adversarial review)** was told that a report finding nothing is a failed review, and to
write a failing `xfail` test for each finding rather than fix it. It returned nine, ranked,
each reproducible. All nine are fixed (§2.5), and its own tests — inverted from `xfail` to
assertions — are what keeps them fixed.

Both were given a narrow file ownership and neither was allowed to touch what it was
reviewing. The reports are `docs/security-review.md` and the two suites
`apps/api/tests/test_security_review.py` and `apps/web/e2e/`.
