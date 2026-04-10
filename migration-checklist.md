# Migration Checklist — Three-Stack Architecture

**Date**: 2026-03-14
**From**: Single `docker-compose.yaml` (26 services)
**To**: Three separate stacks (`ai-infra`, `dograh`, `fazle-ai`)

---

## Pre-Migration

- [ ] **Read this entire checklist** before starting
- [ ] **Backup all Docker volumes** on the VPS:
  ```bash
  # On VPS — identify current volume names
  docker volume ls | grep -E "postgres_data|redis_data|minio|qdrant|ollama|prometheus|grafana|loki|shared"

  # Backup PostgreSQL
  docker exec ai-postgres pg_dumpall -U postgres > /home/azim/backup_$(date +%Y%m%d).sql

  # Backup Redis
  docker exec ai-redis redis-cli -a "$REDIS_PASSWORD" BGSAVE
  ```
- [ ] **Verify .env file exists** with all required variables
- [ ] **Test current system health** — confirm everything works BEFORE migration:
  ```bash
  curl -s https://iamazim.com/api/v1/health
  curl -s https://fazle.iamazim.com/health
  ```
- [ ] **Schedule maintenance window** — expect 2-5 minutes downtime
- [ ] **Notify users** of planned maintenance

---

## Network Requirements

The split stacks share external Docker networks. These must be created BEFORE starting any stack.

```bash
# Create shared networks (the migration script does this automatically)
docker network create --driver bridge app-network
docker network create --driver bridge --internal db-network
docker network create --driver bridge --internal ai-network
docker network create --driver bridge --internal monitoring-network
```

| Network | Type | Purpose |
|---------|------|---------|
| `app-network` | bridge (public) | Inter-service communication, Nginx proxies |
| `db-network` | bridge (internal) | Database access (Postgres, Redis, MinIO, Qdrant) |
| `ai-network` | bridge (internal) | AI services (Ollama, Brain, Memory, etc.) |
| `monitoring-network` | bridge (internal) | Prometheus, Grafana, Loki, Promtail |

---

## Volume Migration

### REVIEW_REQUIRED

Existing volumes may have project-name prefixes (e.g., `vps-deploy_postgres_data`). The new compose files use explicit names without prefixes (e.g., `postgres_data`).

**Check existing volume names:**
```bash
docker volume ls --format '{{.Name}}' | sort
```

**If volumes have prefixes, the migration script handles this automatically.** It will:
1. Detect the old project name
2. Create new volumes with clean names
3. Copy data from old to new

**Old volumes are NOT deleted** — they remain as backups.

| Old Name (example) | New Name |
|---------------------|----------|
| `vps-deploy_postgres_data` | `postgres_data` |
| `vps-deploy_redis_data` | `redis_data` |
| `vps-deploy_minio-data` | `minio-data` |
| `vps-deploy_qdrant_data` | `qdrant_data` |
| `vps-deploy_ollama_data` | `ollama_data` |
| `vps-deploy_prometheus_data` | `prometheus_data` |
| `vps-deploy_grafana_data` | `grafana_data` |
| `vps-deploy_loki_data` | `loki_data` |
| `vps-deploy_shared-tmp` | `shared-tmp` |

---

## Deployment Order

**Critical**: Stacks must be started in this exact order.

### Step 1 — Infrastructure

```bash
cd /home/azim/ai-infra
docker compose --env-file ../.env up -d
```

**Wait for health checks:**
```bash
docker inspect --format='{{.State.Health.Status}}' ai-postgres   # → healthy
docker inspect --format='{{.State.Health.Status}}' ai-redis       # → healthy
docker inspect --format='{{.State.Health.Status}}' qdrant          # → healthy
docker inspect --format='{{.State.Health.Status}}' minio           # → healthy
```

### Step 2 — Dograh

```bash
cd /home/azim/ai-call-platform/dograh
docker compose --env-file ../.env up -d
```

**Wait for health checks:**
```bash
docker inspect --format='{{.State.Health.Status}}' livekit     # → healthy
docker inspect --format='{{.State.Health.Status}}' dograh-api  # → healthy
docker inspect --format='{{.State.Health.Status}}' dograh-ui   # → healthy
```

### Step 3 — Fazle AI

```bash
cd /home/azim/ai-call-platform/fazle-ai
docker compose --env-file ../.env up -d
```

**Wait for health checks:**
```bash
docker inspect --format='{{.State.Health.Status}}' fazle-brain    # → healthy
docker inspect --format='{{.State.Health.Status}}' fazle-memory   # → healthy
docker inspect --format='{{.State.Health.Status}}' fazle-api      # → healthy
docker inspect --format='{{.State.Health.Status}}' fazle-ui       # → healthy
```

---

## Post-Migration Verification

### Health Endpoints

```bash
# Dograh
curl -s http://127.0.0.1:8000/api/v1/health
curl -s http://127.0.0.1:3010

# Fazle
curl -s http://127.0.0.1:8100/health
curl -s http://127.0.0.1:3020

# Grafana
curl -s http://127.0.0.1:3030/api/health

# External (via Nginx)
curl -s https://iamazim.com/api/v1/health
curl -s https://fazle.iamazim.com/health
```

### Cross-Stack Communication

```bash
# Fazle Brain → Redis (cross-stack via db-network)
docker exec fazle-brain python -c "import socket; socket.getaddrinfo('redis', 6379); print('OK')"

# Fazle Brain → Ollama (cross-stack via ai-network)
docker exec fazle-brain python -c "import socket; socket.getaddrinfo('ollama', 11434); print('OK')"

# Fazle Memory → Qdrant (cross-stack via db-network)
docker exec fazle-memory python -c "import socket; socket.getaddrinfo('qdrant', 6333); print('OK')"

# Fazle Task Engine → Dograh API (cross-stack via app-network)
docker exec fazle-task-engine python -c "import socket; socket.getaddrinfo('api', 8000); print('OK')"

# Fazle Voice → LiveKit (cross-stack via app-network)
docker exec fazle-voice python -c "import socket; socket.getaddrinfo('livekit', 7880); print('OK')"

# Dograh API → PostgreSQL (cross-stack via db-network)
docker exec dograh-api python -c "import socket; socket.getaddrinfo('postgres', 5432); print('OK')"
```

### Functional Tests

```bash
# Test Dograh → Fazle integration (POST /fazle/decision)
# This is the critical cross-system call
docker exec dograh-api python -c "
import urllib.request
req = urllib.request.Request('http://fazle-api:8100/health')
resp = urllib.request.urlopen(req)
print('Dograh → Fazle: OK' if resp.status == 200 else 'FAIL')
"

# Test login flow
curl -s -X POST https://fazle.iamazim.com/api/fazle/auth/setup-status

# Test Grafana
curl -s http://127.0.0.1:3030/api/health
```

---

## What Changed (and What Didn't)

### UNCHANGED:
- Container names
- Port bindings
- Environment variables
- Volume names/data
- Service hostnames
- API endpoints
- Nginx configuration
- SSL certificates
- Database content
- Redis data
- Qdrant vectors
- Docker images

### CHANGED:
- Compose file locations (split into 3 subdirectories)
- Networks are now `external: true` (pre-created)
- Some `depends_on` removed (cross-compose deps replaced by retry logic)
- Build context paths use `../` prefix
- Config mount paths use `../` prefix
- Volumes have explicit `name:` to avoid project-name prefixes

### REMOVED `depends_on` (Cross-Compose):
| Service | Removed Dependency | Reason |
|---------|-------------------|--------|
| livekit | redis | Redis is in ai-infra (cross-compose) |
| dograh-api | postgres, redis, minio | Infrastructure in ai-infra (cross-compose) |
| fazle-api | postgres | Infrastructure in ai-infra (cross-compose) |
| fazle-brain | qdrant, ollama | Infrastructure in ai-infra (cross-compose) |
| fazle-memory | qdrant | Infrastructure in ai-infra (cross-compose) |
| fazle-task-engine | postgres | Infrastructure in ai-infra (cross-compose) |
| fazle-voice | livekit | LiveKit is in dograh (cross-compose) |

### KEPT `depends_on` (Same-Compose):
| Service | Dependency | Stack |
|---------|-----------|-------|
| promtail | loki (service_healthy) | ai-infra |
| dograh-api | livekit (service_healthy) | dograh |
| dograh-ui | dograh-api (service_healthy) | dograh |
| fazle-api | fazle-brain, fazle-memory (service_healthy) | fazle-ai |
| fazle-voice | fazle-brain (service_healthy) | fazle-ai |
| fazle-ui | fazle-api (start order) | fazle-ai |

---

## Rollback Procedure

If anything goes wrong, rollback to the original single compose:

```bash
# 1. Stop all new stacks
cd /home/azim/ai-call-platform/ai-infra  && docker compose down
cd /home/azim/ai-call-platform/dograh    && docker compose down
cd /home/azim/ai-call-platform/fazle-ai  && docker compose down

# 2. Remove external networks (they'll be recreated by the old compose)
docker network rm app-network db-network ai-network monitoring-network 2>/dev/null || true

# 3. If volumes were migrated, rename back (REVIEW_REQUIRED)
# Only needed if the old compose used prefixed volume names

# 4. Start old compose
cd /home/azim
docker compose -f docker-compose.yaml up -d

# 5. Verify
curl -s https://iamazim.com/api/v1/health
curl -s https://fazle.iamazim.com/health
```

---

## Management Commands (Post-Migration)

### Start/Stop Individual Stacks

```bash
# Infrastructure
cd /home/azim/ai-infra && docker compose up -d
cd /home/azim/ai-infra && docker compose down

# Dograh
cd /home/azim/ai-call-platform/dograh && docker compose --env-file ../.env up -d
cd /home/azim/ai-call-platform/dograh && docker compose down

# Fazle AI
cd /home/azim/ai-call-platform/fazle-ai && docker compose --env-file ../.env up -d
cd /home/azim/ai-call-platform/fazle-ai && docker compose down
```

### View Logs

```bash
# By stack
cd /home/azim/ai-infra && docker compose logs -f postgres redis
cd /home/azim/ai-call-platform/dograh && docker compose logs -f api
cd /home/azim/ai-call-platform/fazle-ai && docker compose logs -f fazle-brain

# By container name (works from anywhere)
docker logs -f fazle-brain
docker logs -f dograh-api
```

### Rebuild Fazle Services

```bash
cd /home/azim/fazle-ai
docker compose --env-file ../.env build fazle-brain
docker compose --env-file ../.env up -d fazle-brain
```
