#!/usr/bin/env bash
# Create the vendoriq role and the two databases on a locally running PostgreSQL 16.
# Idempotent: safe to run again.
set -euo pipefail

ROLE="${DB_ROLE:-vendoriq}"
PASSWORD="${DB_PASSWORD:-vendoriq}"
DATABASES=("${ROLE}" "${ROLE}_test")

psql_as_superuser() {
  if [ "$(id -u)" = "0" ]; then
    su postgres -c "psql -v ON_ERROR_STOP=1 -c \"$1\""
  else
    sudo -u postgres psql -v ON_ERROR_STOP=1 -c "$1"
  fi
}

exists() {
  if [ "$(id -u)" = "0" ]; then
    su postgres -c "psql -tAc \"$1\""
  else
    sudo -u postgres psql -tAc "$1"
  fi
}

if [ "$(exists "SELECT 1 FROM pg_roles WHERE rolname='${ROLE}'")" != "1" ]; then
  psql_as_superuser "CREATE ROLE ${ROLE} LOGIN PASSWORD '${PASSWORD}' CREATEDB"
  echo "role ${ROLE} created"
else
  echo "role ${ROLE} already exists"
fi

for db in "${DATABASES[@]}"; do
  if [ "$(exists "SELECT 1 FROM pg_database WHERE datname='${db}'")" != "1" ]; then
    psql_as_superuser "CREATE DATABASE ${db} OWNER ${ROLE}"
    echo "database ${db} created"
  else
    echo "database ${db} already exists"
  fi
done
