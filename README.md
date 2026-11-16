# Dispensary Desk — Hybrid Hospital Dispensary System

Billing and inventory for a hospital dispensary with 2–5 computers. It **works without internet inside the hospital**, synchronises safely to a self-managed cloud server, and gives registered staff authenticated remote access.

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, React Router, TanStack Query, Axios |
| Backend | Python, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic (modular monolith) |
| Databases | PostgreSQL 16 on the hospital server **and** on the cloud server |
| Auth | JWT access tokens + rotating HttpOnly refresh cookie, Argon2id, mobile OTP, RBAC |
| Deployment | Docker Compose, Nginx (HTTPS), WireGuard |

## How it fits together

```
 Hospital LAN (works offline)                           Internet
 PC-1..PC-5 ─HTTPS─► Nginx ─► API (hospital role)  ◄══ WireGuard ══►  API (cloud role) ◄─ Nginx ◄─HTTPS─ remote staff
                              PostgreSQL: stock, bills     10.8.0.x     PostgreSQL: replica + users/OTP
                              (authoritative)
```

* **Single writer.** Only the hospital database changes stock. The cloud never makes stock decisions.
* **Transactional outbox.** Each bill, reversal, approved adjustment and alert writes a sync event in the *same* transaction. A background worker sends events in order over WireGuard, HMAC-signed.
* **Idempotent inbox.** The cloud records every applied event ID, so retries never duplicate bills or deductions. Version numbers detect conflicts, which are held for admin review and never overwritten silently.
* **Remote writes** go through the cloud gateway to the hospital API. When the hospital is unreachable, remote users see "live billing temporarily unavailable" plus read-only data with the last sync time.
* **Offline login** uses the Argon2id hashes cached on the hospital server (only for accounts that have already verified their mobile number). The cloud owns the user directory and OTP.

Full design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Repository layout

```
backend/    FastAPI app (app/), Alembic migrations, pytest suite (tests/)
frontend/   React + TypeScript SPA
deploy/     docker-compose.hospital.yml, docker-compose.cloud.yml, nginx/, wireguard/, backup/, .env templates
data/       stock.csv — initial medicine register
docs/       installation, cloud setup, network/VPN, backup & recovery, testing
```

## Run locally for development (no Docker needed)

Prerequisites: Python 3.12+ and Node 20+. Commands are for bash (Git Bash on Windows).

```bash
# 1. backend + tests
cd backend
python -m venv .venv && source .venv/Scripts/activate     # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest                                          # hospital + cloud apps wired together in-process

# 2. hospital API on :8000 (terminal 1)
export APP_ROLE=hospital DATABASE_URL=sqlite:///./hospital.db PEER_API_URL=http://127.0.0.1:8001 \
       JWT_SECRET=dev-hospital-secret-0123456789abcdef SYNC_SHARED_SECRET=dev-shared RUN_SYNC_WORKER=true
alembic upgrade head && python -m app.cli seed-stock ../data/stock.csv
uvicorn app.main:create_app --factory --port 8000

# 3. cloud API on :8001 (terminal 2)
export APP_ROLE=cloud DATABASE_URL=sqlite:///./cloud.db PEER_API_URL=http://127.0.0.1:8000 \
       JWT_SECRET=dev-cloud-secret-0123456789abcdef SYNC_SHARED_SECRET=dev-shared DEV_EXPOSE_OTP=true
alembic upgrade head
uvicorn app.main:create_app --factory --port 8001

# 4. frontend (terminal 3)
cd frontend && npm install
npm run dev                                                    # hospital UI → http://localhost:5173
VITE_API_PROXY=http://localhost:8001 npx vite --port 5174      # remote/cloud UI → http://localhost:5174
```

**First run:** open the app. With no accounts yet, it shows a **sign-up form**. Enter the dispensary name, the low-stock threshold and your Admin account, then sign in. Add billers from *Users & access*.

There are two roles. **Admin** can do everything. A **Biller** creates bills and can change stock or rates, but those changes apply only after an Admin approves them.

For automated testing only, `python -m app.cli seed-demo` creates the demo users `admin`, `biller` and `newbiller` (not yet verified) with password `demo1234`. It refuses to run in production. In the cloud UI the one-time code is shown on screen because `DEV_EXPOSE_OTP=true`.

To simulate an outage, stop the cloud server. The hospital UI switches to offline mode and billing continues. Restart the cloud server and the queued events sync automatically.

## Production

1. [docs/INSTALL_HOSPITAL.md](docs/INSTALL_HOSPITAL.md): local hospital server
2. [docs/CLOUD_SETUP.md](docs/CLOUD_SETUP.md): cloud server
3. [docs/NETWORK_VPN.md](docs/NETWORK_VPN.md): WireGuard and firewall
4. [docs/BACKUP_RECOVERY.md](docs/BACKUP_RECOVERY.md): backups, restoration and restore tests
5. [docs/TESTING.md](docs/TESTING.md): automated and manual acceptance tests
