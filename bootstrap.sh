#!/usr/bin/env bash
# DFHA one-shot bootstrap for a fresh Ubuntu 24.04 Hetzner box.
#
# Installs Postgres, nginx, gunicorn, Let's Encrypt cert, and the Django app.
# Run once as root on the freshly provisioned server:
#
#   ssh root@<server-ip>
#   curl -fsSL https://raw.githubusercontent.com/rblackhurst/darkforesthomeautomation/claude/plan-dark-forest-architecture-qMxhN/bootstrap.sh | bash
#
# Re-running is safe (idempotent for config; secrets are preserved).

set -euo pipefail

# ─── Config ─────────────────────────────────────────────────────────────────
DOMAIN="app.darkforesthomeautomation.com"
APP_USER="dfha"
APP_HOME="/home/${APP_USER}"
REPO_URL="https://github.com/rblackhurst/darkforesthomeautomation.git"
REPO_BRANCH="${DFHA_BRANCH:-claude/plan-dark-forest-architecture-qMxhN}"
REPO_DIR="${APP_HOME}/darkforesthomeautomation"
APP_DIR="${REPO_DIR}/app"
ENV_FILE="${APP_DIR}/.env"
VENV="${APP_DIR}/.venv"
DB_NAME="dfha"
DB_USER="dfha"
GUNICORN_BIND="127.0.0.1:8000"

log() { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run as root. Try: sudo bash $0"

# ─── Admin email for Let's Encrypt ──────────────────────────────────────────
if [[ -z "${ADMIN_EMAIL:-}" ]]; then
  # When invoked via `curl ... | bash`, stdin is the script itself, so a
  # plain `read` would swallow the next line. Read from the controlling
  # terminal explicitly.
  if [[ -t 0 ]]; then
    read -rp "Email address for Let's Encrypt renewal notices: " ADMIN_EMAIL
  elif [[ -r /dev/tty ]]; then
    read -rp "Email address for Let's Encrypt renewal notices: " ADMIN_EMAIL </dev/tty
  else
    die "ADMIN_EMAIL not set and no terminal available. Re-run with: ADMIN_EMAIL=you@example.com bash bootstrap.sh"
  fi
fi
[[ "${ADMIN_EMAIL}" == *@* ]] || die "Invalid email: ${ADMIN_EMAIL}"

# ─── System packages ────────────────────────────────────────────────────────
log "Updating apt and installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  nginx postgresql postgresql-contrib \
  python3 python3-venv python3-pip python3-dev \
  libpq-dev build-essential \
  certbot python3-certbot-nginx \
  git ufw curl

# ─── Firewall ───────────────────────────────────────────────────────────────
log "Configuring UFW firewall (22, 80, 443)"
ufw --force reset >/dev/null
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow 22/tcp >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null

# ─── App user ───────────────────────────────────────────────────────────────
log "Ensuring ${APP_USER} system user exists"
if ! id "${APP_USER}" &>/dev/null; then
  adduser --system --group --home "${APP_HOME}" --shell /bin/bash "${APP_USER}"
fi

# ─── Postgres ───────────────────────────────────────────────────────────────
log "Configuring Postgres role and database"
if [[ -f "${ENV_FILE}" ]] && grep -q '^DJANGO_DB_PASSWORD=' "${ENV_FILE}"; then
  DB_PASSWORD="$(grep '^DJANGO_DB_PASSWORD=' "${ENV_FILE}" | cut -d= -f2-)"
else
  DB_PASSWORD="$(openssl rand -base64 32 | tr -d '/+=' | cut -c1-32)"
fi

sudo -u postgres psql <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='${DB_USER}') THEN
    CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASSWORD}';
  ELSE
    ALTER ROLE ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';
  END IF;
END\$\$;
SQL
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1 \
  || sudo -u postgres createdb -O "${DB_USER}" "${DB_NAME}"

# ─── Repo checkout ──────────────────────────────────────────────────────────
log "Fetching app source (branch: ${REPO_BRANCH})"
if [[ -d "${REPO_DIR}/.git" ]]; then
  sudo -u "${APP_USER}" git -C "${REPO_DIR}" fetch --quiet origin
  sudo -u "${APP_USER}" git -C "${REPO_DIR}" checkout --quiet "${REPO_BRANCH}"
  sudo -u "${APP_USER}" git -C "${REPO_DIR}" reset --quiet --hard "origin/${REPO_BRANCH}"
else
  sudo -u "${APP_USER}" git clone --quiet --branch "${REPO_BRANCH}" "${REPO_URL}" "${REPO_DIR}"
fi

# ─── Python venv + deps ─────────────────────────────────────────────────────
log "Setting up Python virtualenv and installing requirements"
if [[ ! -d "${VENV}" ]]; then
  sudo -u "${APP_USER}" python3 -m venv "${VENV}"
fi
sudo -u "${APP_USER}" "${VENV}/bin/pip" install --quiet --upgrade pip
sudo -u "${APP_USER}" "${VENV}/bin/pip" install --quiet -r "${APP_DIR}/requirements.txt"

# ─── .env file ──────────────────────────────────────────────────────────────
log "Writing ${ENV_FILE}"
if [[ -f "${ENV_FILE}" ]] && grep -q '^DJANGO_SECRET_KEY=' "${ENV_FILE}"; then
  SECRET_KEY="$(grep '^DJANGO_SECRET_KEY=' "${ENV_FILE}" | cut -d= -f2-)"
else
  SECRET_KEY="$("${VENV}/bin/python" -c 'import secrets; print(secrets.token_urlsafe(50))')"
fi

cat > "${ENV_FILE}" <<ENV
DJANGO_SECRET_KEY=${SECRET_KEY}
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=${DOMAIN}
DJANGO_DB_NAME=${DB_NAME}
DJANGO_DB_USER=${DB_USER}
DJANGO_DB_PASSWORD=${DB_PASSWORD}
DJANGO_DB_HOST=127.0.0.1
DJANGO_DB_PORT=5432
ENV
chown "${APP_USER}:${APP_USER}" "${ENV_FILE}"
chmod 600 "${ENV_FILE}"

# ─── Django migrate + collectstatic ─────────────────────────────────────────
log "Running migrations and collecting static files"
sudo -u "${APP_USER}" --preserve-env=PATH bash -c "
  set -a; . '${ENV_FILE}'; set +a
  cd '${APP_DIR}'
  '${VENV}/bin/python' manage.py migrate --noinput
  '${VENV}/bin/python' manage.py collectstatic --noinput
"

# ─── systemd unit for gunicorn ──────────────────────────────────────────────
log "Installing systemd unit for gunicorn"
cat > /etc/systemd/system/dfha.service <<UNIT
[Unit]
Description=DFHA Django app (gunicorn)
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=notify
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${VENV}/bin/gunicorn dfha.wsgi:application \\
  --bind ${GUNICORN_BIND} \\
  --workers 3 \\
  --access-logfile - \\
  --error-logfile -
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --quiet dfha.service
systemctl restart dfha.service

# ─── nginx site ─────────────────────────────────────────────────────────────
log "Configuring nginx for ${DOMAIN}"
cat > /etc/nginx/sites-available/dfha <<NGINX
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    client_max_body_size 25M;

    location / {
        proxy_pass http://${GUNICORN_BIND};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_redirect off;
    }
}
NGINX
ln -sf /etc/nginx/sites-available/dfha /etc/nginx/sites-enabled/dfha
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

# ─── Let's Encrypt cert ─────────────────────────────────────────────────────
log "Requesting Let's Encrypt certificate for ${DOMAIN}"
if ! certbot certificates 2>/dev/null | grep -q "${DOMAIN}"; then
  certbot --nginx -d "${DOMAIN}" \
    --non-interactive --agree-tos -m "${ADMIN_EMAIL}" \
    --redirect
else
  log "Certificate already exists; skipping issuance."
fi

# ─── Done ───────────────────────────────────────────────────────────────────
log "Bootstrap complete."
echo
echo "  → Visit: https://${DOMAIN}"
echo "  → Service: systemctl status dfha"
echo "  → Logs:    journalctl -u dfha -f"
echo
