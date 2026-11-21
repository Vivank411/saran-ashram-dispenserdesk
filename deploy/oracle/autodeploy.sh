#!/usr/bin/env bash
# Pulls new commits from GitHub and rebuilds the backend only when something changed (run by cron).
set -euo pipefail
cd "$(dirname "$0")/../.."

git fetch --quiet origin main
if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then
  echo "$(date -Is) deploying $(git rev-parse --short origin/main)"
  git reset --hard --quiet origin/main
  cd deploy
  sudo docker compose -f docker-compose.oracle.yml --env-file .env.oracle up -d --build
  sudo docker image prune -f >/dev/null
fi
