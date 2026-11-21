#!/usr/bin/env bash
# One-time setup of the backend on a fresh Oracle Cloud Always Free Ubuntu VM.
#   curl -fsSL https://raw.githubusercontent.com/<you>/<repo>/main/deploy/oracle/setup.sh | bash -s -- https://github.com/<you>/<repo>.git
# or, after cloning:  bash deploy/oracle/setup.sh
set -euo pipefail

REPO_URL="${1:-https://github.com/gagan-singh05/saran-ashram-dispenserdesk.git}"
APP_DIR="${APP_DIR:-$HOME/dispenserdesk}"

echo "==> Installing Docker"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
fi
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y git iptables-persistent >/dev/null 2>&1 || sudo apt-get install -y git

echo "==> Opening ports 80/443 in the VM firewall (Oracle Ubuntu images block them by default)"
for port in 80 443; do
  if ! sudo iptables -C INPUT -m state --state NEW -p tcp --dport "$port" -j ACCEPT 2>/dev/null; then
    sudo iptables -I INPUT 1 -m state --state NEW -p tcp --dport "$port" -j ACCEPT
  fi
done
sudo netfilter-persistent save 2>/dev/null || true

echo "==> Getting the code"
if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR/deploy"

if [ ! -f .env.oracle ]; then
  cp .env.oracle.example .env.oracle
  IP="$(curl -fsSL https://api.ipify.org || true)"
  [ -n "$IP" ] && sed -i "s/^API_DOMAIN=.*/API_DOMAIN=${IP//./-}.sslip.io/" .env.oracle
  sed -i "s/^JWT_SECRET=.*/JWT_SECRET=$(openssl rand -hex 32)/" .env.oracle
  sed -i "s/^SYNC_SHARED_SECRET=.*/SYNC_SHARED_SECRET=$(openssl rand -hex 32)/" .env.oracle
  echo
  echo "Created deploy/.env.oracle. Edit it now and paste your Neon DATABASE_URL:"
  echo "   nano $APP_DIR/deploy/.env.oracle"
  echo "Then re-run:  bash $APP_DIR/deploy/oracle/setup.sh"
  exit 0
fi

echo "==> Starting the backend"
sudo docker compose -f docker-compose.oracle.yml --env-file .env.oracle up -d --build

echo "==> Enabling auto-deploy (checks GitHub every 5 minutes)"
chmod +x "$APP_DIR/deploy/oracle/autodeploy.sh"
CRON_LINE="*/5 * * * * $APP_DIR/deploy/oracle/autodeploy.sh >> $HOME/autodeploy.log 2>&1"
( crontab -l 2>/dev/null | grep -v autodeploy.sh; echo "$CRON_LINE" ) | crontab -

DOMAIN="$(grep '^API_DOMAIN=' .env.oracle | cut -d= -f2)"
echo
echo "Done. Backend: https://$DOMAIN/api/health"
echo "Put https://$DOMAIN in frontend/vercel.json (the /api rewrite) and push."
