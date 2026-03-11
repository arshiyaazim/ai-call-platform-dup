#!/usr/bin/env bash
# ============================================================
# turn_tls_check.sh — Validate TURN TLS reachability and cert
#                      correctness on port 5349
# Usage: sudo ./scripts/vps/turn_tls_check.sh [HOST]
# Exit non-zero if handshake fails or cert expires ≤7 days.
# ============================================================
set -euo pipefail

MIN_DAYS=7
PORT=5349

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ── Resolve host: prefer turn.iamazim.com, fallback to iamazim.com ──
if [ -n "${1:-}" ]; then
  HOST="$1"
elif getent ahosts turn.iamazim.com >/dev/null 2>&1; then
  HOST="turn.iamazim.com"
else
  HOST="iamazim.com"
  echo -e "${YELLOW}INFO${NC}   turn.iamazim.com does not resolve — using ${HOST}"
fi

echo "════════════════════════════════════════════"
echo " TURN TLS Check: ${HOST}:${PORT}"
echo "════════════════════════════════════════════"

# ── TCP connectivity check ──
echo -n "  TCP connect .......... "
TCP_OK=0
if command -v nc >/dev/null 2>&1; then
  if nc -z -w5 "$HOST" "$PORT" 2>/dev/null; then
    TCP_OK=1
  fi
else
  # fallback: bash /dev/tcp
  if (echo >/dev/tcp/"$HOST"/"$PORT") 2>/dev/null; then
    TCP_OK=1
  fi
fi

if [ "$TCP_OK" -eq 0 ]; then
  echo -e "${RED}FAIL${NC}"
  echo -e "${RED}Cannot reach ${HOST}:${PORT} — is Coturn running and port open?${NC}"
  exit 1
fi
echo -e "${GREEN}OK${NC}"

# ── TLS handshake ──
echo -n "  TLS handshake ........ "
TLS_OUTPUT=$(openssl s_client \
  -connect "${HOST}:${PORT}" \
  -servername "${HOST}" \
  -verify_return_error \
  </dev/null 2>&1) || true

# Check for handshake failure
if echo "$TLS_OUTPUT" | grep -qi "handshake failure\|ssl_error\|Connection refused"; then
  echo -e "${RED}FAIL${NC}"
  echo "$TLS_OUTPUT" | grep -iE "error|failure|refused" | head -5
  exit 1
fi

# Check verify return code
VERIFY_CODE=$(echo "$TLS_OUTPUT" | grep -oP 'Verify return code: \K[0-9]+' | head -1)
if [ -z "$VERIFY_CODE" ]; then
  echo -e "${YELLOW}WARN${NC} (could not parse verify code)"
elif [ "$VERIFY_CODE" -ne 0 ]; then
  VERIFY_MSG=$(echo "$TLS_OUTPUT" | grep 'Verify return code:' | head -1)
  echo -e "${YELLOW}WARN${NC} ${VERIFY_MSG}"
else
  echo -e "${GREEN}OK${NC} (verify return code: 0)"
fi

# ── Certificate expiry from handshake ──
echo -n "  Certificate expiry ... "
CERT_EXPIRY=$(echo "$TLS_OUTPUT" | openssl x509 -noout -enddate 2>/dev/null | sed 's/^notAfter=//') || true

if [ -z "$CERT_EXPIRY" ]; then
  echo -e "${YELLOW}WARN${NC} (could not extract expiry from handshake)"
else
  EXPIRY_EPOCH=$(date -d "$CERT_EXPIRY" +%s 2>/dev/null) || true
  NOW_EPOCH=$(date +%s)

  if [ -z "${EXPIRY_EPOCH:-}" ]; then
    echo -e "${YELLOW}WARN${NC} (could not parse date: ${CERT_EXPIRY})"
  else
    DAYS_REMAINING=$(( (EXPIRY_EPOCH - NOW_EPOCH) / 86400 ))
    if [ "$DAYS_REMAINING" -le 0 ]; then
      echo -e "${RED}EXPIRED${NC} (${CERT_EXPIRY})"
      exit 1
    elif [ "$DAYS_REMAINING" -le "$MIN_DAYS" ]; then
      echo -e "${YELLOW}${DAYS_REMAINING} days${NC} — renew now! (${CERT_EXPIRY})"
      exit 1
    else
      echo -e "${GREEN}${DAYS_REMAINING} days${NC} (${CERT_EXPIRY})"
    fi
  fi
fi

# ── Subject / SAN from handshake ──
PEER_SUBJECT=$(echo "$TLS_OUTPUT" | openssl x509 -noout -subject 2>/dev/null | sed 's/^subject=//') || true
if [ -n "$PEER_SUBJECT" ]; then
  echo "  Subject .............. ${PEER_SUBJECT}"
fi

echo "════════════════════════════════════════════"
echo -e "${GREEN}PASS${NC}  TURN TLS on ${HOST}:${PORT} is operational."
exit 0
