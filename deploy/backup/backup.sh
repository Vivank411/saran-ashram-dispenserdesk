#!/bin/bash
# Encrypted PostgreSQL backup: pg_dump (custom format) -> GPG AES-256 -> /backups, with checksum and retention.
set -euo pipefail
export PGPASSWORD="${POSTGRES_PASSWORD}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="/backups/${BACKUP_PREFIX}-${TS}.dump.gpg"

pg_dump -h "${PGHOST:-db}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -Fc --no-owner \
  | gpg --batch --yes --pinentry-mode loopback --passphrase-file /run/secrets/backup_passphrase \
        --symmetric --cipher-algo AES256 -o "${OUT}.partial"
mv "${OUT}.partial" "${OUT}"
sha256sum "${OUT}" > "${OUT}.sha256"
echo "$(date -u +%FT%TZ) backup written: ${OUT} ($(du -h "${OUT}" | cut -f1))"

# Retention
find /backups -maxdepth 1 -name "${BACKUP_PREFIX}-*.dump.gpg*" -mtime "+${BACKUP_RETENTION_DAYS:-30}" -print -delete

# Separate storage (off-site copy), e.g. OFFSITE_RSYNC_TARGET=backup@nas.hospital.lan:/srv/dispensary
if [ -n "${OFFSITE_RSYNC_TARGET:-}" ]; then
  rsync -a -e "ssh -o StrictHostKeyChecking=accept-new -i /backups/.ssh/id_ed25519" \
    "${OUT}" "${OUT}.sha256" "${OFFSITE_RSYNC_TARGET}/"
  echo "copied to ${OFFSITE_RSYNC_TARGET}"
fi
