#!/usr/bin/env bash
# ============================================================
# stack-status.sh — Show health and status of all stacks
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$ROOT_DIR/.env"

echo "============================================================"
echo " Stack Status Report"
echo "============================================================"
echo ""

for stack in ai-infra dograh fazle-ai; do
  dir="$ROOT_DIR/$stack"
  if [ ! -f "$dir/docker-compose.yaml" ]; then
    echo "[$stack] No docker-compose.yaml found"
    echo ""
    continue
  fi

  echo "── $stack ──"
  docker compose -f "$dir/docker-compose.yaml" --env-file "$ENV_FILE" -p "$stack" ps \
    --format "table {{.Name}}\t{{.Status}}\t{{.Health}}" 2>/dev/null || echo "  (not running)"
  echo ""
done

# Phase-5 standalone
if [ -f "$ROOT_DIR/scripts/phase5-standalone.yaml" ]; then
  echo "── phase5 ──"
  docker compose -f "$ROOT_DIR/scripts/phase5-standalone.yaml" --env-file "$ENV_FILE" -p "phase5" ps \
    --format "table {{.Name}}\t{{.Status}}\t{{.Health}}" 2>/dev/null || echo "  (not running)"
  echo ""
fi

echo "── Docker Networks ──"
for net in app-network db-network ai-network monitoring-network; do
  if docker network inspect "$net" >/dev/null 2>&1; then
    count=$(docker network inspect "$net" --format '{{len .Containers}}')
    echo "  $net: $count containers"
  else
    echo "  $net: NOT CREATED"
  fi
done
echo ""

echo "── Disk Usage ──"
df -h / | tail -1 | awk '{printf "  Used: %s / %s (%s)\n", $3, $2, $5}'
docker system df --format "table {{.Type}}\t{{.TotalCount}}\t{{.Size}}\t{{.Reclaimable}}" 2>/dev/null || true
