#!/usr/bin/env bash
# ============================================================
# stack-down.sh — Stop stacks in reverse order
# Usage: ./scripts/stack-down.sh [--stack ai-infra|dograh|fazle-ai]
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$ROOT_DIR/.env"

stop_stack() {
  local name="$1"
  local dir="$ROOT_DIR/$name"

  if [ ! -f "$dir/docker-compose.yaml" ]; then
    echo "SKIP: $dir/docker-compose.yaml not found"
    return 0
  fi

  echo "── Stopping $name ──"
  docker compose -f "$dir/docker-compose.yaml" --env-file "$ENV_FILE" -p "$name" down
  echo ""
}

TARGET="${1:-all}"

case "$TARGET" in
  --stack)
    stop_stack "${2:?Usage: --stack ai-infra|dograh|fazle-ai}"
    ;;
  all|"")
    # Reverse order: phase5 → fazle-ai → dograh → ai-infra
    if [ -f "$ROOT_DIR/scripts/phase5-standalone.yaml" ]; then
      echo "── Stopping phase5 ──"
      docker compose -f "$ROOT_DIR/scripts/phase5-standalone.yaml" --env-file "$ENV_FILE" -p "phase5" down 2>/dev/null || true
      echo ""
    fi
    stop_stack "fazle-ai"
    stop_stack "dograh"
    stop_stack "ai-infra"
    echo "── All stacks stopped ──"
    ;;
  *)
    echo "Usage: $0 [--stack ai-infra|dograh|fazle-ai]"
    exit 1
    ;;
esac
