# Phase 3B — adversarial review

**Scope:** authorisation (per role, per vendor), data integrity (snapshot and model-version
immutability, audit atomicity), credentials and files (API keys, webhook secrets, uploads,
OTP), and i18n completeness.
**Branch reviewed:** `claude/vendoriq-orchestration-7ls8e6`, phase 2 complete, 1015 tests green.
**Method:** every claim below was reproduced against the running application through the HTTP
API. Nothing was fixed. Each defect has a test in `apps/api/tests/test_security_review.py`
marked `xfail(strict=True)` — it turns green the moment the defect is fixed, so the file is
also the fix checklist. The attacks that *bounced* are plain passing tests in the same file;
they are the part of the review that can be checked.

Run: `cd apps/api && python -m pytest tests/test_security_review.py`
→ **22 passed, 9 xfailed**. `ruff check .`, `ruff format --check` on this file and `mypy .`
are all clean.

---

## Findings, ranked by what an attacker gains

### 1 — A procurement officer can prequalify a vendor outright · authorisation

`PATCH /api/vendors/{id}` is declared `_p(EVERYONE, Scope.VENDORS_WRITE, vendor_scoped=True)`
in `security/permissions.py`, and its body (`schemas/vendors.py::VendorPatch`) accepts
`status`. `services/vendors.py::_set_status` refuses only two things: a `vendor` caller, and
the `suspended` target. Every other staff role — including `officer` and `commission` —
can write `status = "prequalified"` straight onto the register row.

That column is not decorative. `services/matching.py:137` builds each matching candidate with
`is_prequalified=vendor.status is VendorStatus.PREQUALIFIED`, and the engine's eligibility
rule (`packages/scoring`, spec §11.1) reads exactly that flag.

**What it gains:** an officer — the role whose job stops at *preparing* the evaluation
(spec §3) — puts an arbitrary vendor into the eligible-candidate pool for every project
package, with no application, no rubric, no score, no commission decision and no manager
approval. It bypasses the whole of spec §9 and the score gate in
`services/evaluation.py::decide`. The vendor register then shows `prequalified` with a null
score, which reads as a data-entry oddity rather than as a forged qualification.

**Test:** `test_only_a_manager_can_put_a_vendor_into_the_prequalified_state`.

---

### 2 — A scoring model version never locks, so a live one can be rewritten · data integrity

`ScoringModel.is_locked` is the flag `services/scoring_models.py::patch_draft` guards on, and
ADR-014/017 and spec §10.3 say a version is immutable once used. **No code path ever sets it.**
The only assignment in the repository is `seed/real.py:162`, which locks `sub-4` at seed time.
`services/evaluation.py::save_evaluation` scores an application against a version and leaves
`is_locked` false.

So every version except the seeded `sub-4` — `sup-1`, and anything the phase-2D model editor
creates and publishes — stays editable for ever. `PATCH /api/scoring-models/{version}` accepts
`criteria`, `classes`, `pass_mark` and `validity_months` on an `active` version whose own
response body reports `application_count: 1`. There is no status check in `patch_draft` at all;
`draft` is in the operation's name only.

**What it gains:** the criteria weights, threshold tables, class bands and pass mark that a
cycle's decided applications were scored against can be changed after the fact. Demonstrated
end to end: an application scoring 5.7 (class F) is refused approval with `409`; the manager
patches the same live version's `pass_mark` from 70 to 1; the identical application is then
approved and lands in `prequalified` — with nothing about the evidence changed, and an audit
trail that reads as an ordinary approval plus an ordinary model edit.

**Tests:** `test_a_model_version_that_has_scored_an_application_is_immutable` (xfail) and
`test_lowering_the_pass_mark_of_a_used_model_approves_a_failing_application` (passes — it
records the current behaviour rather than asserting the rule).

---

### 3 — Logging out does not revoke the session · credentials

`POST /api/auth/logout` (`routers/auth.py:198`) calls `delete_cookie` three times and nothing
else. The session is a stateless signature (`security/tokens.sign`) with no server-side
record, so a copy of the cookie captured before logout keeps authenticating until
`ACCESS_TOKEN_TTL_MINUTES` expires — **8 hours by default**.

`security/deps.py` documents deactivating the account as the revocation mechanism, and that
does work (`test_deactivating_an_account_kills_its_live_session` passes). But there is no way
to revoke a single session: an admin who logs out of a shared or suspected-compromised
machine has not ended anything.

**What it gains:** any cookie exfiltration — a shared workstation, a browser extension, a
proxy log — survives the one action a user takes to close it.

**Test:** `test_logging_out_revokes_the_session_token`.

---

### 4 — The information-request loop cannot correct a number · data integrity

Spec §9: `information_requested` → "vendor supplies the missing data" → back to
`under_review`. `services/answers.py::_EDITABLE_STATUSES` correctly lets the vendor write in
that state. But `services/evaluation.py::_base_raw` returns `application.raw_snapshot`
whenever one exists, and nothing re-derives the snapshot after submission — `submission.py`
writes it once, in `submit`.

Reproduced: an application submitted with `B.1 = 1 000`, sent back for information, the vendor
supplies three corrected annual turnovers totalling 9 000 000, and the officer's evaluation
sheet still reports `raw_value = 1 000.0` for B.1.

**What it gains:** less an attack than a silent integrity failure in the officer's favour or
against it, depending on which way the first number was wrong. The officer sees a figure the
vendor has already superseded, believes the information request was answered, and scores the
old one. A vendor that under-reported and was asked to correct it keeps its low number in the
score; a vendor that over-reported keeps its high one. Spec §5's freeze and spec §9's
correction loop are in direct conflict and the freeze silently wins.

**Test:** `test_information_requested_lets_a_corrected_indicator_reach_the_score`.

---

### 5 — A commission member can rewrite the register · authorisation

Same root as finding 1: `patchVendor` is open to `EVERYONE`. Spec §3 gives the commission
"reviews evaluations, records the committee decision and justification" — not the legal name,
the VÖEN, the vendor type or the `external_ref`. A commission member renaming a vendor or
changing its VÖEN passes with a `reason` string and one audit row.

**What it gains:** modest on its own — the audit trail records it — but VÖEN is the register's
uniqueness key and the handle every future integration maps on (`external_ref`, brief §2).

**Test:** `test_a_commission_member_cannot_rewrite_the_register`.

---

### 6 — A wrong OTP never burns an attempt; `OTP_MAX_ATTEMPTS` is inert · credentials

`services/auth.py::verify_otp` increments `candidate.attempts` for each non-matching code and
then `raise invalid` — a `401`. `security/deps.py::get_uow` catches every exception and
rolls the request's transaction back, taking the increments with it. After three wrong codes
the row still reads `attempts = 0`, and the original code is still accepted.

`OTP_MAX_ATTEMPTS = 5` therefore has no effect at all; the only thing bounding guessing is the
in-process rate limiter, which allows `otp_rate_limit * 3` = 15 verifications per address per
10-minute window and lives in a module-level dict that resets on restart and is not shared
between workers. Against a 6-digit space that is not a break, but the defence the settings
advertise is not there, and the same rollback would erase any future per-credential counter
written the same way.

Two smaller notes on the same code path: the `_rate_limit` docstring claims the OTP bucket is
keyed "per e-mail address (and per client address)" — it is keyed by address only, so nothing
slows an attacker spraying many accounts; and five OTP requests lock a victim out of
requesting a code for ten minutes.

**Test:** `test_a_wrong_otp_code_burns_an_attempt`.

---

### 7 — Five of the eight application statuses reach the screen as raw identifiers · i18n

`features/manager/ApplicationsQueue.tsx:99` renders the status filter as
``t(`st_${value}`)``, with an explicit fallback to the raw value when the key is missing.
Of the eight `ApplicationStatus` values only `st_under_review`, `st_prequalified` and
`st_rejected` exist in the dictionaries. The manager's queue filter therefore offers
`invited`, `in_progress`, `submitted`, `information_requested` and `withdrawn` — English
snake_case identifiers — **in the Azerbaijani UI as well as the English one**.

`test_i18n_contract.py` does not catch this: it checks two enums (`PackageMatch.gap`,
`MatchCandidate.reasons`) and then checks that the two dictionaries have the *same* keys. A
key missing from both languages passes both checks.

**Test:** `test_every_application_status_has_an_st_label_in_both_languages`.

---

### 8 — Withdrawn and suspended are labelled "Rejected" · i18n

`features/manager/shared.tsx`'s `STATUS_KEY` maps `withdrawn → st_rejected` and
`suspended → st_rejected`. Both therefore render as "Rədd edilib" / "Rejected". This is not a
missing translation — it is a factual misstatement in the UI, and it contradicts
`services/state_machine.py`, which is explicit that a withdrawn application "is not a
rejection and must not read as one".

**Test:** `test_withdrawn_and_suspended_are_not_labelled_rejected`.

---

### 9 — Production accepts the placeholder signing secret · configuration

`config.Settings` has exactly one production guard — `_refuse_test_auth_in_production`,
which does what brief §6 asks for `AUTH_MODE`. There is no equivalent for `session_secret`,
whose default is the literal `"change-me-in-production"` committed in the repository, and
`infra/.env.example` ships `change-me-a-long-random-string`. `infra/docker-compose.yml` uses
`${SESSION_SECRET:?…}`, which refuses an *unset* variable but happily accepts a copied
placeholder; a non-compose deployment (bare uvicorn, systemd) gets the code default silently.

That one string signs session cookies, TOTP challenge tokens, upload tickets and every signed
storage URL. The blast radius is limited by `_session_principal` re-reading the role from the
database — a forged cookie must name a real user id — so this is ranked last rather than
first. It is still the single value the whole scheme rests on, with no guard.

**Test:** `test_production_refuses_the_placeholder_session_secret`.

---

## Recorded behaviour — judgement calls, not defects

Two things reproduce as designed but are worth a decision rather than silence. Both have
passing tests that pin the current behaviour.

- **One `admin:read` scope on a machine key reads the staff directory and the audit log.**
  `docs/integration-guide.md` names the two closures it considers permanent — no key mints a
  key, no key manages webhooks — but `listUsers`, `listAuditEvents` and `exportAuditLog` all
  carry `Scope.ADMIN_READ`. A single integration credential therefore reads every staff
  account (e-mail, role, last login) and the whole audit trail, which spec §13 describes as
  committee minutes. Test: `test_an_admin_read_key_reads_the_staff_directory_and_the_audit_log`.
- **A vendor can read a scoring model's full threshold tables.** `permissions.py` justifies
  the vendor's access as "vendors see the class bands of the version they were scored with
  (spec §10.3)", but `GET /api/scoring-models/{version}` returns the entire definition,
  including every cut point of every numeric criterion. A vendor can read exactly which
  turnover figure buys the next band. Test:
  `test_a_vendor_can_read_the_full_criteria_and_thresholds_of_a_scoring_model`.

One cosmetic note with no test: `routers/storage.py::upload_object` lets
`ObjectNotFoundError` escape when a key would leave the storage root. The containment check
itself is correct (`storage/local.py::_path` refuses it, verified), but the route answers with
an unhandled 500 instead of the error envelope. Only reachable by someone who can forge a
storage token, i.e. who already holds `SESSION_SECRET`.

---

## Attacked and found sound

Each line below is a passing test in `apps/api/tests/test_security_review.py`.

**Vendor isolation.** Walked every vendor-scoped path with a second vendor's id — vendor
detail, categories, contacts, observations, documents, the application, `PATCH /vendors`,
`PATCH …/answers`, `POST …/submit`, `POST …/documents/upload-init`. All ten answer `404`, not
`403`, so the register is not a VÖEN oracle. The two shared list endpoints narrow server-side:
`GET /vendors` returns one row, and `GET /applications?vendor_id=<victim>` ignores the
parameter for a vendor caller rather than trusting it. Every vendor-scoped handler in
`routers/vendors.py` and `routers/portal.py` routes through a `_load` helper that calls
`scope_to_vendor`; there is no endpoint that checks the role and forgets the row.

**Score confidentiality.** A vendor reading its own application before the decision gets
`score_released: false`, `computed: null`, `rubric_scores: null`, `total: null`, `cls: null`,
and `403` on the evaluation sheet.

**Role separation on the evaluation.** A commission member cannot write the rubric (`403`).
An officer cannot record a decision (`403`, the matrix). A commission member cannot approve
(`403`, the state machine — `under_review → prequalified` is the manager's edge only).
Approval below the pass mark or on a knock-out is refused server-side with `409` and the
numbers in `details`, not merely by a disabled button.

**API keys.** The plaintext appears in the creation response and nowhere else — not in the
list endpoint, not in the audit row. A revoked key is anonymous on the very next request
(`401`), with no cache to wait out. No combination of scopes reaches `createApiKey` or
`createUser`; both answer `403` to a machine principal by construction, because `Principal.may`
requires a non-null scope for an API-key caller.

**Webhook secrets.** Returned once at creation; absent from the list response and from the
patch response; never written to an audit row.

**Uploads.** `upload-init` refuses a non-PDF content type before a key is ever minted. The
local backend's PUT route checks the magic number, not the client's claim: `MZ…` bytes with a
valid ticket are refused `415`. `document_key` strips path separators and collapses dot runs,
so a filename of `../../../etc/passwd` produces a contained key, and `LocalStorage._path`
independently refuses a key that resolves outside the storage root.

**Snapshot immutability.** Answers cannot be edited once an application is `submitted`
(`409`). Manual observations written after submission do not move the evaluation's raw
values. A decided application refuses further rubric writes (`409`).

**Audit atomicity.** One request is one transaction (`db.UnitOfWork`, committed only by
`security/deps.get_uow` on a clean return). A staff `PATCH /vendors` with no reason is refused
*after* the handler has already mutated the row; both the mutation and any audit row are gone
after the rollback. There is no second session, no `session_scope()` and no autocommit
anywhere in `services/` — webhook delivery is queued and drained on `after_commit`, so a
rolled-back request delivers nothing.

**CSRF.** A cookie-authenticated mutation without `X-CSRF-Token` is refused `403`. Session
cookies are `httpOnly`, `SameSite=Lax` and `Secure` outside development. Deactivating an
account kills its live session on the next request.

**OTP rate limiting.** `POST /auth/otp/request` answers `429` past `OTP_RATE_LIMIT`, and the
`202` body is identical whether or not the address has an account, so it is not an enumeration
oracle.

**Error-envelope i18n.** All ten `ErrorEnvelope.code` values have a sentence in both `az.json`
and `en.json`; `features/admin/shared.tsx` renders `err_${code}` and never falls through to
the code. E-mail templates in `services/notifications.py` are written per locale for every
notification kind, chosen from `User.locale` with the organisation default as the fallback.
The `features/*.az.json` and `features/*.en.json` sets are pairwise complete.
