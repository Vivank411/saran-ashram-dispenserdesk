#!/bin/bash
# Schedules encrypted backups and periodic restoration tests with crond.
set -euo pipefail
[ -s /run/secrets/backup_passphrase ] || { echo "Missing /run/secrets/backup_passphrase" >&2; exit 1; }
ENV_FILE=/etc/backup.env
# Pass the container environment to cron jobs.
env | grep -E '^(PG|POSTGRES_|BACKUP_|OFFSITE_|TZ)' | sed 's/^/export /' > "$ENV_FILE"
cat > /etc/crontabs/root <<EOF
${BACKUP_SCHEDULE:-0 2 * * *} . $ENV_FILE && /usr/local/bin/backup.sh >> /backups/backup.log 2>&1
${RESTORE_TEST_SCHEDULE:-30 3 * * 0} . $ENV_FILE && /usr/local/bin/restore-test.sh >> /backups/restore-test.log 2>&1
EOF
echo "Backup schedule: ${BACKUP_SCHEDULE:-0 2 * * *} | restore test: ${RESTORE_TEST_SCHEDULE:-30 3 * * 0}"
exec crond -f -l 8
