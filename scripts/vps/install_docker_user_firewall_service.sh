#!/usr/bin/env bash
# ============================================================
# install_docker_user_firewall_service.sh
# Installs the docker-user-firewall systemd unit so iptables
# rules persist after Docker restarts / reboots.
#
# Run from the repo root:
#   sudo ./scripts/vps/install_docker_user_firewall_service.sh
# ============================================================
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "[install] ERROR: Must be run as root (sudo)." >&2
  exit 1
fi

# Resolve repo root (two levels up from this script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

SERVICE_SRC="$REPO_ROOT/ops/systemd/docker-user-firewall.service"
SERVICE_DST="/etc/systemd/system/docker-user-firewall.service"

if [[ ! -f "$SERVICE_SRC" ]]; then
  echo "[install] ERROR: Template not found: $SERVICE_SRC" >&2
  exit 1
fi

if [[ ! -f "$REPO_ROOT/scripts/vps/docker_user_firewall.sh" ]]; then
  echo "[install] ERROR: Script not found: $REPO_ROOT/scripts/vps/docker_user_firewall.sh" >&2
  exit 1
fi

# Substitute placeholder with actual repo path
sed "s|__REPO_PATH__|${REPO_ROOT}|g" "$SERVICE_SRC" > "$SERVICE_DST"
chmod 644 "$SERVICE_DST"

# Ensure the firewall script is executable
chmod +x "$REPO_ROOT/scripts/vps/docker_user_firewall.sh"

# Reload and enable
systemctl daemon-reload
systemctl enable docker-user-firewall.service

echo "[install] ════════════════════════════════════════════"
echo "[install] Installed: $SERVICE_DST"
echo "[install] Repo path: $REPO_ROOT"
echo "[install] Service enabled — will run after docker.service on boot."
echo "[install]"
echo "[install] To apply now:  sudo systemctl start docker-user-firewall"
echo "[install] To verify:     sudo systemctl status docker-user-firewall"
echo "[install] ════════════════════════════════════════════"
