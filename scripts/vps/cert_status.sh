#!/usr/bin/env bash
# ============================================================
# cert_status.sh — Print safe certificate summary and check expiry
# Usage: sudo ./scripts/vps/cert_status.sh [CERT_DIR]
# Exit non-zero if cert missing or expires within 7 days.
# ============================================================
set -euo pipefail

CERT_DIR="${1:-/etc/letsencrypt/live/iamazim.com}"
FULLCHAIN="${CERT_DIR}/fullchain.pem"
PRIVKEY="${CERT_DIR}/privkey.pem"
MIN_DAYS=7

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

FAIL=0

# ── Check files exist ──
for f in "$FULLCHAIN" "$PRIVKEY"; do
  if [ ! -f "$f" ]; then
    echo -e "${RED}MISSING${NC}  $f"
    FAIL=1
  fi
done
if [ "$FAIL" -ne 0 ]; then
  echo -e "${RED}Certificate files not found — cannot continue.${NC}"
  exit 1
fi

# ── Extract certificate details (no private key content) ──
SUBJECT=$(openssl x509 -in "$FULLCHAIN" -noout -subject 2>/dev/null | sed 's/^subject=//')
ISSUER=$(openssl x509 -in "$FULLCHAIN" -noout -issuer 2>/dev/null | sed 's/^issuer=//')
NOT_BEFORE=$(openssl x509 -in "$FULLCHAIN" -noout -startdate 2>/dev/null | sed 's/^notBefore=//')
NOT_AFTER=$(openssl x509 -in "$FULLCHAIN" -noout -enddate 2>/dev/null | sed 's/^notAfter=//')

# ── Compute days remaining ──
EXPIRY_EPOCH=$(date -d "$NOT_AFTER" +%s)
NOW_EPOCH=$(date +%s)
DAYS_REMAINING=$(( (EXPIRY_EPOCH - NOW_EPOCH) / 86400 ))

# ── Print summary ──
echo "════════════════════════════════════════════"
echo " Certificate Status: ${CERT_DIR}"
echo "════════════════════════════════════════════"
echo "  Subject  : ${SUBJECT}"
echo "  Issuer   : ${ISSUER}"
echo "  NotBefore: ${NOT_BEFORE}"
echo "  NotAfter : ${NOT_AFTER}"

if [ "$DAYS_REMAINING" -le 0 ]; then
  echo -e "  Remaining: ${RED}EXPIRED${NC} (${DAYS_REMAINING} days)"
  FAIL=1
elif [ "$DAYS_REMAINING" -le "$MIN_DAYS" ]; then
  echo -e "  Remaining: ${YELLOW}${DAYS_REMAINING} days${NC} (≤ ${MIN_DAYS} — renew now!)"
  FAIL=1
else
  echo -e "  Remaining: ${GREEN}${DAYS_REMAINING} days${NC}"
fi
echo "════════════════════════════════════════════"

exit "$FAIL"
