#!/usr/bin/env bash
# =============================================================================
# scripts/vps/monitoring_smoke.sh
# Phase 8: Alerting & Dashboards — Monitoring Stack Smoke Test
#
# Verifies that all monitoring services are reachable and healthy.
# Exits 0 only when every check passes; exits 1 on any failure.
#
# Usage:
#   bash scripts/vps/monitoring_smoke.sh
#
# Requirements:
#   - curl (usually pre-installed)
#   - Running Docker Compose stack (monitoring-network services up)
#   - Script should be run on the VPS host (127.0.0.1 bindings assumed)
# =============================================================================

set -euo pipefail

# ── Colour helpers ─────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Colour

pass() { echo -e "${GREEN}[PASS]${NC} $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*"; FAILURES=$((FAILURES + 1)); }
info() { echo -e "${YELLOW}[INFO]${NC} $*"; }

FAILURES=0

# ── Helper: HTTP liveness probe ────────────────────────────────────────────
# Usage: check_http <label> <url> [expected_string]
check_http() {
  local label="$1"
  local url="$2"
  local expect="${3:-}"
  local body
  local http_code

  http_code=$(curl -s -o /tmp/_smoke_body -w "%{http_code}" \
    --max-time 10 --retry 2 --retry-delay 2 "$url" 2>/dev/null) || {
    fail "${label}: curl failed (network error or timeout)"
    return
  }

  body=$(cat /tmp/_smoke_body 2>/dev/null || echo "")

  if [[ "$http_code" -lt 200 || "$http_code" -ge 400 ]]; then
    fail "${label}: HTTP ${http_code} — expected 2xx/3xx (url=${url})"
    return
  fi

  if [[ -n "$expect" && "$body" != *"$expect"* ]]; then
    fail "${label}: response did not contain expected string '${expect}' (http=${http_code})"
    return
  fi

  pass "${label}: HTTP ${http_code} OK"
}

# ── Helper: Docker container running? ──────────────────────────────────────
check_container() {
  local name="$1"
  local status
  status=$(docker inspect --format '{{.State.Status}}' "$name" 2>/dev/null || echo "missing")
  if [[ "$status" == "running" ]]; then
    pass "Container ${name}: running"
  else
    fail "Container ${name}: status=${status} (expected running)"
  fi
}

# ── Helper: Docker container healthy? ──────────────────────────────────────
check_container_health() {
  local name="$1"
  local health
  health=$(docker inspect --format '{{.State.Health.Status}}' "$name" 2>/dev/null || echo "unknown")
  case "$health" in
    healthy)  pass  "Container ${name}: healthy" ;;
    starting) info  "Container ${name}: health check still starting — skipping" ;;
    "")       info  "Container ${name}: no healthcheck defined" ;;
    *)        fail  "Container ${name}: health=${health}" ;;
  esac
}

# =============================================================================
echo ""
echo "============================================================"
echo " Monitoring Stack Smoke Test — $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "============================================================"
echo ""

# ── 1. Container running checks ────────────────────────────────────────────
echo "--- Container Status ---"
for svc in prometheus grafana loki promtail node-exporter cadvisor; do
  check_container "$svc"
done
echo ""

# ── 2. Container healthcheck checks ───────────────────────────────────────
echo "--- Container Healthchecks ---"
for svc in prometheus grafana loki; do
  check_container_health "$svc"
done
echo ""

# ── 3. Prometheus liveness & readiness ─────────────────────────────────────
echo "--- Prometheus ---"
check_http "Prometheus /-/healthy"  "http://127.0.0.1:9090/-/healthy"  "Prometheus is Healthy"
check_http "Prometheus /-/ready"    "http://127.0.0.1:9090/-/ready"    "Prometheus is Ready"
check_http "Prometheus /api/v1/rules" \
  "http://127.0.0.1:9090/api/v1/rules" "success"

# Verify alert rules were loaded
RULES_STATUS=$(curl -s --max-time 10 \
  "http://127.0.0.1:9090/api/v1/rules" 2>/dev/null | \
  python3 -c "import sys,json; d=json.load(sys.stdin); \
    groups=d.get('data',{}).get('groups',[]); \
    print(len(groups))" 2>/dev/null || echo "0")

if [[ "$RULES_STATUS" -gt 0 ]]; then
  pass "Prometheus alert rules: ${RULES_STATUS} rule group(s) loaded"
else
  fail "Prometheus alert rules: no rule groups loaded (check configs/prometheus/alerts/)"
fi
echo ""

# ── 4. Grafana liveness ─────────────────────────────────────────────────────
echo "--- Grafana ---"
check_http "Grafana /api/health" "http://127.0.0.1:3030/api/health" "ok"
check_http "Grafana datasources" \
  "http://127.0.0.1:3030/api/datasources" ""
echo ""

# ── 5. Loki liveness ───────────────────────────────────────────────────────
echo "--- Loki ---"
# Loki is on the internal monitoring-network; reach it via docker exec
if docker exec loki wget -q --spider http://localhost:3100/ready 2>/dev/null; then
  pass "Loki /ready: reachable inside container"
else
  fail "Loki /ready: not reachable (is loki container running?)"
fi
echo ""

# ── 6. Node Exporter metrics ────────────────────────────────────────────────
echo "--- Node Exporter ---"
# node-exporter is on monitoring-network; check via docker exec on prometheus
if docker exec prometheus wget -q --spider http://node-exporter:9100/metrics 2>/dev/null; then
  pass "Node Exporter /metrics: reachable from Prometheus container"
else
  fail "Node Exporter /metrics: not reachable from Prometheus container"
fi
echo ""

# ── 7. cAdvisor metrics ──────────────────────────────────────────────────────
echo "--- cAdvisor ---"
if docker exec prometheus wget -q --spider http://cadvisor:8080/metrics 2>/dev/null; then
  pass "cAdvisor /metrics: reachable from Prometheus container"
else
  fail "cAdvisor /metrics: not reachable from Prometheus container"
fi
echo ""

# ── 8. Prometheus scrape targets ────────────────────────────────────────────
echo "--- Prometheus Scrape Targets ---"
TARGETS_UP=$(curl -s --max-time 10 \
  "http://127.0.0.1:9090/api/v1/targets?state=active" 2>/dev/null | \
  python3 -c "
import sys, json
d = json.load(sys.stdin)
active = d.get('data', {}).get('activeTargets', [])
up_count = sum(1 for t in active if t.get('health') == 'up')
down_count = sum(1 for t in active if t.get('health') != 'up')
print(f'{up_count} up, {down_count} down')
for t in active:
  status = t.get('health','unknown')
  job    = t.get('labels',{}).get('job','?')
  inst   = t.get('labels',{}).get('instance','?')
  print(f'  [{status.upper():4}] {job} ({inst})')
" 2>/dev/null || echo "parse error")

echo "  ${TARGETS_UP}"

if echo "$TARGETS_UP" | grep -q "0 down"; then
  pass "All Prometheus scrape targets are UP"
else
  fail "One or more Prometheus scrape targets are DOWN — see above"
fi
echo ""

# ── Summary ────────────────────────────────────────────────────────────────
echo "============================================================"
if [[ "$FAILURES" -eq 0 ]]; then
  echo -e "${GREEN} ALL CHECKS PASSED${NC}"
else
  echo -e "${RED} ${FAILURES} CHECK(S) FAILED${NC}"
fi
echo "============================================================"
echo ""

exit "$FAILURES"
