# VendorIQ — operations runbook

For whoever deploys and keeps VendorIQ running. Everything here assumes Docker and the
Compose plugin on the target host; nothing else is required of it.

> **What has and has not been executed.** The build host for this project had no Docker
> daemon (BUILD_BRIEF §9), so the commands below have not been run end to end anywhere. What
> *has* been verified is the configuration they use: `apps/api/tests/test_compose_profiles.py`
> renders the production stack with `docker compose config` and asserts what comes out, and
> `apps/api/tests/test_backup_scripts.py` exercises the restore script's refusals. The
> containers themselves — image builds, `pg_restore`, `mc mirror`, ACME — are unverified.
> Treat the first deployment as a rehearsal, on a host you can throw away.

## 1. What runs

Six containers, one network, three volumes.

| Container | What it is | Reachable from outside |
|---|---|---|
| `caddy` | TLS termination and reverse proxy | **yes** — 80 and 443 |
| `web` | the built single-page app on nginx | no |
| `api` | FastAPI; runs `alembic upgrade head` at start-up | no |
| `worker` | scheduled jobs (expiry notices, digests) | no |
| `db` | PostgreSQL 16 | no |
| `minio` | S3-compatible document storage | no |

Volumes: `db-data`, `minio-data`, `caddy-data` (which holds the issued certificates — losing
it means re-issuing, and Let's Encrypt rate-limits that).

In production only Caddy publishes a port. Everything else is reachable only over the
compose network, which is checked by a test rather than promised here.

## 2. Development stack

```bash
cp infra/.env.example infra/.env      # the defaults are fine for a laptop
make up                               # docker compose --profile dev up --build
```

Serves `http://localhost` with the seed loaded — the 13 real vendors with their Rev4
outcomes, the removable demo layer, and the accounts in `docs/TEST_ACCOUNTS.md`. The
database, MinIO console and API are published on the host as well (5432, 9001, 8000).

`AUTH_MODE=test` here: sign-in codes are shown in the UI. That is the whole reason the
production stack is a different command.

## 3. Production stack

### 3.1 Before the first deploy

1. A DNS `A`/`AAAA` record for the hostname, pointing at the host. Caddy obtains its
   certificate over HTTP-01, so this has to resolve *before* the first start or issuance
   fails and retries with a backoff.
2. Ports 80 and 443 reachable from the internet. 80 is not optional — it is what the ACME
   challenge uses, and Caddy redirects it to 443 afterwards.
3. An SMTP account that can send from the address you will put in `SMTP_FROM`. Without it
   nobody can sign in: staff and vendors both receive a code by e-mail.

### 3.2 Configuration

```bash
cp infra/.env.example infra/.env
openssl rand -hex 32                  # → SESSION_SECRET
```

Fill in `infra/.env`. The production overlay requires each of these and `docker compose`
refuses to render anything at all while one is missing, so there is no way to start the
stack half-configured:

| Variable | |
|---|---|
| `SESSION_SECRET` | 32 random bytes. Changing it later signs everyone out. |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | not the values in `.env.example` |
| `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` | likewise |
| `SMTP_HOST` / `SMTP_FROM` | and `SMTP_USER`, `SMTP_PASSWORD` if the relay authenticates |
| `DOMAIN` | the public hostname, e.g. `vendoriq.uniko.az` |
| `TLS_DIRECTIVE` | `tls ops@uniko.az` for automatic Let's Encrypt certificates |

`APP_ENV=production` and `AUTH_MODE=live` are not variables here — the overlay pins them, and
the API refuses to start if it is ever handed `AUTH_MODE=test` under `APP_ENV=production`.

Own certificates instead of ACME: mount them into the Caddy container and set
`TLS_DIRECTIVE=tls /etc/caddy/cert.pem /etc/caddy/key.pem`.

### 3.3 Start

```bash
make prod-up          # docker compose -f infra/docker-compose.yml \
                      #   -f infra/docker-compose.prod.yml --profile prod up --build -d
make prod-logs
```

The API applies migrations as it starts, so the first run creates the schema. Wait for
`caddy` to report the certificate obtained, then check:

```bash
curl -sSf https://$DOMAIN/health
```

### 3.4 The first user

A production stack starts **empty**. No seed runs and no accounts exist — deliberately, since
the seeded accounts have published passwords. Nothing can be done through the UI until there
is one user, and there is no screen that can create it, because every screen is behind the
sign-in. Create it from the container:

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml \
	exec api python -m vendoriq_api.seed create-admin \
	--email ops@uniko.az --name "Operations"
```

It asks for a password (twice, not echoed, never on the command line) and prints a TOTP
secret and enrolment URI **once**. Enrol the authenticator app before closing the terminal;
the secret cannot be read back afterwards from any endpoint or table you would want to use.

Then load the reference data the application needs to be usable — the categories and the two
scoring models, without the demo layer:

```bash
docker compose ... exec api python -m vendoriq_api.seed load --real
```

`--real` includes the 13 vendors and the TQS2026006 Rev4 cycle. For a genuinely blank system
that is not what you want; for Uni Ko it is exactly the starting position, since those are
their own vendors and their own Rev4 outcome.

Other staff accounts are created the same way with `--role manager|commission|officer`, or
through **Administration → Users** once the first administrator is in.

## 4. Backup

```bash
make backup                       # → var/backups/vendoriq-YYYYmmdd-HHMMSSZ/
```

A snapshot is a directory with three files that only mean anything together:

- `database.dump` — `pg_dump` custom format
- `documents/` — a mirror of the MinIO bucket
- `manifest.txt` — the timestamp, the Alembic revision, and the counts

The pairing is the point. `document.storage_key` is a reference, not a blob: a database
restored beside the wrong bucket gives you an application whose every download is a 404 and
which cannot tell you so, because as far as the row is concerned the file is there.

Copy the snapshot off the host. A backup on the disk you are protecting against is not one.
Run it from cron nightly and keep whatever retention your policy says; the script writes a
new directory each time and never deletes an old one.

## 5. Restore

```bash
make restore SNAPSHOT=var/backups/vendoriq-20260826-030000Z
```

It refuses a directory missing any of the three parts, refuses a snapshot whose Alembic
revision differs from the running code's (pass `--force` if you have decided it does not
matter), and asks you to type the database name before it does anything. Then it stops `api`
and `worker`, restores both halves, and starts them again — restoring under a running worker
is a race with a process that has no idea a restore is happening.

To restore onto a fresh host: deploy §3 first, at the code revision named in `manifest.txt`,
then restore. Do not create the administrator first — the restore replaces the whole
database, and the account would go with it.

## 6. Upgrading

```bash
make backup
git pull
make prod-up          # rebuilds the images and restarts
make prod-logs
```

The API runs `alembic upgrade head` at start-up, so a deploy that adds a migration applies it
before serving. A migration that fails leaves the container restarting; the logs carry the
reason, and the database is untouched because Alembic runs each migration in a transaction.

Roll back by checking out the previous revision and running `make prod-up` again. If the
upgrade applied a migration, that is not enough on its own — a downgrade is a restore from
the snapshot you took in the first line.

## 7. Routine checks

```bash
curl -sSf https://$DOMAIN/health                 # API and its database connection
make prod-logs                                   # everything
docker compose ... logs worker                   # the scheduled jobs, one line per run
docker system df                                 # images and volumes, when disk gets tight
```

The worker logs each job it runs and each notification it sends. Silence there is the signal
that expiry notices have stopped going out.

## 8. When something is wrong

**No certificate.** Caddy's log names the ACME failure. Almost always DNS not resolving to
this host yet, or port 80 not reachable. `docker compose ... logs caddy | grep -i acme`.

**Sign-in codes never arrive.** Check `SMTP_HOST` is set — with it empty the API writes mail
to the log instead of sending it, silently. `docker compose ... logs api | grep -i mail` shows
which of the two is happening. Then check the relay accepts your `SMTP_FROM`.

**The API restarts in a loop.** Read the first lines after each restart. A refused
configuration (`AUTH_MODE=test` with `APP_ENV=production`, a missing `SESSION_SECRET`) says so
in one line and exits; a failed migration says which revision.

**`docker compose` will not even print the configuration.** That is the overlay working as
designed: the error names the variable missing from `infra/.env`.

**Uploads fail, everything else works.** MinIO. `docker compose ... logs minio`, and check
`MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` match what the API is given — they are the same two
variables, so a mismatch means one of them was changed without restarting the API.

**Disk full.** `db-data` and `minio-data` grow; `var/backups` grows fastest of all if backups
are not being copied away and pruned.
