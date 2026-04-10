#!/usr/bin/env bash
# ============================================================
# stack-up.sh — Start all three stacks in correct order
# Usage: ./scripts/stack-up.sh [--stack ai-infra|dograh|fazle-ai]
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$ROOT_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: .env file not found at $ENV_FILE"
  exit 1
fi

start_stack() {
  local name="$1"
  local dir="$ROOT_DIR/$name"

  if [ ! -f "$dir/docker-compose.yaml" ]; then
    echo "ERROR: $dir/docker-compose.yaml not found"
    return 1
  fi

  echo "── Starting $name ──"
  docker compose -f "$dir/docker-compose.yaml" --env-file "$ENV_FILE" -p "$name" up -d
  echo ""
}

wait_healthy() {
  local container="$1"
  local timeout="${2:-120}"
  echo "  Waiting for $container to be healthy (timeout: ${timeout}s)..."
  local elapsed=0
  while [ $elapsed -lt "$timeout" ]; do
    local status
    status=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "missing")
    if [ "$status" = "healthy" ]; then
      echo "  [OK] $container is healthy"
      return 0
    fi
    sleep 5
    elapsed=$((elapsed + 5))
  done
  echo "  [WARN] $container did not become healthy within ${timeout}s (status: $status)"
  return 0  # Don't fail — other services may still start
}

# Ensure networks exist
"$SCRIPT_DIR/create-networks.sh"
echo ""

TARGET="${1:-all}"

case "$TARGET" in
  --stack)
    start_stack "${2:?Usage: --stack ai-infra|dograh|fazle-ai}"
    ;;
  all|"")
    # Stack 1: Infrastructure (databases, caches, monitoring)
    start_stack "ai-infra"
    wait_healthy "ai-postgres" 60
    wait_healthy "ai-redis" 30
    wait_healthy "ollama" 60

    # Stack 2: Dograh platform
    start_stack "dograh"
    wait_healthy "dograh-api" 90

    # Stack 3: Fazle AI system
    start_stack "fazle-ai"

    # Stack 4: Phase-5 autonomous services
    if [ -f "$ROOT_DIR/scripts/phase5-standalone.yaml" ]; then
      echo "── Starting phase5 ──"
      docker compose -f "$ROOT_DIR/scripts/phase5-standalone.yaml" --env-file "$ENV_FILE" -p "phase5" up -d
      echo ""
    fi

    echo "── All stacks started ──"
    echo ""
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | head -40
    ;;
  *)
    echo "Usage: $0 [--stack ai-infra|dograh|fazle-ai]"
    exit 1
    ;;
esac
