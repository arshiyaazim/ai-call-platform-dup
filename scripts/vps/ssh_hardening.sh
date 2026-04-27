#!/usr/bin/env bash
# =============================================================================
# scripts/vps/ssh_hardening.sh
# Harden SSH on the AI Call Platform VPS.
#
# Changes applied:
#   - Disable root login via SSH (PermitRootLogin no)
#   - Disable password authentication (PasswordAuthentication no)
#   - Enable public-key authentication (PubkeyAuthentication yes)
#   - Restrict SSH access to the deploy user only (AllowUsers azim)
#   - Set LoginGraceTime and MaxAuthTries limits
#   - Fix ~/.ssh and ~/.ssh/authorized_keys permissions/ownership
#
# Safety guard: the script verifies that an authorized_keys file exists for
# the deploy user BEFORE disabling password auth, preventing lock-out.
# It also repairs common permission problems that prevent key-based login.
#
# Usage:
#   sudo bash scripts/vps/ssh_hardening.sh [--deploy-user <user>] [--dry-run]
#
# Prerequisites:
#   - Must be run as root (sudo)
#   - The deploy user's ~/.ssh/authorized_keys must already contain at least
#     one public key before running this script
# =============================================================================

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────
DEPLOY_USER="azim"
DRY_RUN=false
SSHD_CONFIG="/etc/ssh/sshd_config"
SSHD_HARDENING_DROP_IN="/etc/ssh/sshd_config.d/99-hardening.conf"

# ── Colour helpers ─────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${YELLOW}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
die()   { err "$*"; exit 1; }

# ── Parse arguments ────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --deploy-user)
      shift
      DEPLOY_USER="${1:?--deploy-user requires a username}"
      ;;
    --dry-run)
      DRY_RUN=true
      ;;
    -h|--help)
      echo "Usage: sudo $0 [--deploy-user <user>] [--dry-run]"
      exit 0
      ;;
    *)
      die "Unknown option: $1"
      ;;
  esac
  shift
done

# ── Must be root ───────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
  die "This script must be run as root: sudo bash $0"
fi

echo ""
echo "============================================================"
echo " SSH Hardening — $(hostname) — $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo " Deploy user : ${DEPLOY_USER}"
echo " Dry run     : ${DRY_RUN}"
echo "============================================================"
echo ""

# ── Pre-flight: verify deploy user exists ─────────────────────────────────
if ! id "${DEPLOY_USER}" &>/dev/null; then
  die "Deploy user '${DEPLOY_USER}' does not exist. Create the user first."
fi
ok "Deploy user '${DEPLOY_USER}' exists."

DEPLOY_USER_HOME=$(getent passwd "${DEPLOY_USER}" | cut -d: -f6)
SSH_DIR="${DEPLOY_USER_HOME}/.ssh"
AUTH_KEYS="${SSH_DIR}/authorized_keys"

# ── Fix ~/.ssh directory permissions (common cause of login failures) ──────
# SSH is strict: ~/.ssh must be 700 and owned by the user.
# authorized_keys must be 600 and owned by the user.
if [[ "${DRY_RUN}" == "false" ]]; then
  info "Ensuring correct permissions on ${SSH_DIR} ..."

  # Create ~/.ssh if it does not exist
  if [[ ! -d "${SSH_DIR}" ]]; then
    mkdir -p "${SSH_DIR}"
    info "Created ${SSH_DIR}"
  fi

  # Fix ownership — must be owned by the deploy user, not root
  chown "${DEPLOY_USER}:${DEPLOY_USER}" "${DEPLOY_USER_HOME}"
  chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "${SSH_DIR}"

  # Fix directory permissions — must be 700 (rwx------)
  chmod 700 "${SSH_DIR}"

  # Fix authorized_keys permissions if the file exists
  if [[ -f "${AUTH_KEYS}" ]]; then
    chmod 600 "${AUTH_KEYS}"
    chown "${DEPLOY_USER}:${DEPLOY_USER}" "${AUTH_KEYS}"
    ok "Permissions fixed: ${AUTH_KEYS} → 600, owned by ${DEPLOY_USER}"
  fi

  ok "Permissions fixed: ${SSH_DIR} → 700, owned by ${DEPLOY_USER}"
else
  info "DRY RUN — would fix permissions on ${SSH_DIR} and ${AUTH_KEYS}"
fi

# ── Pre-flight: verify authorized_keys is populated ───────────────────────
if [[ ! -f "${AUTH_KEYS}" ]] || [[ ! -s "${AUTH_KEYS}" ]]; then
  die "No authorized_keys found at ${AUTH_KEYS}.\n" \
      "Add your SSH public key before disabling password auth:\n" \
      "  ssh-copy-id ${DEPLOY_USER}@<this-server>"
fi

KEY_COUNT=$(grep -cE '^(ssh-rsa|ssh-ed25519|ssh-dss|ecdsa-sha2-nistp256|ecdsa-sha2-nistp384|ecdsa-sha2-nistp521|sk-ssh-ed25519|sk-ecdsa-sha2-nistp256)' "${AUTH_KEYS}" 2>/dev/null || echo 0)
if [[ "${KEY_COUNT}" -eq 0 ]]; then
  die "${AUTH_KEYS} exists but contains no valid public keys.\n" \
      "Add at least one SSH public key before running this script."
fi
ok "Found ${KEY_COUNT} public key(s) in ${AUTH_KEYS}."

# ── Pre-flight: detect sshd ───────────────────────────────────────────────
if ! command -v sshd &>/dev/null; then
  die "sshd not found. Install openssh-server first."
fi

# ── Build hardening config ────────────────────────────────────────────────
HARDENING_CONTENT="# SSH hardening — managed by ssh_hardening.sh
# Do NOT edit this file manually; re-run the script to update.

# Disable root login
PermitRootLogin no

# Disable password-based authentication
PasswordAuthentication no
ChallengeResponseAuthentication no
KbdInteractiveAuthentication no

# Enforce public-key authentication
PubkeyAuthentication yes
AuthorizedKeysFile .ssh/authorized_keys

# Restrict SSH access to the deploy user only
AllowUsers ${DEPLOY_USER}

# Reduce attack surface
LoginGraceTime 30
MaxAuthTries 3
MaxSessions 10

# Disable unused features
X11Forwarding no
AllowAgentForwarding no
AllowTcpForwarding no
PermitEmptyPasswords no
PermitUserEnvironment no
"

if [[ "${DRY_RUN}" == "true" ]]; then
  echo ""
  info "DRY RUN — would write to: ${SSHD_HARDENING_DROP_IN}"
  echo "─────────────────────────────────────────────────────"
  echo "${HARDENING_CONTENT}"
  echo "─────────────────────────────────────────────────────"
  info "DRY RUN — no changes made."
  exit 0
fi

# ── Check for drop-in directory (OpenSSH ≥ 8.2) ──────────────────────────
DROPIN_DIR="/etc/ssh/sshd_config.d"
if [[ -d "${DROPIN_DIR}" ]]; then
  # Modern approach: write a drop-in file
  info "Writing drop-in config: ${SSHD_HARDENING_DROP_IN}"
  echo "${HARDENING_CONTENT}" > "${SSHD_HARDENING_DROP_IN}"
  chmod 600 "${SSHD_HARDENING_DROP_IN}"
  ok "Drop-in config written."
else
  # Fallback: patch sshd_config directly using sed
  info "No drop-in directory; patching ${SSHD_CONFIG} directly."

  # Backup
  cp -p "${SSHD_CONFIG}" "${SSHD_CONFIG}.bak.$(date +%Y%m%d%H%M%S)"
  ok "Backup saved: ${SSHD_CONFIG}.bak.*"

  _patch_or_append() {
    local key="$1"
    local value="$2"
    if grep -qE "^#?[[:space:]]*${key}[[:space:]]" "${SSHD_CONFIG}"; then
      sed -i -E "s|^#?[[:space:]]*${key}[[:space:]].*|${key} ${value}|" "${SSHD_CONFIG}"
    else
      echo "${key} ${value}" >> "${SSHD_CONFIG}"
    fi
  }

  _patch_or_append "PermitRootLogin"                "no"
  _patch_or_append "PasswordAuthentication"         "no"
  _patch_or_append "ChallengeResponseAuthentication" "no"
  _patch_or_append "PubkeyAuthentication"           "yes"
  _patch_or_append "LoginGraceTime"                 "30"
  _patch_or_append "MaxAuthTries"                   "3"
  _patch_or_append "X11Forwarding"                  "no"
  _patch_or_append "PermitEmptyPasswords"           "no"

  # AllowUsers: add only if not present (multiple runs safe)
  if ! grep -qE "^AllowUsers" "${SSHD_CONFIG}"; then
    echo "AllowUsers ${DEPLOY_USER}" >> "${SSHD_CONFIG}"
  fi

  ok "Patched ${SSHD_CONFIG}."
fi

# ── Validate sshd config ──────────────────────────────────────────────────
info "Validating sshd configuration..."
if sshd -t; then
  ok "sshd -t passed."
else
  err "sshd config validation FAILED — reverting."
  if [[ -d "${DROPIN_DIR}" ]]; then
    rm -f "${SSHD_HARDENING_DROP_IN}"
  else
    # Restore backup
    LATEST_BAK=$(ls -t "${SSHD_CONFIG}".bak.* 2>/dev/null | head -1 || true)
    if [[ -n "${LATEST_BAK}" ]]; then
      cp -p "${LATEST_BAK}" "${SSHD_CONFIG}"
      err "Restored from backup: ${LATEST_BAK}"
    fi
  fi
  die "Aborting. Fix the sshd config error shown above and re-run."
fi

# ── Reload sshd ───────────────────────────────────────────────────────────
info "Reloading sshd service..."
if systemctl is-active --quiet sshd 2>/dev/null; then
  systemctl reload sshd
  ok "sshd reloaded (systemctl reload sshd)."
elif systemctl is-active --quiet ssh 2>/dev/null; then
  systemctl reload ssh
  ok "ssh reloaded (systemctl reload ssh)."
else
  info "Could not determine sshd service name; reload manually with:"
  info "  sudo systemctl reload sshd   OR   sudo service ssh reload"
fi

# ── Summary ───────────────────────────────────────────────────────────────
PROJECT_DIR="${DEPLOY_USER_HOME}/ai-call-platform"

echo ""
echo "============================================================"
echo -e "${GREEN} SSH hardening applied successfully${NC}"
echo ""
echo "  ~/.ssh permissions:"
echo "    ${SSH_DIR}  → 700, owned by ${DEPLOY_USER}"
echo "    ${AUTH_KEYS} → 600, owned by ${DEPLOY_USER}"
echo ""
echo "  Effective sshd settings:"
echo "    PermitRootLogin            no"
echo "    PasswordAuthentication     no"
echo "    PubkeyAuthentication       yes"
echo "    AllowUsers                 ${DEPLOY_USER}"
echo "    LoginGraceTime             30"
echo "    MaxAuthTries               3"
echo ""
echo "  Verify in a NEW terminal before closing this session:"
echo "    ssh ${DEPLOY_USER}@$(hostname -I | awk '{print $1}' 2>/dev/null || echo '<VPS_IP>')"
echo "    # You will land in ${DEPLOY_USER_HOME}"
echo "    # Project directory: ${PROJECT_DIR}"
echo "    cd ${PROJECT_DIR}"
echo "============================================================"
echo ""
