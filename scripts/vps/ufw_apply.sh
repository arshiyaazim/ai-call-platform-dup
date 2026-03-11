#!/usr/bin/env bash
# ============================================================
# ufw_apply.sh — Configure UFW firewall for AI Voice Agent VPS
# Idempotent: safe to re-run at any time.
#
# NOTE: UFW alone does NOT filter Docker-published ports because
# Docker inserts its own iptables rules via the DOCKER chain that
# bypass the INPUT chain where UFW operates. Run
# docker_user_firewall.sh to address Docker-level filtering.
# ============================================================
set -euo pipefail

# ── Must be root ─────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
  echo "[ufw] ERROR: This script must be run as root (sudo)." >&2
  exit 1
fi

# ── Check ufw is installed ───────────────────────────────────
if ! command -v ufw &>/dev/null; then
  echo "[ufw] ERROR: ufw is not installed." >&2
  echo "[ufw] Install it with:  sudo apt-get update && sudo apt-get install -y ufw" >&2
  exit 1
fi

echo "[ufw] Configuring firewall rules for iamazim.com VPS..."

# ── Defaults ─────────────────────────────────────────────────
ufw default deny incoming
ufw default allow outgoing

# ── Allowed ports ────────────────────────────────────────────
# HTTP / HTTPS (Nginx)
ufw allow 80/tcp    comment 'HTTP - Nginx'
ufw allow 443/tcp   comment 'HTTPS - Nginx SSL'

# SSH (rate-limited: max 6 connections per 30s from single IP)
ufw limit 22/tcp    comment 'SSH rate-limited'

# STUN / TURN (Coturn)
ufw allow 3478/tcp  comment 'STUN/TURN TCP - Coturn'
ufw allow 3478/udp  comment 'STUN/TURN UDP - Coturn'

# TURN TLS (Coturn)
ufw allow 5349/tcp  comment 'TURN TLS TCP - Coturn'
ufw allow 5349/udp  comment 'TURN TLS UDP - Coturn'

# LiveKit RTC direct
ufw allow 7881/tcp  comment 'LiveKit RTC TCP'

# Coturn relay range
ufw allow 49152:49252/udp  comment 'Coturn UDP relay range'

# LiveKit WebRTC media range
ufw allow 50000:50200/udp  comment 'LiveKit WebRTC UDP media'

# ── Enable (idempotent — answers 'y' automatically) ─────────
echo "y" | ufw enable

# ── Show final state ────────────────────────────────────────
echo ""
echo "[ufw] ════════════════════════════════════════════════"
echo "[ufw] Firewall rules applied successfully."
echo "[ufw] ════════════════════════════════════════════════"
echo ""
ufw status verbose
