# Architecture

## Roles of the two servers

One codebase runs in two roles, selected by `APP_ROLE`.

| | Hospital (`APP_ROLE=hospital`) | Cloud (`APP_ROLE=cloud`) |
|---|---|---|
| Authoritative for | medicine stock, rates, bills, reversals, inventory ledger, adjustment approvals, low-stock alerts, threshold | user directory, OTP challenges |
| Holds a copy of | user directory (incl. Argon2id hashes, for offline login) | everything the hospital is authoritative for (read replica) |
| Needs internet for | sync, first-time OTP verification, user administration | always online |
| Writes stock? | yes — single writer | **never** independently; forwards to the hospital |

Both PostgreSQL instances use the **same schema and migration chain** (`backend/alembic`). Some tables are used by only one role: `outbox_events` on the hospital, `inbox_events` and `sync_conflicts` on the cloud.

## Bill confirmation (one transaction)

`services/billing.create_bill` runs these steps inside one PostgreSQL transaction. Any error rolls back everything.

1. If the client's `request_id` has already been used, return that bill (idempotency against double clicks and retries).
2. Lock the medicine rows with `SELECT … FOR UPDATE`, ordered by id. This serialises terminals and avoids deadlocks.
3. Validate every line (exists, rate > 0, enough stock) before changing anything.
4. Deduct stock and increment each medicine's `version`.
5. Insert the bill, bill items and `inventory_movements` (ledger).
6. Insert a `bill.created` outbox event carrying the bill and each medicine's `base_version → version`.
7. Raise or refresh low-stock alerts (threshold default 50), and write their outbox events.
8. Write the audit log, then `COMMIT`.

A reversal locks the bill and its medicines. It restores stock through separate `bill_reversal` ledger entries and emits `bill.reversed`. The original bill is kept.

## Synchronisation protocol

**Outbox (hospital).** Events are written in the business transaction. `SyncRunner`, a thread in the API process, delivers them every `SYNC_INTERVAL_SECONDS` and immediately after each write. A database lease guarantees a single active runner.

**Delivery.** `POST {cloud}/api/internal/sync/push` over WireGuard. Each request is HMAC-SHA256 signed over the timestamp, method, path and body hash, with a 5-minute skew limit. Events go strictly in `seq` order, batch after batch, until the queue is empty. The same call carries a heartbeat (pending/failed/conflict counts) and unsynced audit rows.

**Inbox (cloud).** For each event, in order:
* `event_id` already applied → **duplicate**: acknowledged, never re-applied.
* `seq` behind the last applied → **error**, and the hospital retries.
* Each medicine's cloud `version` must equal the event's `base_version`. If not, it is a **conflict**: recorded in `sync_conflicts`, nothing is applied, and processing stops so ordering is preserved.
* Otherwise the cloud applies the event, inserts the inbox row and commits (one commit per event).

**Hospital reaction.**
* applied/duplicate → `synced`.
* conflict → `conflict`, and the queue pauses.
* network failure → the event becomes `failed` with exponential backoff (2 s … 60 s).

A confirmed bill is never affected by sync state.

**Conflict resolution.** A user with `sync.manage` reviews the conflict in the Sync monitor and enters a note. The hospital re-sends that event with `force` and the note. The cloud adopts the hospital's authoritative value and records who resolved it and why. Both sides write an audit entry. Nothing is ever resolved automatically.

**Directory pull.** The hospital fetches `GET {cloud}/api/internal/sync/users` (at most every `USER_PULL_INTERVAL_SECONDS`) and upserts its cache. Revocations and password resets propagate through `token_version`.

## Remote access

The browser always calls its own server's public API, which has the same paths on both roles.
* **Reads** on the cloud come from the replica. Responses carry `source: "cloud_replica"`, and the UI shows the last sync time.
* **Writes** on the cloud (bills, reversals, adjustment requests and decisions, alert acknowledgements, settings, sync actions) are forwarded to `POST {hospital}/api/internal/exec/...` with the user's id. The hospital re-checks that user's role against its own directory copy and executes locally (channel `remote`), then wakes the sync worker.
* The live stock list used for remote billing (`GET /api/medicines?live=true`) is also forwarded.
* If the hospital is unreachable, the cloud returns **HTTP 503 `LIVE_BILLING_UNAVAILABLE`** with `last_sync`. The cloud never confirms an inventory transaction on its own.

## Authentication

* Passwords: Argon2id. Unknown usernames still run one hash, so timing does not reveal which accounts exist.
* Lockout: 5 failures → 15 minutes. There is also a per-IP in-process rate limit, and Nginx `limit_req` on login and OTP.
* Access token: JWT HS256, 15 minutes, kept in memory only. Claims: user, role, token version, session id, channel, offline flag.
* Refresh token: random 256-bit value, stored SHA-256-hashed in `auth_sessions`, sent as an HttpOnly, SameSite=Strict cookie scoped to `/api/auth`. It rotates on every use, and its absolute lifetime is `SESSION_HOURS`.
* Revocation: `token_version` on the user and `revoked_at` on the session. Both are checked on every request.
* **Hospital login:** the password is checked against the local hash, so it works offline for verified accounts with `offline_login_enabled`. Offline sign-ins are flagged in the session and the audit log. Unverified accounts must complete OTP verification through the cloud, which needs internet.
* **Cloud login:** password **and** mobile OTP every time. OTP: 6 digits, stored as HMAC, 5-minute TTL, 3 attempts, at most 3 sends per 10 minutes.

## Roles

There are two roles.

| Permission | Admin | Biller |
|---|:-:|:-:|
| Create and view bills | ✓ | ✓ |
| Reverse bills | ✓ | |
| View stock, ledger, alerts; acknowledge alerts | ✓ | ✓ |
| Change stock or rates | ✓ applied immediately | ✓ **after Admin approval** |
| Approve or reject billers' changes | ✓ | |
| Reports | ✓ | ✓ |
| Sync monitor, audit log, users, settings | ✓ | |

* **Admin can do everything.** An Admin's stock or rate change is applied at once. It is still recorded as an adjustment with ledger and audit entries.
* **A Biller can manage inventory with the Admin's permission.** The Biller's change is saved as a pending request and touches stock only when an Admin approves it.
* At least one active Admin must always exist. Every permission is enforced in the backend (`deps.require`); the UI only hides what the user cannot use.

## First-time sign-up

When the system has no accounts, the sign-in screen shows a **set-up form**. The person installing the system enters:
* the dispensary name and low-stock threshold
* their full name, username, mobile and password

They become the first **Admin** and then sign in normally. Billers are added later in *Users & access*.

* Sign-up is refused as soon as any account exists (`ALREADY_SET_UP`).
* Sign-up at the hospital registers the Admin in the central directory on the cloud. This needs internet once, and the account is then cached for offline sign-in. The dispensary settings are stored on the hospital and synchronised to the cloud.

## Code map

```
backend/app/
  main.py            app factory (role-specific routers, error handlers, sync runner)
  config.py          environment settings + production guards
  models.py          schema shared by both roles
  deps.py            DB session, Actor, permission checks, peer HMAC verification
  peer.py            signed HTTP client for hospital <-> cloud
  services/billing.py, inventory.py      business logic (hospital)
  services/sync_worker.py                outbox delivery, backoff, lease, conflict resolution
  services/sync_inbox.py                 idempotent ordered apply, conflict detection (cloud)
  services/auth.py, otp.py, directory.py authentication, OTP, user directory
  routers/operations.py                  bills/stock/approvals/alerts (local or forwarded)
  routers/internal.py                    peer-only endpoints for each role
```
