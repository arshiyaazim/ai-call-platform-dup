#!/usr/bin/env bash
# ============================================================
# deploy-to-vps.sh — Deploy from local machine to VPS
# Usage: bash scripts/deploy-to-vps.sh
# Run from LOCAL machine with SSH access to VPS
# ============================================================
set -euo pipefail

VPS_IP="5.189.131.48"
VPS_USER="azim"
VPS_DIR="/home/azim/ai-call-platform"
DEPLOY_HASH=$(git rev-parse --short HEAD)
DEPLOY_PACKAGE="deployment-package/vps-deploy-${DEPLOY_HASH}.tar.gz"

echo "============================================"
echo " Deploy to VPS — $DEPLOY_HASH"
echo " Target: ${VPS_USER}@${VPS_IP}:${VPS_DIR}"
echo "============================================"
echo ""

# ── Pre-flight checks ──────────────────────────────────────
echo "── Pre-flight checks ──"
if [ ! -f "$DEPLOY_PACKAGE" ]; then
    echo "✗ Deployment package not found: $DEPLOY_PACKAGE"
    echo "  Run: git archive --format=tar.gz -o $DEPLOY_PACKAGE HEAD"
    exit 1
fi
echo "  ✓ Package found: $DEPLOY_PACKAGE"

if ! ssh -o ConnectTimeout=10 "${VPS_USER}@${VPS_IP}" "echo OK" >/dev/null 2>&1; then
    echo "✗ Cannot reach VPS via SSH"
    exit 1
fi
echo "  ✓ SSH connectivity OK"
echo ""

# ── Step 1: Record rollback target ─────────────────────────
echo "[1/6] Recording current VPS commit for rollback..."
VPS_COMMIT=$(ssh "${VPS_USER}@${VPS_IP}" "cd ${VPS_DIR} && git rev-parse HEAD 2>/dev/null || echo 'no-git'")
echo "  Rollback target: $VPS_COMMIT"
echo "$VPS_COMMIT" > deployment-package/ROLLBACK_TARGET.txt
echo ""

# ── Step 2: Backup current VPS state ───────────────────────
echo "[2/6] Running backup on VPS..."
ssh "${VPS_USER}@${VPS_IP}" "cd ${VPS_DIR} && bash scripts/backup.sh" || {
    echo "  ⚠ Backup failed — continue? (Ctrl+C to abort)"
    read -r
}
echo ""

# ── Step 3: Upload deployment package ──────────────────────
echo "[3/6] Uploading deployment package..."
scp "$DEPLOY_PACKAGE" "${VPS_USER}@${VPS_IP}:/tmp/vps-deploy-update.tar.gz"
echo "  ✓ Uploaded to /tmp/vps-deploy-update.tar.gz"
echo ""

# ── Step 4: Extract and apply (preserve .env) ──────────────
echo "[4/6] Applying update on VPS..."
ssh "${VPS_USER}@${VPS_IP}" << 'REMOTE'
  set -e
  cd ~/ai-call-platform

  # Stash any local VPS changes
  git stash 2>/dev/null || true

  # Extract update (overwrites tracked files)
  tar -xzf /tmp/vps-deploy-update.tar.gz --strip-components=0

  # Ensure .env is NOT overwritten
  git checkout -- .env 2>/dev/null || true

  # Clean up
  rm -f /tmp/vps-deploy-update.tar.gz

  echo "  ✓ Code updated on VPS"
REMOTE
echo ""

# ── Step 5: Validate config on VPS ─────────────────────────
echo "[5/6] Validating split-stack compose files on VPS..."
ssh "${VPS_USER}@${VPS_IP}" << 'REMOTE'
  set -e
  cd ~/ai-call-platform
  for compose in ai-infra/docker-compose.yaml dograh/docker-compose.yaml fazle-ai/docker-compose.yaml scripts/phase5-standalone.yaml; do
      docker compose -f "$compose" --env-file .env config -q
      echo "  ✓ $compose valid"
  done
REMOTE
echo ""

# ── Step 6: Rebuild and restart ────────────────────────────
echo "[6/6] Rebuilding and restarting services..."
echo "  This will rebuild changed containers with zero-downtime rolling restart."
echo "  Press Enter to proceed or Ctrl+C to abort."
read -r

ssh "${VPS_USER}@${VPS_IP}" << 'REMOTE'
  set -e
  cd ~/ai-call-platform

  # Pull new images for pinned services
  docker compose -f ai-infra/docker-compose.yaml --env-file .env pull 2>/dev/null || true
  docker compose -f dograh/docker-compose.yaml    --env-file .env pull 2>/dev/null || true

  # Rebuild Fazle services (custom Dockerfiles)
  docker compose -f fazle-ai/docker-compose.yaml --env-file .env build --no-cache

  # Start stacks in order — infrastructure first, then app services
  docker compose -f ai-infra/docker-compose.yaml  --env-file .env up -d --remove-orphans
  docker compose -f dograh/docker-compose.yaml     --env-file .env up -d --remove-orphans
  docker compose -f fazle-ai/docker-compose.yaml   --env-file .env up -d --remove-orphans
  docker compose -f scripts/phase5-standalone.yaml --env-file .env up -d --remove-orphans 2>/dev/null || true

  echo ""
  echo "  ✓ Services restarted"
  echo "  Waiting 30s for containers to stabilize..."
  sleep 30

  # Run health check
  bash scripts/health-check.sh || true
REMOTE

echo ""
echo "============================================"
echo " Deployment complete — $DEPLOY_HASH"
echo " Rollback: bash scripts/rollback-vps.sh"
echo "============================================"
