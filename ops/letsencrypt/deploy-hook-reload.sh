#!/usr/bin/env bash
# ============================================================
# deploy-hook-reload.sh — Certbot deploy hook
# Installed to: /etc/letsencrypt/renewal-hooks/deploy/iamazim-reload.sh
# Called automatically by certbot after successful renewal.
#
# Actions:
#   1. Reload Nginx (host systemd or Docker container)
#   2. Restart Coturn (Docker container picks up new cert mounts)
# ============================================================
set -euo pipefail

LOG_TAG="certbot-deploy-hook"
LOGFILE="/var/log/iamazim-certbot-deploy.log"

log() {
  local msg
  msg="$(date '+%Y-%m-%d %H:%M:%S') [${LOG_TAG}] $*"
  echo "$msg" | tee -a "$LOGFILE"
  logger -t "$LOG_TAG" "$*" 2>/dev/null || true
}

log "Deploy hook triggered for renewed domain(s): ${RENEWED_DOMAINS:-unknown}"

# ── 1. Reload Nginx ──
if systemctl is-active --quiet nginx 2>/dev/null; then
  systemctl reload nginx
  log "Reloaded host Nginx (systemd)."
elif command -v docker >/dev/null 2>&1; then
  # Best-effort: try to find a running Nginx container
  NGINX_ID=$(docker ps --filter "name=nginx" --format '{{.ID}}' 2>/dev/null | head -1)
  if [ -n "$NGINX_ID" ]; then
    docker exec "$NGINX_ID" nginx -s reload 2>/dev/null && \
      log "Reloaded Nginx inside container ${NGINX_ID}." || \
      log "WARN: Failed to reload Nginx container ${NGINX_ID}."
  else
    log "INFO: No host Nginx service or Docker Nginx container found — skipping Nginx reload."
  fi
else
  log "INFO: No Nginx detected — skipping."
fi

# ── 2. Restart Coturn (picks up re-mounted cert files) ──
if command -v docker >/dev/null 2>&1; then
  # Prefer docker compose if compose project exists
  COMPOSE_DIR="__REPO_PATH__"
  if [ -f "${COMPOSE_DIR}/docker-compose.yaml" ] || [ -f "${COMPOSE_DIR}/docker-compose.yml" ]; then
    docker compose -f "${COMPOSE_DIR}/docker-compose.yaml" restart coturn 2>/dev/null && \
      log "Restarted Coturn via docker compose." || \
      log "WARN: docker compose restart coturn failed — trying docker restart."
  fi

  # Fallback: bare docker restart
  if docker ps --filter "name=coturn" --format '{{.Names}}' 2>/dev/null | grep -q coturn; then
    docker restart coturn 2>/dev/null && \
      log "Restarted Coturn container." || \
      log "WARN: docker restart coturn failed."
  else
    log "INFO: No running Coturn container found — skipping."
  fi
else
  log "INFO: Docker not available — cannot restart Coturn."
fi

log "Deploy hook completed."
