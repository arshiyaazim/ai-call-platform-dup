#!/bin/bash
# Weekly Docker cleanup script
# Runs every Sunday at 3:00 AM via cron
# Only removes unused resources — does NOT affect running containers

set -euo pipefail

LOG_FILE="/home/azim/scripts/cleanup.log"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Docker cleanup..." >> "$LOG_FILE"

echo '--- Pruning stopped containers ---' >> "$LOG_FILE"
docker container prune -f >> "$LOG_FILE" 2>&1

echo '--- Pruning unused images ---' >> "$LOG_FILE"
docker image prune -a -f >> "$LOG_FILE" 2>&1

echo '--- Pruning unused volumes ---' >> "$LOG_FILE"
docker volume prune -f >> "$LOG_FILE" 2>&1

echo '--- Pruning build cache ---' >> "$LOG_FILE"
docker builder prune -a -f >> "$LOG_FILE" 2>&1

echo '--- Pruning unused networks ---' >> "$LOG_FILE"
docker network prune -f >> "$LOG_FILE" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Cleanup complete." >> "$LOG_FILE"
echo '---' >> "$LOG_FILE"
