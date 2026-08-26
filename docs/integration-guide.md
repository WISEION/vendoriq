# VendorIQ integration guide

How another system reads VendorIQ, writes into it, and learns when something changes.

This is the document brief §7.4 makes a delivery criterion: "OpenAPI served at `/api/docs`;
`docs/integration-guide.md` explains API keys, webhooks, event log, `external_ref`, and how a
future product subscribes." Everything below is implemented and covered by tests in
`apps/api/tests/test_integrations.py`, `test_adapters.py` and `test_webhooks.py`.

**The contract is `docs/openapi.yaml`.** It is hand-written and served verbatim (ADR-006), so
what you read there is what the server does — not a generated approximation of it. Fetch it
from a running instance at `/api/openapi.yaml` or `/api/openapi.json`; the browsable version
is `/api/docs`.

---

## 1. The shape of the API

* Base path `/api`. Every response is JSON.
* Collections are always `{items, total, page, page_size}` with `page` / `page_size` query
  parameters.
* Every failure is the same envelope, whatever went wrong:

  ```json
  { "error": { "code": "forbidden", "message": "…", "details": {} } }
  ```

  `code` is from a closed list (`bad_request`, `unauthenticated`, `forbidden`, `not_found`,
  `conflict`, `payload_too_large`, `unsupported_media_type`, `validation_error`,
  `rate_limited`, `internal_error`). Branch on `code`, never on `message` — the message is
  English text for developers and logs, and it changes.
* Identifiers are UUIDs and are stable for the lifetime of the row.

---

## 2. Authenticating with an API key

### Getting one

An **administrator** creates keys, in the UI at `/integrations` → *API keys*, or through the
API:

```http
POST /api/integrations/api-keys
Content-Type: application/json

{ "name": "Acme ERP bridge", "scopes": ["vendors:read", "projects:read"] }
```

```json
{
  "id": "0f2c…",
  "name": "Acme ERP bridge",
  "scopes": ["vendors:read", "projects:read"],
  "prefix": "vq_8Kd2mQ1s",
  "is_active": true,
  "key": "vq_8Kd2mQ1s_ZmVkY2JhOTg3NjU0MzIx…"
}
```

**`key` appears in this response and never again.** Only a SHA-256 hash is stored, so there is
no endpoint — none, not even for an administrator — that can return it later. If it is lost,
revoke the key and create another.

`prefix` *is* kept, and is listed by `listApiKeys`, so a person can tell two keys apart
without the plaintext being retrievable. It is the leading fragment of a 32-byte random
body: knowing it identifies the key and leaves the remaining entropy untouched.

### Using one

Send it in `X-API-Key` on every request:

```http
GET /api/vendors?status=prequalified&page_size=50
X-API-Key: vq_8Kd2mQ1s_ZmVkY2JhOTg3NjU0MzIx…
```

An API key is not a browser session: no cookie is set and no CSRF token is needed. If a
session cookie *and* a key are both present, the cookie wins — do not mix the two in one
client.

### Scopes

A scope is `<module>:<read|write>`. The full set:

| Module | Read | Write |
|---|---|---|
| Vendors | `vendors:read` | `vendors:write` |
| Applications & cycles | `applications:read` | `applications:write` |
| Projects & matching | `projects:read` | `projects:write` |
| Market intelligence | `intel:read` | — |
| Integrations & event log | `integrations:read` | `integrations:write` |
| Administration | `admin:read` | `admin:write` |

Which operation each scope unlocks is declared in one place,
`apps/api/vendoriq_api/security/permissions.py`, and the same table answers for people and
for machines. That file is the authority; `docs/openapi.yaml` names the operation ids it is
keyed by.

`GET /api/auth/me` is **not** available to an API key — it is a person's endpoint, with no
scope attached — so a machine client cannot ask "what may I do?" and should be configured
with the scopes it needs. A call outside them answers `403` with `details.operation` naming
the operation that was refused, which is enough to diagnose a misconfigured key.

**Two closures are deliberate and permanent:**

* **A key can never mint another key.** `createApiKey`, `patchApiKey` and `revokeApiKey` have
  no scope at all, so no combination of scopes reaches them. A leaked key cannot become a
  permanent foothold.
* **A key can never manage webhooks.** Redirecting the event stream to a new endpoint is a
  person's decision, made in the UI by an administrator.

### Revocation

`DELETE /api/integrations/api-keys/{api_key_id}` deactivates the key and stamps
`revoked_at`. Both are checked on **every** request, so the next call with that key is
anonymous — there is no cache to expire and no token lifetime to wait out. A revoked key can
never be reactivated; its plaintext is gone, so there is nothing to reactivate.

---

## 3. Webhooks

### Subscribing

An administrator subscribes at `/integrations` → *Webhooks*, or:

```http
POST /api/integrations/webhooks
{ "url": "https://acme.example/vendoriq/hook",
  "events": ["vendor.prequalified", "application.submitted",
             "document.expiring", "project.matched"] }
```

The response carries `secret` — **this once only**, for the same reason the API key is shown
once. Store it where the receiving service can read it.

Subscribable event types are the whole event log: `vendor.registered`, `vendor.invited`,
`vendor.prequalified`, `vendor.rejected`, `vendor.suspended`, `application.submitted`,
`application.decided`, `document.uploaded`, `document.expiring`, `project.matched`,
`model.published`, `sync.completed`.

### What arrives

```http
POST /vendoriq/hook HTTP/1.1
Content-Type: application/json
X-VendorIQ-Signature: t=1787822042,v1=bf4fafa57c01d369c92e4327b76002f52c6e85be7442cad1760834786fd7df48
X-VendorIQ-Event: vendor.prequalified
X-VendorIQ-Delivery: 0d5b7c31-2e64-4f09-8b1a-3c7d9e0f2a48
X-VendorIQ-Attempt: 1
User-Agent: VendorIQ-Webhook/1.0
```

```json
{"created_at":"2026-08-26T09:14:02+00:00","delivered_at":"2026-08-26T09:14:02+00:00","delivery_id":"0d5b7c31-2e64-4f09-8b1a-3c7d9e0f2a48","entity_id":"b2c4e9f1-5a67-4c8d-90ab-11f2d3c4e5f6","entity_type":"vendor","event_id":"6f1d0a2c-9b3e-4d77-9a10-2c5f8e41b7d3","payload":{"class":"B","external_ref":"ERP-4471","score":84.3,"valid_until":"2027-08-26"},"type":"vendor.prequalified"}
```

The body is serialised with sorted keys and no spaces, so the bytes are reproducible.

### Verifying the signature

The signed message is **the delivery timestamp, a dot, and the raw request body**:

```
signed_message = b"<t>." + raw_body
signature      = hex(HMAC-SHA256(secret, signed_message))
```

Three rules, and each one matters:

1. **Verify before you parse.** Hash the bytes you read off the socket. A body that
   re-serialises to equivalent JSON is not the same bytes, and re-serialising before hashing
   is how a signature check becomes decorative.
2. **Compare in constant time.** `hmac.compare_digest` in Python, `crypto.timingSafeEqual` in
   Node.
3. **Check the timestamp.** `t` is inside the signed message, so it cannot be moved without
   breaking the signature — but a genuine old delivery can be captured and replayed. Reject
   anything more than five minutes from your own clock.

#### Worked example

These numbers are real: they are produced by
`vendoriq_api.services.webhooks.sign` and reproduced by the snippets below.

```
secret         whsec_3aK1qP9vY2mZ8rT6bN4xL0sD7fH5jC1e
t              1787822042
raw body       {"created_at":"2026-08-26T09:14:02+00:00","delivered_at":"2026-08-26T09:14:02+00:00","delivery_id":"0d5b7c31-2e64-4f09-8b1a-3c7d9e0f2a48","entity_id":"b2c4e9f1-5a67-4c8d-90ab-11f2d3c4e5f6","entity_type":"vendor","event_id":"6f1d0a2c-9b3e-4d77-9a10-2c5f8e41b7d3","payload":{"class":"B","external_ref":"ERP-4471","score":84.3,"valid_until":"2027-08-26"},"type":"vendor.prequalified"}
signature      bf4fafa57c01d369c92e4327b76002f52c6e85be7442cad1760834786fd7df48
header         X-VendorIQ-Signature: t=1787822042,v1=bf4fafa57c01d369c92e4327b76002f52c6e85be7442cad1760834786fd7df48
```

Change `"class":"B"` to `"class":"A"` — one byte — and the signature no longer verifies. That
is the attack this exists to stop: a receiver being told a vendor is class A when the
commission graded it B.

**Python**

```python
import hmac, time
from hashlib import sha256


def verify(secret: str, header: str, raw_body: bytes, tolerance: int = 300) -> bool:
    parts = dict(part.split("=", 1) for part in header.split(","))
    timestamp = int(parts["t"])
    if abs(time.time() - timestamp) > tolerance:
        return False  # replay
    expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + raw_body, sha256).hexdigest()
    return hmac.compare_digest(expected, parts["v1"])
```

**Node**

```js
import crypto from 'node:crypto';

export function verify(secret, header, rawBody, tolerance = 300) {
  const parts = Object.fromEntries(header.split(',').map((p) => p.split('=')));
  const timestamp = Number(parts.t);
  if (Math.abs(Date.now() / 1000 - timestamp) > tolerance) return false;
  const expected = crypto
    .createHmac('sha256', secret)
    .update(Buffer.concat([Buffer.from(`${timestamp}.`), rawBody]))
    .digest('hex');
  const given = Buffer.from(parts.v1, 'hex');
  const mine = Buffer.from(expected, 'hex');
  return given.length === mine.length && crypto.timingSafeEqual(given, mine);
}
```

In Express, `rawBody` means `express.raw({ type: 'application/json' })` — `express.json()`
has already thrown the bytes away.

### Delivery, retry and failure

* Delivery is **asynchronous and after commit**. The request that prequalified a vendor is
  never slowed by your endpoint and never fails because of it; an event from a transaction
  that rolled back is never delivered at all.
* **Answer 2xx quickly.** Anything else is a failure. A 5xx, a 429 or a connection failure is
  retried three times with exponential backoff (1 s, 2 s); a 4xx is not retried, because a
  receiver that rejected the payload will reject it again.
* **Each attempt is signed afresh**, so a retry after a backoff still falls inside your
  tolerance window. Use `X-VendorIQ-Delivery` (stable across attempts) to make your handler
  idempotent, and `X-VendorIQ-Attempt` to log the retry.
* `failure_count` on the subscription counts consecutive failures and resets on the first
  success. It is visible on the *Webhooks* tab.

### Testing an endpoint

`POST /api/integrations/webhooks/{webhook_id}/test` sends one signed delivery immediately,
synchronously and without retry, and returns exactly what your endpoint answered:

```json
{ "delivered": true, "status_code": 200, "duration_ms": 41, "error": null }
```

The test payload has `"type": "webhook.test"`; treat it as a health check, not as a domain
event.

---

## 4. The event log

Everything the webhooks deliver is also a row in the event log. A system that would rather
poll than expose an endpoint reads it directly:

```http
GET /api/events?since=2026-08-26T09:14:02Z&page_size=100
X-API-Key: …            # scope: integrations:read
```

```json
{ "items": [ { "id": "6f1d…", "type": "vendor.prequalified", "entity_type": "vendor",
               "entity_id": "b2c4…", "payload": { … },
               "created_at": "2026-08-26T09:14:02.481773+00:00" } ],
  "total": 1, "page": 1, "page_size": 100 }
```

Filter by `type` (repeatable), `entity_type`, `entity_id` and `since`. Events are returned
newest first.

**Resuming.** Keep the `created_at` of the last event you processed and pass it as `since` on
the next poll; `since` is strictly greater-than. Timestamps are stamped per event rather than
per transaction precisely so that two events emitted by one request can be distinguished and
a poller can resume between them.

The log is append-only. Nothing rewrites or deletes a row, so replaying the whole stream from
the beginning reconstructs the same history.

---

## 5. `external_ref` — mapping to your own identifiers

Vendors and projects each carry `external_ref`: a free-text, indexed field holding **your**
identifier for that row.

```http
PATCH /api/vendors/{vendor_id}
{ "external_ref": "ERP-4471" }
```

Use it to avoid keeping a translation table:

* It comes back on every vendor and project payload, and on the webhook payloads that carry
  those entities.
* The adapters use it as the **remote key**: when a connector calls your endpoint it
  substitutes `external_ref` if it is set, and falls back to the VÖEN otherwise. So setting
  `external_ref` is also how you tell VendorIQ what to ask your ERP about.
* VendorIQ's own ids are UUIDs and are stable; `external_ref` is not unique and is never used
  as a key by VendorIQ itself. Keep it unique on your side if you rely on it.

The VÖEN (ten digits, unique across the register) is the other natural join key, and is what
the Excel importer matches an uploaded form on.

---

## 6. Adapters — pushing data in

Every source of vendor data is an adapter with one interface (brief §5):

```python
pull(vendor, since) -> Observation[]
```

| Key | State | What it does |
|---|---|---|
| `generic_rest` | **working** | Calls a configured per-vendor JSON endpoint with an auth header and a field map |
| `csv` | **working** | The same, reading `text/csv` — one header row, one row per vendor |
| `erp_1c`, `erp_sap`, `erp_odoo` | **mocked** | Same class, same configuration, same output; a fixture response instead of the HTTP GET |
| `registry` | **stub** | Always answers "not configured" — see below |
| `excel` | **working** | The eleven-sheet application form, via the two-step import |

### The generic REST contract

Publish an endpoint that answers a GET with a JSON object about one vendor. VendorIQ calls it
with the vendor's remote key — substituted into `{vendor}` if your URL template names it,
appended as `?vendor=` otherwise — and adds `?since=<ISO-8601>` when it is asking for
changes.

```http
GET https://acme.example/vendoriq/vendors/ERP-4471?since=2026-07-01T00%3A00%3A00%2B00%3A00
Authorization: Bearer <the secret configured in VendorIQ>
Accept: application/json
```

```json
{ "financials": { "turnover_avg_3y": "4 812 500,00", "equity": 1150000 },
  "headcount":  { "total": 64, "engineers": 9 },
  "projects":   { "completed": 7, "largest_value": 5250000, "ongoing": 3 } }
```

The **field map** turns that into field codes, and is configured per vendor at
`/integrations/adapters/generic_rest`:

```json
{ "financials.turnover_avg_3y": "B.1",
  "financials.equity":          "B.2",
  "headcount.total":            "E.1",
  "headcount.engineers":        "E.2",
  "projects.completed":         "C.1",
  "projects.largest_value":     "C.2",
  "projects.ongoing":           "C.3" }
```

A dotted path walks the response; a numeric segment indexes a list
(`d.results.0.AnnualTurnover`, which is what the SAP mock's map looks like). Numbers survive
the formats a real export produces — `"4 812 500,00"`, `"1,250"`, `"85%"` — because the same
normalisation the Excel importer uses is applied here. A path your payload does not carry
produces nothing at all: **a source that does not know a field has said nothing about it**,
which is not the same as saying it is empty.

### What a pull writes

Each value becomes an **observation**: field code, value, `source`, `source_ref`, timestamp
(ADR-004). There is no `vendor.turnover` column; the current value of a field is the
observation from the most trusted source, newest first, in the order of spec §6.6:

| Source | Trust rank |
|---|---|
| `registry` | 1 (highest) |
| `api` — every ERP connector | 2 |
| `document` — a verified PDF | 3 |
| `portal`, `excel` | 4 |
| `manual` | 5 |

So an ERP pull refreshes a turnover figure over the vendor's own form entry, and never over a
registry check.

Every run also writes a `SyncLog` row — adapter, vendor, start and finish, records written,
warnings, result — readable at `GET /api/integrations/sync-log` and emitted as a
`sync.completed` event.

### What an adapter does when it cannot read

It says so. It does not return a plausible value and it does not return an empty result
pretending the source answered.

* Not configured, disabled, or no field map → `409` from `POST
  /integrations/adapters/{adapter}/sync`, and **no sync-log row**: nothing ran.
* Configured but unreachable, unauthorised or unparsable → `202` with `result: "failed"`,
  `fields_written: 0` and the reason as a bilingual warning: the run happened and failed.

### The registry adapter

`registry` answers `409 registry_not_configured`, always. Registry is trust rank 1 and covers
A.4 tax clearance and A.1 licence validity — both **knock-out** criteria, where a raw value of
0 rejects a vendor regardless of its score. A stub that returned a pass would put an invented
verification at the top of the trust order, where nothing else can correct it. When the State
Tax Service e-services and the construction licence register become reachable, `pull` is
implemented in `adapters/registry.py` and the refusal goes with it.

---

## 7. The Excel import

Two operations, because a human has to look at the file before it becomes the register's
truth.

```http
POST /api/integrations/excel-import/preview        # multipart: file, kind, vendor_id
```

Parses the workbook and **writes nothing**. The response carries the mapped fields with the
current value beside each (`will_change`), the section tables, the document checklist, the
derived raw indicators, and the anomalies the parser found. `.xlsx` only — the extension, the
declared content type and the ZIP structure are all checked.

```http
POST /api/integrations/excel-import/runs
{ "preview_id": "…", "accept_field_codes": ["A.3", "B.1"] }
```

Writes the confirmed fields as observations with `source: "excel"`, and returns the sync-log
row. A preview is valid for one hour and can be confirmed exactly once; a second attempt, or
one after the hour, answers `404` with `details.reason` of `consumed` or `expired`.

Anomaly codes you may see (the WESA fixture produces eight of them):
`stale_certificate`, `mixed_percent_format`, `multi_value_cell`, `no_expiry_literal`,
`mandatory_cell_empty`, `currency_label_mismatch`, `unknown_field_code`, `unparsable_date`,
`unparsable_value`, `document_status_missing`, `missing_sheet`. Each carries `message_az`,
`message_en`, a required `severity` (`error` | `warning` | `info`), and the sheet and cell
where it was seen. Triage on `severity`, not on `code`: the WESA form's one `error` is the
tax-clearance certificate 66 months out of date, and that is the finding that should stop an
import rather than annotate it.

`SyncLog.warnings` uses the same shape for **adapter** failures, whose `code` names the
adapter problem instead — `source_unreachable`, `source_error_status`, `source_unparsable`,
`adapter_not_configured`, `adapter_disabled`, `adapter_no_field_map`, `registry_not_configured`,
`mock_record_not_found`, `workbook_not_found`, `workbook_unreadable`. Treat `code` as an open
string and branch on `severity`.

---

## 8. A worked subscription, end to end

1. An administrator creates a key with `vendors:read` and stores it in your service.
2. An administrator subscribes `https://acme.example/vendoriq/hook` to
   `vendor.prequalified`, and stores the secret.
3. Your service is called with a signed delivery. It verifies the signature against the raw
   body, checks `t`, and answers `204` in under a second.
4. It reads `payload.external_ref` to find its own record, or calls
   `GET /api/vendors/{entity_id}` with the API key for the full profile.
5. If it was down, it catches up with
   `GET /api/events?type=vendor.prequalified&since=<last processed>`.

Nothing in that sequence depends on the UI: every action the VendorIQ screens perform is the
same public API call (brief §2, "API-first"; no business logic in the frontend).

---

## 9. Limits and things to know

* **A preview is single-use and expires after an hour.** It is a row in `import_preview`, so
  the confirmation may reach any API process; `consumed_at` is stamped in the same
  transaction as the observations, so a double-clicked confirm answers `404` with
  `details.reason: "consumed"` rather than importing the workbook twice. An expired one
  answers `404` with `details.reason: "expired"` — re-upload the file.
* **Adapter configuration is per vendor**, one row per `(adapter, vendor_id)` in
  `adapter_config`, including the credential, which is stored so it can be used and is never
  returned by the API (`secret_masked`; echo the mask back to keep it).
* **The mocked ERP fixtures answer for fictional vendors** with VÖENs `1000000001`–
  `1000000004`. They deliberately hold no data about the real companies in the register.
* **Rate limiting** applies to the authentication endpoints (OTP and password), not to
  API-key traffic in this release.
