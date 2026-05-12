#!/usr/bin/env bash
# DFHA server hardening — run once after bootstrap.sh succeeds.
#
# Effects:
#   * SSH: key-only (password auth disabled), root password locked
#   * unattended-upgrades: daily security patches
#   * fail2ban: 5 failed SSH attempts in 10 min → 1 hour ban
#
# Fallback if something goes wrong with SSH: Hetzner's web console
# at https://console.hetzner.cloud/ → server → "Console" button.

set -euo pipefail

log() { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }

[[ $EUID -eq 0 ]] || { echo "Run as root: sudo bash harden.sh"; exit 1; }

# ─── Safety check: don't lock the only door if no key is set ────────────────
if [[ ! -s /root/.ssh/authorized_keys ]]; then
  echo
  echo "✗ /root/.ssh/authorized_keys is empty or missing." >&2
  echo "  Locking down SSH now would lose remote access." >&2
  echo "  Add your SSH key first, or recover via Hetzner web console." >&2
  exit 1
fi

# ─── SSH hardening ──────────────────────────────────────────────────────────
log "Disabling SSH password authentication (key-only login)"
cat > /etc/ssh/sshd_config.d/99-dfha-hardening.conf <<EOF
# Managed by harden.sh — do not edit by hand.
PasswordAuthentication no
PermitEmptyPasswords no
ChallengeResponseAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
EOF
sshd -t  # syntax-check before reload
systemctl reload ssh

log "Locking root password (SSH key login still works)"
passwd -l root >/dev/null

# ─── Unattended security upgrades ───────────────────────────────────────────
log "Installing unattended-upgrades"
export DEBIAN_FRONTEND=noninteractive
apt-get install -y -qq unattended-upgrades apt-listchanges
cat > /etc/apt/apt.conf.d/20auto-upgrades <<EOF
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF

# ─── fail2ban ───────────────────────────────────────────────────────────────
log "Installing fail2ban (SSH brute-force protection)"
apt-get install -y -qq fail2ban
cat > /etc/fail2ban/jail.d/sshd.local <<EOF
[sshd]
enabled  = true
port     = ssh
maxretry = 5
findtime = 10m
bantime  = 1h
EOF
systemctl enable --quiet fail2ban
systemctl restart fail2ban

log "Hardening complete."
echo
echo "  → SSH: key-only, root password locked"
echo "  → Daily automatic security updates"
echo "  → fail2ban active (5 failed attempts = 1h ban)"
echo "  → Recovery fallback: Hetzner web console (console.hetzner.cloud)"
echo
