#!/usr/bin/env bash
# ============================================================
# Fazle Database Migration Script
# Idempotent — safe to run multiple times
# Usage: ./scripts/db-migrate.sh
# ============================================================
set -euo pipefail

# ── Configuration ───────────────────────────────────────────
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-postgres}"
POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"

export PGPASSWORD="$POSTGRES_PASSWORD"

echo "=== Fazle Database Migration ==="
echo "Host: $POSTGRES_HOST:$POSTGRES_PORT / $POSTGRES_DB"

# ── Wait for PostgreSQL ────────────────────────────────────
echo "[1/3] Waiting for PostgreSQL..."
for i in $(seq 1 30); do
    if pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -q 2>/dev/null; then
        echo "  PostgreSQL is ready"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "  ERROR: PostgreSQL not reachable after 30 attempts"
        exit 1
    fi
    sleep 2
done

# ── Run SQL migrations ─────────────────────────────────────
echo "[2/3] Running scheduler table migrations..."
MIGRATION_DIR="$(dirname "$0")/../fazle-system/tasks/migrations"

for sql_file in "$MIGRATION_DIR"/*.sql; do
    if [ -f "$sql_file" ]; then
        echo "  Applying: $(basename "$sql_file")"
        psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
            -f "$sql_file" --set ON_ERROR_STOP=1 -q
    fi
done
echo "  SQL migrations complete"

# ── Validate Qdrant collections ────────────────────────────
echo "[3/3] Checking Qdrant collections..."
QDRANT_URL="${QDRANT_URL:-http://qdrant:6333}"

if curl -sf "${QDRANT_URL}/collections" >/dev/null 2>&1; then
    COLLECTIONS=$(curl -sf "${QDRANT_URL}/collections" | python3 -c "
import sys, json
data = json.load(sys.stdin)
names = [c['name'] for c in data.get('result', {}).get('collections', [])]
print(' '.join(names) if names else '(none)')
" 2>/dev/null || echo "(parse error)")
    echo "  Qdrant collections: $COLLECTIONS"
else
    echo "  WARNING: Qdrant not reachable at $QDRANT_URL (non-fatal)"
fi

echo ""
echo "=== Migration complete ==="
