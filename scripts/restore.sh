#!/usr/bin/env bash
#
# Restore a snapshot taken by backup.sh over a running stack.
#
#   scripts/restore.sh SNAPSHOT_DIRECTORY [--force]
#
# This destroys the current contents of the database and the document bucket. It asks first,
# and it checks first:
#
#   * both halves of the snapshot must be present — a database without its documents restores
#     rows whose every attachment is a 404 the application cannot detect;
#   * the snapshot's Alembic revision must match the running code's, unless --force. A dump
#     from an older schema loads cleanly and then fails on the first query touching a column
#     added since, which is a long way from here.
#
# `--clean --if-exists` means the restore is idempotent: run it twice and the second run
# arrives at the same place.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="${COMPOSE_PROJECT_NAME:-vendoriq}"

snapshot="${1:-}"
force="${2:-}"
if [[ -z "$snapshot" ]]; then
	echo "usage: scripts/restore.sh SNAPSHOT_DIRECTORY [--force]" >&2
	exit 64
fi
snapshot="$(cd "$snapshot" && pwd)"

for required in database.dump documents manifest.txt; do
	[[ -e "$snapshot/$required" ]] || {
		echo "not a snapshot: $snapshot/$required is missing" >&2
		exit 65
	}
done

cd "$REPO_ROOT/infra"
# `docker compose` reads infra/.env for POSTGRES_USER and the rest; so do we, for the values
# the helper containers need. An `&&` chain here would be a trap: under `set -e` a false test
# is a failed statement, so a host without an .env file would exit before doing any work.
# Read .env as compose does — KEY=VALUE pairs, comments skipped — NOT by sourcing it.
# Sourcing executes the file as shell, and the first unquoted value with a space in it
# (`TLS_DIRECTIVE=tls internal`, straight from .env.example) becomes a command invocation.
# Found by running, like everything else in this file's history.
if [[ -f .env ]]; then
	while IFS= read -r line; do
		[[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]] || continue
		export "${line?}"
	done <.env
fi
POSTGRES_USER="${POSTGRES_USER:-vendoriq}"
POSTGRES_DB="${POSTGRES_DB:-vendoriq}"
S3_BUCKET="${S3_BUCKET:-vendoriq}"

snapshot_revision="$(sed -n 's/^alembic_revision=//p' "$snapshot/manifest.txt")"
running_revision="$(docker compose exec -T api alembic current 2>/dev/null </dev/null | grep -oE '^[0-9a-f]+' | head -1 || true)"
if [[ "$force" != "--force" && -n "$running_revision" && "$snapshot_revision" != "$running_revision" ]]; then
	cat >&2 <<-MESSAGE
		schema mismatch — refusing to restore.

		  snapshot: $snapshot_revision
		  running:  $running_revision

		Check out the code at the snapshot's revision and restore there, or pass --force if
		you have decided the difference does not matter.
	MESSAGE
	exit 66
fi

cat "$snapshot/manifest.txt"
echo
read -r -p "This replaces database '$POSTGRES_DB' and bucket '$S3_BUCKET'. Type the database name to continue: " confirmation
[[ "$confirmation" == "$POSTGRES_DB" ]] || {
	echo "aborted" >&2
	exit 1
}

# The worker writes to both stores; leaving it running during a restore is a race with a
# process that has no idea a restore is happening.
echo "→ stopping worker and api"
docker compose stop worker api >/dev/null

echo "→ database"
docker compose exec -T db \
	pg_restore --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --clean --if-exists --no-owner \
	<"$snapshot/database.dump"

echo "→ documents"
docker run --rm \
	--network "${PROJECT}_default" \
	--volume "$snapshot/documents:/backup:ro" \
	--entrypoint sh minio/mc -c "
		mc --quiet alias set snapshot http://minio:9000 '${MINIO_ROOT_USER:-vendoriq}' '${MINIO_ROOT_PASSWORD:-vendoriq-secret}' &&
		mc --quiet mb --ignore-existing 'snapshot/$S3_BUCKET' &&
		mc --quiet mirror --overwrite --remove /backup 'snapshot/$S3_BUCKET'
	"

echo "→ starting api and worker"
docker compose start api worker >/dev/null

echo "✓ restored from $snapshot"
