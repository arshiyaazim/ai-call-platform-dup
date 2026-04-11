# Fazle Brain — Core Reasoning Engine

The central intelligence service of the Dograh/Fazle platform. Orchestrates AI reasoning, memory retrieval, autonomous intelligence, action execution, knowledge management, and self-learning — all under owner control.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Fazle Brain (8200)                 │
│                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐ │
│  │  Chat Engine  │  │ Action Engine │  │ Autonomous│ │
│  │  (main.py)   │  │(action_engine)│  │Intelligence│ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬────┘ │
│         │                 │                  │      │
│  ┌──────┴─────────────────┴──────────────────┴────┐ │
│  │        Knowledge / Memory / Identity           │ │
│  └────────────────────────────────────────────────┘ │
└───────────────┬─────────────┬───────────────────────┘
                │             │
    ┌───────────┴──┐  ┌──────┴──────┐
    │ LLM Gateway  │  │  PostgreSQL  │
    │   (8800)     │  │  + pgvector  │
    └──────────────┘  └─────────────┘
```

## Phase History

| Phase | Name | Key Additions |
|-------|------|---------------|
| 1 | Single LLM Entry Point | Centralized LLM calls through gateway |
| 2 | OpenAI Fallback & Cost Protection | Provider failover, cost tracking |
| 3 | System Audit & Owner Processing | Audit, optimized owner message handling |
| 4 | Local Embeddings | Ollama-first embedding with OpenAI fallback |
| 5 | LLM Observability & Cost Intelligence | Request logging, cost analytics |
| 6 | Knowledge Overwrite Engine | Fact versioning, category hierarchy |
| 7 | Smart Retrieval & Context Optimization | Semantic search, context windowing |
| 8 | Action & Automation Engine | ACTION_REGISTRY, 4 handlers, validation, idempotency |
| 9 | Critical Gaps Fix & Admin Dashboard | Rule-based intent, rollback, workflows, permissions, HTML dashboard |
| 10 | Autonomous Intelligence Layer | Event detection, recommendations, approval flow, auto-execution |
| 11 | Self-Learning Intelligence | Feedback learning, adaptive scoring, behavior memory, safety limits |

## Key Files

| File | Lines | Purpose |
|------|-------|---------|
| `main.py` | ~3,960 | FastAPI brain service — 51+ endpoints, chat, agents, dashboard |
| `action_engine.py` | ~780 | Action registry, execution, rollback, workflows, permissions |
| `autonomous_intelligence.py` | ~750 | Event detection, recommendations, self-learning engine |
| `dashboard.html` | ~300 | Admin dashboard — 6 tabs (Recommendations, Actions, Knowledge, LLM, Metrics, Learning) |
| `persona_engine.py` | | System prompt generation, identity, tone, context |
| `context_builder.py` | | Knowledge retrieval, smart context, intent detection |
| `intent_engine.py` | | Social media intent processing |
| `memory_manager.py` | | Redis-backed conversation & preference memory |
| `lead_capture.py` | | Automated lead capture from conversations |
| `owner_control/command_taxonomy.py` | | Owner command classification |

## API Endpoints

### Health & Status
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/status` | Full system status with multi-agent info |
| GET | `/control-plane/status` | Control plane status |

### Chat Operations
| Method | Path | Description |
|--------|------|-------------|
| POST | `/chat` | Main chat endpoint |
| POST | `/chat/voice` | Voice-optimized chat |
| POST | `/chat/owner` | Owner (admin) chat with action detection |
| POST | `/chat/stream` | Streaming chat response |
| POST | `/chat/fast` | Low-latency chat |
| POST | `/chat/agent` | Multi-agent chat routing |
| POST | `/chat/multimodal` | Multimodal (image+text) chat |

### Recommendations & Intelligence (Phase 10-11)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/recommendations` | List all recommendations |
| POST | `/recommendations/{id}/approve` | Approve + optionally execute |
| POST | `/recommendations/{id}/dismiss` | Dismiss a recommendation |
| POST | `/recommendations/scan` | Trigger intelligence scan |
| GET | `/recommendations/stats` | Recommendation statistics |
| GET | `/recommendations/learning` | Self-learning statistics |

### Actions & Workflow
| Method | Path | Description |
|--------|------|-------------|
| POST | `/decide` | AI-powered decision routing |
| POST | `/actions/rollback` | Rollback an executed action |
| POST | `/actions/workflow` | Execute multi-step workflow |

### Knowledge & Memory
| Method | Path | Description |
|--------|------|-------------|
| POST | `/tree/store` | Store tree memory |
| POST | `/tree/search` | Search tree memory |
| GET | `/tree/browse` | Browse memory tree structure |
| POST | `/knowledge-graph/update` | Update knowledge graph |
| GET | `/knowledge-graph/stats` | Knowledge graph statistics |

### Dashboard
| Method | Path | Description |
|--------|------|-------------|
| GET | `/dashboard` | Admin dashboard HTML |
| GET | `/dashboard/overview` | Dashboard overview data |
| GET | `/dashboard/actions` | Action audit log |
| GET | `/dashboard/knowledge` | Knowledge facts list |
| GET | `/dashboard/llm-usage` | LLM usage tracking |
| GET | `/analytics/action-metrics` | Action metrics breakdown |

## Database Tables

### Core
| Table | Purpose |
|-------|---------|
| `fazle_clients` | Client registry with activity tracking |
| `fazle_actions_audit` | Action execution audit trail |
| `fazle_knowledge_facts` | Versioned knowledge storage |
| `fazle_tree_memory` | Hierarchical memory tree |

### Intelligence (Phase 10-11)
| Table | Purpose |
|-------|---------|
| `ai_recommendations` | AI-generated recommendations with feedback scores |
| `ai_learning_weights` | Self-learning weights per event+action pair |

### Key Columns in `ai_learning_weights`
```
event_type VARCHAR(100) — e.g., "inactive_client"
action VARCHAR(100) — e.g., "follow_up_client"
weight REAL — multiplicative priority modifier (0.05-3.0)
approve_count INTEGER — owner approvals
dismiss_count INTEGER — owner dismissals
```

## Self-Learning System (Phase 11)

### How It Works
1. **Event Detection** → Scans DB for inactive clients, unassigned guards, missing pricing
2. **Recommendation Generation** → Creates scored, prioritized suggestions
3. **Owner Feedback** → Approve (+1.0) or dismiss (-1.0) each recommendation
4. **Weight Adjustment** → Approved: weight × 1.1 (boost), Dismissed: weight × 0.85 (reduce)
5. **Adaptive Scoring** → Next scan uses learned weights: `priority = base × learning_weight`
6. **Pattern Learning** → Weight < 0.2 → recommendation type auto-suppressed
7. **Behavior Memory** → Tracks consistently approved/dismissed patterns

### Safety Limits
- High-risk actions (`assign_guard`, `set_pricing`) weight capped at **1.5**
- Low-risk actions capped at **3.0**
- Weight floor: **0.05** (prevents permanent suppression)
- Auto-execution limited to `_LOW_RISK_ACTIONS = {"follow_up_client"}` only
- Auto-execution disabled by default (`AUTO_EXECUTION_ENABLED = False`)

## Infrastructure Requirements

### Minimum VPS Specs
| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 4 cores | 8 cores |
| RAM | 8 GB | 16 GB |
| Storage | 40 GB SSD | 80 GB SSD |
| OS | Ubuntu 22.04+ | Ubuntu 24.04 |

### Required Services
| Service | Image | Purpose | Resource Notes |
|---------|-------|---------|----------------|
| PostgreSQL | pgvector:pg17 | Primary DB + vectors | 1-2 GB RAM |
| Redis | redis:8.0.2-alpine | Cache, pub-sub | 512 MB max |
| Ollama | ollama:0.3.14 | Local LLM inference | 4 CPU, 6 GB RAM |
| Qdrant | qdrant:v1.17.0 | Vector search | 512 MB RAM |
| MinIO | minio:latest | Object storage | Minimal |
| LiveKit | livekit-server:v1.8.2 | WebRTC voice | Moderate |
| Coturn | coturn:4.6.2 | TURN/STUN NAT traversal | Minimal |

### Fazle Microservices (20 services)
| Service | Port | Purpose |
|---------|------|---------|
| fazle-api | 8100 | API gateway |
| fazle-brain | 8200 | **Core reasoning (this service)** |
| fazle-memory | 8300 | Vector memory |
| fazle-task-engine | 8400 | Scheduling & automation |
| fazle-web-intelligence | 8500 | Search & web extraction |
| fazle-trainer | 8600 | Learning & preference |
| fazle-voice | WS | LiveKit STT/TTS |
| fazle-llm-gateway | 8800 | Centralized LLM routing |
| fazle-queue | 8810 | Async request queue |
| fazle-workers | 8820 | LLM worker pool (2 replicas) |
| fazle-learning-engine | 8900 | Self-improvement |
| fazle-ui | 3020 | Next.js dashboard |
| fazle-autonomy-engine | 9100 | Goal decomposition |
| fazle-tool-engine | 9200 | Secure tools |
| fazle-knowledge-graph | 9300 | Entity/relationship store |
| fazle-autonomous-runner | 9400 | Background task loops |
| fazle-self-learning | 9500 | Pattern extraction |
| fazle-guardrail-engine | 9600 | AI safety |
| fazle-workflow-engine | 9700 | Multi-step workflows |
| fazle-social-engine | 9800 | WhatsApp/Facebook |

**Total: 28 containers** (20 Fazle + 8 infrastructure)

## Deployment

### Build & Start
```bash
# Infrastructure first
cd ai-infra && docker-compose up -d

# Application services
cd fazle-ai && docker-compose up -d --build
```

### Environment Variables
```bash
FAZLE_DATABASE_URL=postgresql://postgres:postgres@postgres:5432/postgres
REDIS_URL=redis://redis:6379/1
LLM_GATEWAY_URL=http://fazle-llm-gateway:8800
MEMORY_SERVICE_URL=http://fazle-memory:8300
OLLAMA_BASE_URL=http://ollama:11434
OPENAI_API_KEY=<your-key>
```

### Verify
```bash
curl http://localhost:8200/health
curl http://localhost:8200/status
curl http://localhost:8200/dashboard  # Admin dashboard
```

## Dashboard

Access at `http://<host>:8200/dashboard`

**6 Tabs:**
1. **Recommendations** — AI suggestions with approve/dismiss, scan trigger
2. **Actions** — Execution audit log with rollback
3. **Knowledge** — Stored facts with versioning
4. **LLM Usage** — Provider, model, latency, fallback tracking
5. **Metrics** — Action success rates, registry overview
6. **Learning** — Self-learning weights, behavior patterns, approval rates
