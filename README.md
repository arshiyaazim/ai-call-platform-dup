# Dograh + Fazle AI — Autonomous Voice Agent Platform

> AI-powered voice agent platform with an autonomous intelligence layer. Handles real-time phone calls via Twilio SIP and LiveKit WebRTC, backed by a multi-agent AI brain that plans, reasons, learns, and self-improves across every interaction.

**Domain:** `iamazim.com` &nbsp;|&nbsp; **VPS:** Contabo (4 CPUs, 7.8 GB RAM, 73 GB disk, Ubuntu)  
**Version:** Phase 6 — Ollama-First LLM Gateway &nbsp;|&nbsp; **Containers:** 38  
**Last updated:** 2026-04-11

---

## Table of Contents

- [Overview](#overview)
- [LLM Strategy](#llm-strategy)
- [Architecture](#architecture)
- [Services](#services)
  - [Stack 1 — ai-infra (Foundation)](#stack-1--ai-infra-foundation)
  - [Stack 2 — dograh (Voice Platform)](#stack-2--dograh-voice-platform)
  - [Stack 3 — fazle-ai (Intelligence Layer)](#stack-3--fazle-ai-intelligence-layer)
- [Fazle Personal AI System](#fazle-personal-ai-system)
  - [Multi-Agent Brain](#multi-agent-brain)
  - [LLM Gateway](#llm-gateway)
  - [How a Call Flows](#how-a-call-flows)
- [Dashboard](#dashboard)
- [Networking & Domains](#networking--domains)
- [Monitoring & Observability](#monitoring--observability)
- [Database](#database)
- [Security](#security)
- [Deployment](#deployment)
- [Scripts Reference](#scripts-reference)
- [Secrets Management](#secrets-management)
- [Testing](#testing)
- [Configuration Files](#configuration-files)
- [Known Issues & Cost Drivers](#known-issues--cost-drivers)
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
- **Ollama-first LLM** — all chat routed through local `qwen2.5:1.5b` with automatic OpenAI `gpt-4o` fallback (10 s timeout)
- Real-time voice call handling (Twilio → LiveKit → STT → LLM → TTS)
- Multi-agent brain with 9+ specialized agents (conversation, memory, research, task, tool, voice, social, system, learning)
- LLM gateway with caching (300 s TTL), rate limiting (60 RPM), request batching, PostgreSQL conversation logging, and trainable data export
- Autonomous goal planning with self-reflection and retry logic
- Tool execution engine with permission control and sandboxing
- Knowledge graph tracking people, projects, conversations, and relationships
- Background autonomous task runner (research, monitoring, digests, reminders)
- Self-learning engine that detects patterns and optimizes agent routing
- Personality injection with relationship-aware context (family, social, professional)
- Semantic memory search over all past conversations (Qdrant vectors)
- Workflow engine for multi-step automation
- Social engine with WhatsApp/Facebook intent detection
- Guardrail engine for content safety enforcement
- OpenTelemetry distributed tracing
- Full observability: Prometheus + Grafana + Loki + Promtail + OTel
- Zero-downtime blue/green deployments
- Row-Level Security on all database tables

---

## LLM Strategy

As of 2026-04-11, the platform runs **Ollama-first** with automatic OpenAI fallback:

| Layer | Provider | Model | Purpose |
|-------|----------|-------|---------|
| **Primary chat** | Ollama (local) | `qwen2.5:1.5b` | All brain + trainer chat via LLM gateway |
| **Fallback chat** | OpenAI (API) | `gpt-4o` | Triggered when Ollama times out (10 s) or errors |
| **Voice fast path** | Ollama (direct) | `qwen2.5:1.5b` | `/chat/voice` bypasses gateway for TTFB |
| **Emergency fallback** | Ollama (direct) | `qwen2.5:0.5b` | Last resort before static reply |
| **Embeddings (primary)** | OpenAI | `text-embedding-3-small` | Memory service vector embeddings |
| **Embeddings (fallback)** | Ollama | `nomic-embed-text` | Embedding fallback when OpenAI fails |
| **Audio transcription** | OpenAI | `whisper-1` | Voice + multimodal uploads |
| **Image captioning** | OpenAI | `gpt-4o` (vision) | Multimodal chat image analysis |
| **TTS** | Deepgram / ElevenLabs | — | Voice synthesis (configurable) |

**Installed Ollama models:** `qwen2.5:1.5b` (986 MB), `nomic-embed-text` (274 MB), `qwen2.5:0.5b` (397 MB), `qwen2.5:3b` (1.9 GB)

**LLM Gateway routing:**
1. Check Redis cache (300 s TTL) → return cached if hit
2. Call Ollama `qwen2.5:1.5b` with 10 s timeout
3. If Ollama fails/times out → fallback to OpenAI `gpt-4o`
4. Log every exchange to `llm_conversation_log` in PostgreSQL (provider, model, latency, is_fallback, trainable)
5. Fallback responses marked `trainable=true` for future fine-tuning export via `/training-data`

---

## Architecture

```
                          ┌──────────────────────┐
                          │   Cloudflared Tunnel  │
                          │   + Nginx (SSL)       │
                          │   iamazim.com :443    │
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
                        │  │(9 agents)  └────┬───┘  └─────┬──────┘ │
                        │  └────┬────┘       │      Ollama│→OpenAI  │
                        │       │       ┌────▼───┐  ┌────▼──────┐ │
                        │  ┌────▼────┐  │Trainer │  │  Queue    │ │
                        │  │ Tasks   │  │ :8600  │  │  :8810    │ │
                        │  │ :8400   │  └────────┘  └────┬──────┘ │
                        │  └─────────┘                   │         │
                        │                          ┌─────▼───────┐ │
                        │  ┌──────────┐ ┌────────┐ │  Workers    │ │
                        │  │  Voice   │ │Learning│ │  :8820 × 2  │ │
                        │  │  :8700   │ │ :8900  │ └─────────────┘ │
                        │  └──────────┘ └────────┘                 │
                        │                                           │
                        │  ┌──────────┐ ┌──────────┐ ┌──────────┐ │
                        │  │ Social   │ │Workflow  │ │Guardrail │ │
                        │  │ :9800    │ │ :9700    │ │ :9600    │ │
                        │  └──────────┘ └──────────┘ └──────────┘ │
                        │  ┌──────────────────┐                    │
                        │  │ Web Intelligence │                    │
                        │  │     :8500        │                    │
                        │  └──────────────────┘                    │
                        │                                           │
                        │  Autonomous: Autonomy(:9100) Tool(:9200) │
                        │  KnowledgeGraph(:9300) Runner(:9400)     │
                        │  SelfLearning(:9500)                     │
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
              │                                                     │
              │  OTel Collector  node-exporter  cAdvisor  Promtail │
              │  :4317-4318      :9100          :8080     :9080    │
              └─────────────────────────────────────────────────────┘
```

---

## Services

The system deploys as **three Docker Compose stacks** plus a Cloudflare tunnel, totaling **38 containers**.

### Stack 1 — ai-infra (Foundation)

All shared infrastructure. Must start first.

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| ai-postgres | `pgvector/pgvector:pg17` | 5432 | PostgreSQL 17 + pgvector embeddings |
| ai-redis | `redis:7.2.5-alpine` | 6379 | Cache, pub/sub, streams, session store |
| minio | `minio/minio` | 9000 | S3-compatible object storage (recordings, files) |
| livekit | `livekit/livekit-server:v1.8.2` | 7880 / 7881 | WebRTC server for real-time audio |
| qdrant | `qdrant/qdrant:v1.17.0` | 6333 | Vector database for semantic memory |
| ollama | `ollama/ollama:0.3.14` | 11434 | Local LLM — primary provider (qwen2.5:1.5b) |
| coturn | `coturn/coturn:4.6.2` | 3478 / 5349 | TURN/STUN NAT traversal for WebRTC |
| prometheus | `prom/prometheus:latest` | 9090 | Metrics collection |
| grafana | `grafana/grafana:latest` | 3030 | Monitoring dashboards |
| loki | `grafana/loki:latest` | 3100 | Log aggregation |
| promtail | `grafana/promtail:latest` | 9080 | Log shipping → Loki |
| node-exporter | `prom/node-exporter:latest` | 9100 | Host-level metrics |
| cadvisor | `gcr.io/cadvisor/cadvisor:latest` | 8080 | Container metrics |
| cloudflared-tunnel | `cloudflare/cloudflared` | — | Cloudflare tunnel for edge routing |

### Stack 2 — dograh (Voice Platform)

Pre-built Dograh containers for voice call handling.

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| dograh-api | `dograhai/dograh-api:1.0.0` | 8000 | FastAPI backend — call routing, STT/TTS, webhooks |
| dograh-ui | `dograhai/dograh-ui:1.0.0` | 3010 | Next.js dashboard — call management |

### Stack 3 — fazle-ai (Intelligence Layer)

All Fazle services — core intelligence, Phase-5 autonomous services, and supporting infrastructure — in a single Compose file. Each builds from `fazle-system/`.

| Service | Port | Purpose |
|---------|------|---------|
| **Core** | | |
| fazle-api | 8100 | API Gateway — routing, JWT auth, rate limiting, Phase-5 proxy |
| fazle-brain | 8200 | Multi-agent reasoning — 9+ agents, Ollama-first via gateway |
| fazle-memory | 8300 | Vector memory — Qdrant semantic search, OpenAI embeddings |
| fazle-task-engine | 8400 | Scheduler — reminders, recurring tasks (APScheduler) |
| fazle-web-intelligence | 8500 | Web search & scraping (Serper API, BeautifulSoup) |
| fazle-trainer | 8600 | ML training — preference extraction, fine-tuning |
| fazle-voice | 8700 | Voice processing — LiveKit STT/TTS, accent modulation |
| fazle-ui | 3020 | Next.js dashboard — settings, conversations, Phase-5 management |
| **LLM Infrastructure** | | |
| fazle-llm-gateway | 8800 | Centralized LLM routing — Ollama→OpenAI fallback, caching, DB logging |
| fazle-queue | 8810 | Async request queue (Redis Streams) |
| fazle-workers ×2 | 8820 | Worker pool consuming from queue |
| **Autonomous AI** | | |
| fazle-autonomy-engine | 9100 | Goal decomposition — multi-step plans with self-reflection |
| fazle-tool-engine | 9200 | Tool registry — permission control, sandboxed execution |
| fazle-knowledge-graph | 9300 | Entity & relationship store — people, projects, conversations |
| fazle-autonomous-runner | 9400 | Background task runner — research, monitoring, digests |
| fazle-self-learning | 9500 | Pattern analysis — behavioral insights, routing optimization |
| **Extended Services** | | |
| fazle-guardrail-engine | 9600 | Content safety — input/output moderation |
| fazle-workflow-engine | 9700 | Multi-step workflow automation |
| fazle-social-engine | 9800 | WhatsApp/Facebook — intent detection, contact intelligence |
| fazle-learning-engine | 8900 | Self-improvement — conversation analysis, knowledge extraction |
| **Observability** | | |
| fazle-otel-collector | 4317-4318 | OpenTelemetry collector — distributed tracing |

---

## Fazle Personal AI System

Fazle is a layered intelligence system composed of 22 microservices:

```
Layer 1  API Gateway (fazle-api :8100)
           ├── JWT auth, rate limiting, request routing
           ├── Phase-5 proxy routes (autonomy, tools, KG, learning)
           │
Layer 2  Brain + Agents (fazle-brain :8200)
           ├── Multi-agent orchestration (9+ agents)
           ├── Query routing: FAST_VOICE / CONVERSATION / FULL_PIPELINE
           ├── Personality injection from persona definitions
           ├── USE_LLM_GATEWAY=true → routes chat through gateway
           │
           │   ┌─────────────────────────────────────────────────────┐
           │   │  Agent Manager                                      │
           │   │  Strategy Tier:                                     │
           │   │  ├── StrategyAgent — domain routing coordinator     │
           │   │  Domain Agents:                                     │
           │   │  ├── SocialAgent — WhatsApp/FB intent + contacts   │
           │   │  ├── VoiceAgent — ultra-low latency voice calls    │
           │   │  ├── SystemAgent — governor + autonomy coordination│
           │   │  ├── LearningAgent — corrections + memory storage  │
           │   │  Utility Agents:                                    │
           │   │  ├── ConversationAgent — direct LLM responses      │
           │   │  ├── MemoryAgent — semantic recall & fact storage   │
           │   │  ├── ResearchAgent — web search & content scraping  │
           │   │  ├── TaskAgent — scheduling & reminders             │
           │   │  └── ToolAgent — plugin-based tool execution        │
           │   └─────────────────────────────────────────────────────┘
           │
Layer 3  Memory (fazle-memory :8300)
           ├── Qdrant vector search (OpenAI embeddings → Ollama fallback)
           ├── Embedding generation
           └── Structured knowledge (PostgreSQL)
           │
Layer 4  LLM Gateway (fazle-llm-gateway :8800)
           ├── Ollama qwen2.5:1.5b (10s timeout) → OpenAI gpt-4o fallback
           ├── Response caching (300s TTL)
           ├── Rate limiting (60 RPM / 10 req/s per user)
           ├── Request batching (75ms window / 4 max)
           ├── PostgreSQL conversation logging (llm_conversation_log)
           └── Trainable data export (/training-data)
           │
Layer 5  Extended Services
           ├── Social Engine (:9800) — WhatsApp/FB platform routing
           ├── Workflow Engine (:9700) — multi-step automation
           ├── Guardrail Engine (:9600) — content safety
           ├── Learning Engine (:8900) — conversation analysis
           ├── Tasks (:8400), Web Intelligence (:8500), Trainer (:8600)
           └── Queue (:8810) + Workers ×2 (:8820)
           │
Layer 6  Autonomous AI
           ├── Autonomy Engine (:9100) — goal planning & execution
           ├── Tool Engine (:9200) — secure tool orchestration
           ├── Knowledge Graph (:9300) — entity relationship store
           ├── Autonomous Runner (:9400) — background task execution
           └── Self Learning (:9500) — pattern analysis & optimization
```

### Multi-Agent Brain

The Brain service (`USE_LLM_GATEWAY=true`, `LLM_PROVIDER=ollama`, `LLM_MODEL=qwen2.5:1.5b`) runs an **Agent Manager** with a two-tier architecture:

**Strategy Tier** — StrategyAgent routes to the correct domain agent based on platform, caller, and intent.

**Domain Agents (4):**

| Agent | Role | Trigger |
|-------|------|---------|
| **SocialAgent** | WhatsApp/Facebook interactions — intent classification (HOT/WARM/COLD/RISK), contact intelligence | Platform = whatsapp/facebook |
| **VoiceAgent** | Voice call interactions — ultra-low latency, direct Ollama | Platform = voice |
| **SystemAgent** | Governor v2 status, autonomy coordination, self-development patches | System queries |
| **LearningAgent** | Correction processing, permanent memory storage, instruction learning | Correction/feedback |

**Utility Agents (5):**

| Agent | Role |
|-------|------|
| **ConversationAgent** | Direct LLM conversation (default fallback) |
| **MemoryAgent** | Semantic memory recall, fact storage |
| **ResearchAgent** | Web search, content scraping, summarization |
| **TaskAgent** | Task creation, scheduling, reminders |
| **ToolAgent** | Plugin tool discovery and execution |

**Query complexity classification** determines LLM routing:
- `simple` → greetings, yes/no, short (<8 chars) → fast path
- `medium` → single questions, factual lookups → standard pipeline
- `complex` → multi-part reasoning, analysis → full pipeline with all agents

### LLM Gateway

**Current deployed configuration:**

```
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen2.5:1.5b
OLLAMA_TIMEOUT=10
FALLBACK_PROVIDER=openai
FALLBACK_MODEL=gpt-4o
CACHE_TTL=300
RATE_LIMIT_RPM=60
RATE_LIMIT_PER_USER_RPS=10
BATCH_WINDOW_MS=75
BATCH_MAX_SIZE=4
DATABASE_URL=postgresql://postgres:***@postgres:5432/postgres
```

**DB logging (llm_conversation_log):**
Every LLM request/response is logged with: provider, model, system prompt hash, user prompt, reply, latency_ms, is_fallback, trainable, timestamp.

**Training data export:** `GET /training-data?limit=100` returns all rows where `trainable=true` (OpenAI fallback responses) for future Ollama fine-tuning.

### How a Call Flows

1. Incoming Twilio SIP call → **Dograh API** receives webhook
2. Audio streamed via **LiveKit** WebRTC room
3. Real-time STT transcribes caller speech
4. **Brain** classifies query complexity → routes to agent pipeline
5. **MemoryAgent** retrieves relevant context from Qdrant
6. System prompt built with personality, relationship tone, and knowledge context (truncated to ~800 chars for CPU budget)
7. **LLM Gateway** generates response: Ollama first (10 s) → OpenAI fallback → logged to DB
8. Response humanized (AI-isms removed) + confidence check
9. TTS converts response to audio, streamed back via LiveKit
10. Conversation stored in Redis (24h TTL) + memory service
11. **Knowledge Graph** updates entities and relationships (async)
12. **Self Learning** analyzes the interaction (async)

---

## Dashboard

The Fazle UI (Next.js 14, TypeScript, Tailwind CSS) provides a control dashboard at `fazle.iamazim.com` with the following pages:

| Page | Route | Purpose |
|------|-------|---------|
| Overview | `/dashboard/fazle` | System status, quick actions |
| Logs | `/dashboard/fazle/logs` | Conversation history, search |
| Memory | `/dashboard/fazle/memory` | Semantic memory search, fact storage |
| Agents | `/dashboard/fazle/agents` | Agent registry and status |
| Tools | `/dashboard/fazle/tools` | Tool registry, enable/disable tools, trigger manual executions |
| Tasks | `/dashboard/fazle/tasks` | Task scheduling and reminders |
| Persona | `/dashboard/fazle/persona` | Personality configuration |
| Autonomy | `/dashboard/fazle/autonomy` | Goal decomposition and autonomous planning |
| Knowledge Graph | `/dashboard/fazle/knowledge-graph` | Visualize entities and relationships, browse nodes by type |
| Auto Tasks | `/dashboard/fazle/autonomous-tasks` | Create/manage background tasks, schedule intervals, view execution history |
| Learning | `/dashboard/fazle/learning` | View learning insights, trigger analysis, monitor pattern detection stats |
| AI Safety | `/dashboard/fazle/ai-safety` | Content safety and guardrail configuration |
| Observability | `/dashboard/fazle/observability` | Distributed tracing and metrics |
| Workflows | `/dashboard/fazle/workflows` | Multi-step workflow automation |
| Marketplace | `/dashboard/fazle/tool-marketplace` | Tool marketplace |
| Watchdog | `/dashboard/fazle/watchdog` | AI watchdog monitoring |
| Users | `/dashboard/fazle/users` | User management |
| Social | `/dashboard/fazle/social` | WhatsApp/Facebook intent detection |
| Contacts | `/dashboard/fazle/contacts` | Contact intelligence |
| Privacy | `/dashboard/fazle/privacy` | Privacy controls |
| GDPR Admin | `/dashboard/fazle/gdpr-admin` | GDPR compliance administration |
| Settings | `/dashboard/fazle/settings` | Brain, memory, voice configuration |

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

## Monitoring & Observability

**Prometheus → Grafana → Loki → Promtail → OpenTelemetry**

| Component | Port | Function |
|-----------|------|----------|
| Prometheus | 9090 | Scrapes metrics from all services |
| Grafana | 3030 | Dashboards and alerting |
| Loki | 3100 | Centralized log storage |
| Promtail | 9080 | Ships Docker container logs to Loki |
| node-exporter | 9100 | Host CPU, memory, disk, network metrics |
| cAdvisor | 8080 | Per-container resource metrics |
| fazle-otel-collector | 4317-4318 | OpenTelemetry — distributed tracing across Fazle services |

**Metrics collected:** CPU/memory/disk (host + container), PostgreSQL queries, Redis operations, LiveKit status, LLM gateway cache hit rates, Ollama vs OpenAI fallback ratios, queue depth, worker throughput, and per-service Prometheus client metrics.

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
| `llm_conversation_log` | Gateway | Every LLM request/response — provider, model, latency, fallback flag, trainable flag |

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
3. LLM: Ollama `qwen2.5:1.5b` (primary) with OpenAI `gpt-4o` fallback via gateway
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
| 3 | LLM Gateway | Response cache (300s TTL), rate limits (10 req/s), Ollama→OpenAI fallback stats |
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
| NUM_PARALLEL | 1 | Prevent RAM exhaustion on 7.8 GB VPS |
| MAX_LOADED_MODELS | 1 | Only load one model at a time |
| MAX_QUEUE | 2 | Prevent request pile-up |
| Memory limit | 6 GB | Hard ceiling |
| Primary model | qwen2.5:1.5b (986 MB) | Fast inference, fits in RAM alongside all services |
| Installed models | qwen2.5:1.5b, qwen2.5:0.5b, qwen2.5:3b, nomic-embed-text | 4 models, ~3.5 GB total disk |

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

## Known Issues & Cost Drivers

### OpenAI Cost Drivers (as of 2026-04-11)

| # | Driver | Impact | Location |
|---|--------|--------|----------|
| 1 | **Brain parallel fan-out** | Fires Ollama direct + gateway simultaneously → double Ollama load → more timeouts → more OpenAI fallbacks | brain/main.py `query_llm_smart()` |
| 2 | **Hidden owner profile extraction** | Background LLM call after every owner message to extract identity info | brain/main.py `_extract_owner_profile_from_message()` |
| 3 | **Embeddings OpenAI-first** | Memory service tries `text-embedding-3-small` first for every store/search/ingest, falls back to Ollama `nomic-embed-text` | memory/main.py `get_embedding()` |
| 4 | **Multimodal embeddings OpenAI-only** | `text-embedding-3-large` with no Ollama fallback | memory/main.py `get_multimodal_embedding()` |
| 5 | **GPT-4o vision captioning** | Every uploaded image goes through GPT-4o vision | api/main.py `_caption_image_gpt4o()` |
| 6 | **Whisper transcription** | Every audio upload uses `whisper-1` API | api/main.py + brain/main.py |

### Known Technical Issues

- On 4-CPU VPS, Ollama inference with `qwen2.5:1.5b` averages 5-7 s, often exceeding the 10 s gateway timeout → high fallback rate to OpenAI
- Brain's parallel fan-out (`query_llm_smart`) causes Ollama contention: two simultaneous requests compete for the single-threaded Ollama instance

---

## Roadmap

### Completed

| Phase | Feature | Status |
|-------|---------|--------|
| Phase 1 | Core platform (Dograh + Fazle) | Deployed |
| Phase 2 | Firewall, ports, network isolation | Deployed |
| Phase 3 | TLS/SSL, Certbot, Coturn hardening | Deployed |
| Phase 4 | Database RLS, security hardening, learning system | Deployed |
| Phase 5 | Autonomous AI — multi-agent brain, autonomy engine, tool engine, knowledge graph, runner, self-learning | Deployed (2026-03-19) |
| Phase 6 | Ollama-first LLM gateway — caching, fallback, DB logging, training data export | Deployed (2026-04-10) |

### Planned

- **Single gateway architecture** — Remove brain's parallel fan-out, route ALL LLM calls through gateway only
- **Embedding migration** — Switch memory service to Ollama `nomic-embed-text` primary, OpenAI fallback
- **Ollama fine-tuning** — Train on collected OpenAI fallback responses from `llm_conversation_log`
- **Voice AI Training** — Custom voice model training pipeline
- **PII Redaction** — Strip personal data before storing extracted knowledge
- **CI/CD Pipeline** — Automated testing and deployment

---

## License

Private / proprietary. All rights reserved.
