# Test accounts and `AUTH_MODE`

These accounts exist **only** while `AUTH_MODE=test`. They are created by `make seed` and
removed by switching to `AUTH_MODE=live` and re-seeding.

## `AUTH_MODE`

| Mode | What it does |
|---|---|
| `test` | Seeds the accounts below. One-time codes and TOTP codes are written to the server log and returned in `debug_code`, and the web shell shows a permanent banner. The vendor OTP `000000` is always accepted. |
| `live` | Real e-mail delivery through `SMTP_*`; `debug_code` is always `null`; no banner; the seeded accounts are not created. |

**The mode cannot be left on by accident.** The API refuses to start when `AUTH_MODE=test` and
`APP_ENV=production` — `Settings` raises at import time, before a port is opened (brief §6).
The check is covered by `apps/api/tests/test_health.py::test_test_auth_mode_is_refused_in_production`.

## Staff accounts — e-mail + password + TOTP

| Role | Login | Password |
|---|---|---|
| Admin | `admin@vendoriq.test` | `Admin!2026` |
| Manager | `manager@vendoriq.test` | `Manager!2026` |
| Commission | `commission@vendoriq.test` | `Commission!2026` |
| Officer | `officer@vendoriq.test` | `Officer!2026` |

Each staff account gets a TOTP secret. The seed prints the secret and the `otpauth://` URI once;
in test mode the current 6-digit code is also printed to the server log on every login attempt
and shown in the dev banner, so an authenticator app is optional during development.

Login is two calls: `POST /api/auth/staff/login` returns a `challenge_id`, then
`POST /api/auth/staff/totp/verify` exchanges it for the session cookie.

## Vendor accounts — e-mail + one-time code

| Vendor | Login | Code |
|---|---|---|
| VVESA MMC (Wesa) — a full, submitted application | `habib.atakisiyev@wesa.az` | `000000` |
| Shield — prequalified, class A | `a.tabit@shield.az` | `000000` |
| New, empty vendor — nothing filled in yet | `vendor.new@vendoriq.test` | `000000` |

Login is two calls: `POST /api/auth/otp/request` then `POST /api/auth/otp/verify`. In test mode
any freshly requested code works **and** `000000` is accepted unconditionally, so an e-mail
server is not needed to click through the portal.

## Roles

| Role | Sees | Does |
|---|---|---|
| `vendor` | Only its own vendor record | Maintains the profile, fills the application, uploads documents, signs the declaration |
| `officer` | The whole register | Invites, imports Excel, verifies documents, enters the 0–3 rubric scores, requests information |
| `commission` | Applications and evaluations | Records the committee decision and justification |
| `manager` | Everything | Approves prequalification, sets thresholds and model versions, reads market intelligence, go/no-go |
| `admin` | Everything | Users, integrations, taxonomy, model versions, audit log |

The permission matrix is enforced server-side on every endpoint; the frontend only hides what a
role cannot use (spec §3, §13).

## Local environment

```
APP_ENV=development
AUTH_MODE=test
DATABASE_URL=postgresql+psycopg://vendoriq:vendoriq@localhost:5432/vendoriq
STORAGE_BACKEND=local
SMTP_HOST=            # empty → e-mail is written to the log
```

The full list with every variable is `infra/.env.example`.
