# ============================================================
# FAZLE PERSONAL AI SYSTEM — Documentation
# Integrated with Dograh Voice AI Platform
# ============================================================

## Overview

Fazle is a personal AI brain system that integrates with the existing
Dograh Voice AI platform. It adds intelligence, memory, and autonomous
capabilities while keeping Dograh as the voice interface layer.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: Voice Infrastructure (Existing — Unchanged)       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐      │
│  │ Dograh   │ │ Dograh   │ │ LiveKit  │ │  Coturn   │      │
│  │ API:8000 │ │ UI:3010  │ │ WS:7880  │ │ TURN:3478 │      │
│  └────┬─────┘ └──────────┘ └──────────┘ └───────────┘      │
│       │                                                     │
│       │  POST /fazle/decision                               │
│       ▼                                                     │
│  Layer 2: Fazle Brain (Intelligence)                        │
│  ┌──────────────────────────────────────────────────┐       │
│  │ Fazle API Gateway (:8100)                        │       │
│  │   └── Fazle Brain (:8200)  ← reasoning engine   │       │
│  │         ├── OpenAI API (external)                │       │
│  │         └── Ollama (:11434) (local LLM)          │       │
│  └──────────────────────────────────────────────────┘       │
│                                                             │
│  Layer 3: Memory & Knowledge                                │
│  ┌──────────────────────────────────────────────────┐       │
│  │ Fazle Memory (:8300) ← vector search             │       │
│  │   └── Qdrant (:6333) ← vector database           │       │
│  └──────────────────────────────────────────────────┘       │
│                                                             │
│  Layer 4: Autonomous Tasks                                  │
│  ┌──────────────────────────────────────────────────┐       │
│  │ Task Engine (:8400)  ← scheduling & automation   │       │
│  │ Web Intelligence (:8500) ← search & scraping     │       │
│  └──────────────────────────────────────────────────┘       │
│                                                             │
│  Layer 5: Training & UI                                     │
│  ┌──────────────────────────────────────────────────┐       │
│  │ Trainer (:8600) ← preference extraction          │       │
│  │ Fazle UI (:3020) ← Next.js dashboard             │       │
│  └──────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

## Services

| Service              | Container             | Port  | Purpose                     |
|----------------------|-----------------------|-------|-----------------------------|
| Fazle API            | fazle-api             | 8100  | API gateway                 |
| Fazle Brain          | fazle-brain           | 8200  | Reasoning engine            |
| Fazle Memory         | fazle-memory          | 8300  | Vector memory system        |
| Fazle Task Engine    | fazle-task-engine     | 8400  | Scheduling & automation     |
| Fazle Web Intel      | fazle-web-intelligence| 8500  | Internet search & scraping  |
| Fazle Trainer        | fazle-trainer         | 8600  | Learning & extraction       |
| Fazle UI             | fazle-ui              | 3020  | Dashboard (Next.js)         |
| Qdrant               | qdrant                | 6333  | Vector database             |
| Ollama               | ollama                | 11434 | Local LLM server            |

## Access Points

### Domains

| Domain | Backend | Purpose |
|--------|---------|----------|
| `iamazim.com` | dograh-ui :3010 | Main domain — Dograh voice platform UI |
| `api.iamazim.com` | dograh-api :8000 | Dograh REST API — call routing, webhooks |
| `livekit.iamazim.com` | livekit :7880 | WebRTC server for real-time audio |
| `fazle.iamazim.com` | fazle-ui :3020 / fazle-api :8100 | Fazle AI dashboard and API |

### Fazle Endpoints

| Service    | URL                                          |
|------------|----------------------------------------------|
| Fazle UI   | https://fazle.iamazim.com                    |
| Fazle API  | https://fazle.iamazim.com/api/fazle/         |
| API Docs   | https://fazle.iamazim.com/docs               |
| Health     | https://fazle.iamazim.com/health             |

## API Endpoints

### Decision (Dograh Integration)
```
POST /fazle/decision
{
  "caller": "Rahim",
  "intent": "meeting_request",
  "conversation_context": "..."
}
→ { "response": "Offer meeting tomorrow at 11 AM", "confidence": 0.9 }
```

### Chat
```
POST /fazle/chat
{
  "message": "Fazle, remember I prefer meetings after 10 AM",
  "user": "Azim"
}
→ { "reply": "Got it, I'll remember that preference.", "conversation_id": "..." }
```

### Memory
```
POST /fazle/memory         — Store memory
POST /fazle/memory/search  — Search memories
```

### Knowledge
```
POST /fazle/knowledge/ingest  — Ingest documents
```

### Tasks
```
POST /fazle/tasks  — Create task
GET  /fazle/tasks  — List tasks
```

### Web Search
```
POST /fazle/web/search  — Internet search
```

### Training
```
POST /fazle/train  — Train from transcript
```

### System Status
```
GET /fazle/status  — Check all service health
```

## Deployment

### Prerequisites

Add DNS A records (all point to `5.189.131.48`):
- `iamazim.com` → `5.189.131.48`
- `api.iamazim.com` → `5.189.131.48`
- `livekit.iamazim.com` → `5.189.131.48`
- `fazle.iamazim.com` → `5.189.131.48`

### Step 1: Add Environment Variables

Append Fazle variables to your `.env`:
```bash
# See fazle-system/.env.example for all variables
OPENAI_API_KEY=sk-your-key
SERPER_API_KEY=your-serper-key
FAZLE_LLM_PROVIDER=openai
FAZLE_LLM_MODEL=gpt-4o
```

### Step 2: Install Nginx Config
```bash
cp configs/nginx/fazle.iamazim.com.conf /etc/nginx/sites-available/
ln -sf /etc/nginx/sites-available/fazle.iamazim.com.conf /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

### Step 3: Setup SSL for New Subdomain
```bash
certbot --nginx -d fazle.iamazim.com
```

### Step 4: Deploy
```bash
bash scripts/deploy.sh
```

## Memory Types

| Type         | Description                              | Example                          |
|-------------|------------------------------------------|----------------------------------|
| preference  | User preferences and habits              | "Prefers meetings after 10 AM"   |
| contact     | People and relationships                 | "Rahim is a business partner"    |
| knowledge   | Ingested documents and facts             | PDF content, web articles        |
| personal    | Personal facts and reminders             | "Birthday is March 15"           |
| conversation| Conversation history                     | Chat logs and call transcripts   |

## Plugin System

Plugins are located in `fazle-system/tools/plugins/`. Each plugin:
- Extends the `Plugin` base class
- Defines `name`, `description`, `input_schema`
- Implements `async execute(**kwargs)`

Built-in plugins:
- **calendar** — Calendar event management
- **email** — Email automation
- **crm** — Contact/CRM management

To add a new plugin, create a `.py` file in `tools/plugins/` that defines a class
inheriting from `Plugin`. It will be auto-discovered at startup.

## Authentication

### Default Login Accounts

Created by `scripts/seed-family.py` on first setup:

| Email | Default Password | Role |
|-------|-----------------|------|
| `azim@iamazim.com` | `ChangeMe123!` | admin |
| `wife@iamazim.com` | `ChangeMe123!` | member |
| `daughter@iamazim.com` | `ChangeMe123!` | member |

> **Change all default passwords immediately after first login.**

### Auth Flow

- **Dashboard login:** NextAuth.js (Credentials provider) → Fazle API `/fazle/auth/login` → JWT + bcrypt verification
- **API auth:** JWT Bearer token (7-day expiry) or `FAZLE_API_KEY` header for service-to-service calls
- **Session:** 7-day expiry, stored via NextAuth

Secrets are auto-generated by `scripts/gen-secrets.sh` — see main README for the full list.

## Security

- All Fazle services are internal to Docker network (no public ports)
- Only `fazle-ui` (3020) and `fazle-api` (8100) are bound to 127.0.0.1
- Nginx handles SSL termination and rate limiting
- JWT auth (PyJWT) + bcrypt password hashing
- Service-to-service auth via `FAZLE_API_KEY` with `hmac.compare_digest` (timing-safe)
- Row-Level Security on all PostgreSQL tables
- Rate limiting: 120 RPM / 10 req/s per IP
- No direct database or Qdrant access from outside

## Health Check & Debugging Toolkit

Scripts in `scripts/` provide automated diagnostics for the entire platform.

### Quick Commands

```bash
# Full platform health check (containers, endpoints, resources, ports, SSL)
bash scripts/health-check.sh

# Debug overview (container status, failing logs, ports, disk, CPU, memory, nginx)
bash scripts/debug.sh              # all sections
bash scripts/debug.sh containers   # just container status
bash scripts/debug.sh logs         # just failing service logs
bash scripts/debug.sh memory       # just memory usage
bash scripts/debug.sh nginx        # just nginx status

# Test all Fazle AI services (health endpoints, Ollama, Qdrant, integration tests)
bash scripts/test-fazle.sh

# Verify monitoring stack (Prometheus, Grafana, Loki, Promtail, exporters)
bash scripts/check-monitoring.sh

# Run ALL diagnostics with summary report
bash scripts/diagnose.sh
bash scripts/diagnose.sh --save 2>&1 | tee diagnose-report.txt
```

### Docker Healthchecks

All services have Docker healthchecks configured in `docker-compose.yaml`:

| Service              | Healthcheck Method                        |
|----------------------|-------------------------------------------|
| Fazle API/Brain/Memory/Tasks/Tools/Trainer | `python urllib.request` to `/health` |
| Fazle UI             | `wget --spider` to port 3020              |
| Qdrant               | `bash /dev/tcp/localhost/6333`            |
| Ollama               | `bash /dev/tcp/localhost/11434`           |
| Prometheus           | `wget --spider /-/healthy`                |
| Grafana              | `wget --spider /api/health`               |
| Loki                 | `/usr/bin/loki -version`                  |

### Monitoring URLs

| Service    | Internal URL               | External URL                     |
|------------|----------------------------|----------------------------------|
| Prometheus | http://127.0.0.1:9090      | (internal only)                  |
| Grafana    | http://127.0.0.1:3030      | https://iamazim.com/grafana/     |
| Loki       | http://127.0.0.1:3100      | (via Grafana datasource)         |

## Troubleshooting

### Fazle services not starting
```bash
# Quick: check all failing services at once
bash scripts/debug.sh logs

# Manual:
docker compose logs fazle-api --tail 50
docker compose logs fazle-brain --tail 50
docker compose logs fazle-memory --tail 50
```

### Container crash looping
```bash
# Check restart count
docker inspect --format='{{.RestartCount}}' <container-name>

# View recent logs
docker logs --tail 50 <container-name>

# Check resource limits (OOM?)
bash scripts/debug.sh memory
```

### Qdrant issues
```bash
docker logs qdrant --tail 50
curl http://127.0.0.1:6333/healthz
curl http://127.0.0.1:6333/collections
```

### Ollama model not available
```bash
# List available models
docker exec ollama ollama list

# Pull a model into Ollama
docker exec ollama ollama pull llama3.1

# Check Ollama tags API
docker exec ollama curl -s http://localhost:11434/api/tags
```

### Memory search not working
```bash
# Check Qdrant collection
curl http://127.0.0.1:6333/collections/fazle_memories
```

### Disk space running low
```bash
# Check usage
bash scripts/debug.sh disk

# Clean Docker
docker system prune -f
docker image prune -a -f  # removes unused images
```

### Nginx or SSL issues
```bash
bash scripts/debug.sh nginx
sudo nginx -t
sudo systemctl reload nginx
sudo certbot certificates  # check SSL cert status
```

## File Structure

```
fazle-system/
├── api/
│   ├── Dockerfile
│   ├── main.py              # API gateway
│   └── requirements.txt
├── brain/
│   ├── Dockerfile
│   ├── main.py              # Reasoning engine
│   └── requirements.txt
├── memory/
│   ├── Dockerfile
│   ├── main.py              # Vector memory system
│   └── requirements.txt
├── tasks/
│   ├── Dockerfile
│   ├── main.py              # Task scheduler
│   └── requirements.txt
├── tools/
│   ├── Dockerfile
│   ├── main.py              # Web intelligence
│   ├── requirements.txt
│   └── plugins/
│       ├── __init__.py       # Plugin loader
│       ├── calendar_plugin.py
│       ├── crm_plugin.py
│       └── email_plugin.py
├── trainer/
│   ├── Dockerfile
│   ├── main.py              # Voice trainer
│   └── requirements.txt
├── ui/
│   ├── Dockerfile
│   ├── next.config.js
│   ├── package.json
│   ├── postcss.config.js
│   ├── tailwind.config.js
│   └── src/
│       ├── globals.css
│       ├── app/
│       │   ├── layout.js
│       │   └── page.js
│       └── components/
│           ├── ChatPanel.js
│           ├── KnowledgePanel.js
│           ├── MemoryPanel.js
│           ├── Sidebar.js
│           └── TasksPanel.js
├── .env.example
└── README.md                 # This file
```
