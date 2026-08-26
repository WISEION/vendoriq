#!/usr/bin/env bash
#
# Take one snapshot of a running VendorIQ stack.
#
#   scripts/backup.sh [DESTINATION]        (default: ./var/backups)
#
# A snapshot is a directory holding three things that only mean anything together:
#
#   database.dump   pg_dump custom format — the rows
#   documents/      a mirror of the object-storage bucket — the files those rows point at
#   manifest.txt    what this snapshot is, and which schema it was taken from
#
# The pairing is the point. `document.storage_key` is a reference, not a blob: a database
# restored beside somebody else's bucket gives you an application whose every download is a
# 404, and which cannot tell you so — the row insists the file is there. So both halves are
# written into one directory, and restore.sh refuses a directory missing either.
#
# The manifest records the Alembic revision the dump came from. Restoring a dump into a
# schema that has moved on is the failure that looks like success until the first query
# against a column that was added afterwards; restore.sh compares the two and stops.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESTINATION="${1:-$REPO_ROOT/var/backups}"
PROJECT="${COMPOSE_PROJECT_NAME:-vendoriq}"

cd "$REPO_ROOT/infra"
# `docker compose` reads infra/.env for POSTGRES_USER and the rest; so do we, for the values
# the helper containers need. An `&&` chain here would be a trap: under `set -e` a false test
# is a failed statement, so a host without an .env file would exit before doing any work.
if [[ -f .env ]]; then
	set -a
	# shellcheck disable=SC1091  # deployment-local, not in the repository
	. ./.env
	set +a
fi

POSTGRES_USER="${POSTGRES_USER:-vendoriq}"
POSTGRES_DB="${POSTGRES_DB:-vendoriq}"
S3_BUCKET="${S3_BUCKET:-vendoriq}"

stamp="$(date -u +%Y%m%d-%H%M%SZ)"
snapshot="$DESTINATION/vendoriq-$stamp"
mkdir -p "$snapshot/documents"

echo "→ snapshot $snapshot"

# ── rows ────────────────────────────────────────────────────────────────────────────────
# Custom format (-Fc), so restore can run --clean --if-exists and does not need the dump to
# be replayed as a script by a superuser.
echo "→ database"
docker compose exec -T db \
	pg_dump --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --format=custom \
	>"$snapshot/database.dump"

# ── files ───────────────────────────────────────────────────────────────────────────────
# `mc mirror` rather than a tar of the volume: the volume is being written to while we read
# it, and MinIO's on-disk layout is its own business. The bucket contents are the contract.
echo "→ documents"
docker run --rm \
	--network "${PROJECT}_default" \
	--volume "$snapshot/documents:/backup" \
	--entrypoint sh minio/mc -c "
		mc --quiet alias set snapshot http://minio:9000 '${MINIO_ROOT_USER:-vendoriq}' '${MINIO_ROOT_PASSWORD:-vendoriq-secret}' &&
		mc --quiet mirror --overwrite --remove 'snapshot/$S3_BUCKET' /backup
	"

# ── what this is ────────────────────────────────────────────────────────────────────────
# `|| true`: a stack whose API is down still deserves a backup of the rows it has. The
# manifest records the revision as unknown and restore.sh then has nothing to compare.
revision="$(docker compose exec -T api alembic current 2>/dev/null | grep -oE '^[0-9a-f]+' | head -1 || true)"
documents=$(find "$snapshot/documents" -type f | wc -l)
{
	echo "taken_at=$stamp"
	echo "alembic_revision=${revision:-unknown}"
	echo "database=$POSTGRES_DB"
	echo "bucket=$S3_BUCKET"
	echo "document_files=$documents"
	echo "database_bytes=$(stat -c %s "$snapshot/database.dump")"
} >"$snapshot/manifest.txt"

echo
cat "$snapshot/manifest.txt"
echo
echo "✓ $snapshot"
if [[ "${revision:-unknown}" == "unknown" ]]; then
	echo "! the Alembic revision could not be read; restore.sh will not be able to check it" >&2
fi
