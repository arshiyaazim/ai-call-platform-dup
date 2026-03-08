# DEPLOYMENT MANIFEST

**Branch:** `hotfix/audit-remediation-local`  
**Date:** 2024-12-XX  
**Author:** azim@iamazim.com  

---

## Pre-Deploy Checklist

- [ ] Run `bash scripts/health-check-local.sh` — all checks pass
- [ ] Verify `.env` on VPS has all required variables (see below)
- [ ] Ensure PostgreSQL `fazle_tasks` table migration is planned
- [ ] Confirm backup exists before deploying: `bash scripts/backup.sh`
- [ ] Review changed files below

---

## Files Changed by Phase

### Phase 0 — Local Environment Setup
| File | Action | Description |
|------|--------|-------------|
| `.gitignore` | CREATED | Excludes .env, passwords, node_modules, __pycache__ |
| `.pre-commit-config.yaml` | CREATED | Pre-commit hooks for YAML lint, secret detection |
| `local-validation/checklist.md` | CREATED | Manual validation checklist |
| `local-validation/backup-docker-compose.yaml` | CREATED | Pre-change backup of docker-compose |

### Phase 1 — Critical Security Lockdown
| File | Action | Description |
|------|--------|-------------|
| `.env.example` | MODIFIED | Added GRAFANA_ADMIN_PASSWORD, FAZLE_API_KEY, LLM config vars |
| `fazle-system/api/main.py` | MODIFIED | Fixed auth bypass — empty API key no longer skips verification |
| `docker-compose.yaml` | MODIFIED | Removed cadvisor `privileged: true`; restricted MinIO CORS; added `read_only: true` to 6 Fazle services |

### Phase 2 — Data Persistence Layer
| File | Action | Description |
|------|--------|-------------|
| `fazle-system/tasks/main.py` | MODIFIED | In-memory dict → PostgreSQL `fazle_tasks` table |
| `fazle-system/tasks/requirements.txt` | MODIFIED | Added SQLAlchemy, psycopg2-binary |
| `fazle-system/brain/main.py` | MODIFIED | In-memory conversations → Redis-backed via memory_manager |
| `fazle-system/brain/requirements.txt` | MODIFIED | Added redis |
| `fazle-system/brain/memory_manager.py` | CREATED | Redis conversation manager with TTL |
| `fazle-system/tasks/migrations/001_scheduler_tables.sql` | CREATED | Idempotent CREATE TABLE for fazle_tasks |
| `scripts/db-migrate.sh` | CREATED | Migration runner + Qdrant collection validator |
| `docker-compose.yaml` | MODIFIED | Added DATABASE_URL, REDIS_URL env vars to services |

### Phase 3 — Infrastructure Hardening
| File | Action | Description |
|------|--------|-------------|
| `docker-compose.yaml` | MODIFIED | Pinned 13 Docker images to specific versions |
| `configs/coturn/turnserver.conf` | MODIFIED | Fixed TLS cert paths → `/etc/coturn/certs/` |
| `fazle-system/tasks/main.py` | MODIFIED | CORS `*` → env-configurable ALLOWED_ORIGINS |
| `fazle-system/brain/main.py` | MODIFIED | CORS `*` → env-configurable ALLOWED_ORIGINS |
| `fazle-system/memory/main.py` | MODIFIED | CORS `*` → env-configurable ALLOWED_ORIGINS |
| `fazle-system/tools/main.py` | MODIFIED | CORS `*` → env-configurable ALLOWED_ORIGINS |
| `fazle-system/trainer/main.py` | MODIFIED | CORS `*` → env-configurable ALLOWED_ORIGINS |
| `scripts/setup-ollama.sh` | CREATED | Pulls llama3.1 + nomic-embed-text models |

### Phase 4 — Operational Scripts & Cleanup
| File | Action | Description |
|------|--------|-------------|
| `scripts/backup.sh` | MODIFIED | Pre-backup health check; Qdrant via docker exec; MinIO metadata backup |
| `scripts/health-check-local.sh` | CREATED | Local pre-deploy validation (no SSH needed) |
| `nginx-iamazim.conf` | DELETED | Stale root-level config (authoritative copy: `configs/nginx/iamazim.com.conf`) |
| `DEPLOYMENT_MANIFEST.md` | CREATED | This file |

---

## New Environment Variables

These must be set in `.env` on the VPS before deploying:

| Variable | Service(s) | Required | Default | Description |
|----------|-----------|----------|---------|-------------|
| `FAZLE_API_KEY` | fazle-api | **YES** | — | 64-char API key (must not be empty) |
| `DATABASE_URL` | fazle-task-engine | **YES** | — | PostgreSQL connection string |
| `REDIS_URL` | fazle-brain | NO | `redis://ai-redis:6379/0` | Redis connection for conversations |
| `ALLOWED_ORIGINS` | fazle-* (5 services) | NO | `https://fazle.iamazim.com,https://iamazim.com,http://localhost:3020` | Comma-separated CORS origins |
| `GRAFANA_ADMIN_PASSWORD` | grafana | **YES** | — | Grafana admin password |
| `OPENAI_API_KEY` | fazle-brain | NO | — | OpenAI fallback key |
| `FAZLE_LLM_PROVIDER` | fazle-brain | NO | `ollama` | LLM provider |
| `FAZLE_LLM_MODEL` | fazle-brain | NO | `llama3.1` | LLM model name |

---

## Database Migrations

### PostgreSQL — fazle_tasks table
```bash
# Run from VPS
bash scripts/db-migrate.sh
```
This creates `fazle_tasks` table and indexes. Idempotent — safe to re-run.

Migration file: `fazle-system/tasks/migrations/001_scheduler_tables.sql`

### Qdrant — Collections
Validated by `db-migrate.sh`. No schema changes needed.

---

## Docker Images Pinned

| Service | Image | Pinned Version |
|---------|-------|---------------|
| ai-redis | redis | 7.2.5-alpine |
| minio | minio/minio | RELEASE.2024-11-11T11-18-37Z |
| livekit | livekit/livekit-server | v1.8.2 |
| coturn | coturn/coturn | 4.6.2-r12-alpine |
| qdrant | qdrant/qdrant | v1.12.1 |
| ollama | ollama/ollama | 0.3.14 |
| prometheus | prom/prometheus | v2.55.0 |
| grafana | grafana/grafana | 11.2.2 |
| node-exporter | prom/node-exporter | v1.8.2 |
| cadvisor | gcr.io/cadvisor/cadvisor | v0.49.1 |
| loki | grafana/loki | 3.2.1 |
| promtail | grafana/promtail | 3.2.1 |
| cloudflared | cloudflare/cloudflared | 2024.10.1 |

**NOT pinned (intentional):** Dograh API, Dograh UI — controlled by CI/CD pipeline.

---

## Deploy Procedure

```bash
# 1. SSH to VPS
ssh azim@5.189.131.48

# 2. Backup current state
cd /home/azim/ai-call-platform
bash scripts/backup.sh

# 3. Pull changes
git pull origin hotfix/audit-remediation-local

# 4. Update .env with new variables
nano .env  # Add FAZLE_API_KEY, DATABASE_URL, GRAFANA_ADMIN_PASSWORD

# 5. Run database migrations
bash scripts/db-migrate.sh

# 6. Setup Ollama models (if not already done)
bash scripts/setup-ollama.sh

# 7. Rebuild and restart services (zero-downtime rolling)
docker compose pull
docker compose up -d --build --remove-orphans

# 8. Verify
bash scripts/health-check.sh
```

---

## Rollback Procedure

```bash
# 1. SSH to VPS
ssh azim@5.189.131.48
cd /home/azim/ai-call-platform

# 2. Restore previous compose file
cp backups/docker-compose-YYYYMMDD_HHMMSS.yaml docker-compose.yaml

# 3. Restore .env if changed
cp backups/env-YYYYMMDD_HHMMSS.bak .env

# 4. Restart with old config
docker compose up -d --remove-orphans

# 5. If DB migration needs rollback (fazle_tasks table):
docker exec ai-postgres psql -U postgres -d postgres -c "DROP TABLE IF EXISTS fazle_tasks;"
# Note: APScheduler job store table (apscheduler_jobs) will be recreated automatically

# 6. Verify rollback
bash scripts/health-check.sh
```

---

## Risk Assessment

| Change | Risk | Mitigation |
|--------|------|------------|
| Auth bypass fix | Low | Only affects empty API keys |
| Privileged mode removal (cadvisor) | Low | CAP_ADD provides equivalent access |
| In-memory → PostgreSQL (tasks) | Medium | Migration is idempotent; existing tasks lost (acceptable — they were ephemeral) |
| In-memory → Redis (conversations) | Low | Conversations had no persistence before |
| Image version pinning | Low | All versions match currently running |
| CORS restriction | Low | Only allowed origins change; defaults include all used domains |
| Coturn TLS path fix | Medium | Verify cert files are mounted correctly |
| Backup script changes | Low | Improvements only; no breaking changes |
