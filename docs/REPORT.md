# VendorIQ — build report

**Status: draft, written as the run proceeds.** The delivery and verification sections are
completed at Gate 3; the deviations and known gaps below are recorded as they are decided, so
the reasoning is written down while it is fresh rather than reconstructed afterwards. Nothing
here is a claim about work that has not happened — where something is unverified, it says so.

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

### 2.2 Where the spec and the system disagreed, and who won

* **TQS-238 coverage.** Spec §11.2 states 96 % with flooring the only NO-GO. The system
  returned 76 %. The spec was right: the demo seed wrote all category assignments unconfirmed
  and never qualified the demo suppliers, so nothing was a match candidate. Fixed in the demo
  layer; the system now returns 96 % and **nothing was tuned to reach it**. ADR-018.
* The test that had "verified" that 96 % was reading a status label out of `seed/data.json`
  instead of scoring anyone, so it agreed with the spec while the product contradicted it. It
  now derives qualification from the score, which is the question the seed asks.

---

## 3. Decisions

Twenty ADRs in `docs/DECISIONS.md`. The ones that change behaviour a reader would notice:
ADR-008 (engineers exclude technicians), ADR-009 and ADR-011 (certificates resolve against the
vendor's own model, and one with no criterion is not held), ADR-013 (the rail is built from the
server's permission list, never a copy of it), ADR-014 and ADR-017 (`status` and `is_locked` are
different questions), ADR-018 (the demo layer must demonstrate something), ADR-019 and ADR-020 (a production stack
starts with no users and needs a way to get its first one; its overlay makes the development
defaults impossible rather than merely discouraged).

---

## 4. How to run it · 5. Test accounts · 6. Verification evidence

Completed at Gate 3.
