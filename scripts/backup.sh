#!/usr/bin/env bash
# ============================================================
# backup.sh — Backup PostgreSQL, Qdrant, MinIO, and configs
# Usage: bash scripts/backup.sh
# Cron:  0 2 * * * /home/azim/ai-call-platform/scripts/backup.sh >> /var/log/backup.log 2>&1
# ============================================================
set -euo pipefail

BACKUP_DIR="/home/azim/ai-call-platform/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=7
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
STEP=0
TOTAL=7

echo "============================================"
echo " Backup — $TIMESTAMP"
echo "============================================"

mkdir -p "$BACKUP_DIR"

# ── Pre-backup health check ────────────────────────────────
STEP=$((STEP + 1))
echo "[$STEP/$TOTAL] Pre-backup health check..."
HEALTHY=true
for svc in ai-postgres ai-redis minio qdrant; do
    if docker inspect --format='{{.State.Health.Status}}' "$svc" 2>/dev/null | grep -q "healthy"; then
        echo "  ✓ $svc — healthy"
    elif docker inspect --format='{{.State.Status}}' "$svc" 2>/dev/null | grep -q "running"; then
        echo "  ⚠ $svc — running (no healthcheck)"
    else
        echo "  ✗ $svc — NOT running"
        HEALTHY=false
    fi
done
if [ "$HEALTHY" = false ]; then
    echo "  WARNING: Some services are down. Backup may be incomplete."
fi

# ── PostgreSQL dump ─────────────────────────────────────────
STEP=$((STEP + 1))
echo "[$STEP/$TOTAL] Backing up PostgreSQL..."
if docker exec ai-postgres pg_dumpall -U postgres | gzip > "$BACKUP_DIR/postgres-$TIMESTAMP.sql.gz"; then
    echo "  ✓ Saved: postgres-$TIMESTAMP.sql.gz ($(du -h "$BACKUP_DIR/postgres-$TIMESTAMP.sql.gz" | cut -f1))"
else
    echo "  ✗ PostgreSQL backup FAILED"
fi

# ── Qdrant snapshot ─────────────────────────────────────────
STEP=$((STEP + 1))
echo "[$STEP/$TOTAL] Backing up Qdrant vector database..."
QDRANT_SNAPSHOT=$(docker exec qdrant curl -sf -X POST "http://localhost:6333/snapshots" 2>/dev/null | grep -o '"name":"[^"]*"' | head -1 | cut -d'"' -f4) || true
if [ -n "${QDRANT_SNAPSHOT:-}" ]; then
    docker exec qdrant curl -sf "http://localhost:6333/snapshots/${QDRANT_SNAPSHOT}" -o "/tmp/${QDRANT_SNAPSHOT}" 2>/dev/null
    docker cp "qdrant:/tmp/${QDRANT_SNAPSHOT}" "$BACKUP_DIR/qdrant-$TIMESTAMP.snapshot"
    docker exec qdrant rm -f "/tmp/${QDRANT_SNAPSHOT}" 2>/dev/null || true
    docker exec qdrant curl -sf -X DELETE "http://localhost:6333/snapshots/${QDRANT_SNAPSHOT}" >/dev/null 2>&1 || true
    echo "  ✓ Saved: qdrant-$TIMESTAMP.snapshot ($(du -h "$BACKUP_DIR/qdrant-$TIMESTAMP.snapshot" | cut -f1))"
else
    echo "  ⚠ Qdrant snapshot skipped (service unavailable or no data)"
fi

# ── Redis RDB snapshot ──────────────────────────────────────
STEP=$((STEP + 1))
echo "[$STEP/$TOTAL] Backing up Redis..."
REDIS_PASS="${REDIS_PASSWORD:-redissecret}"
if docker exec ai-redis redis-cli -a "$REDIS_PASS" BGSAVE >/dev/null 2>&1; then
    sleep 2
    docker cp ai-redis:/data/dump.rdb "$BACKUP_DIR/redis-$TIMESTAMP.rdb" 2>/dev/null || true
    echo "  ✓ Saved: redis-$TIMESTAMP.rdb"
else
    echo "  ⚠ Redis backup skipped"
fi

# ── MinIO data (bucket listing + metadata) ──────────────────
STEP=$((STEP + 1))
echo "[$STEP/$TOTAL] Backing up MinIO metadata..."
docker exec minio mc alias set local http://localhost:9000 "${MINIO_ACCESS_KEY:-minioadmin}" "${MINIO_SECRET_KEY:-minioadmin}" >/dev/null 2>&1 || true
docker exec minio mc ls local/ > "$BACKUP_DIR/minio-buckets-$TIMESTAMP.txt" 2>/dev/null || true
# Backup bucket policies and metadata
docker exec minio mc stat local/ > "$BACKUP_DIR/minio-stats-$TIMESTAMP.txt" 2>/dev/null || true
for bucket in $(docker exec minio mc ls --json local/ 2>/dev/null | grep -o '"key":"[^"]*"' | cut -d'"' -f4); do
    docker exec minio mc policy get "local/${bucket}" >> "$BACKUP_DIR/minio-policies-$TIMESTAMP.txt" 2>/dev/null || true
done
echo "  ✓ Saved bucket listing + metadata"

# ── Docker Compose config snapshot ──────────────────────────
STEP=$((STEP + 1))
echo "[$STEP/$TOTAL] Saving compose + config snapshots..."
for compose in ai-infra/docker-compose.yaml dograh/docker-compose.yaml fazle-ai/docker-compose.yaml scripts/phase5-standalone.yaml; do
    if [ -f "$PROJECT_DIR/$compose" ]; then
        cp "$PROJECT_DIR/$compose" "$BACKUP_DIR/$(echo "$compose" | tr '/' '-')-$TIMESTAMP.yaml"
    fi
done
if [ -f "$PROJECT_DIR/.env" ]; then
    cp "$PROJECT_DIR/.env" "$BACKUP_DIR/env-$TIMESTAMP.bak"
    chmod 600 "$BACKUP_DIR/env-$TIMESTAMP.bak"
fi
# Backup all config files
tar czf "$BACKUP_DIR/configs-$TIMESTAMP.tar.gz" -C "$PROJECT_DIR" configs/ 2>/dev/null || true
echo "  ✓ Saved compose + env + configs snapshots"

# ── Cleanup old backups ────────────────────────────────────
STEP=$((STEP + 1))
echo "[$STEP/$TOTAL] Cleaning backups older than $RETENTION_DAYS days..."
DELETED=0
for pattern in "*.sql.gz" "*.snapshot" "*.rdb" "minio-buckets-*.txt" "minio-stats-*.txt" "minio-policies-*.txt" "docker-compose-*.yaml" "env-*.bak" "configs-*.tar.gz"; do
    COUNT=$(find "$BACKUP_DIR" -name "$pattern" -mtime +$RETENTION_DAYS -delete -print 2>/dev/null | wc -l)
    DELETED=$((DELETED + COUNT))
done
echo "  ✓ Removed $DELETED old backup file(s)"

echo ""
echo "============================================"
echo " Backup complete — $TIMESTAMP"
echo "============================================"
echo "Files:"
ls -lh "$BACKUP_DIR"/*-$TIMESTAMP* 2>/dev/null
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
echo ""
echo "Total backup directory size: $TOTAL_SIZE"
