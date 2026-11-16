#!/bin/bash
# Periodic restoration test: restore the newest backup into a scratch database and verify integrity.
set -euo pipefail
export PGPASSWORD="${POSTGRES_PASSWORD}"
LATEST="$(ls -1t /backups/${BACKUP_PREFIX}-*.dump.gpg 2>/dev/null | head -1)"
[ -n "${LATEST}" ] || { echo "No backups found"; exit 1; }
DB="restore_test_$(date +%s)"
trap 'psql -h "${PGHOST:-db}" -U "${POSTGRES_USER}" -d postgres -qc "DROP DATABASE IF EXISTS ${DB}"' EXIT

/usr/local/bin/restore.sh "${LATEST}" "${DB}" >/dev/null
q() { psql -h "${PGHOST:-db}" -U "${POSTGRES_USER}" -d "${DB}" -tAc "$1"; }

FAIL=0
check() { if [ "$2" = "$3" ]; then echo "  PASS  $1"; else echo "  FAIL  $1 (got '$2', expected '$3')"; FAIL=1; fi; }
echo "$(date -u +%FT%TZ) restoration test of ${LATEST}"
check "migration version present" "$(q "select count(*) from alembic_version")" "1"
check "medicines restored" "$( [ "$(q "select count(*) from medicines")" -gt 0 ] && echo yes)" "yes"
check "bill items reference bills" "$(q "select count(*) from bill_items i left join bills b on b.id=i.bill_id where b.id is null")" "0"
check "bill totals equal item sums" "$(q "select count(*) from bills b where b.total <> (select coalesce(sum(amount),0) from bill_items where bill_id=b.id)")" "0"
if [ "${BACKUP_PREFIX}" = "hospital" ]; then  # the hospital ledger includes opening balances
  check "stock equals ledger sum (per medicine)" \
    "$(q "select count(*) from medicines m where m.stock <> coalesce((select sum(qty_change) from inventory_movements v where v.medicine_id=m.id), m.stock)")" "0"
  check "outbox sequence has no duplicates" "$(q "select count(*) - count(distinct event_id) from outbox_events")" "0"
fi
[ "${FAIL}" = 0 ] && echo "RESULT: PASSED" || { echo "RESULT: FAILED"; exit 1; }
