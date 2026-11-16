#!/bin/bash
# Restore an encrypted backup into a database.
#   restore.sh /backups/hospital-20261114T020000Z.dump.gpg [target_db]
# Stop the api container first:  docker compose stop api
set -euo pipefail
FILE="${1:?backup file}"
TARGET="${2:-${POSTGRES_DB}}"
export PGPASSWORD="${POSTGRES_PASSWORD}"
sha256sum -c "${FILE}.sha256"
if [ "${TARGET}" = "${POSTGRES_DB}" ] && [ "${CONFIRM_RESTORE:-}" != "yes" ]; then
  echo "Refusing to overwrite the live database. Re-run with CONFIRM_RESTORE=yes." >&2
  exit 1
fi
psql -h "${PGHOST:-db}" -U "${POSTGRES_USER}" -d postgres -tc "SELECT 1 FROM pg_database WHERE datname='${TARGET}'" | grep -q 1 \
  || psql -h "${PGHOST:-db}" -U "${POSTGRES_USER}" -d postgres -c "CREATE DATABASE \"${TARGET}\""
gpg --batch --pinentry-mode loopback --passphrase-file /run/secrets/backup_passphrase -d "${FILE}" \
  | pg_restore -h "${PGHOST:-db}" -U "${POSTGRES_USER}" -d "${TARGET}" --clean --if-exists --no-owner
echo "Restored ${FILE} into ${TARGET}"
