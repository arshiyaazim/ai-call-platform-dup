#!/usr/bin/env bash
# ============================================================
# install_certbot_deploy_hook.sh — Install the Certbot deploy
#   hook that reloads Nginx + restarts Coturn on cert renewal.
#
# Usage:
#   sudo ./scripts/vps/install_certbot_deploy_hook.sh              (install only)
#   sudo ./scripts/vps/install_certbot_deploy_hook.sh --dry-run    (install + certbot dry-run)
#   sudo ./scripts/vps/install_certbot_deploy_hook.sh --install-only  (same as default)
# ============================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

MODE="install-only"
for arg in "$@"; do
  case "$arg" in
    --dry-run)     MODE="dry-run" ;;
    --install-only) MODE="install-only" ;;
    *) echo -e "${RED}Unknown flag: ${arg}${NC}"; exit 1 ;;
  esac
done

# ── Root check ──
if [ "$(id -u)" -ne 0 ]; then
  echo -e "${RED}ERROR${NC}  This script must be run as root."
  echo "  Usage: sudo $0 [--install-only|--dry-run]"
  exit 1
fi

# ── Resolve repo root (two levels up from this script) ──
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

HOOK_SRC="${REPO_ROOT}/ops/letsencrypt/deploy-hook-reload.sh"
HOOK_DEST="/etc/letsencrypt/renewal-hooks/deploy/iamazim-reload.sh"

if [ ! -f "$HOOK_SRC" ]; then
  echo -e "${RED}ERROR${NC}  Template not found: ${HOOK_SRC}"
  exit 1
fi

# ── Install hook ──
echo "════════════════════════════════════════════"
echo " Installing Certbot Deploy Hook"
echo "════════════════════════════════════════════"

mkdir -p "$(dirname "$HOOK_DEST")"

# Substitute __REPO_PATH__ with actual repo location
sed "s|__REPO_PATH__|${REPO_ROOT}|g" "$HOOK_SRC" > "$HOOK_DEST"
chmod 755 "$HOOK_DEST"
echo -e "  ${GREEN}✓${NC} Installed: ${HOOK_DEST}"

# ── Verify certbot renewal scheduling ──
echo ""
echo "── Checking certbot timer / cron ──"
TIMER_FOUND=0
if systemctl list-timers 2>/dev/null | grep -qiE 'certbot'; then
  systemctl list-timers 2>/dev/null | grep -iE 'certbot'
  echo -e "  ${GREEN}✓${NC} certbot systemd timer is active."
  TIMER_FOUND=1
fi

if crontab -l 2>/dev/null | grep -q 'certbot'; then
  crontab -l 2>/dev/null | grep 'certbot'
  echo -e "  ${GREEN}✓${NC} certbot cron job found."
  TIMER_FOUND=1
fi

if [ "$TIMER_FOUND" -eq 0 ]; then
  echo -e "  ${YELLOW}WARN${NC}  No certbot timer or cron job detected."
  echo "  To enable the systemd timer:"
  echo "    sudo systemctl enable --now certbot.timer"
  echo "  Or add a cron entry:"
  echo '    0 3 * * * certbot renew --quiet'
fi

# ── Optional dry-run ──
if [ "$MODE" = "dry-run" ]; then
  echo ""
  echo "── Running certbot renew --dry-run ──"
  certbot renew --dry-run
  echo -e "  ${GREEN}✓${NC} Dry-run completed successfully."
else
  echo ""
  echo "── Skipping dry-run (pass --dry-run to test renewal) ──"
fi

echo ""
echo "════════════════════════════════════════════"
echo -e " ${GREEN}Deploy hook installed.${NC}"
echo ""
echo " The hook will automatically:"
echo "   • Reload Nginx  (host systemd or Docker)"
echo "   • Restart Coturn (Docker container)"
echo " after every successful certificate renewal."
echo ""
echo " Logs: /var/log/iamazim-certbot-deploy.log"
echo "════════════════════════════════════════════"
