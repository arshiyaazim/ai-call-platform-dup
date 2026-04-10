# Dograh + Fazle AI — Autonomous Voice Agent Platform

> AI-powered voice agent platform with an autonomous intelligence layer. Handles real-time phone calls via Twilio SIP and LiveKit WebRTC, backed by a multi-agent AI brain that plans, reasons, learns, and self-improves across every interaction.

**Domain:** `iamazim.com` &nbsp;|&nbsp; **VPS:** Contabo (4 CPUs, 8 GB RAM, Ubuntu)  
**Version:** Phase 5 — Autonomous AI System &nbsp;|&nbsp; **Containers:** 20+

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Services](#services)
  - [Stack 1 — ai-infra (Foundation)](#stack-1--ai-infra-foundation)
  - [Stack 2 — dograh (Voice Platform)](#stack-2--dograh-voice-platform)
  - [Stack 3 — fazle-ai (Intelligence Layer)](#stack-3--fazle-ai-intelligence-layer)
  - [Stack 4 — Phase-5 Autonomous Services](#stack-4--phase-5-autonomous-services)
  - [Auxiliary — AI Watchdog & Control Plane](#auxiliary--ai-watchdog--control-plane)
- [Fazle Personal AI System](#fazle-personal-ai-system)
  - [Multi-Agent Brain](#multi-agent-brain)
  - [Autonomous AI (Phase 5)](#autonomous-ai-phase-5)
  - [How a Call Flows](#how-a-call-flows)
- [Dashboard](#dashboard)
- [Networking & Domains](#networking--domains)
- [Monitoring Stack](#monitoring-stack)
- [Database](#database)
- [Security](#security)
- [Deployment](#deployment)
  - [Prerequisites](#prerequisites)
  - [Quick Start](#quick-start)
  - [Zero-Downtime Rolling Deploy](#zero-downtime-rolling-deploy)
  - [Rollback](#rollback)
- [Scripts Reference](#scripts-reference)
- [Secrets Management](#secrets-management)
- [Testing](#testing)
- [Configuration Files](#configuration-files)
- [Roadmap](#roadmap)
- [License](#license)

---

## Overview

The platform combines two systems:

| System | Purpose |
|--------|---------|
| **Dograh** | Open-source voice AI SaaS — handles inbound/outbound phone calls with real-time STT/TTS, LiveKit WebRTC streaming, and Twilio SIP integration. |
| **Fazle** | Custom autonomous AI layer — multi-agent reasoning, goal decomposition, tool execution, knowledge graph, semantic memory, self-learning, relationship-aware personality, and voice cloning. |

Together they deliver an AI voice clone that answers phone calls, remembers conversations, autonomously plans and executes multi-step tasks, builds a knowledge graph from interactions, learns from its own behavior, and maintains relationship-specific behavior (family, friends, professional contacts) with content safety boundaries.

**Key capabilities:**
- Real-time voice call handling (Twilio → LiveKit → STT → LLM → TTS)
- Multi-agent brain with 5 specialized agents (conversation, memory, research, task, tool)
- Autonomous goal planning with self-reflection and retry logic
- Tool execution engine with permission control and sandboxing
- Knowledge graph tracking people, projects, conversations, and relationships
- Background autonomous task runner (research, monitoring, digests, reminders)
- Self-learning engine that detects patterns and optimizes agent routing
- Personality injection with relationship-aware context
- Semantic memory search over all past conversations (Qdrant vectors)
- LLM gateway with caching, rate limiting, request batching, and OpenAI ↔ Ollama fallback
- Async task queue with auto-scaling workers
- Full observability: Prometheus + Grafana + Loki + Promtail
- Self-healing infrastructure via AI Watchdog and AI Control Plane
- Zero-downtime blue/green deployments
- Row-Level Security on all database tables

---

## Architecture

```
                          ┌──────────────────────┐
                          │      Nginx (SSL)     │
                          │  iamazim.com :443     │
                          └──┬─────┬─────┬────┬──┘
                             │     │     │    │
              ┌──────────────┘     │     │    └──────────────┐
              ▼                    ▼     ▼                   ▼
       ┌─────────────┐   ┌────────────┐ ┌──────────┐  ┌───────────┐
       │ Dograh UI   │   │ Dograh API │ │ LiveKit  │  │ Fazle UI  │
       │ :3010       │   │ :8000      │ │ :7880    │  │ :3020     │
       └─────────────┘   └─────┬──────┘ └────┬─────┘  └─────┬─────┘
                               │              │              │
                        ┌──────▼──────────────▼──────────────▼──────┐
                        │              Fazle AI Services             │
                        │                                            │
                        │  ┌─────────┐  ┌────────┐  ┌────────────┐ │
                        │  │  Brain  │  │ Memory │  │ LLM Gateway│ │
                        │  │  :8200  │  │ :8300  │  │   :8800    │ │
                        │  │(5 agents)  └────┬───┘  └─────┬──────┘ │
                        │  └────┬────┘       │            │         │
                        │       │       ┌────▼───┐  ┌────▼──────┐ │
                        │  ┌────▼────┐  │Trainer │  │  Queue    │ │
                        │  │ Tasks   │  │ :8600  │  │  :8810    │ │
                        │  │ :8400   │  └────────┘  └────┬──────┘ │
                        │  └─────────┘                   │         │
                        │                          ┌─────▼───────┐ │
                        │  ┌──────────┐ ┌────────┐ │  Workers    │ │
                        │  │  Voice   │ │Learning│ │  :8820 × 4  │ │
                        │  │  :8700   │ │ :8900  │ └─────────────┘ │
                        │  └──────────┘ └────────┘                 │
                        │  ┌──────────────────┐                    │
                        │  │ Web Intelligence │                    │
                        │  │     :8500        │                    │
                        │  └──────────────────┘                    │
                        └───────────────┬──────────────────────────┘
                                        │
                        ┌───────────────▼──────────────────────────┐
                        │       Phase 5 — Autonomous Services       │
                        │                                           │
                        │  ┌────────────────┐  ┌────────────────┐  │
                        │  │ Autonomy Engine│  │  Tool Engine   │  │
                        │  │    :9100       │  │    :9200       │  │
                        │  │ Goal planning  │  │ Tool registry  │  │
                        │  │ & execution    │  │ & sandboxed    │  │
                        │  └────────────────┘  │   execution    │  │
                        │                      └────────────────┘  │
                        │  ┌────────────────┐  ┌────────────────┐  │
                        │  │Knowledge Graph │  │ Auto Runner    │  │
                        │  │    :9300       │  │    :9400       │  │
                        │  │ Entity &       │  │ Background     │  │
                        │  │ relationship   │  │ tasks &        │  │
                        │  │ tracking       │  │ scheduling     │  │
                        │  └────────────────┘  └────────────────┘  │
                        │  ┌────────────────┐                      │
                        │  │ Self Learning  │                      │
                        │  │    :9500       │                      │
                        │  │ Pattern        │                      │
                        │  │ analysis &     │                      │
                        │  │ optimization   │                      │
                        │  └────────────────┘                      │
                        └───────────────┬──────────────────────────┘
                                        │
              ┌─────────────────────────┼───────────────────────────┐
              │        Foundation (ai-infra)                        │
              │                                                     │
              │  PostgreSQL+pgvector  Redis  Qdrant  MinIO  Ollama │
              │  :5432               :6379  :6333   :9000  :11434  │
              │                                                     │
              │  LiveKit  Coturn  Prometheus  Grafana  Loki        │
              │  :7880    :3478   :9090       :3030    :3100       │
              └─────────────────────────────────────────────────────┘
```

---

## Services

The system deploys as **four Docker Compose stacks** started in order.

### Stack 1 — ai-infra (Foundation)

All shared infrastructure. Must start first.

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| postgres | `pgvector/pgvector:pg17` | 5432 | PostgreSQL 17 + pgvector embeddings |
| redis | `redis:7.2.5-alpine` | 6379 | Cache, pub/sub, streams, session store |
| minio | `minio/minio:2025-09-07` | 9000 / 9001 | S3-compatible object storage (recordings, files) |
| livekit | `livekit/livekit-server:v1.8.2` | 7880 / 7881 | WebRTC server for real-time audio |
| qdrant | `qdrant/qdrant:v1.17.0` | 6333 | Vector database for semantic memory |
| ollama | `ollama/ollama:0.3.14` | 11434 | Local LLM (fallback when OpenAI is unavailable) |
| coturn | `coturn/coturn:4.6.2` | 3478 / 5349 | TURN/STUN NAT traversal for WebRTC |
| prometheus | `prom/prometheus:latest` | 9090 | Metrics collection |
| grafana | `grafana/grafana:latest` | 3030 | Monitoring dashboards |
| loki | `grafana/loki:latest` | 3100 | Log aggregation |
| promtail | `grafana/promtail:latest` | 9080 | Log shipping → Loki |
| node-exporter | `prom/node-exporter:latest` | 9100 | Host-level metrics |
| cadvisor | `gcr.io/cadvisor/cadvisor:latest` | 8080 | Container metrics |

### Stack 2 — dograh (Voice Platform)

Pre-built Dograh containers for voice call handling.

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| api | `dograhai/dograh-api:1.0.0` | 8000 | FastAPI backend — call routing, STT/TTS, webhooks |
| ui | `dograhai/dograh-ui:1.0.0` | 3010 | Next.js dashboard — call management |

### Stack 3 — fazle-ai (Intelligence Layer)

Custom-built Fazle services. Each builds from `fazle-system/`.

| Service | Port | Purpose |
|---------|------|---------|
| fazle-api | 8100 | API Gateway — routing, JWT auth, rate limiting, Phase-5 proxy |
| fazle-brain | 8200 | Multi-agent reasoning engine — 5 agents, personality injection |
| fazle-memory | 8300 | Vector memory — Qdrant semantic search, context retrieval |
| fazle-task-engine | 8400 | Scheduler — reminders, recurring tasks (APScheduler) |
| fazle-web-intelligence | 8500 | Web search & scraping (Serper API, BeautifulSoup) |
| fazle-trainer | 8600 | ML training — preference extraction, fine-tuning |
| fazle-voice | 8700 | Voice processing — accent modulation, cloning |
| fazle-ui | 3020 | Next.js dashboard — settings, conversations, Phase-5 management |
| fazle-llm-gateway | 8800 | Centralized LLM routing with cache & rate limits |
| fazle-queue | 8810 | Async request queue (Redis Streams) |
| fazle-learning-engine | 8900 | Self-improvement — conversation analysis, knowledge extraction |
| fazle-workers | 8820 | Worker pool (4 replicas) consuming from queue |

### Stack 4 — Phase-5 Autonomous Services

Five new microservices enabling autonomous operation. Deployed via `phase5-standalone.yaml`.

| Service | Port | Purpose |
|---------|------|---------|
| fazle-autonomy-engine | 9100 | Goal decomposition — breaks goals into multi-step plans with self-reflection and retry |
| fazle-tool-engine | 9200 | Tool orchestration — registry, permission control, sandboxed execution (6 built-in tools) |
| fazle-knowledge-graph | 9300 | Entity & relationship store — people, projects, conversations, topics with link tracking |
| fazle-autonomous-runner | 9400 | Background task runner — research, monitoring, digests, reminders on interval/cron triggers |
| fazle-self-learning | 9500 | Pattern analysis — detects behavioral patterns, optimizes agent routing, generates insights |

All Phase-5 services expose `/health` and `/metrics` (Prometheus) endpoints. The API gateway proxies all Phase-5 routes through `/fazle/autonomy/*`, `/fazle/tool-engine/*`, `/fazle/knowledge-graph/*`, and `/fazle/self-learning/*`.

### Auxiliary — AI Watchdog & Control Plane

| Component | Purpose |
|-----------|---------|
| **AI Watchdog** | Self-healing monitor — checks containers every 30 s, auto-restarts unhealthy services, manages disk space, auto-scales workers based on queue depth. |
| **AI Control Plane** | LLM-powered DevOps agent — snapshots system state every 60 s, uses AI reasoning to diagnose issues and execute repairs (restart, scale, cleanup). Produces daily JSON reports. |

---

## Fazle Personal AI System

Fazle is a layered intelligence system composed of 17 microservices across 5 layers:

```
Layer 1  API Gateway (fazle-api :8100)
           ├── JWT auth, rate limiting, request routing
           ├── Phase-5 proxy routes (autonomy, tools, KG, learning)
           │
Layer 2  Brain + Agents (fazle-brain :8200)
           ├── Multi-agent orchestration (5 agents)
           ├── Query routing: FAST_VOICE / CONVERSATION / FULL_PIPELINE
           ├── Personality injection from persona definitions
           │
           │   ┌─────────────────────────────────────────────────────┐
           │   │  Agent Manager                                      │
           │   │  ├── ConversationAgent — direct LLM responses       │
           │   │  ├── MemoryAgent — semantic recall & fact storage    │
           │   │  ├── ResearchAgent — web search & content scraping   │
           │   │  ├── TaskAgent — scheduling & reminders              │
           │   │  └── ToolAgent — plugin-based tool execution         │
           │   └─────────────────────────────────────────────────────┘
           │
         Memory (fazle-memory :8300)
           ├── Qdrant vector search
           ├── Embedding generation
           └── Context retrieval
           │
Layer 3  Tasks (fazle-task-engine :8400)     Tools (fazle-web-intelligence :8500)
           ├── Scheduling (APScheduler)         ├── Web search (Serper)
           └── Reminders & automation           └── Scraping + summarization
           │
         Trainer (fazle-trainer :8600)
           ├── Preference extraction
           └── Fine-tuning
           │
Layer 4  LLM Gateway (fazle-llm-gateway :8800)
           ├── Response caching (300 s TTL)
           ├── Rate limiting (10 req/s)
           ├── Request batching (75 ms / 4)
           └── Model fallback (OpenAI → Ollama)
           │
         Learning Engine (fazle-learning-engine :8900)
           ├── Conversation analysis
           ├── Relationship graph updates
           ├── Correction processing
           └── Nightly batch learning
           │
         Queue (fazle-queue :8810) + Workers (fazle-workers × 4 :8820)
           ├── Redis Streams consumer group
           ├── Async request handling
           └── Auto-scaling (2–4 workers)
           │
Layer 5  Voice (fazle-voice :8700)           UI (fazle-ui :3020)
           ├── Accent/tone personalization      ├── Next.js 14 dashboard
           └── Voice cloning                    └── Phase-5 management pages
           │
Layer 6  Autonomous AI (Phase 5)
           ├── Autonomy Engine (:9100) — goal planning & execution
           ├── Tool Engine (:9200) — secure tool orchestration
           ├── Knowledge Graph (:9300) — entity relationship store
           ├── Autonomous Runner (:9400) — background task execution
           └── Self Learning (:9500) — pattern analysis & optimization
```

### Multi-Agent Brain

The Brain service runs an **Agent Manager** that orchestrates 5 specialized agents through a pipeline:

| Agent | Role | Trigger Keywords |
|-------|------|-----------------|
| **ConversationAgent** | Direct LLM responses (Ollama fast path or gateway) | Default fallback for all queries |
| **MemoryAgent** | Semantic memory recall, fact storage | "remember", "what did I", "who is", "my preference" |
| **ResearchAgent** | Web search, content scraping, summarization | "search", "find", "look up", "latest", "news" |
| **TaskAgent** | Task creation, scheduling, reminders | "remind", "schedule", "set up", "tomorrow" |
| **ToolAgent** | Plugin tool discovery and execution | "send email", "run code", "check calendar" |

**Query routing** classifies incoming messages into three paths:
- **FAST_VOICE** — Simple greetings via voice, routed directly to Ollama for ultra-low latency
- **CONVERSATION** — Normal conversation with basic memory context
- **FULL_PIPELINE** — Complex queries running all agents (memory + research + task + tool + LLM)

### Autonomous AI (Phase 5)

Five microservices that give Fazle the ability to act independently:

**Autonomy Engine** (:9100) — Receives high-level goals and decomposes them into multi-step plans. Each plan step can invoke tools, query memory, or call the LLM. Supports self-reflection after execution, automatic retry (up to 3 attempts), and plan status tracking (pending → planning → executing → reflecting → completed).

**Tool Engine** (:9200) — Manages a registry of 6 built-in tools with permission control:
| Tool | Category | Requires Approval |
|------|----------|-------------------|
| `web_search` | Web search | No |
| `http_request` | HTTP requests | Yes |
| `memory_search` | Memory operations | No |
| `memory_store` | Memory operations | No |
| `summarize` | Summarization | No |
| `code_sandbox` | Code execution | Yes |

Tools can be enabled/disabled per-tool. Dangerous operations (HTTP requests, code execution) require explicit approval.

**Knowledge Graph** (:9300) — Maintains an in-memory graph of entities and relationships extracted from conversations. Supports 8 node types (person, project, company, conversation, task, topic, location, concept) and 10 relationship types (works_with, belongs_to, discussed_in, related_to, etc.). Provides context enrichment for the Brain via `/context/{node_id}`.

**Autonomous Runner** (:9400) — Executes background tasks on schedules (interval, cron, or one-shot). Task types include research, monitoring, reminders, digests, and learning. Limits to 5 concurrent tasks with a 5-minute runtime cap per task.

**Self Learning** (:9500) — Analyzes conversation patterns and agent performance. Detects 6 insight types: patterns, preferences, improvements, routing optimizations, knowledge gaps, and behavioral insights. Tracks metrics per agent (latency, success rate, user satisfaction) and suggests routing optimizations.

### How a Call Flows

1. Incoming Twilio SIP call → **Dograh API** receives webhook
2. Audio streamed via **LiveKit** WebRTC room
3. Real-time STT transcribes caller speech
4. **Agent Manager** in Brain classifies query → routes to agent pipeline
5. **MemoryAgent** retrieves relevant context from Qdrant
6. **ResearchAgent** / **TaskAgent** / **ToolAgent** contribute if triggered
7. **LLM Gateway** generates response (cached / rate-limited / batched)
8. Response injected with personality from `personality/*.md`
9. TTS converts response to audio, streamed back via LiveKit
10. **Knowledge Graph** updates entities and relationships
11. **Self Learning** asynchronously analyzes the interaction
12. **Memory** stores embeddings; **Trainer** extracts preferences

---

## Dashboard

The Fazle UI (Next.js 14, TypeScript, Tailwind CSS) provides a control dashboard at `fazle.iamazim.com` with the following pages:

| Page | Route | Purpose |
|------|-------|---------|
| Overview | `/dashboard` | System status, quick actions |
| Conversations | `/dashboard/conversations` | Chat history, search |
| Settings | `/dashboard/settings` | Brain, memory, voice configuration |
| **Autonomous Tasks** | `/dashboard/autonomous-tasks` | Create/manage background tasks, schedule intervals, view execution history |
| **Tool Engine** | `/dashboard/tool-engine` | View tool registry, enable/disable tools, trigger manual tool executions |
| **Knowledge Graph** | `/dashboard/knowledge-graph` | Visualize entities and relationships, browse nodes by type |
| **Learning** | `/dashboard/learning` | View learning insights, trigger analysis, monitor pattern detection stats |

Pages marked in **bold** were added in Phase 5.

---

## Networking & Domains

### Docker Networks

| Network | Scope | Purpose |
|---------|-------|---------|
| `app-network` | Bridged | Connects Dograh + Fazle front-end services |
| `db-network` | Internal | PostgreSQL, Redis, MinIO, Qdrant (not externally reachable) |
| `ai-network` | Internal | Fazle AI services inter-communication |
| `monitoring-network` | Internal | Prometheus, Grafana, Loki, Promtail |

### Nginx Reverse Proxy (SSL)

| Domain | Backend | Port |
|--------|---------|------|
| `iamazim.com` | dograh-ui | 3010 |
| `api.iamazim.com` | dograh-api | 8000 |
| `livekit.iamazim.com` | livekit | 7880 |
| `fazle.iamazim.com` | fazle-ui / fazle-api | 3020 / 8100 |

### Externally Exposed Ports

| Port | Protocol | Service |
|------|----------|---------|
| 80 | TCP | Nginx (HTTP → HTTPS redirect) |
| 443 | TCP | Nginx (SSL termination) |
| 3478 | TCP/UDP | Coturn STUN/TURN |
| 5349 | TCP/UDP | Coturn TURN over TLS |
| 7881 | TCP | LiveKit RTC (direct, not proxied) |
| 49152–49252 | UDP | Coturn relay range |
| 50000–50200 | UDP | LiveKit WebRTC media range |

---

## Monitoring Stack

**Prometheus → Grafana → Loki → Promtail**

| Component | Port | Function |
|-----------|------|----------|
| Prometheus | 9090 | Scrapes metrics from all services (15 min retention) |
| Grafana | 3030 | Dashboards and alerting |
| Loki | 3100 | Centralized log storage |
| Promtail | 9080 | Ships Docker container logs to Loki |
| node-exporter | 9100 | Host CPU, memory, disk, network metrics |
| cAdvisor | 8080 | Per-container resource metrics |

**Metrics collected:** CPU/memory/disk (host + container), PostgreSQL queries, Redis operations, LiveKit status, LLM gateway cache hit rates, queue depth, worker throughput, and per-service Prometheus client metrics.

---

## Database

**PostgreSQL 17** with **pgvector** and **uuid-ossp** extensions.

### Core Tables

| Table | Scope | Purpose |
|-------|-------|---------|
| `calls` | Dograh | Call history (caller, duration, recordings, status) |
| `messages` | Dograh | Call transcripts (speaker, timestamp, text) |
| `voice_configurations` | Dograh | Per-contact voice/personality settings |
| `call_logs` | Dograh | Audit trail |
| `fazle_conversation_history` | Fazle | All chats & interactions |
| `fazle_audit_log` | Fazle | Append-only audit log (RLS enforced) |
| `fazle_relationship_graph` | Fazle | Contacts, relationships, interaction counts |
| `fazle_corrections` | Fazle | User corrections to AI responses |
| `fazle_learning_runs` | Fazle | Learning job history |
| `fazle_scheduler_jobs` | Fazle | Scheduled tasks & reminders |
| `fazle_web_intelligence_cache` | Fazle | Cached web search results & summaries |

### Vector Storage

**Qdrant** stores conversation embeddings for semantic search across all past interactions.

---

## Security

| Layer | Implementation |
|-------|---------------|
| **Authentication** | JWT tokens (PyJWT) + bcrypt password hashing |
| **Service-to-service auth** | FAZLE_API_KEY with `hmac.compare_digest` (timing-safe) |
| **Row-Level Security** | RLS policies via `_rls_conn()` on all tables — user isolation enforced at DB level |
| **Audit logging** | Append-only `fazle_audit_log` table (RLS prevents updates/deletes) |
| **Transport** | HTTPS everywhere + HSTS; HTTP → HTTPS redirect |
| **CORS** | Restricted to `iamazim.com` and `fazle.iamazim.com` |
| **Input validation** | Pydantic schemas with length limits and regex patterns |
| **Content safety** | OpenAI Moderation API with stricter thresholds for child accounts |
| **SSRF protection** | Private IP blocking on web scraper endpoints |
| **Container hardening** | Read-only filesystems, resource limits, pinned image versions |
| **Network isolation** | `db-network` and `monitoring-network` are Docker internal networks |
| **Secrets** | All critical secrets use `${VAR:?}` fail-fast; never echoed to logs |
| **Database hardening** | Password complexity, connection limits, query timeouts |
| **API docs blocked** | `/docs` and `/openapi.json` disabled in production Nginx |

---

## Deployment

### Prerequisites

- Ubuntu VPS with Docker and Docker Compose v2
- Domain pointed to VPS IP (`iamazim.com` + subdomains)
- Let's Encrypt SSL certificates (use `scripts/setup-ssl.sh`)
- UFW firewall configured (use `scripts/setup-firewall.sh`)
- `.env` file with all required secrets (see [Secrets Management](#secrets-management))

### Quick Start

```bash
# 1. Clone and enter directory
git clone <repo-url> vps-deploy && cd vps-deploy

# 2. Generate secrets
./scripts/gen-secrets.sh

# 3. Create Docker networks
./scripts/create-networks.sh

# 4. Start foundation services
cd ai-infra && docker compose up -d && cd ..

# 5. Run database migrations
./scripts/db-migrate.sh

# 6. Start voice platform
cd dograh && docker compose --env-file ../.env up -d && cd ..

# 7. Start Fazle AI (core services)
cd fazle-ai && docker compose --env-file ../.env up -d && cd ..

# 8. Start Phase-5 autonomous services
cd scripts && docker compose -f phase5-standalone.yaml --env-file ../.env up -d && cd ..

# 9. Verify all services
./scripts/health-check.sh
```

### Full VPS Deployment

```bash
# Deploys via SSH: backup → upload → extract → rebuild → migrate → healthcheck
./scripts/deploy-to-vps.sh
```

### Zero-Downtime Rolling Deploy

For **fazle-api** (blue/green via Nginx):

```bash
./scripts/deploy-rolling.sh
```

Process:
1. Build new image
2. Start on green port (8102) alongside blue (8101)
3. Health check the green instance
4. Switch Nginx upstream to both → drain → switch to green only
5. Stop blue

For **internal services** (brain, memory, etc.): Docker DNS round-robin during transition.

### Rollback

```bash
# Reverts to previous image tag (rolling-previous)
./scripts/rollback-rolling.sh

# Full VPS rollback to previous commit
./scripts/rollback-vps.sh
```

### Stack Management

```bash
./scripts/stack-up.sh       # Start all 3 stacks
./scripts/stack-down.sh     # Stop all 3 stacks
./scripts/stack-status.sh   # Health status of all services
```

---

## Scripts Reference

### Deployment & Infrastructure

| Script | Purpose |
|--------|---------|
| `deploy-to-vps.sh` | Full VPS deployment via SSH |
| `rollback-vps.sh` | Rollback to previous commit |
| `deploy-rolling.sh` | Zero-downtime blue/green deploy |
| `rollback-rolling.sh` | Rollback rolling deployment |
| `deploy-phase6.sh` | Deploy three-stack architecture |
| `migration-deploy.sh` | Migrate single-compose → 3 stacks |
| `db-migrate.sh` | Run PostgreSQL migrations |
| `setup-ssl.sh` | Generate Let's Encrypt certificates |
| `setup-firewall.sh` | Configure UFW rules |
| `setup-minio.sh` | Initialize MinIO buckets |
| `setup-ollama.sh` | Pull Ollama models |
| `create-networks.sh` | Create Docker networks |

### Stack Management

| Script | Purpose |
|--------|---------|
| `stack-up.sh` | Start all services |
| `stack-down.sh` | Stop all services |
| `stack-status.sh` | Check health status of all containers |

### Monitoring & Debugging

| Script | Purpose |
|--------|---------|
| `health-check.sh` | Verify all services are healthy |
| `check-monitoring.sh` | Verify Prometheus/Grafana/Loki pipeline |
| `check-livekit-api.py` | Test LiveKit connectivity |
| `check-watchdog-prereqs.sh` | Verify AI watchdog dependencies |
| `debug.sh` | Detailed system diagnostics |
| `diagnose.sh` | Troubleshoot common issues |
| `load-test.py` | Performance / concurrency testing |

### Data & Configuration

| Script | Purpose |
|--------|---------|
| `gen-secrets.sh` | Generate / rotate secrets |
| `backup.sh` | Backup PostgreSQL, Qdrant, Redis, MinIO (7-day retention) |
| `verify-configs.sh` | Validate all config files |
| `verify-remediation.sh` | Verify security audit fixes |
| `set-persona-overrides.py` | Configure voice personality |
| `seed-family.py` | Initialize family relationships |

### Testing & Integration

| Script | Purpose |
|--------|---------|
| `test-login.sh` | Test authentication flow |
| `test-fazle.sh` | Test Fazle API endpoints |
| `test-api-dns.py` / `.js` | DNS resolution tests |
| `test-openai-final.py` | OpenAI integration test |
| `test-multimodal.sh` | Multi-modal LLM tests |
| `test-full-login.sh` | End-to-end login flow |

---

## Secrets Management

Secrets are generated and managed by `scripts/gen-secrets.sh` and stored in `.env`.

### Managed Secrets

| Variable | Purpose | Rotation Impact |
|----------|---------|-----------------|
| `POSTGRES_PASSWORD` | Database auth | DB restart required |
| `REDIS_PASSWORD` | Redis auth | All Redis clients restart |
| `MINIO_SECRET_KEY` | S3 storage auth | Invalidates S3 access |
| `MINIO_ACCESS_KEY` | S3 storage credentials | MinIO credential change |
| `OSS_JWT_SECRET` | Dograh JWT signing | All Dograh sessions invalidated |
| `LIVEKIT_API_KEY` | LiveKit auth | Breaks active voice calls |
| `LIVEKIT_API_SECRET` | LiveKit auth | Breaks active voice calls |
| `TURN_SECRET` | Coturn auth | Breaks NAT traversal |
| `FAZLE_API_KEY` | Fazle service-to-service auth | Breaks Fazle internal calls |
| `FAZLE_JWT_SECRET` | Fazle JWT signing | Invalidates user sessions |
| `NEXTAUTH_SECRET` | Fazle UI session signing | Invalidates UI sessions |
| `GRAFANA_PASSWORD` | Grafana login | Only Grafana affected |

### Commands

```bash
./scripts/gen-secrets.sh                    # Generate missing secrets
./scripts/gen-secrets.sh --check            # Verify all secrets present
./scripts/gen-secrets.sh --rotate-all       # Rotate all (use with caution)
./scripts/gen-secrets.sh --rotate VAR1,VAR2 # Rotate specific secrets
./scripts/gen-secrets.sh --env-file /path   # Custom .env file
```

Security properties:
- `.env` created with `chmod 600`
- Atomic writes (temp file + `mv`)
- Cryptographic randomness via `openssl rand`
- Secrets never echoed to stdout

---

## Testing

**Framework:** pytest with `asyncio_mode = auto`

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_llm_gateway.py
```

### Test Coverage

| Test File | Area |
|-----------|------|
| `test_learning_engine.py` | Learning service functionality |
| `test_llm_gateway.py` | LLM gateway caching & rate limiting |
| `test_persona_evolution.py` | Personality update logic |
| `test_safety_fail_closed.py` | Content moderation fail-closed behavior |
| `test_autonomy_engine.py` | Goal decomposition, plan execution, self-reflection |
| `test_tool_engine.py` | Tool registry, permission control, sandboxed execution |
| `test_knowledge_graph.py` | Entity/relationship CRUD, context retrieval |
| `test_autonomous_runner.py` | Task scheduling, background execution |
| `test_self_learning.py` | Pattern detection, insight generation, routing optimization |
| `test_agent_manager.py` | Multi-agent routing, pipeline orchestration |
| `test_phase5_integration.py` | End-to-end Phase-5 service integration |
| `test_phase5_api_proxy.py` | API gateway proxy routes for Phase-5 |

Integration tests are available as shell scripts in `scripts/test-*.sh`.

---

## Configuration Files

```
configs/
├── coturn/
│   └── turnserver.conf         # TURN/STUN server (realm: iamazim.com)
├── grafana/                    # Grafana dashboards & data sources
├── livekit/
│   └── livekit.yaml            # WebRTC config (ports, webhooks, Redis backend)
├── loki/
│   └── loki.yaml               # Log aggregation server config
├── nginx/                      # Reverse proxy configs for 4 domains
├── prometheus/
│   └── prometheus.yaml         # Metric scrape targets
└── promtail/
    └── promtail.yaml           # Log shipper config → Loki
```

Additional configs:
- `personality/personality.md` — Master personality definition
- `personality/azim-master-persona.md` — Detailed persona rules, relationship boundaries, content safety
- `scripts/phase5-standalone.yaml` — Docker Compose for Phase-5 autonomous services (standalone deployment)
- `db/rls/rls_policies.sql` — Row-Level Security policies
- `db/hardening/` — Database hardening scripts

---

## First-Time Platform Setup

### 1. Open Dashboard
- Go to https://iamazim.com
- Create admin account

### 2. Configure API Keys (Dashboard → Settings)
- **OpenAI API Key** — for LLM responses
- **Twilio credentials** — Account SID + Auth Token
- **ElevenLabs** (optional) — for voice cloning TTS

### 3. Configure LiveKit (Dashboard → Settings → Voice)
- LiveKit URL: `wss://livekit.iamazim.com`
- API Key: (from your `.env` `LIVEKIT_API_KEY`)
- API Secret: (from your `.env` `LIVEKIT_API_SECRET`)

### 4. Create AI Agent
1. Click "New Agent" → "Inbound"
2. Paste content from `personality/personality.md` as system prompt
3. Select LLM: GPT-4o / GPT-4o-mini
4. Select TTS: Deepgram / ElevenLabs
5. Select STT: Deepgram
6. Save and test with "Web Call"

### 5. Connect Twilio Phone Number
1. Dashboard → Settings → Telephony → Add Twilio
2. Enter Account SID + Auth Token
3. Purchase/assign phone number
4. Dograh auto-configures the webhook

---

## Management Commands

```bash
cd /home/azim/ai-call-platform

# ── Deploy & Status ────────────────────────────────────────
bash scripts/deploy.sh              # Full deploy
bash scripts/deploy.sh status       # Service status + resource usage
bash scripts/deploy.sh restart      # Restart all services
bash scripts/deploy.sh update fazle # Rolling update Fazle only
bash scripts/deploy.sh logs         # Tail all logs
bash scripts/deploy.sh logs fazle-api  # Tail specific service

# ── Monitoring & Logs ──────────────────────────────────────
# Grafana: https://iamazim.com/grafana/ (change admin password on first login!)
docker stats --no-stream

# ── Backups (auto-scheduled via cron) ──────────────────────
bash scripts/backup.sh              # Manual backup
# Cron: 0 2 * * * /home/azim/ai-call-platform/scripts/backup.sh

# ── Health check ───────────────────────────────────────────
bash scripts/health-check.sh
```

---

## Redis Database Allocation

| DB | Service | Purpose |
|----|---------|---------|
| 0 | Default (Dograh, LiveKit) | Session data, coordination |
| 1 | Fazle Brain | Conversation cache (24h TTL) |
| 2 | Fazle Trainer | Training session tracking |
| 3 | LLM Gateway | Response cache (300s TTL), rate limits (10 req/s), usage stats |
| 4 | Learning Engine | Relationship graph, user corrections |
| 5 | Queue + Workers | Redis Streams for async LLM requests |

---

## Resource Limits

| Service          | CPU  | Memory | Reserved |
|------------------|------|--------|----------|
| PostgreSQL       | 2    | 2 GB   | 512 MB   |
| Redis            | 1    | 768 MB | 256 MB   |
| MinIO            | 1    | 1 GB   | 256 MB   |
| LiveKit          | 2    | 1 GB   | 256 MB   |
| Coturn           | 1    | 512 MB | 128 MB   |
| Ollama           | 4    | 6 GB   | 2 GB     |
| Qdrant           | 1    | 1 GB   | 256 MB   |
| Fazle Brain      | 2    | 1 GB   | 256 MB   |
| Fazle API        | 1    | 512 MB | 128 MB   |
| Fazle Memory     | 1    | 512 MB | 128 MB   |
| Fazle Tasks      | 0.5  | 512 MB | 128 MB   |
| Fazle Web Intel  | 0.5  | 512 MB | 128 MB   |
| Fazle Trainer    | 1    | 512 MB | 128 MB   |
| Fazle Voice      | 1    | 512 MB | 128 MB   |
| Fazle UI         | 0.5  | 256 MB | 128 MB   |
| LLM Gateway      | 1    | 1 GB   | 256 MB   |
| Learning Engine  | 0.5  | 512 MB | 128 MB   |
| Queue            | 0.5  | 512 MB | 128 MB   |
| Workers ×2       | 1 ea | 1 GB ea| 256 MB ea|
| Prometheus       | 0.5  | 512 MB | 256 MB   |
| Grafana          | 0.5  | 256 MB | 128 MB   |
| Loki             | 0.5  | 512 MB | 256 MB   |

### Ollama Resource Protection

| Setting | Value | Rationale |
|---------|-------|-----------|
| NUM_PARALLEL | 1 | Prevent RAM exhaustion on 7.8GB VPS |
| MAX_LOADED_MODELS | 1 | Only load one model at a time |
| MAX_QUEUE | 2 | Prevent request pile-up |
| Memory limit | 6 GB | Hard ceiling |
| Installed model | qwen2.5:3b (1.9GB) | Only model on VPS |

---

## Troubleshooting

### LiveKit not connecting
```bash
docker logs livekit --tail 50
ss -tlnp | grep 7881
curl -i https://livekit.iamazim.com
```

### TURN server issues
```bash
docker logs coturn --tail 50
stun turn.iamazim.com:3478
openssl s_client -connect turn.iamazim.com:5349
```

### Call quality problems
- Check API response time: `curl -w "%{time_total}" https://api.iamazim.com/api/v1/health`
- Check LiveKit connectivity: Browser DevTools → Network → WS tab
- Check TURN relay: LiveKit dashboard → Room details
- Monitor resources: `docker stats --no-stream`

---

## Roadmap

### Completed

| Phase | Feature | Status |
|-------|---------|--------|
| Phase 1 | Core platform (Dograh + Fazle) | Deployed |
| Phase 2 | Firewall, ports, network isolation | Deployed |
| Phase 3 | TLS/SSL, Certbot, Coturn hardening | Deployed |
| Phase 4 | Database RLS, security hardening, learning system | Deployed |
| Phase 5 | Autonomous AI — multi-agent brain, autonomy engine, tool engine, knowledge graph, autonomous runner, self-learning | Deployed (2026-03-19) |

### Planned

- **Voice AI Training** — Custom voice model training pipeline
- **Voice Cloning** — Full voice clone with accent/tone personalization
- **PII Redaction** — Strip personal data before storing extracted knowledge
- **PWA Support** — Service worker, manifest, and offline capabilities
- **CI/CD Pipeline** — Automated testing and deployment
- **Coturn Rootless** — Run Coturn with `CAP_NET_BIND_SERVICE` instead of root

---

## License

Private / proprietary. All rights reserved.
