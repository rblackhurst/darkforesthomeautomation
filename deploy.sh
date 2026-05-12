#!/usr/bin/env bash
# DFHA fast deploy — pull latest, install deps, migrate, restart gunicorn.
#
# Installed at /usr/local/bin/dfha-deploy on the server. Run as root:
#
#   sudo dfha-deploy
#
# Optionally point at a non-default branch:
#
#   sudo DFHA_BRANCH=feature/foo dfha-deploy

set -euo pipefail

APP_USER="dfha"
APP_HOME="/home/${APP_USER}"
REPO_DIR="${APP_HOME}/darkforesthomeautomation"
APP_DIR="${REPO_DIR}/app"
VENV="${APP_DIR}/.venv"
ENV_FILE="${APP_DIR}/.env"
BRANCH="${DFHA_BRANCH:-main}"

log() { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }

[[ $EUID -eq 0 ]] || { echo "Run as root: sudo dfha-deploy"; exit 1; }

log "Pulling latest from origin/${BRANCH}"
sudo -u "${APP_USER}" git -C "${REPO_DIR}" fetch --quiet origin
sudo -u "${APP_USER}" git -C "${REPO_DIR}" checkout --quiet "${BRANCH}"
sudo -u "${APP_USER}" git -C "${REPO_DIR}" reset --quiet --hard "origin/${BRANCH}"

log "Refreshing Python dependencies"
sudo -u "${APP_USER}" "${VENV}/bin/pip" install --quiet -r "${APP_DIR}/requirements.txt"

log "Running migrations and collecting static files"
sudo -u "${APP_USER}" --preserve-env=PATH bash -c "
  set -a; . '${ENV_FILE}'; set +a
  cd '${APP_DIR}'
  '${VENV}/bin/python' manage.py migrate --noinput
  '${VENV}/bin/python' manage.py collectstatic --noinput
"

log "Restarting gunicorn"
systemctl restart dfha.service

log "Deploy complete."
systemctl --no-pager --lines=0 status dfha.service | head -3
