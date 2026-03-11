#!/usr/bin/env bash
# ============================================================
# ports_audit.sh — Audit listening ports and Docker exposures
#
# Prints all listening TCP/UDP ports, Docker-published ports,
# and highlights any unexpected 0.0.0.0 bindings.
# Exits non-zero if unexpected public exposures are detected.
# ============================================================
set -euo pipefail

# ── Allowed public ports (0.0.0.0 or :: binding is OK) ───────
# Format: port/proto
ALLOWED_PUBLIC=(
  "80/tcp"
  "443/tcp"
  "22/tcp"
  "3478/tcp"
  "3478/udp"
  "5349/tcp"
  "5349/udp"
  "7881/tcp"
)
# UDP ranges checked separately
ALLOWED_UDP_RANGES=(
  "49152:49252"
  "50000:50200"
)

EXIT_CODE=0

# ── Colors (if terminal supports it) ────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

echo "════════════════════════════════════════════════════════"
echo " Port Audit — iamazim.com VPS"
echo " $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "════════════════════════════════════════════════════════"
echo ""

# ── 1. System listening ports ────────────────────────────────
echo "── Listening Ports (ss -lntup) ──────────────────────────"
if command -v ss &>/dev/null; then
  ss -lntup 2>/dev/null || ss -lntu 2>/dev/null || echo "(ss failed)"
else
  echo "(ss not available, trying netstat)"
  netstat -tlnup 2>/dev/null || echo "(netstat also unavailable)"
fi
echo ""

# ── 2. Docker container port mappings ────────────────────────
echo "── Docker Published Ports ───────────────────────────────"
if command -v docker &>/dev/null; then
  docker ps --format 'table {{.Names}}\t{{.Ports}}' 2>/dev/null || echo "(docker ps failed — is Docker running?)"
else
  echo "(docker not found)"
fi
echo ""

# ── 3. Check for unexpected 0.0.0.0 bindings ────────────────
echo "── Checking for Unexpected Public Exposures ─────────────"

is_port_in_range() {
  local port="$1"
  for range in "${ALLOWED_UDP_RANGES[@]}"; do
    local lo hi
    lo="${range%%:*}"
    hi="${range##*:}"
    if [[ "$port" -ge "$lo" && "$port" -le "$hi" ]]; then
      return 0
    fi
  done
  return 1
}

is_allowed() {
  local port="$1"
  local proto="$2"

  # Check exact match
  for allowed in "${ALLOWED_PUBLIC[@]}"; do
    if [[ "$allowed" == "${port}/${proto}" ]]; then
      return 0
    fi
  done

  # Check UDP ranges
  if [[ "$proto" == "udp" ]] && is_port_in_range "$port"; then
    return 0
  fi

  return 1
}

UNEXPECTED=""

# Parse Docker port bindings for 0.0.0.0 exposures
if command -v docker &>/dev/null; then
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    container=$(echo "$line" | awk '{print $1}')
    ports_field=$(echo "$line" | cut -d$'\t' -f2-)

    # Docker ports format: 0.0.0.0:7881->7881/tcp, 127.0.0.1:8000->8000/tcp, ...
    # Extract each mapping
    IFS=',' read -ra mappings <<< "$ports_field"
    for mapping in "${mappings[@]}"; do
      mapping="$(echo "$mapping" | xargs)"  # trim whitespace
      # Match 0.0.0.0:PORT->PORT/PROTO  or  :::PORT->PORT/PROTO
      if echo "$mapping" | grep -qE '^(0\.0\.0\.0|::):'; then
        # Extract host port and protocol
        host_part=$(echo "$mapping" | grep -oE '^[^-]+' | sed 's/^(0\.0\.0\.0|::)://')
        # Handle range: 0.0.0.0:49152-49252->49152-49252/udp
        port_num=$(echo "$mapping" | grep -oE ':([-0-9]+)->' | sed 's/://' | sed 's/->//')
        proto=$(echo "$mapping" | grep -oE '(tcp|udp)$')
        [[ -z "$proto" ]] && proto="tcp"

        # Handle port ranges like 49152-49252
        if echo "$port_num" | grep -q '-'; then
          range_lo=$(echo "$port_num" | cut -d'-' -f1)
          range_hi=$(echo "$port_num" | cut -d'-' -f2)
          # Check if entire range is allowed
          if [[ "$proto" == "udp" ]]; then
            range_ok=false
            for ar in "${ALLOWED_UDP_RANGES[@]}"; do
              alo="${ar%%:*}"
              ahi="${ar##*:}"
              if [[ "$range_lo" -ge "$alo" && "$range_hi" -le "$ahi" ]]; then
                range_ok=true
                break
              fi
            done
            if ! $range_ok; then
              UNEXPECTED+="  ${RED}UNEXPECTED${NC}: $container → $mapping\n"
              EXIT_CODE=1
            fi
          else
            UNEXPECTED+="  ${RED}UNEXPECTED${NC}: $container → $mapping (TCP range)\n"
            EXIT_CODE=1
          fi
        else
          if [[ -n "$port_num" ]] && ! is_allowed "$port_num" "$proto"; then
            UNEXPECTED+="  ${RED}UNEXPECTED${NC}: $container → $mapping\n"
            EXIT_CODE=1
          fi
        fi
      fi
    done
  done < <(docker ps --format '{{.Names}}\t{{.Ports}}' 2>/dev/null)
fi

# Also check host-level listeners on 0.0.0.0 (non-Docker)
if command -v ss &>/dev/null; then
  while IFS= read -r line; do
    # Example: tcp  LISTEN 0  4096  0.0.0.0:9090  0.0.0.0:*  users:(("prometheus",...))
    addr=$(echo "$line" | awk '{print $5}')
    if echo "$addr" | grep -qE '^(0\.0\.0\.0|\*|::):'; then
      port=$(echo "$addr" | grep -oE '[0-9]+$')
      proto=$(echo "$line" | awk '{print $1}')
      # Normalize proto
      [[ "$proto" == "tcp" || "$proto" == "tcp6" ]] && proto="tcp"
      [[ "$proto" == "udp" || "$proto" == "udp6" ]] && proto="udp"
      if [[ -n "$port" ]] && ! is_allowed "$port" "$proto"; then
        process=$(echo "$line" | grep -oP 'users:\(\("\K[^"]+' 2>/dev/null || echo "unknown")
        UNEXPECTED+="  ${RED}UNEXPECTED${NC}: host 0.0.0.0:$port/$proto ($process)\n"
        EXIT_CODE=1
      fi
    fi
  done < <(ss -lntup 2>/dev/null | tail -n +2)
fi

if [[ -n "$UNEXPECTED" ]]; then
  echo ""
  echo -e "${RED}⚠ UNEXPECTED PUBLIC EXPOSURES DETECTED:${NC}"
  echo -e "$UNEXPECTED"
  echo ""
  echo "These ports are bound to 0.0.0.0 and are NOT in the approved allowlist."
  echo "Fix by binding to 127.0.0.1 in docker-compose.yaml or removing the port mapping."
else
  echo -e "  ${GREEN}✓ No unexpected public exposures detected.${NC}"
fi

echo ""

# ── 4. UFW status summary ───────────────────────────────────
echo "── UFW Status ───────────────────────────────────────────"
if command -v ufw &>/dev/null; then
  ufw status 2>/dev/null || echo "(ufw status failed — are you root?)"
else
  echo -e "  ${YELLOW}! UFW not installed.${NC}"
fi
echo ""

# ── 5. DOCKER-USER chain summary ────────────────────────────
echo "── DOCKER-USER iptables Chain ───────────────────────────"
if command -v iptables &>/dev/null; then
  iptables -t filter -S DOCKER-USER 2>/dev/null || echo "(DOCKER-USER chain not found — run docker_user_firewall.sh)"
else
  echo "(iptables not available)"
fi
echo ""

echo "════════════════════════════════════════════════════════"
if [[ $EXIT_CODE -eq 0 ]]; then
  echo -e " ${GREEN}AUDIT PASSED${NC} — All port bindings match allowlist."
else
  echo -e " ${RED}AUDIT FAILED${NC} — Unexpected exposures found above."
fi
echo "════════════════════════════════════════════════════════"

exit $EXIT_CODE
