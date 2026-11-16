# Cloud server setup

## Server

* A Linux VPS (Ubuntu 24.04 LTS, 2 vCPU, 4 GB RAM, 80 GB disk) in a region close to the hospital.
* A DNS name (for example `dispensary.example-hospital.in`) with an A record pointing to the VPS.
* Turn on the provider's automated disk snapshots in addition to the encrypted database backups.

## 1. Base system and firewall

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-v2 wireguard ufw git certbot
sudo systemctl enable --now docker && sudo timedatectl set-ntp true
sudo ufw default deny incoming && sudo ufw default allow outgoing
sudo ufw allow OpenSSH && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw allow 51820/udp
sudo ufw enable
```

Use key-only SSH (`PasswordAuthentication no`), and consider `fail2ban`.

## 2. TLS certificate (Let's Encrypt)

```bash
sudo certbot certonly --standalone -d dispensary.example-hospital.in
echo '0 4 * * * root certbot renew --quiet --pre-hook "docker stop dispensary-cloud-web-1" --post-hook "docker start dispensary-cloud-web-1"' \
  | sudo tee /etc/cron.d/certbot-dispensary
```

Set `TLS_CERT_DIR=/etc/letsencrypt/live/<domain>`. The files in that folder are symlinks into `/etc/letsencrypt/archive`. If your Docker setup does not follow them, mount `/etc/letsencrypt` read-only instead and adjust the paths.

## 3. Configure and start

```bash
sudo mkdir -p /opt/dispensary && sudo chown $USER /opt/dispensary
git clone <your-repo-url> /opt/dispensary && cd /opt/dispensary/deploy
cp .env.cloud.example .env.cloud && chmod 600 .env.cloud
nano .env.cloud     # JWT_SECRET (new), SYNC_SHARED_SECRET (same as hospital), POSTGRES_PASSWORD, SMS_*, SERVER_NAME
mkdir -p secrets && openssl rand -base64 48 > secrets/backup_passphrase && chmod 600 secrets/backup_passphrase
sudo mkdir -p /srv/dispensary-backups
sudo systemctl enable --now wg-quick@wg0          # see NETWORK_VPN.md
docker compose -f docker-compose.cloud.yml --env-file .env.cloud up -d --build
```

With `ENVIRONMENT=production`, the API refuses to start if secrets are short or default, if `DEV_EXPOSE_OTP=true`, if SQLite is configured, or if `COOKIE_SECURE` is false on the cloud.

## 4. SMS gateway for OTP

`SMS_PROVIDER=webhook` sends `POST SMS_WEBHOOK_URL` with the JSON body `{"to": "+91…", "message": "…"}` and the header `Authorization: Bearer SMS_WEBHOOK_TOKEN`. Point it at your SMS provider's HTTP API. If the provider expects a different format, adapt `backend/app/services/otp.py:send_sms`. In India, register the sender ID and message template under DLT.

## 5. First Admin and staff accounts

Open `https://dispensary.example-hospital.in`, or the hospital address. The **sign-up form** appears while no account exists. Whoever completes it first becomes the Admin, so do this immediately after deployment. Then go to **Users & access** → Register user to add billers. New billers verify their mobile with a one-time code on first sign-in, either remotely or at the hospital while it is online. After that they can sign in at the hospital even when the internet is down.

If you prefer the command line: `docker compose ... exec -e ADMIN_PASSWORD='…' api python -m app.cli create-admin --username admin --name "Admin" --mobile "+91 9xxxxxxxxx"`.

## 6. Verify the link

* The hospital shows "Cloud in sync", and the cloud shows "Hospital server connected".
* Cloud → Stock & ledger shows the register, with the "Cloud replica" badge.
* A remote bill reduces hospital stock immediately and appears in both systems.
* Stop the hospital API. The cloud shows the red "Live billing is temporarily unavailable" banner, New bill is disabled, and read-only pages still work.
