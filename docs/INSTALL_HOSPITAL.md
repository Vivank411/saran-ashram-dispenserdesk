# Installing the hospital (local) server

## Hardware and prerequisites

* A dedicated Linux machine (Ubuntu Server 24.04 LTS recommended): 4 cores, 8 GB RAM, 256 GB SSD, plus a second disk or a NAS for backups.
* A **UPS** with automatic safe shutdown (for example `apt install nut`).
* A static LAN IP (for example `192.168.1.10`) and a LAN DNS name (for example `dispensary.hospital.lan`), set on the router or in each PC's hosts file.
* NTP time sync: `timedatectl set-ntp true`. Signed peer requests are rejected if the server clocks differ by more than 5 minutes.

## 1. Install Docker and WireGuard

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-v2 wireguard ufw git
sudo systemctl enable --now docker
```

## 2. Get the code and configure

```bash
sudo mkdir -p /opt/dispensary && sudo chown $USER /opt/dispensary
git clone <your-repo-url> /opt/dispensary && cd /opt/dispensary/deploy
cp .env.hospital.example .env.hospital && chmod 600 .env.hospital
openssl rand -hex 32        # -> JWT_SECRET
openssl rand -hex 32        # -> SYNC_SHARED_SECRET (the SAME value goes on the cloud server)
nano .env.hospital          # secrets, POSTGRES_PASSWORD, SERVER_NAME, BACKUP_DIR
mkdir -p secrets && openssl rand -base64 48 > secrets/backup_passphrase && chmod 600 secrets/backup_passphrase
```

Keep a copy of `secrets/backup_passphrase` **off the server**, for example in a sealed envelope in the hospital safe. Encrypted backups cannot be restored without it.

## 3. HTTPS on the LAN

```bash
./nginx/make-lan-cert.sh dispensary.hospital.lan 192.168.1.10
```

Install `deploy/nginx/certs/hospital-ca.crt` as a trusted root certificate on every hospital PC (one time). On Windows: double-click it → Install Certificate → Local Machine → Trusted Root Certification Authorities.

## 4. WireGuard

Set up the tunnel as described in [NETWORK_VPN.md](NETWORK_VPN.md). The hospital is `10.8.0.2`, so set `WG_ADDRESS=10.8.0.2`. The tunnel must be up before Docker starts, because the API publishes its peer port on that address:

```bash
sudo systemctl enable --now wg-quick@wg0
sudo mkdir -p /etc/systemd/system/docker.service.d
printf "[Unit]\nAfter=wg-quick@wg0.service\nWants=wg-quick@wg0.service\n" | sudo tee /etc/systemd/system/docker.service.d/wg.conf
sudo systemctl daemon-reload
```

## 5. Start

```bash
sudo mkdir -p /srv/dispensary-backups
docker compose -f docker-compose.hospital.yml --env-file .env.hospital up -d --build
docker compose -f docker-compose.hospital.yml --env-file .env.hospital logs -f api    # migrations run automatically
```

## 6. Load the medicine register

```bash
docker compose -f docker-compose.hospital.yml --env-file .env.hospital exec api python -m app.cli seed-stock /data/stock.csv
```

The CSV columns are `code,name,unit,stock,rate,cost,mrp,company`, the same fields as the original stock register. Any other columns are ignored. Importing queues the events that build the cloud replica. Running it again refreshes names and units only; quantities and rates change only through approvals.

### First-time sign-up

Open `https://dispensary.hospital.lan`. Because no account exists yet, the screen shows the **sign-up form**. Enter the dispensary name, the low-stock threshold and your Admin account (name, username, mobile, password), then sign in. The internet must be up for this one step, because the Admin is registered in the central directory on the cloud. After that, sign-in works offline.

Then add each biller in **Users & access → Register user**, with the role *Biller*.

## 7. Hospital PCs

Open `https://dispensary.hospital.lan` in Chrome or Edge and sign in. No per-PC setup is needed: the server records each computer by its LAN IP address on every bill and audit entry. Give the PCs fixed IPs (DHCP reservations) so the address always identifies the same counter. Allow pop-ups for the site so receipts can print.

## 8. Verify

* The top bar shows **"Cloud in sync"**, and the Sync monitor shows Pending 0.
* Unplug the WAN cable. The top bar changes to "Offline", billing continues and Pending grows. Plug it back in, and the queue drains to 0 within about a minute.
* The next morning, check `tail /srv/dispensary-backups/backup.log`.

## Updating

```bash
cd /opt/dispensary/deploy
docker compose -f docker-compose.hospital.yml --env-file .env.hospital exec backup backup.sh    # manual backup first
git -C .. pull && docker compose -f docker-compose.hospital.yml --env-file .env.hospital up -d --build
```
