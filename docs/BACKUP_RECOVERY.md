# Backup and disaster recovery

Cloud synchronisation is **not** a backup. Each database is backed up independently.

## What runs automatically

The `backup` container in each Compose stack runs:

| Job | Default schedule | Script |
|---|---|---|
| Encrypted backup | daily 02:00 (hospital) / 02:30 (cloud) | `deploy/backup/backup.sh` |
| Restoration test | weekly, Sunday 03:30 / 04:00 | `deploy/backup/restore-test.sh` |

* `pg_dump -Fc` is encrypted with **GPG AES-256** using `deploy/secrets/backup_passphrase`. A `.sha256` checksum is written next to each file.
* Backups are written to `BACKUP_DIR` on the host. Put it on a **separate disk or NAS**, not the database disk.
* Files older than `BACKUP_RETENTION_DAYS` (default 30) are deleted.
* Off-site copy: set `OFFSITE_RSYNC_TARGET=user@host:/path` and place an SSH key at `BACKUP_DIR/.ssh/id_ed25519`. For example, hospital backups go to the cloud server or a second site, and cloud backups go to object storage.
* Recommended policy: 7 daily + 4 weekly + 12 monthly copies off-site.
* The restoration test restores the newest backup into a scratch database and checks:
  * the migration version
  * referential integrity
  * that bill totals equal the sum of their items
  * that stock equals the ledger sum (hospital only)

  Results go to `BACKUP_DIR/restore-test.log`.

## Manual backup (always before an upgrade)

```bash
docker compose -f docker-compose.hospital.yml --env-file .env.hospital exec backup backup.sh
```

## Restoring the hospital database

1. Stop the application, but keep the database running:
   ```bash
   docker compose -f docker-compose.hospital.yml --env-file .env.hospital stop api web
   ```
2. Restore. The checksum is verified first, and the restore refuses to overwrite the live database without confirmation:
   ```bash
   docker compose -f docker-compose.hospital.yml --env-file .env.hospital exec -e CONFIRM_RESTORE=yes backup \
     restore.sh /backups/hospital-20261114T020000Z.dump.gpg
   ```
3. **Reconcile with the cloud.** Bills confirmed after the backup may exist only in the cloud replica.
   * Compare `select max(seq) from outbox_events` (restored hospital) with `select max(seq) from inbox_events` (cloud).
   * If the cloud is ahead, re-enter or import those bills (from `bills`, `bill_items` and `inventory_movements` after the backup time) and record that in the audit log.
   * Reset the cloud's ordering marker so new hospital events are accepted. On the cloud DB, run:
     `update sync_state set value = jsonb_build_object('seq', <hospital max seq>) where key = 'last_applied';`
4. Start the stack with `docker compose ... up -d`, then check the Sync monitor and resolve any conflicts with a review note.

## Restoring the cloud database

Restore the latest cloud backup the same way (`docker-compose.cloud.yml`). The hospital automatically re-sends any events newer than the backup, and the inbox de-duplicates by event id.

If every cloud backup is lost:

1. Start an empty stack (migrations create the schema).
2. Recreate the Admin with the **same id** as in the hospital's `users` table (`create-admin --id`). Recreate the billers, or restore just the `users` table from any backup.
3. On the hospital, run `python -m app.cli seed-stock /data/stock.csv`, then re-queue the history with `update outbox_events set status='pending'`. This is safe because the inbox ignores duplicates.

## Disaster scenarios

| Event | Action |
|---|---|
| Hospital server disk failure | New machine → INSTALL_HOSPITAL steps 1–5 → restore latest backup → reconcile (step 3) |
| Ransomware on hospital PCs | The server only exposes 443 to the LAN; if it is affected, restore from an off-site copy |
| Cloud provider outage | The hospital keeps working; restore the cloud on a new VPS if needed |
| Power cut | UPS safe shutdown; PostgreSQL recovers on boot; containers restart automatically |
| Lost backup passphrase | Backups are unrecoverable — keep two sealed offline copies |

## Checklist

* Daily: the top bar shows "Cloud in sync"; investigate any red banner.
* Weekly: read `backup.log` and `restore-test.log`, and confirm the off-site copies arrived.
* Quarterly: full restore drill on a spare machine, recording how long it took.
* Yearly: rotate `JWT_SECRET` (signs everyone out) and `SYNC_SHARED_SECRET` (change both servers together).
