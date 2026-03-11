#!/usr/bin/env bash
# ============================================================
# cert_san_check.sh — Verify certificate SAN list covers all
#                      required production hostnames
# Usage: sudo ./scripts/vps/cert_san_check.sh [CERT_PATH]
# Exit non-zero if any required SAN is missing.
# ============================================================
set -euo pipefail

FULLCHAIN="${1:-/etc/letsencrypt/live/iamazim.com/fullchain.pem}"

# ── Required SANs (always checked) ──
REQUIRED_SANS=(
  "iamazim.com"
  "api.iamazim.com"
  "livekit.iamazim.com"
  "fazle.iamazim.com"
)

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [ ! -f "$FULLCHAIN" ]; then
  echo -e "${RED}ERROR${NC}  Certificate not found: ${FULLCHAIN}"
  exit 1
fi

# ── Extract SANs from certificate ──
CERT_SANS=$(openssl x509 -in "$FULLCHAIN" -noout -ext subjectAltName 2>/dev/null \
  | grep -oP 'DNS:[^\s,]+' \
  | sed 's/DNS://g' \
  | sort -u)

if [ -z "$CERT_SANS" ]; then
  echo -e "${RED}ERROR${NC}  No Subject Alternative Names found in certificate."
  exit 1
fi

# ── Optionally require turn.iamazim.com if DNS resolves ──
TURN_HOST="turn.iamazim.com"
if getent ahosts "$TURN_HOST" >/dev/null 2>&1; then
  REQUIRED_SANS+=("$TURN_HOST")
else
  echo -e "${YELLOW}INFO${NC}   ${TURN_HOST} does not resolve — skipping SAN check for it."
fi

# ── Check each required SAN ──
echo "════════════════════════════════════════════"
echo " SAN Check: ${FULLCHAIN}"
echo "════════════════════════════════════════════"
echo ""
echo "SANs in certificate:"
for san in $CERT_SANS; do
  echo "  • ${san}"
done
echo ""

MISSING=0
for required in "${REQUIRED_SANS[@]}"; do
  if echo "$CERT_SANS" | grep -qx "$required"; then
    echo -e "  ${GREEN}OK${NC}      ${required}"
  else
    echo -e "  ${RED}MISSING${NC} ${required}"
    MISSING=1
  fi
done

echo ""
if [ "$MISSING" -ne 0 ]; then
  echo -e "${RED}FAIL${NC}  One or more required SANs are missing from the certificate."
  echo ""
  echo "To expand the certificate, run:"
  echo "  sudo certbot certonly --nginx --cert-name iamazim.com \\"
  for san in "${REQUIRED_SANS[@]}"; do
    echo "    -d ${san} \\"
  done
  echo "    --expand"
  exit 1
fi

echo -e "${GREEN}PASS${NC}  All required SANs are present."
exit 0
