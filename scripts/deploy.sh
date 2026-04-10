#!/usr/bin/env bash
# ============================================================
# deploy.sh — AI Voice Agent SaaS Platform Deployment
# Uses split-stack compose files:
#   ai-infra/docker-compose.yaml    — Infrastructure (postgres, redis, ollama, etc.)
#   dograh/docker-compose.yaml      — Voice platform (API + UI)
#   fazle-ai/docker-compose.yaml    — Fazle AI services
#   scripts/phase5-standalone.yaml  — Phase-5 autonomous services
#
# Usage:
#   bash scripts/deploy.sh              # Full deploy
#   bash scripts/deploy.sh status       # Service status
#   bash scripts/deploy.sh restart      # Restart all services
#   bash scripts/deploy.sh update fazle # Rolling update Fazle only
#   bash scripts/deploy.sh rollback     # Rollback to previous images
#   bash scripts/deploy.sh logs [svc]   # Tail logs
# ============================================================
set -euo pipefail

DEPLOY_DIR="/home/azim/ai-call-platform"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"
ACTION="${1:-deploy}"

# ── Compose file paths (canonical split-stack) ─────────────
INFRA_COMPOSE="$PROJECT_DIR/ai-infra/docker-compose.yaml"
DOGRAH_COMPOSE="$PROJECT_DIR/dograh/docker-compose.yaml"
FAZLE_COMPOSE="$PROJECT_DIR/fazle-ai/docker-compose.yaml"
PHASE5_COMPOSE="$PROJECT_DIR/scripts/phase5-standalone.yaml"

# Helper: run docker compose against a specific stack
dc_infra()  { docker compose -f "$INFRA_COMPOSE"  --env-file "$ENV_FILE" "$@"; }
dc_dograh() { docker compose -f "$DOGRAH_COMPOSE" --env-file "$ENV_FILE" "$@"; }
dc_fazle()  { docker compose -f "$FAZLE_COMPOSE"  --env-file "$ENV_FILE" "$@"; }
dc_phase5() { docker compose -f "$PHASE5_COMPOSE" --env-file "$ENV_FILE" "$@"; }

ROLLBACK_TAG="rollback-prev"
ROLLBACK_MANIFEST="$DEPLOY_DIR/backups/.rollback-manifest"

# ── tag_current_images ──────────────────────────────────────
# Snapshots every running container's image with a :rollback-prev
# tag and writes a manifest so rollback knows the original tag.
#
# Manifest format (pipe-delimited):
#   container_name|original_image|rollback_image
# Example:
#   fazle-brain|fazle-brain:latest|fazle-brain:rollback-prev
tag_current_images() {
    echo "  [DEPLOY] Tagging current images for rollback..."
    mkdir -p "$(dirname "$ROLLBACK_MANIFEST")"
    : > "$ROLLBACK_MANIFEST"  # truncate

    local tagged=0
    for container in $(docker ps --format '{{.Names}}'); do
        local image
        image=$(docker inspect --format='{{.Config.Image}}' "$container" 2>/dev/null) || continue

        if docker image inspect "$image" &>/dev/null; then
            local base="${image%%:*}"
            local rollback_ref="${base}:${ROLLBACK_TAG}"
            if docker tag "$image" "$rollback_ref" 2>/dev/null; then
                echo "    ✓ $container | $image → $rollback_ref"
                echo "${container}|${image}|${rollback_ref}" >> "$ROLLBACK_MANIFEST"
                tagged=$((tagged + 1))
            else
                echo "    ✗ $container | failed to tag $image"
            fi
        fi
    done

    echo "  [DEPLOY] Rollback manifest saved ($tagged images) → $ROLLBACK_MANIFEST"
}

# ── do_rollback ─────────────────────────────────────────────
# Restores the previous deployment by re-tagging rollback images
# back to their original names, then restarting all stacks.
#
# 4-phase flow:
#   1. RE-TAG   — docker tag <rollback> <original> so compose resolves them
#   2. STOP     — tear down all stacks in reverse order
#   3. RESTART  — bring stacks up with --no-build --pull never
#   4. HEALTH   — verify services are healthy; exit 1 if not
do_rollback() {
    echo "============================================"
    echo " [ROLLBACK] Rolling back to previous deployment"
    echo "============================================"

    # ── Validate manifest exists ────────────────────────────
    if [ ! -f "$ROLLBACK_MANIFEST" ]; then
        echo "[ROLLBACK] ERROR: No rollback manifest found at $ROLLBACK_MANIFEST"
        echo "[ROLLBACK] A successful deploy must run first to create a rollback snapshot."
        exit 1
    fi

    local entry_count
    entry_count=$(grep -c '.' "$ROLLBACK_MANIFEST" 2>/dev/null || echo 0)
    if [ "$entry_count" -eq 0 ]; then
        echo "[ROLLBACK] ERROR: Rollback manifest is empty."
        exit 1
    fi
    echo "[ROLLBACK] Found manifest with $entry_count image(s)"

    # ── Phase 1: RE-TAG ─────────────────────────────────────
    echo ""
    echo "[ROLLBACK] Phase 1/4: Retagging images..."
    local restored=0
    local skipped=0

    while IFS='|' read -r container original_image rollback_ref; do
        # Skip blank lines and comments
        [[ -z "$container" || "$container" == \#* ]] && continue

        if docker image inspect "$rollback_ref" &>/dev/null; then
            docker tag "$rollback_ref" "$original_image"
            echo "  ✓ docker tag $rollback_ref $original_image"
            restored=$((restored + 1))
        else
            echo "  ✗ $rollback_ref not found — skipping $container"
            skipped=$((skipped + 1))
        fi
    done < "$ROLLBACK_MANIFEST"

    echo "[ROLLBACK] Retagged: $restored | Skipped: $skipped"

    if [ "$restored" -eq 0 ]; then
        echo "[ROLLBACK] FATAL: No images could be restored. Aborting."
        exit 1
    fi

    # ── Phase 2: STOP (reverse order) ───────────────────────
    echo ""
    echo "[ROLLBACK] Phase 2/4: Stopping stacks (reverse order)..."
    dc_phase5 down --remove-orphans 2>/dev/null || true
    dc_fazle  down --remove-orphans 2>/dev/null || true
    dc_dograh down --remove-orphans 2>/dev/null || true
    dc_infra  down --remove-orphans 2>/dev/null || true
    echo "[ROLLBACK] All stacks stopped."

    # ── Phase 3: RESTART (correct order, no build, no pull) ─
    echo ""
    echo "[ROLLBACK] Phase 3/4: Restarting stacks (no rebuild, no pull)..."
    echo "  Starting infrastructure..."
    dc_infra  up -d --no-build --pull never
    sleep 10
    echo "  Starting Dograh voice platform..."
    dc_dograh up -d --no-build --pull never
    sleep 5
    echo "  Starting Fazle AI services..."
    dc_fazle  up -d --no-build --pull never
    sleep 5
    echo "  Starting Phase-5 autonomous services..."
    dc_phase5 up -d --no-build --pull never 2>/dev/null || true
    echo "[ROLLBACK] All stacks restarted."

    # ── Phase 4: HEALTH CHECK ───────────────────────────────
    echo ""
    echo "[ROLLBACK] Phase 4/4: Verifying service health..."
    sleep 10

    local unhealthy=0
    local ALL_SERVICES=(
        "ai-postgres" "ai-redis" "minio" "dograh-api" "dograh-ui" "livekit"
        "qdrant" "ollama" "fazle-api" "fazle-brain" "fazle-memory"
        "fazle-task-engine" "fazle-web-intelligence" "fazle-trainer" "fazle-ui"
        "fazle-guardrail-engine"
        "prometheus" "grafana" "loki"
    )

    for svc in "${ALL_SERVICES[@]}"; do
        echo -n "  $svc: "
        local healthy=false
        for _ in $(seq 1 30); do
            local status
            status=$(docker inspect --format='{{.State.Health.Status}}' "$svc" 2>/dev/null || echo "no-healthcheck")
            if [ "$status" = "healthy" ]; then
                echo "✓ healthy"
                healthy=true
                break
            elif [ "$status" = "no-healthcheck" ]; then
                # No healthcheck defined — accept if container is running
                local running
                running=$(docker inspect --format='{{.State.Running}}' "$svc" 2>/dev/null || echo "false")
                if [ "$running" = "true" ]; then
                    echo "- running (no healthcheck)"
                    healthy=true
                else
                    echo "✗ not running"
                fi
                break
            fi
            sleep 2
        done
        if [ "$healthy" = false ]; then
            echo "✗ UNHEALTHY (check: docker logs $svc)"
            unhealthy=$((unhealthy + 1))
        fi
    done

    # ── Summary ─────────────────────────────────────────────
    echo ""
    echo "============================================"
    if [ "$unhealthy" -gt 0 ]; then
        echo " [ROLLBACK] FAILED: $unhealthy service(s) unhealthy"
        echo "============================================"
        print_status
        exit 1
    fi
    echo " [ROLLBACK] SUCCESS: $restored image(s) restored, all services healthy"
    echo "============================================"
    print_status
}

# ── Helper functions ────────────────────────────────────────
print_status() {
    echo ""
    echo "============================================"
    echo " Service Status"
    echo "============================================"
    docker compose -f "$INFRA_COMPOSE"  --env-file "$ENV_FILE" ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
    docker compose -f "$DOGRAH_COMPOSE" --env-file "$ENV_FILE" ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
    docker compose -f "$FAZLE_COMPOSE"  --env-file "$ENV_FILE" ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
    docker compose -f "$PHASE5_COMPOSE" --env-file "$ENV_FILE" ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || true
    echo ""
    echo " Resource Usage"
    echo "============================================"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" 2>/dev/null || true
    echo ""
    echo "============================================"
    echo " Access Points"
    echo "============================================"
    echo "  Dashboard:   https://iamazim.com"
    echo "  API:         https://api.iamazim.com/api/v1/health"
    echo "  LiveKit:     wss://livekit.iamazim.com"
    echo "  TURN:        turn:turn.iamazim.com:3478"
    echo "  Fazle UI:    https://fazle.iamazim.com"
    echo "  Fazle API:   https://fazle.iamazim.com/api/fazle/health"
    echo "  Grafana:     https://iamazim.com/grafana/"
    echo "============================================"
}

wait_healthy() {
    local services=("$@")
    for svc in "${services[@]}"; do
        echo -n "  $svc: "
        for i in $(seq 1 30); do
            STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$svc" 2>/dev/null || echo "no-healthcheck")
            if [ "$STATUS" = "healthy" ]; then
                echo "✓ healthy"
                break
            elif [ "$STATUS" = "no-healthcheck" ]; then
                echo "- running (no healthcheck)"
                break
            fi
            sleep 2
        done
        if [ "$STATUS" != "healthy" ] && [ "$STATUS" != "no-healthcheck" ]; then
            echo "⚠ still $STATUS (check logs: docker logs $svc)"
        fi
    done
}

# ── Command: rollback ───────────────────────────────────────
if [ "$ACTION" = "rollback" ]; then
    do_rollback
    exit 0
fi

# ── Command: status ─────────────────────────────────────────
if [ "$ACTION" = "status" ]; then
    print_status
    exit 0
fi

# ── Command: logs ───────────────────────────────────────────
if [ "$ACTION" = "logs" ]; then
    SVC="${2:-}"
    if [ -n "$SVC" ]; then
        # Search all stacks for the service
        dc_infra  logs -f --tail 100 "$SVC" 2>/dev/null || \
        dc_dograh logs -f --tail 100 "$SVC" 2>/dev/null || \
        dc_fazle  logs -f --tail 100 "$SVC" 2>/dev/null || \
        dc_phase5 logs -f --tail 100 "$SVC" 2>/dev/null || \
        echo "Service '$SVC' not found in any stack."
    else
        echo "Usage: deploy.sh logs <service-name>"
    fi
    exit 0
fi

# ── Command: restart ────────────────────────────────────────
if [ "$ACTION" = "restart" ]; then
    echo "Restarting all services..."
    dc_infra  restart
    dc_dograh restart
    dc_fazle  restart
    dc_phase5 restart 2>/dev/null || true
    sleep 5
    print_status
    exit 0
fi

# ── Command: update (rolling) ──────────────────────────────
if [ "$ACTION" = "update" ]; then
    TARGET="${2:-}"
    if [ "$TARGET" = "fazle" ]; then
        echo "Rolling update: Fazle AI System..."
        FAZLE_SERVICES="fazle-api fazle-brain fazle-memory fazle-task-engine fazle-web-intelligence fazle-trainer fazle-ui fazle-guardrail-engine"
        dc_fazle build $FAZLE_SERVICES
        for svc in $FAZLE_SERVICES; do
            echo "  Updating $svc..."
            dc_fazle up -d --no-deps --build "$svc"
            sleep 3
        done
        wait_healthy fazle-api fazle-brain fazle-memory fazle-task-engine fazle-web-intelligence fazle-trainer fazle-ui fazle-guardrail-engine
    elif [ "$TARGET" = "infra" ]; then
        echo "Updating infrastructure stack..."
        dc_infra up -d
    elif [ "$TARGET" = "dograh" ]; then
        echo "Updating Dograh voice platform..."
        dc_dograh up -d
    elif [ "$TARGET" = "phase5" ]; then
        echo "Updating Phase-5 autonomous services..."
        dc_phase5 up -d
    elif [ "$TARGET" = "monitoring" ]; then
        echo "Updating monitoring stack..."
        dc_infra up -d --no-deps prometheus grafana node-exporter cadvisor loki promtail
    elif [ -n "$TARGET" ]; then
        echo "Updating service: $TARGET..."
        # Try each stack until the service is found
        dc_fazle  up -d --no-deps --build "$TARGET" 2>/dev/null || \
        dc_infra  up -d --no-deps "$TARGET" 2>/dev/null || \
        dc_dograh up -d --no-deps "$TARGET" 2>/dev/null || \
        dc_phase5 up -d --no-deps "$TARGET" 2>/dev/null || \
        { echo "Service '$TARGET' not found in any stack."; exit 1; }
        sleep 3
        wait_healthy "$TARGET"
    else
        echo "Usage: deploy.sh update [fazle|infra|dograh|phase5|monitoring|<service-name>]"
        exit 1
    fi
    echo "Update complete."
    exit 0
fi

# ── Command: deploy (full) ─────────────────────────────────
echo "============================================"
echo " AI Voice Agent SaaS — Full Deployment"
echo "============================================"

# ── Pre-flight checks ──────────────────────────────────────
echo "[1/9] Pre-flight checks..."

if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker is not installed."
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo "ERROR: Docker Compose V2 is not installed."
    exit 1
fi

if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "ERROR: .env file not found. Copy .env.example to .env and configure it."
    echo "  cp $PROJECT_DIR/.env.example $PROJECT_DIR/.env"
    exit 1
fi

# ── Create deployment directory structure ───────────────────
echo "[2/9] Setting up directory structure..."
mkdir -p "$DEPLOY_DIR"/{logs,backups}

# ── Tag current images for rollback ─────────────────────────
echo "[3/9] Tagging current images for rollback..."
tag_current_images

# ── Backup existing deployment ──────────────────────────────
echo "[4/9] Backing up current state..."
BACKUP_TS=$(date +%Y%m%d_%H%M%S)
for compose in "$INFRA_COMPOSE" "$DOGRAH_COMPOSE" "$FAZLE_COMPOSE" "$PHASE5_COMPOSE"; do
    if [ -f "$compose" ]; then
        docker compose -f "$compose" --env-file "$ENV_FILE" config \
            > "$DEPLOY_DIR/backups/$(basename "$(dirname "$compose")")-backup-$BACKUP_TS.yaml" 2>/dev/null || true
    fi
done

# ── Validate compose files ──────────────────────────────────
echo "[5/9] Validating split-stack compose files..."
for compose in "$INFRA_COMPOSE" "$DOGRAH_COMPOSE" "$FAZLE_COMPOSE" "$PHASE5_COMPOSE"; do
    docker compose -f "$compose" --env-file "$ENV_FILE" config --quiet
    echo "  ✓ $(basename "$(dirname "$compose")")/$(basename "$compose") is valid"
done

# ── Pull latest images ─────────────────────────────────────
echo "[6/9] Pulling latest images..."
dc_infra  pull --ignore-buildable
dc_dograh pull --ignore-buildable
dc_phase5 pull --ignore-buildable 2>/dev/null || true

# ── Build local services ────────────────────────────────────
echo "[7/9] Building Fazle services..."
dc_fazle build

# ── Start services (in order) ──────────────────────────────
echo "[8/9] Starting services..."
echo "  Starting infrastructure..."
dc_infra up -d
sleep 10
echo "  Starting Dograh voice platform..."
dc_dograh up -d
sleep 5
echo "  Starting Fazle AI services..."
dc_fazle up -d
sleep 5
echo "  Starting Phase-5 autonomous services..."
dc_phase5 up -d 2>/dev/null || true

# ── Wait for health checks ─────────────────────────────────
echo "[9/9] Waiting for services to become healthy..."
sleep 10

ALL_SERVICES=(
    "ai-postgres" "ai-redis" "minio" "dograh-api" "dograh-ui" "livekit"
    "qdrant" "ollama" "fazle-api" "fazle-brain" "fazle-memory"
    "fazle-task-engine" "fazle-web-intelligence" "fazle-trainer" "fazle-ui"
    "fazle-guardrail-engine"
    "prometheus" "grafana" "loki"
)
wait_healthy "${ALL_SERVICES[@]}"

# ── Summary ─────────────────────────────────────────────────
echo ""
echo "Deployment complete!"
print_status
