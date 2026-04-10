# ============================================================
# Fazle Brain — Core Reasoning Engine
# Orchestrates AI reasoning, memory retrieval, tool selection,
# and instruction generation for Dograh voice platform
# ============================================================
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from prometheus_fastapi_instrumentator import Instrumentator
import httpx
import json
import logging
import uuid
import asyncio
from typing import Optional
import os
from datetime import datetime
from memory_manager import conversation_get, conversation_set
from context_builder import build_knowledge_context, detect_intents, normalize_text, KNOWLEDGE_FALLBACK_BN, get_cached_context, set_cached_context
from intent_engine import process_social_intent, _get_state as _get_intent_state
from lead_capture import try_capture_lead
from persona_engine import build_system_prompt, build_system_prompt_async
from persona_engine import (
    build_user_history_context, build_anti_repetition_context,
    detect_user_type, build_context_awareness,
    build_owner_style_context,
    build_owner_system_prompt, build_daily_report_prompt,
    build_identity_context,
)
from memory_manager import (
    user_history_get, user_history_append,
    user_replies_get, user_replies_track,
    owner_pending_action_set, owner_pending_action_get, owner_pending_action_clear,
    owner_preference_set, owner_preferences_all,
    owner_instruction_store, owner_instructions_get,
    owner_conversation_append, owner_conversation_get,
    owner_tone_profile_update, owner_tone_profile_get, owner_tone_dominant,
    owner_pwd_challenge_set, owner_pwd_challenge_get, owner_pwd_challenge_clear,
    azim_profile_set, azim_profile_get, azim_profile_all, azim_profile_update,
    interview_question_push, interview_question_pop, interview_questions_pending,
    interview_answer_store,
    governor_quality_score_push, governor_identity_score_push,
    governor_safe_mode_get, governor_error_log, governor_drift_alert,
    governor_patch_baseline_set, governor_patch_baseline_get,
    intel_usage_track, intel_usage_stats,
    intel_owner_priority_set, intel_owner_priority_active,
)
from safety import check_content
from agents import AgentManager, AgentContext
from agents.manager import QueryRoute
from teaching_pipeline import UnifiedTeachingPipeline
from owner_control.knowledge_lifecycle import KnowledgeLifecycleEngine
from owner_control.owner_policy import OwnerPolicyEngine
from owner_control.response_playbooks import ConfusionHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fazle-brain")


class Settings(BaseSettings):
    openai_api_key: str = ""
    ollama_url: str = "http://ollama:11434"
    llm_provider: str = "openai"  # "openai" or "ollama"
    llm_model: str = "gpt-4o"
    ollama_model: str = "llama3.1"
    memory_url: str = "http://fazle-memory:8300"
    tools_url: str = "http://fazle-web-intelligence:8500"
    task_url: str = "http://fazle-task-engine:8400"
    llm_gateway_url: str = "http://fazle-llm-gateway:8800"
    learning_engine_url: str = "http://fazle-learning-engine:8900"
    autonomy_engine_url: str = "http://fazle-autonomy-engine:9100"
    tool_engine_url: str = "http://fazle-tool-engine:9200"
    knowledge_graph_url: str = "http://fazle-knowledge-graph:9300"
    autonomous_runner_url: str = "http://fazle-autonomous-runner:9400"
    self_learning_url: str = "http://fazle-self-learning:9500"
    use_llm_gateway: bool = False
    # Voice fast mode: bypass gateway, use Ollama, reduce top_k, skip batching
    voice_fast_mode: bool = False
    voice_ollama_model: str = "qwen2.5:0.5b"
    # Ultra-fast voice model (tiny, for <500ms TTFB)
    voice_fast_model: str = "qwen2.5:0.5b"
    # Persona cache TTL in seconds (0 = disabled)
    persona_cache_ttl: int = 300
    redis_url: str = "redis://redis:6379/1"
    # Owner critical action password (VPS login password)
    owner_action_password: str = ""
    # Social engine URL for contact lookup
    social_engine_url: str = "http://fazle-social-engine:9800"

    class Config:
        env_prefix = ""


settings = Settings()

# Shared HTTP client for ultra-fast Ollama calls (avoids per-request connection setup)
_fast_ollama_client: httpx.AsyncClient | None = None


def _get_fast_client() -> httpx.AsyncClient:
    global _fast_ollama_client
    if _fast_ollama_client is None or _fast_ollama_client.is_closed:
        _fast_ollama_client = httpx.AsyncClient(
            base_url=settings.ollama_url,
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0),
        )
    return _fast_ollama_client


app = FastAPI(title="Fazle Brain — Reasoning Engine", version="2.0.0")

Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# ── Agent Manager (multi-agent orchestration) ───────────────
agent_manager: AgentManager | None = None

# ── Production modules (initialized at startup) ─────────────
teaching_pipeline: UnifiedTeachingPipeline | None = None
knowledge_lifecycle: KnowledgeLifecycleEngine | None = None
owner_policy: OwnerPolicyEngine | None = None
confusion_handler: ConfusionHandler | None = None


@app.on_event("startup")
async def init_agents():
    global agent_manager, teaching_pipeline, knowledge_lifecycle, owner_policy, confusion_handler
    agent_manager = AgentManager(
        ollama_url=settings.ollama_url,
        voice_fast_model=settings.voice_fast_model,
        llm_gateway_url=settings.llm_gateway_url,
        memory_url=settings.memory_url,
        tools_url=settings.tools_url,
        task_url=settings.task_url,
        learning_engine_url=settings.learning_engine_url,
        autonomy_engine_url=settings.autonomy_engine_url,
        redis_url=settings.redis_url,
    )
    logger.info(
        "Agent Manager initialized: identity_core + strategy + "
        "4 domain agents (social, voice, system, learning) + 5 utility agents"
    )

    # ── Seed default owner profile if empty (Step 1) ──
    try:
        profile = azim_profile_all()
        if not profile:
            default_profile = {
                "full_name": "Azim",
                "role": "Business Owner & Tech Entrepreneur",
                "personality": "Direct, confident, casual, witty",
                "communication_style": "Desi-British mix, uses 'bro', 'bruh', 'wallah', bilingual Bangla-English",
                "language": "Bangla, English, Banglish",
                "location": "Bangladesh",
                "greeting_style": "Casual desi-british: 'yo', 'hey bro', 'assalamu alaikum'",
                "humor_level": "7",
                "strictness": "5",
                "tone_variation": "Direct and casual with friends, professional with clients, warm with family",
            }
            azim_profile_update(default_profile)
            logger.info("Seeded default owner profile (Step 1)")
    except Exception as e:
        logger.warning(f"Profile seeding failed: {e}")

    # ── Initialize production modules ──
    try:
        _dsn = os.getenv("FAZLE_DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/postgres")
        teaching_pipeline = UnifiedTeachingPipeline(dsn=_dsn, redis_url=settings.redis_url)
        knowledge_lifecycle = KnowledgeLifecycleEngine(dsn=_dsn)
        knowledge_lifecycle.ensure_tables()
        owner_policy = OwnerPolicyEngine(dsn=_dsn)
        owner_policy.ensure_tables()
        confusion_handler = ConfusionHandler()
        logger.info("Production modules initialized: teaching_pipeline, knowledge_lifecycle, owner_policy, confusion_handler")
    except Exception as e:
        logger.warning(f"Production module init failed (non-fatal): {e}")

    # Start Ollama pre-warm background task
    asyncio.create_task(_ollama_prewarm_loop())


_ollama_busy = False  # Guard to prevent prewarm during active requests


async def _ollama_prewarm_loop():
    """Ping Ollama every 2 minutes with a tiny prompt to keep the model loaded in RAM.
    Prevents cold-start delays on the memory-constrained VPS."""
    await asyncio.sleep(5)  # let startup finish
    while True:
        if _ollama_busy:
            logger.debug("Ollama pre-warm: skipped, request in-flight")
        else:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        f"{settings.ollama_url}/api/chat",
                        json={
                            "model": settings.ollama_model,
                            "messages": [{"role": "user", "content": "hi"}],
                            "stream": False,
                            "options": {"num_predict": 1},
                        },
                    )
                    if resp.status_code == 200:
                        logger.debug("Ollama pre-warm: model kept hot")
                    else:
                        logger.warning(f"Ollama pre-warm: status {resp.status_code}")
            except Exception as e:
                logger.warning(f"Ollama pre-warm failed: {e}")
        await asyncio.sleep(120)  # every 2 minutes

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://fazle.iamazim.com,https://iamazim.com").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Default system prompt — used as fallback when no user context is provided
DEFAULT_SYSTEM_PROMPT = """You are Fazle, a personal AI assistant for Azim. You are intelligent, direct, and helpful.

Your capabilities:
- Remember personal preferences, contacts, and important information
- Make decisions about calls and meetings based on stored preferences
- Search the internet for information when needed
- Schedule tasks and reminders
- Learn from conversations to improve over time

Key personality traits:
- Professional but warm
- Proactive — anticipate needs
- Concise and clear in responses
- Respects user privacy
- Always honest about uncertainty

When the user says "Fazle, remember..." — extract the information and store it.
When making decisions about calls, always check stored preferences first.

Respond in JSON with these fields:
- "reply": your spoken/text response
- "memory_updates": array of objects to store (each with "type", "content", "text")
- "actions": array of actions to take (each with "type" and relevant fields)
"""


# ── LLM Failover Constants ────────────────────────────────────
_LLM_TIMEOUT_GATEWAY = 20.0    # Gateway: 20s
_LLM_TIMEOUT_OPENAI = 5.0     # Direct OpenAI: 5s per-provider cap
_LLM_TIMEOUT_OLLAMA = 50.0    # Local Ollama: 50s (handles cold-start + larger prompts on CPU)
_LLM_TIMEOUT_FAST = 8.0       # Fast model fallback: 8s cap
_LLM_PARALLEL_GLOBAL = 55.0   # Global parallel timeout: 55s max total

_FALLBACK_REPLY_BN = "দুঃখিত, একটু সমস্যা হয়েছে। আবার বলবেন?"
_FALLBACK_REPLY_EN = "Sorry, having a small issue. Please try again shortly."


# ── FIX 3: Identity hard override — instant answers, no LLM needed ──
_IDENTITY_PATTERNS = [
    "তুমি কে", "আপনি কে", "তুই কে", "who are you", "what are you",
    "তোমার নাম কি", "আপনার নাম কি", "তোমার পরিচয়", "আপনার পরিচয়",
    "your name", "introduce yourself", "নিজের পরিচয় দাও", "পরিচয় দিন",
    "পরিচয় দাও", "তুমি কি ai", "are you ai", "are you a bot",
    "তুমি কি রোবট", "তুমি কি বট",
]

_IDENTITY_REPLY = (
    "আমি ফজলে আজিম, আল-আকসা সিকিউরিটি সার্ভিস এর পরিচালক। "
    "কিভাবে সাহায্য করতে পারি?"
)


def _check_identity_override(message: str) -> str | None:
    """Return instant identity reply if the message is an identity question."""
    msg = message.strip().lower()
    for pattern in _IDENTITY_PATTERNS:
        if pattern in msg:
            return _IDENTITY_REPLY
    return None


# ── FIX 9: Human response filter ──
def _humanize_reply(reply: str) -> str:
    """Remove robotic phrases and ensure natural Bangla tone."""
    import re
    # Remove common AI-isms
    _ROBOTIC = [
        "Certainly!", "Of course!", "Absolutely!", "Sure thing!",
        "I'd be happy to help", "I'm here to help", "Great question!",
        "That's a great question", "Let me help you with that",
        "I understand your concern", "Thank you for reaching out",
        "How can I assist you today",
    ]
    for phrase in _ROBOTIC:
        reply = reply.replace(phrase, "").replace(phrase.lower(), "")
    # Clean up whitespace
    reply = re.sub(r'\n{3,}', '\n\n', reply)
    reply = reply.strip()
    return reply


async def query_openai(messages: list[dict]) -> dict:
    """Call OpenAI API for reasoning (direct, used as fallback)."""
    async with httpx.AsyncClient(timeout=_LLM_TIMEOUT_OPENAI) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.llm_model,
                "messages": messages,
                "temperature": 0.7,
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return json.loads(data["choices"][0]["message"]["content"])


async def query_ollama(messages: list[dict]) -> dict:
    """Call local Ollama LLM for reasoning (direct, used as fallback)."""
    global _ollama_busy
    _ollama_busy = True
    try:
      async with httpx.AsyncClient(timeout=_LLM_TIMEOUT_OLLAMA) as client:
        resp = await client.post(
            f"{settings.ollama_url}/api/chat",
            json={
                "model": settings.ollama_model,
                "messages": messages,
                "stream": False,
                "options": {"num_predict": 50},
            },
        )
        resp.raise_for_status()
        data = resp.json()
        # Log Ollama performance metrics
        _pec = data.get("prompt_eval_count", 0)
        _ec = data.get("eval_count", 0)
        _ed = data.get("eval_duration", 0) / 1e9
        _td = data.get("total_duration", 0) / 1e9
        _ld = data.get("load_duration", 0) / 1e9
        _tps = _ec / _ed if _ed > 0 else 0
        _msg_sizes = [len(m.get("content", "")) for m in messages]
        logger.info(
            f"Ollama perf: prompt_tok={_pec} eval_tok={_ec} eval={_ed:.1f}s "
            f"tok/s={_tps:.1f} total={_td:.1f}s load={_ld:.2f}s msg_chars={_msg_sizes}"
        )
        content = data["message"]["content"]
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return {"reply": content.strip(), "memory_updates": [], "actions": []}
    finally:
        _ollama_busy = False


async def query_gateway(messages: list[dict]) -> dict:
    """Call LLM Gateway for centralized routing, caching, and fallback."""
    async with httpx.AsyncClient(timeout=_LLM_TIMEOUT_GATEWAY) as client:
        resp = await client.post(
            f"{settings.llm_gateway_url}/generate",
            json={
                "messages": messages,
                "response_format": "json",
                "caller": "fazle-brain",
                "temperature": 0.7,
            },
        )
        resp.raise_for_status()
        return json.loads(resp.json()["content"])


async def query_llm(messages: list[dict]) -> dict:
    """Route to LLM Gateway (preferred) or direct provider (fallback)."""
    if settings.use_llm_gateway:
        try:
            return await query_gateway(messages)
        except Exception as e:
            logger.warning(f"LLM Gateway unavailable, falling back to direct: {e}")
    if settings.llm_provider == "ollama":
        return await query_ollama(messages)
    return await query_openai(messages)


async def query_llm_voice(messages: list[dict]) -> dict:
    """Voice-optimized LLM call: direct Ollama (fast), bypass gateway."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.ollama_url}/api/chat",
                json={
                    "model": settings.voice_ollama_model,
                    "messages": messages,
                    "stream": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["message"]["content"]
            try:
                return json.loads(content)
            except (json.JSONDecodeError, TypeError):
                return {"reply": content.strip(), "memory_updates": [], "actions": []}
    except Exception as e:
        logger.warning(f"Voice fast Ollama failed, falling back to gateway: {e}")
        return await query_llm(messages)


async def stream_llm_voice(messages: list[dict]):
    """Voice-optimized SSE streaming: direct Ollama, yields text chunks."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{settings.ollama_url}/api/chat",
                json={
                    "model": settings.voice_ollama_model,
                    "messages": messages,
                    "stream": True,
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.strip():
                        data = json.loads(line)
                        chunk = data.get("message", {}).get("content", "")
                        done = data.get("done", False)
                        yield json.dumps({"content": chunk, "done": done}) + "\n"
                        if done:
                            break
    except Exception as e:
        logger.error(f"Voice stream failed: {e}")
        yield json.dumps({"content": "", "done": True, "error": str(e)}) + "\n"


async def stream_llm_gateway(messages: list[dict]):
    """Stream from LLM Gateway SSE endpoint, yields text chunks."""
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{settings.llm_gateway_url}/generate",
                json={
                    "messages": messages,
                    "caller": "fazle-brain-stream",
                    "temperature": 0.7,
                    "stream": True,
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        chunk_str = line[6:].strip()
                        if chunk_str == "[DONE]":
                            yield json.dumps({"content": "", "done": True}) + "\n"
                            break
                        try:
                            chunk_data = json.loads(chunk_str)
                            delta = chunk_data.get("choices", [{}])[0].get("delta", {})
                            text = delta.get("content", "")
                            yield json.dumps({"content": text, "done": False}) + "\n"
                        except (json.JSONDecodeError, IndexError, KeyError):
                            yield json.dumps({"content": chunk_str, "done": False}) + "\n"
    except Exception as e:
        logger.error(f"Gateway stream failed: {e}")
        yield json.dumps({"content": "", "done": True, "error": str(e)}) + "\n"


# ── Human Presence Engine ────────────────────────────────────
import random as _random

def _compute_presence(message: str, reply: str, complexity: str, relationship: str) -> dict:
    """Compute human-like presence metadata for response.
    Returns suggested delays + tone energy for the client to apply.
    Server does NOT block — client decides whether to use delays."""
    msg_len = len(message)
    reply_len = len(reply)
    reply_words = len(reply.split())

    # Typing delay: simulates human typing speed (~40-80 WPM, ~50-150ms per char)
    # Faster for simple/short, slower for complex/long
    base_typing_ms = reply_words * _random.randint(60, 120)  # per word
    if complexity == "simple":
        base_typing_ms = min(base_typing_ms, 1500)
    elif complexity == "complex":
        base_typing_ms = min(base_typing_ms, 5000)
    else:
        base_typing_ms = min(base_typing_ms, 3000)

    # Response delay: "thinking time" before typing starts
    if complexity == "simple":
        response_delay_ms = _random.randint(200, 800)
    elif complexity == "complex":
        response_delay_ms = _random.randint(1500, 3500)
    else:
        response_delay_ms = _random.randint(500, 1800)

    # Owner gets slightly faster responses
    if relationship in ("self",):
        response_delay_ms = int(response_delay_ms * 0.5)
        base_typing_ms = int(base_typing_ms * 0.7)

    # Tone energy based on content signals
    energy = "medium"
    msg_lower = message.lower()
    if any(w in msg_lower for w in ["urgent", "emergency", "help", "জরুরি", "সাহায্য"]):
        energy = "high"
        response_delay_ms = min(response_delay_ms, 500)
    elif any(w in msg_lower for w in ["thanks", "bye", "ok", "ধন্যবাদ", "ঠিক আছে"]):
        energy = "low"
    elif complexity == "complex" or len(message) > 200:
        energy = "high"

    return {
        "typing_delay_ms": base_typing_ms,
        "response_delay_ms": response_delay_ms,
        "tone_energy": energy,
    }


# ── Intelligence Tuning Layer ────────────────────────────────

# STEP 3: Fast Response Path — classify query complexity
_SIMPLE_PATTERNS = {
    "hi", "hello", "hey", "yo", "sup", "assalamu alaikum", "salam",
    "ok", "okay", "thanks", "thank you", "bye", "good", "nice",
    "yes", "no", "yeah", "nah", "haha", "lol", "hmm",
    "কেমন আছো", "কি খবর", "ভালো", "হ্যাঁ", "না", "ধন্যবাদ",
    "good morning", "good night", "good evening",
}

def _classify_query_complexity(message: str) -> str:
    """Classify query as 'simple', 'medium', or 'complex'.
    Simple: greetings, yes/no, short acknowledgments → fast path.
    Medium: single questions, factual lookups → standard model.
    Complex: multi-part, reasoning, analysis → full model."""
    msg = message.strip().lower()
    # Ultra-simple: greeting or acknowledgment
    if msg in _SIMPLE_PATTERNS or len(msg) < 8:
        return "simple"
    words = msg.split()
    # Short messages (fewer than 6 words) without complex indicators
    if len(words) <= 5:
        complex_indicators = {"explain", "analyze", "compare", "why", "how does", "difference", "বিশ্লেষণ", "ব্যাখ্যা"}
        if not any(ind in msg for ind in complex_indicators):
            return "simple"
    # Complex indicators
    if len(words) > 30 or msg.count("?") > 1 or msg.count("\n") > 2:
        return "complex"
    complex_words = {"explain", "analyze", "compare", "detailed", "step by step", "pros and cons",
                     "architecture", "design", "strategy", "plan", "debug", "optimize",
                     "বিশ্লেষণ", "ব্যাখ্যা", "বিস্তারিত", "পরিকল্পনা"}
    if any(w in msg for w in complex_words):
        return "complex"
    return "medium"


# STEP 4: Cost-aware LLM routing with failover
import time as _time


async def query_llm_smart(messages: list[dict], complexity: str = "medium") -> dict:
    """FIX 5: Ollama-first LLM routing with parallel fallback.
    Fires Ollama + Gateway simultaneously. OpenAI only if key configured.
    Global timeout: 12s. Falls back to fast model, then static Bangla reply."""
    model_override = None
    route_label = "full"

    if complexity == "simple":
        model_override = None  # FIX 5: Use Ollama default model, not gpt-4o-mini
        route_label = "fast"
    elif complexity == "complex":
        model_override = settings.llm_model
        route_label = "complex"

    t0 = _time.monotonic()

    # FIX 5: Ollama is priority 0 (preferred), gateway secondary, OpenAI last
    _PRIORITY = {"ollama": 0, "gateway": 1, "openai_direct": 2}

    # ── Build provider coroutines ──
    async def _provider_gateway():
        return await _query_gateway_with_model(messages, model_override)

    async def _provider_openai():
        return await _query_openai_with_model(messages, model_override)

    async def _provider_ollama():
        return await query_ollama(messages)

    # FIX 5: Ollama first, then gateway, then OpenAI
    providers: list[tuple[str, asyncio.Task]] = []
    providers.append(("ollama", asyncio.create_task(_provider_ollama())))
    if settings.use_llm_gateway:
        providers.append(("gateway", asyncio.create_task(_provider_gateway())))
    # OpenAI disabled — API key is 429-blocked, wastes ~1s per request
    # if settings.openai_api_key:
    #     providers.append(("openai_direct", asyncio.create_task(_provider_openai())))

    task_to_name: dict[asyncio.Task, str] = {t: n for n, t in providers}
    pending = {t for _, t in providers}
    failed_providers: list[str] = []
    result = None
    winner = None

    try:
        remaining = _LLM_PARALLEL_GLOBAL
        while pending and result is None:
            done, pending = await asyncio.wait(
                pending, timeout=remaining, return_when=asyncio.FIRST_COMPLETED
            )
            elapsed_now = _time.monotonic() - t0
            remaining = max(0, _LLM_PARALLEL_GLOBAL - elapsed_now)

            # ── Evaluate completed tasks, pick best by priority ──
            candidates: list[tuple[int, str, dict]] = []
            for task in done:
                name = task_to_name[task]
                if task.exception() is not None:
                    ex = task.exception()
                    logger.warning(f"LLM parallel: {name}_fail in {elapsed_now:.2f}s err={ex}")
                    failed_providers.append(name)
                else:
                    candidates.append((_PRIORITY.get(name, 99), name, task.result()))

            if candidates:
                candidates.sort(key=lambda c: c[0])  # best priority first
                _, winner, result = candidates[0]

            # ── Fast fail: if all done and none succeeded, stop early ──
            if not pending and result is None:
                break

            if remaining <= 0:
                break
    except Exception as e:
        logger.error(f"LLM parallel orchestration error: {e}")
    finally:
        # ── Cancel all remaining tasks ──
        cancelled_names = []
        for task in pending:
            task.cancel()
            cancelled_names.append(task_to_name[task])
        # Also cancel any non-winner from done set
        for _, t in providers:
            if not t.done():
                t.cancel()

    elapsed = _time.monotonic() - t0

    if result is not None:
        intel_usage_track(model_override or settings.llm_model, route=f"{route_label}_{winner}")
        logger.info(
            f"LLM OK via {winner} in {elapsed:.2f}s | "
            f"cancelled={cancelled_names} failed={failed_providers} route={route_label}"
        )
        return result

    # ── All parallel providers failed — try fast model if Ollama wasn't already tried ──
    deadline_left = _LLM_PARALLEL_GLOBAL - (_time.monotonic() - t0)
    if "ollama" in failed_providers:
        # Ollama backend is down — fast_model (same backend) would also fail
        logger.warning(
            f"LLM parallel ALL FAILED in {elapsed:.2f}s failed={failed_providers} — "
            f"skipping fast_model (ollama already failed)"
        )
    elif deadline_left > 0.5:
        logger.warning(
            f"LLM parallel ALL FAILED in {elapsed:.2f}s failed={failed_providers} — trying fast_model"
        )
        try:
            result = await asyncio.wait_for(
                _query_fast_model_fallback(messages), timeout=min(deadline_left, _LLM_TIMEOUT_FAST)
            )
            elapsed = _time.monotonic() - t0
            intel_usage_track(settings.voice_fast_model, route="emergency_fast")
            logger.info(f"LLM OK via fast_model in {elapsed:.2f}s after parallel failure")
            return result
        except Exception as e:
            failed_providers.append("fast_model")
            elapsed = _time.monotonic() - t0
            logger.error(f"LLM fast_model also failed in {elapsed:.2f}s err={e}")
    else:
        logger.warning(
            f"LLM parallel ALL FAILED in {elapsed:.2f}s — no time left for fast_model"
        )

    # ── Static fallback — return empty so /chat endpoint detects failure ──
    intel_usage_track("static_fallback", route="emergency_static")
    logger.error(f"LLM ALL PROVIDERS FAILED — returning empty reply for fallback. chain={failed_providers}")
    return {
        "reply": "",
        "memory_updates": [],
        "actions": [],
    }


async def _query_gateway_with_model(messages: list[dict], model: str = None) -> dict:
    """Call LLM Gateway with optional model override."""
    payload = {
        "messages": messages,
        "caller": "fazle-brain",
        "temperature": 0.7,
    }
    if model:
        payload["model"] = model
    async with httpx.AsyncClient(timeout=_LLM_TIMEOUT_GATEWAY) as client:
        resp = await client.post(f"{settings.llm_gateway_url}/generate", json=payload)
        resp.raise_for_status()
        content = resp.json()["content"]
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return {"reply": content.strip(), "memory_updates": [], "actions": []}


async def _query_openai_with_model(messages: list[dict], model: str = None) -> dict:
    """Direct OpenAI call with optional model override. 8s hard timeout."""
    use_model = model or settings.llm_model
    async with httpx.AsyncClient(timeout=_LLM_TIMEOUT_OPENAI) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": use_model,
                "messages": messages,
                "temperature": 0.7,
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return json.loads(data["choices"][0]["message"]["content"])


async def _query_fast_model_fallback(messages: list[dict]) -> dict:
    """Emergency fallback: use the tiny fast model (qwen2.5:0.5b) via Ollama."""
    async with httpx.AsyncClient(timeout=_LLM_TIMEOUT_FAST) as client:
        resp = await client.post(
            f"{settings.ollama_url}/api/chat",
            json={
                "model": settings.voice_fast_model,
                "messages": messages,
                "stream": False,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["message"]["content"]
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return {"reply": content.strip(), "memory_updates": [], "actions": []}


# STEP 1: Question Strategy — confidence-aware response
_UNCERTAINTY_MARKERS = [
    "i'm not sure", "i think", "maybe", "possibly", "i believe",
    "i don't know", "not certain", "might be", "could be",
    "আমি নিশ্চিত না", "হয়তো", "মনে হয়", "জানি না",
]

def _detect_low_confidence(reply: str) -> bool:
    """Detect if the LLM reply shows uncertainty markers."""
    reply_lower = reply.lower()
    markers_found = sum(1 for m in _UNCERTAINTY_MARKERS if m in reply_lower)
    return markers_found >= 2


# STEP 2: Owner Priority Interrupt
async def _check_owner_priority(relationship: str) -> bool:
    """If owner is active, non-owner requests get deprioritized."""
    if relationship in ("self",):
        # Owner sets priority
        intel_owner_priority_set(True)
        return False  # Owner is never blocked
    # Non-owner: check if owner has active priority
    if intel_owner_priority_active():
        await asyncio.sleep(0.5)  # Brief yield to let owner requests go first
    return False  # Never fully block, just deprioritize


# Minimal system prompt for ultra-fast voice path (no JSON, no tools)
FAST_VOICE_PROMPT = (
    "You are Azim's AI assistant. Respond naturally in 1-2 sentences. "
    "Be concise, warm, and direct. Plain text only."
)


async def stream_ollama_fast(prompt: str):
    """Ultra-fast Ollama streaming via /api/generate — skips chat overhead."""
    try:
        client = _get_fast_client()
        async with client.stream(
            "POST",
            "/api/generate",
            json={
                "model": settings.voice_fast_model,
                "prompt": prompt,
                "system": FAST_VOICE_PROMPT,
                "stream": True,
                "options": {"num_ctx": 512, "num_predict": 40},
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.strip():
                    data = json.loads(line)
                    chunk = data.get("response", "")
                    done = data.get("done", False)
                    yield json.dumps({"content": chunk, "done": done}) + "\n"
                    if done:
                        break
    except Exception as e:
        logger.error(f"Fast Ollama stream failed, falling back to gateway: {e}")
        # Fallback: use gateway with minimal messages
        messages = [
            {"role": "system", "content": FAST_VOICE_PROMPT},
            {"role": "user", "content": prompt},
        ]
        async for chunk in stream_llm_gateway(messages):
            yield chunk


async def retrieve_memories(query: str, memory_type: Optional[str] = None, user_id: Optional[str] = None, limit: int = 5) -> list[dict]:
    """Retrieve relevant memories from memory service, optionally filtered by user."""
    body: dict = {"query": query, "memory_type": memory_type, "limit": limit}
    if user_id:
        body["user_id"] = user_id
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{settings.memory_url}/search",
                json=body,
            )
            if resp.status_code == 200:
                return resp.json().get("results", [])
        except Exception as e:
            logger.warning(f"Memory retrieval failed: {e}")
    return []


async def retrieve_multimodal_memories(query: str, user_id: Optional[str] = None, limit: int = 3) -> list[dict]:
    """Retrieve relevant multimodal memories (images, documents with images)."""
    body: dict = {"query": query, "limit": limit}
    if user_id:
        body["user_id"] = user_id
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{settings.memory_url}/search-multimodal",
                json=body,
            )
            if resp.status_code == 200:
                return resp.json().get("results", [])
        except Exception as e:
            logger.warning(f"Multimodal memory retrieval failed: {e}")
    return []


def _format_memory_context(text_memories: list[dict], multimodal_memories: list[dict]) -> str:
    """Format text and multimodal memories into prompt context."""
    parts = []
    if text_memories:
        parts.append("\nRelevant memories:")
        for m in text_memories:
            parts.append(f"- {m.get('text', str(m.get('content', '')))}")
    if multimodal_memories:
        parts.append("\nRelevant images in memory:")
        for m in multimodal_memories:
            caption = m.get("caption", m.get("text", ""))
            fname = m.get("original_filename", "")
            label = f" ({fname})" if fname else ""
            parts.append(f"<image>{caption}{label}</image>")
    return "\n".join(parts) if parts else ""


async def store_memory_updates(updates: list[dict], user_id: Optional[str] = None, user_name: str = "Azim"):
    """Store memory updates extracted by the LLM."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        for update in updates:
            try:
                body = {
                    "type": update.get("type", "personal"),
                    "user": user_name,
                    "content": update.get("content", {}),
                    "text": update.get("text", str(update.get("content", ""))),
                }
                if user_id:
                    body["user_id"] = user_id
                await client.post(
                    f"{settings.memory_url}/store",
                    json=body,
                )
            except Exception as e:
                logger.warning(f"Memory store failed: {e}")


async def execute_actions(actions: list[dict]):
    """Execute actions decided by the brain."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        for action in actions:
            action_type = action.get("type", "")
            try:
                if action_type == "web_search":
                    await client.post(
                        f"{settings.tools_url}/search",
                        json={"query": action.get("query", ""), "max_results": 5},
                    )
                elif action_type == "create_task":
                    await client.post(
                        f"{settings.task_url}/tasks",
                        json={
                            "title": action.get("title", ""),
                            "description": action.get("description", ""),
                            "scheduled_at": action.get("scheduled_at"),
                            "task_type": action.get("task_type", "reminder"),
                        },
                    )
            except Exception as e:
                logger.warning(f"Action execution failed ({action_type}): {e}")


# ── Health ──────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "fazle-brain", "timestamp": datetime.utcnow().isoformat()}


# ── Owner Control Plane Status ──────────────────────────────
@app.get("/control-plane/status")
async def control_plane_status():
    """Phase 2 — return command taxonomy + capability matrix + lifecycle info."""
    from owner_control.command_taxonomy import taxonomy_summary, OWNER_COMMANDS
    from owner_control.capability_matrix import matrix_summary, CAPABILITIES
    return {
        "phase": 2,
        "features": {
            "1A_command_taxonomy": True,
            "1B_knowledge_governance": True,
            "1C_capability_matrix": True,
            "2A_owner_query_apis": True,
            "2B_user_rules": True,
            "2C_knowledge_lifecycle": True,
            "2D_governance_injection": True,
        },
        "taxonomy": taxonomy_summary(),
        "capabilities": matrix_summary(),
        "commands": {k: {"category": v.category.value, "risk": v.risk.value,
                         "enforcement": v.enforcement.value}
                     for k, v in OWNER_COMMANDS.items()},
    }


# ── Decision endpoint (called by Fazle API for Dograh) ──────
class DecisionRequest(BaseModel):
    caller: str
    intent: str
    conversation_context: str = ""
    metadata: dict = Field(default_factory=dict)


@app.post("/decide")
async def decide(request: DecisionRequest):
    """Make a decision for a voice call interaction."""
    # Retrieve relevant memories about the caller and intent
    caller_memories = await retrieve_memories(f"caller {request.caller}")
    intent_memories = await retrieve_memories(f"{request.intent} preferences")

    memory_context = ""
    if caller_memories or intent_memories:
        all_memories = caller_memories + intent_memories
        memory_context = "\n\nRelevant memories:\n" + "\n".join(
            f"- {m.get('text', str(m.get('content', '')))}" for m in all_memories
        )

    messages = [
        {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"A call decision is needed.\n"
                f"Caller: {request.caller}\n"
                f"Intent: {request.intent}\n"
                f"Context: {request.conversation_context}\n"
                f"{memory_context}\n\n"
                f"Provide your decision as JSON with 'reply', 'memory_updates', and 'actions'."
            ),
        },
    ]

    try:
        result = await query_llm(messages)
    except Exception as e:
        logger.error(f"LLM error: {e}")
        raise HTTPException(status_code=502, detail="LLM service unavailable")

    reply = result.get("reply", "I'll need to get back to you on that.")
    memory_updates = result.get("memory_updates", [])
    actions = result.get("actions", [])

    # Process side effects
    if memory_updates:
        await store_memory_updates(memory_updates)
    if actions:
        await execute_actions(actions)

    return {
        "response": reply,
        "confidence": 0.9,
        "actions": actions,
        "memory_updates": memory_updates,
    }


# ── Voice Call Chat endpoint ────────────────────────────────
class VoiceChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    relationship: Optional[str] = None
    history: list[dict] = Field(default_factory=list)


@app.post("/chat/voice")
async def chat_voice(request: VoiceChatRequest):
    """Voice-call-optimized chat endpoint.

    Returns plain text reply (no JSON structure) with voice-specific
    persona prompt. Uses memory retrieval but skips content moderation
    for latency. Designed for VoiceBrainManager integration.
    """
    from persona_engine import build_voice_system_prompt

    conversation_id = request.conversation_id or str(uuid.uuid4())
    user_name = request.user_name or "User"
    relationship = request.relationship or "social"
    user_id = request.user_id

    # Build voice-optimized system prompt + memory in parallel
    prompt_task = build_voice_system_prompt(
        user_name=user_name,
        relationship=relationship,
        user_id=user_id,
        learning_engine_url=settings.learning_engine_url,
    )
    mem_task = retrieve_memories(request.message, user_id=user_id, limit=2)

    system_prompt, memories = await asyncio.gather(prompt_task, mem_task)

    memory_context = ""
    if memories:
        memory_context = "\n\nRelevant memories:\n" + "\n".join(
            f"- {m.get('text', str(m.get('content', '')))}" for m in memories[:2]
        )

    # ── User-scoped history for voice calls ─────────────────
    voice_platform = "voice"
    voice_user_id = user_id or conversation_id
    voice_user_history = user_history_get(voice_platform, voice_user_id, limit=6)
    voice_history_ctx = build_user_history_context(voice_user_history)
    voice_recent = user_replies_get(voice_platform, voice_user_id, limit=3)
    voice_anti_rep = build_anti_repetition_context(voice_recent)

    # Use provided history or fetch from Redis
    history = request.history or conversation_get(conversation_id)

    # ── Voice: Knowledge context injection ──
    voice_knowledge_ctx = ""
    try:
        voice_knowledge_ctx = await build_knowledge_context(
            message=request.message,
            caller_id=user_id or voice_user_id,
            api_url="http://fazle-api:8100",
        )
        if voice_knowledge_ctx:
            logger.info(f"Voice knowledge context: {len(voice_knowledge_ctx)} chars")
    except Exception:
        pass

    # ── Voice Agent: identity enforcement via strategy ──
    voice_system_prompt = system_prompt + voice_knowledge_ctx + memory_context + voice_history_ctx + voice_anti_rep
    if agent_manager:
        ctx = AgentContext(
            message=request.message,
            user_name=user_name,
            user_id=user_id,
            relationship=relationship,
            conversation_id=conversation_id,
            metadata={"source": "voice"},
        )
        try:
            domain_result = await agent_manager.process_domain(ctx)
            domain_prompt = domain_result.get("system_prompt")
            if domain_prompt:
                voice_system_prompt = domain_prompt + voice_knowledge_ctx + memory_context + voice_history_ctx + voice_anti_rep
            else:
                identity_prompt = domain_result.get("identity_prompt", "")
                if identity_prompt:
                    voice_system_prompt = identity_prompt + "\n" + voice_system_prompt
        except Exception as e:
            logger.debug(f"Voice domain routing skipped: {e}")

    messages = [
        {"role": "system", "content": voice_system_prompt},
        *history[-6:],
        {"role": "user", "content": request.message},
    ]

    # Use voice-optimized LLM path (direct Ollama for speed)
    try:
        if settings.voice_fast_mode or not settings.use_llm_gateway:
            # Direct Ollama — fastest path
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{settings.ollama_url}/api/chat",
                    json={
                        "model": settings.voice_ollama_model,
                        "messages": messages,
                        "stream": False,
                        "options": {"num_ctx": 1024, "num_predict": 60},
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                reply = data["message"]["content"].strip()
        else:
            # Gateway path — with fallback
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{settings.llm_gateway_url}/generate",
                    json={
                        "messages": messages,
                        "caller": "fazle-brain-voice",
                        "temperature": 0.7,
                        "max_tokens": 80,
                    },
                )
                resp.raise_for_status()
                reply = resp.json().get("content", "").strip()
    except Exception as e:
        logger.error(f"Voice LLM failed: {e}")
        reply = "দুঃখিত, একটু সমস্যা হচ্ছে। আবার বলবেন?"

    # Update conversation history in Redis
    history.append({"role": "user", "content": request.message})
    history.append({"role": "assistant", "content": reply})
    conversation_set(conversation_id, history)

    # Track user-scoped voice history
    user_history_append(voice_platform, voice_user_id, "user", request.message)
    user_history_append(voice_platform, voice_user_id, "assistant", reply)
    user_replies_track(voice_platform, voice_user_id, reply)

    # Async learning (fire-and-forget)
    try:
        async with httpx.AsyncClient(timeout=5.0) as learn_client:
            await learn_client.post(
                f"{settings.learning_engine_url}/learn",
                json={
                    "transcript": f"{user_name}: {request.message}\nAzim: {reply}",
                    "user": user_name,
                    "conversation_id": conversation_id,
                },
            )
    except Exception:
        pass

    return {"reply": reply, "conversation_id": conversation_id}


# ── System Governor v2 — Response Scoring ────────────────────

async def _governor_score_response(message: str, reply: str, relationship: str, user_name: str):
    """Score response for identity alignment and quality (fire-and-forget)."""
    try:
        profile = azim_profile_all()
        profile_summary = "; ".join(f"{k}={v}" for k, v in profile.items()) if profile else "no profile"

        prompt = (
            f"Rate this AI response on two dimensions.\n"
            f"Owner Identity Profile: {profile_summary}\n"
            f"User relationship: {relationship}\n"
            f"User message: {message[:300]}\n"
            f"AI reply: {reply[:500]}\n\n"
            f"Return JSON only:\n"
            f'{{"identity_alignment": 0.0-1.0, "quality": 0.0-1.0, "issues": "brief note or empty"}}\n'
            f"identity_alignment: How well does reply match owner personality, style, knowledge?\n"
            f"quality: relevance, correctness, helpfulness of the reply."
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{settings.llm_gateway_url}/generate",
                json={
                    "messages": [
                        {"role": "system", "content": "You are a response quality evaluator. Return ONLY valid JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "caller": "fazle-governor",
                },
            )
            resp.raise_for_status()
            raw = resp.json().get("content", resp.json().get("response", "{}"))

        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
        data = json.loads(raw.strip())

        identity_score = max(0.0, min(1.0, float(data.get("identity_alignment", 0.7))))
        quality_score = max(0.0, min(1.0, float(data.get("quality", 0.7))))
        issues = str(data.get("issues", ""))

        governor_quality_score_push(quality_score, {"relationship": relationship, "user": user_name})
        governor_identity_score_push(identity_score, issues)

        if identity_score < 0.5:
            governor_drift_alert(f"Low identity alignment ({identity_score:.2f}) for {relationship}: {issues}")
        if quality_score < 0.4:
            governor_error_log("low_quality", f"Quality {quality_score:.2f}: {issues}")

    except Exception as e:
        logger.debug(f"Governor scoring skipped: {e}")


async def _governor_validate_learning_check(knowledge: str, field: str = "") -> bool:
    """Check new knowledge against azim_profile. Returns True if valid."""
    if governor_safe_mode_get():
        logger.info("Governor safe mode: learning validation stricter")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.autonomy_engine_url}/governor/validate-learning",
                json={"knowledge": knowledge, "field": field},
            )
            if resp.status_code == 200:
                result = resp.json()
                return result.get("valid", True)
    except Exception:
        pass
    return True


# ── Chat endpoint ───────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    user: str = "Azim"
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    relationship: Optional[str] = None
    context: Optional[str] = None
    ack_sent: bool = False  # True when caller already sent an instant ACK (e.g. WhatsApp)


@app.post("/chat")
async def chat(request: ChatRequest):
    """Interactive chat with Fazle."""
    conversation_id = request.conversation_id or str(uuid.uuid4())

    # Determine user context for persona
    user_name = request.user_name or request.user or "Azim"
    relationship = request.relationship or "self"
    user_id = request.user_id

    # ── FIX 3: Identity hard override — instant, no LLM ──
    identity_reply = _check_identity_override(request.message)
    if identity_reply:
        logger.info(f"Identity override triggered for: {request.message[:60]}")
        return {
            "reply": identity_reply,
            "conversation_id": conversation_id,
            "memory_updates": [],
            "route": "identity_override",
            "presence": {"typing_delay_ms": 0, "response_delay_ms": 0, "tone_energy": "high"},
        }

    # ── Phase 3: Full Intent Detection System (social only) ──
    # 8-step flow: classify → intent match → negative filter → context → reply
    if relationship == "social":
        intent_reply = process_social_intent(request.message, conversation_id)
        if intent_reply:
            # ── Lead Capture ──
            intent_state = _get_intent_state(conversation_id)
            matched_intent = intent_state.get("last_intent")
            intent_reply = await try_capture_lead(
                request.message, matched_intent, conversation_id, intent_reply,
            )
            logger.info(f"Intent engine → {intent_reply[:50]} for: {request.message[:60]}")
            return {
                "reply": intent_reply,
                "conversation_id": conversation_id,
                "memory_updates": [],
                "route": "intent_engine",
                "presence": {"typing_delay_ms": 200, "response_delay_ms": 100, "tone_energy": "medium"},
            }

    # Cache LLM reply for non-social repeated queries
    _reply_cache_key = None

    # ── STEP 2: Owner Priority Interrupt ──
    await _check_owner_priority(relationship)

    # ── STEP 3: Fast Response Path ──
    complexity = _classify_query_complexity(request.message)

    # Ultra-simple queries: skip heavy pipeline entirely
    if complexity == "simple" and relationship in ("self", "wife", "parent", "sibling"):
        history = conversation_get(conversation_id)
        fast_prompt = (
            "You are Azim. Respond naturally in 1-2 short sentences. Be warm and direct. "
            "Use your natural speech: 'bro', 'haha', 'wallah'. Respond in JSON: {\"reply\": \"...\", \"memory_updates\": [], \"actions\": []}"
        )
        fast_messages = [
            {"role": "system", "content": fast_prompt},
            *history[-4:],
            {"role": "user", "content": request.message},
        ]
        try:
            result = await query_llm_smart(fast_messages, complexity="simple")
            reply = result.get("reply", "yo 👋")
            reply = _humanize_reply(reply)
            history.append({"role": "user", "content": request.message})
            history.append({"role": "assistant", "content": reply})
            conversation_set(conversation_id, history)
            fast_presence = _compute_presence(request.message, reply, "simple", relationship)
            return {"reply": reply, "conversation_id": conversation_id, "memory_updates": [], "route": "fast", "presence": fast_presence}
        except Exception:
            pass  # Fall through to full pipeline

    # Trusted relationships skip input moderation for speed
    trusted = relationship in ("self", "wife", "parent", "sibling")

    # Phase 6: Skip slow OpenAI moderation for social — use local keyword check
    if not trusted:
        if relationship == "social":
            # Fast local safety: block obvious slurs/threats only
            _blocked_words = ["kill", "bomb", "hack", "মেরে ফেলব", "ধ্বংস"]
            _msg_low = request.message.lower()
            if any(bw in _msg_low for bw in _blocked_words):
                logger.info(f"Input blocked (local) for user={user_name}")
                return {
                    "reply": "দুঃখিত, এই ধরনের বার্তা গ্রহণযোগ্য নয়।",
                    "conversation_id": conversation_id,
                    "memory_updates": [],
                }
        else:
            safety_result = await check_content(
                request.message,
                openai_api_key=settings.openai_api_key,
                relationship=relationship,
            )
            if not safety_result["safe"]:
                logger.info(f"Input blocked for user={user_name} reason={safety_result['reason']}")
                return {
                    "reply": safety_result["blocked_reply"],
                    "conversation_id": conversation_id,
                    "memory_updates": [],
                }

    # Build social context with intent classification for social interactions
    social_context = None
    contact_data = None
    if relationship == "social":
        from persona_engine import classify_social_intent
        intent = classify_social_intent(request.message)
        context_parts = [f"user_intent: {intent}"]
        if request.context:
            context_parts.append(request.context)
        social_context = "\n".join(context_parts)

        # Fetch contact data from social engine for personalized responses
        if conversation_id and conversation_id.startswith("social-"):
            _parts = conversation_id.split("-", 2)
            if len(_parts) >= 3:
                _platform = _parts[1]
                _phone = _parts[2]
                try:
                    async with httpx.AsyncClient(timeout=5.0) as _client:
                        _resp = await _client.get(
                            f"{settings.social_engine_url}/contacts/lookup",
                            params={"phone": _phone, "platform": _platform},
                        )
                        if _resp.status_code == 200:
                            contact_data = _resp.json().get("contact")
                except Exception as _e:
                    logger.debug(f"Contact lookup failed: {_e}")

    # FIX 7+8: Run persona build + memory searches in parallel (limited to 5 items max)
    # NOTE: Memory retrieval skipped — base system_prompt is always >500 chars
    # and we truncate to 500, so appended contexts are always lost. Saves 2-3s.
    system_prompt_task = build_system_prompt_async(
        user_name=user_name,
        relationship=relationship,
        user_id=user_id,
        learning_engine_url=settings.learning_engine_url,
        social_context=social_context,
        contact_data=contact_data,
    )

    system_prompt = await system_prompt_task
    memories = []
    memory_context = ""

    # ── User-scoped conversation intelligence ───────────────
    platform = "app"
    user_identifier = user_id or conversation_id
    if conversation_id and conversation_id.startswith("social-"):
        parts = conversation_id.split("-", 2)
        if len(parts) >= 3:
            platform = parts[1]
            user_identifier = parts[2]

    user_history_context = ""
    anti_rep_context = ""
    awareness_context = ""

    # ── Owner style learning (STEP 6) — skipped, always truncated ──
    owner_style_context = ""

    # ── Knowledge Base context injection ──
    knowledge_context = ""
    try:
        knowledge_context = await build_knowledge_context(
            message=request.message,
            caller_id=user_id or user_identifier,
            caller_role=relationship,
            api_url=f"http://fazle-api:8100",
        )
        if knowledge_context:
            logger.info(f"Knowledge context injected: {len(knowledge_context)} chars, intents={detect_intents(request.message)}")
    except Exception as _kb_err:
        logger.debug(f"Knowledge context fetch skipped: {_kb_err}")

    # Inject context — knowledge_context goes FIRST (highest priority for truncation survival)
    # Then other optional contexts follow
    system_prompt = system_prompt + knowledge_context + memory_context + user_history_context + anti_rep_context + awareness_context + owner_style_context

    # ── Strategy Agent: domain routing + identity enforcement ──
    domain_result = None
    if agent_manager:
        ctx = AgentContext(
            message=request.message,
            user_name=user_name,
            user_id=user_id,
            relationship=relationship,
            conversation_id=conversation_id,
            memories=memories,
            metadata={"source": "text"},
        )
        try:
            domain_result = await agent_manager.process_domain(ctx)
            domain_prompt = domain_result.get("system_prompt")
            logger.debug(f"domain_prompt_len={len(domain_prompt) if domain_prompt else 0}")
            if domain_prompt:
                system_prompt = domain_prompt + knowledge_context + memory_context + user_history_context + anti_rep_context + awareness_context + owner_style_context
            else:
                # Skip identity_prompt for social — BASE_IDENTITY covers it, saves ~450 chars (~6s on CPU)
                if relationship != "social":
                    identity_prompt = domain_result.get("identity_prompt", "")
                    if identity_prompt:
                        system_prompt = identity_prompt + "\n\n" + system_prompt
        except Exception as e:
            logger.debug(f"Domain routing skipped: {e}")

    # FIX 2: FORCE system prompt as first message, always role=system
    # Build conversation history — FIX 7: limit to last 5 turns
    history = conversation_get(conversation_id)
    logger.debug(f"sys_prompt_len={len(system_prompt)} history={len(history)}")

    # Truncate system prompt to prevent Ollama CPU timeout on large prompts
    # Core identity is always preserved even after truncation
    # Phase 7: Lightweight prompt — shorter core identity, tighter limits
    _CORE_IDENTITY = (
        "You are Azim, Al-Aqsa Security (BD). Reply in Bangla. Short, natural, 1-2 sentences. "
        "Use CONVERSATION KNOWLEDGE as reference. Never copy raw text. Never say you're AI."
    )
    _MAX_SYSTEM_CHARS = 800  # Tight limit for fast LLM inference
    if len(system_prompt) > _MAX_SYSTEM_CHARS:
        logger.info(f"System prompt truncated: {len(system_prompt)} -> {_MAX_SYSTEM_CHARS} chars")
        # Keep core identity + as much persona detail as fits
        remaining = _MAX_SYSTEM_CHARS - len(_CORE_IDENTITY) - 2  # 2 for \n\n
        if remaining > 100:
            detail = system_prompt[:remaining]
            last_newline = detail.rfind("\n")
            if last_newline > remaining // 2:
                detail = detail[:last_newline]
            system_prompt = _CORE_IDENTITY + "\n\n" + detail
        else:
            system_prompt = _CORE_IDENTITY

    messages = [
        {"role": "system", "content": system_prompt},
        *history[-3:],
        {"role": "user", "content": request.message},
    ]

    # ── FIX 1+10: Strict response pipeline with retry + logging ──
    t_llm_start = _time.monotonic()
    result = None
    llm_provider_used = "none"
    fallback_triggered = False

    try:
        result = await query_llm_smart(messages, complexity=complexity)
        llm_provider_used = "smart_parallel"
    except Exception as e:
        logger.error(f"LLM attempt 1 failed: {e}")

    # Check if reply is empty/None — retry once with shorter context
    reply_text = result.get("reply", "") if result else ""
    if not reply_text or not reply_text.strip():
        logger.warning("LLM attempt 1 returned empty — retrying with reduced context")
        retry_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.message},
        ]
        try:
            result = await query_llm_smart(retry_messages, complexity="simple")
            llm_provider_used = "smart_retry"
        except Exception as e:
            logger.error(f"LLM attempt 2 also failed: {e}")

    t_llm_end = _time.monotonic()
    llm_elapsed = t_llm_end - t_llm_start

    reply_text = result.get("reply", "") if result else ""
    if reply_text and reply_text.strip():
        reply = reply_text
        memory_updates = result.get("memory_updates", [])
        actions = result.get("actions", [])
    else:
        # ONLY HERE fallback is allowed (FIX 1)
        # Use knowledge-aware fallback for social interactions
        if relationship == "social" and not knowledge_context:
            reply = KNOWLEDGE_FALLBACK_BN
        else:
            reply = _FALLBACK_REPLY_BN
        memory_updates = []
        actions = []
        fallback_triggered = True

    # ── Confusion Handler: detect low-confidence / unclear replies ──
    if fallback_triggered and confusion_handler and relationship == "social":
        try:
            confusion_result = confusion_handler.handle_confusion(
                message=request.message,
                conversation_id=conversation_id,
            )
            if confusion_result.get("reply"):
                reply = confusion_result["reply"]
                logger.info(f"Confusion handler engaged: action={confusion_result.get('action')}")
        except Exception as e:
            logger.debug(f"Confusion handler failed: {e}")

    # FIX 10: Mandatory logging
    logger.info(
        f"LLM RESULT | provider={llm_provider_used} | elapsed={llm_elapsed:.2f}s | "
        f"fallback={'YES' if fallback_triggered else 'NO'} | "
        f"reply_len={len(reply)} | user={user_name} | rel={relationship}"
    )

    # FIX 9: Human response filter
    reply = _humanize_reply(reply)

    # Cache LLM reply for social (so repeat queries are instant)
    if _reply_cache_key and reply and not fallback_triggered:
        set_cached_context(_reply_cache_key, reply)

    # ── STEP 1: Question Strategy — confidence check ──
    if _detect_low_confidence(reply) and relationship in ("self", "wife", "parent", "sibling"):
        reply = reply.rstrip(". ") + "\n\n(আমি পুরোপুরি sure না — তুমি কি আরেকটু detail দিবে?)"

    # Phase 6: Output moderation — skip OpenAI for social, use local check
    if not trusted:
        if relationship != "social":
            output_safety = await check_content(
                reply,
                openai_api_key=settings.openai_api_key,
                relationship=relationship,
            )
            if not output_safety["safe"]:
                logger.info(f"Output blocked for user={user_name} reason={output_safety['reason']}")
                reply = output_safety["blocked_reply"]
                memory_updates = []
                actions = []

    # Update conversation history in Redis
    history.append({"role": "user", "content": request.message})
    history.append({"role": "assistant", "content": reply})
    conversation_set(conversation_id, history)

    # Track user-scoped history (isolated per platform:user_id)
    user_history_append(platform, user_identifier, "user", request.message)
    user_history_append(platform, user_identifier, "assistant", reply)
    user_replies_track(platform, user_identifier, reply)

    # Track contact interactions for memory enrichment (social messages only)
    if relationship == "social" and platform in ("whatsapp", "facebook"):
        try:
            from memory_manager import contact_interaction_track
            contact_interaction_track(platform, user_identifier, request.message, "incoming")
            contact_interaction_track(platform, user_identifier, reply, "outgoing")
        except Exception:
            pass

    # Process side effects
    if memory_updates:
        await store_memory_updates(memory_updates, user_id=user_id, user_name=user_name)
    if actions:
        await execute_actions(actions)

    # Store conversation memory (tagged with user_id for privacy isolation)
    conv_body: dict = {
        "type": "conversation",
        "user": user_name,
        "content": {"message": request.message, "reply": reply, "conversation_id": conversation_id},
        "text": f"{user_name} said: {request.message}. Azim replied: {reply}",
    }
    if user_id:
        conv_body["user_id"] = user_id
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            await client.post(
                f"{settings.memory_url}/store",
                json=conv_body,
            )
        except Exception:
            pass

    # Trigger async learning from this conversation (via learning agent)
    if agent_manager:
        try:
            await agent_manager.learning_agent_domain.learn_async(
                transcript=f"{user_name}: {request.message}\nAzim: {reply}",
                user_name=user_name,
                conversation_id=conversation_id,
            )
        except Exception:
            pass
    else:
        try:
            async with httpx.AsyncClient(timeout=5.0) as learn_client:
                await learn_client.post(
                    f"{settings.learning_engine_url}/learn",
                    json={
                        "transcript": f"{user_name}: {request.message}\nAzim: {reply}",
                        "user": user_name,
                        "conversation_id": conversation_id,
                    },
                )
        except Exception:
            pass

    # Governor v2: Score response for identity alignment + quality (async, non-blocking)
    asyncio.create_task(_governor_score_response(
        request.message, reply, relationship, user_name,
    ))

    # ── Human Presence Engine: compute response timing metadata ──
    # When ACK was already sent (e.g. WhatsApp instant reply), zero out
    # artificial delays — the user is already engaged and waiting for the real answer.
    if request.ack_sent:
        presence = {"typing_delay_ms": 0, "response_delay_ms": 0, "tone_energy": "high"}
    else:
        presence = _compute_presence(request.message, reply, complexity, relationship)

    return {
        "reply": reply,
        "conversation_id": conversation_id,
        "memory_updates": memory_updates,
        "domain_route": domain_result.get("route") if domain_result else None,
        "agents_used": domain_result.get("tasks_executed", []) if domain_result else [],
        "intelligence": {"complexity": complexity, "route": "fast" if complexity == "simple" else "standard"},
        "presence": presence,
    }


# ── Owner Conversational Control endpoint ───────────────────
class OwnerChatRequest(BaseModel):
    message: str
    sender_id: str = ""
    platform: str = "whatsapp"


@app.post("/chat/owner")
async def chat_owner(request: OwnerChatRequest):
    """Conversational owner control system.

    Handles natural language instructions from the owner with:
    - LLM-powered intent detection (Bangla/English/mixed)
    - Confirmation flow for actions (Redis-backed state)
    - Password-protected critical actions (delete, system changes)
    - Instruction priority system (high/medium/low)
    - Owner tone/mood learning
    - Learning from corrections
    - Persistent owner memory (instructions, preferences)
    - Daily reports on demand

    Called by social-engine webhooks when owner phone is detected.
    """
    message = request.message.strip()
    conversation_id = f"owner-{request.platform}-control"

    # 0. Check for active password challenge FIRST
    pwd_challenge = owner_pwd_challenge_get()
    if pwd_challenge:
        # Owner is in password verification mode
        is_cancel = any(w in message.lower() for w in ["না", "no", "cancel", "বাদ", "don't"])
        if is_cancel:
            owner_pwd_challenge_clear()
            owner_conversation_append("user", message)
            reply = "ঠিক আছে, বাদ দিলাম। 🔓"
            owner_conversation_append("assistant", reply)
            return {"reply": reply, "intent": pwd_challenge.get("intent"), "action_taken": False, "needs_confirmation": False}

        # Verify password (compare with OWNER_ACTION_PASSWORD env var)
        import hmac
        expected = settings.owner_action_password
        if expected and hmac.compare_digest(message.strip(), expected):
            # Password correct — execute the critical action
            action_taken = await _execute_owner_action(pwd_challenge, request.platform)
            owner_pwd_challenge_clear()
            owner_conversation_append("user", "[password verified]")
            reply = "✅ Password verified। Action execute হয়ে গেছে!" if action_taken else "❌ Action execute করতে সমস্যা হয়েছে।"
            owner_conversation_append("assistant", reply)
            logger.info(f"Critical action executed after password: {pwd_challenge.get('intent')}")
            return {"reply": reply, "intent": pwd_challenge.get("intent"), "action_taken": action_taken, "needs_confirmation": False}
        else:
            # Wrong password
            owner_pwd_challenge_clear()
            owner_conversation_append("user", "[wrong password]")
            reply = "❌ Password ভুল হয়েছে। নিরাপত্তার জন্য action বাতিল করা হলো।"
            owner_conversation_append("assistant", reply)
            logger.warning(f"Wrong password attempt for critical action: {pwd_challenge.get('intent')}")
            return {"reply": reply, "intent": pwd_challenge.get("intent"), "action_taken": False, "needs_confirmation": False}

    # 1. Get owner context from Redis
    pending = owner_pending_action_get()
    instructions = owner_instructions_get(limit=15)
    preferences = owner_preferences_all()
    history = owner_conversation_get(limit=20)
    tone_profile = owner_tone_profile_get()

    # 2. Build owner system prompt with full context
    system_prompt = build_owner_system_prompt(
        owner_instructions=instructions,
        owner_preferences=preferences,
        pending_action=pending,
        tone_profile=tone_profile,
        pwd_challenge=None,
    )

    # 3. Retrieve relevant memories + knowledge
    mem_task = retrieve_memories(message, memory_type="knowledge", limit=3)
    personal_task = retrieve_memories(message, memory_type="personal", limit=2)
    mems, personal_mems = await asyncio.gather(mem_task, personal_task)
    memory_context = ""
    all_mems = mems + personal_mems
    if all_mems:
        memory_context = "\nRelevant memories:\n" + "\n".join(
            f"- {m.get('text', '')}" for m in all_mems[:5]
        )

    # 4. Build conversation messages (with identity enforcement)
    owner_full_prompt = system_prompt + memory_context
    if agent_manager:
        identity_prompt = agent_manager.strategy.get_identity_prompt("self")
        owner_full_prompt = identity_prompt + "\n\n" + owner_full_prompt
    messages = [
        {"role": "system", "content": owner_full_prompt},
        *history[-15:],
        {"role": "user", "content": message},
    ]

    # 5. Call LLM (owner is trusted — skip safety checks)
    try:
        result = await query_llm(messages)
    except Exception as e:
        logger.error(f"Owner chat LLM error: {e}")
        return {"reply": "দুঃখিত, একটু সমস্যা হচ্ছে। আবার চেষ্টা করুন।", "intent": None, "action_taken": False}

    reply = result.get("reply", "বুঝতে পারলাম না, আবার বলুন?")
    intent = result.get("intent")
    action = result.get("action")
    needs_confirmation = result.get("needs_confirmation", False)
    needs_password = result.get("needs_password", False)
    detected_tone = result.get("detected_tone")
    memory_updates = result.get("memory_updates", [])

    action_taken = False

    # 5a. Track detected tone passively
    if detected_tone and isinstance(detected_tone, str):
        owner_tone_profile_update(detected_tone)

    # 6. Process action logic
    _CRITICAL_INTENTS = {"delete_data", "system_control"}

    if pending and action and isinstance(action, dict):
        # There was a pending action — check if owner confirmed or rejected
        execute = action.get("execute", False)
        if execute:
            # Check if this is a critical action that needs password
            if pending.get("intent") in _CRITICAL_INTENTS and settings.owner_action_password:
                # Escalate to password challenge
                owner_pwd_challenge_set(pending)
                owner_pending_action_clear()
                reply = "⚠️ এটা critical action। নিশ্চিত করতে আপনার VPS login password দিন।"
                needs_password = True
            else:
                action_taken = await _execute_owner_action(pending, request.platform)
                owner_pending_action_clear()
                if not reply or reply == pending.get("description", ""):
                    reply = "✅ হয়ে গেছে!"
        else:
            owner_pending_action_clear()
            if not reply:
                reply = "ঠিক আছে, বাদ দিলাম।"
    elif needs_confirmation and intent and action and isinstance(action, dict):
        # New action needs confirmation — store as pending
        owner_pending_action_set({
            "intent": intent,
            "description": action.get("description", reply),
            "params": action.get("params", {}),
            "original_message": message,
        })
    elif intent and not needs_confirmation and action and isinstance(action, dict):
        # Direct execution (no confirmation needed — e.g., simple queries)
        # But critical intents ALWAYS need confirmation + password
        if intent in _CRITICAL_INTENTS:
            needs_confirmation = True
            owner_pending_action_set({
                "intent": intent,
                "description": action.get("description", reply),
                "params": action.get("params", {}),
                "original_message": message,
            })
            reply = reply or "⚠️ এটা critical action। আপনি কি নিশ্চিত?"
        else:
            execute_flag = action.get("execute", True)
            if execute_flag:
                action_taken = await _execute_owner_action(
                    {"intent": intent, "params": action.get("params", {}), "original_message": message},
                    request.platform,
                )

    # 7. Handle special intents
    if intent == "correction_learning":
        # Store correction as training data
        await _store_owner_correction(message, memory_updates)

    if intent == "set_instruction" and action and isinstance(action, dict):
        instruction_text = action.get("params", {}).get("instruction", message)
        priority = action.get("params", {}).get("priority", "medium")
        instruction_type = action.get("params", {}).get("type", "permanent")
        ttl = int(action.get("params", {}).get("ttl", 0))
        owner_instruction_store(instruction_text, priority=priority, instruction_type=instruction_type, ttl_seconds=ttl)

    if intent == "set_preference" and action and isinstance(action, dict):
        params = action.get("params", {})
        for k, v in params.items():
            if k not in ("execute", "description", "priority"):
                owner_preference_set(k, str(v))

    # 8. Store memory updates from LLM
    if memory_updates:
        await store_memory_updates(memory_updates, user_id="owner", user_name="Azim")

    # 9. Update owner conversation history
    owner_conversation_append("user", message)
    owner_conversation_append("assistant", reply)

    # 10. Auto-extract identity info from owner messages (STEP 7 — owner = primary truth)
    asyncio.create_task(_extract_owner_profile_from_message(message, reply))

    # 11. Check for pending interview questions — inject into reply if natural
    pending_q = interview_questions_pending()
    if pending_q and not intent and not needs_confirmation:
        q = pending_q[0]
        interview_addition = f"\n\nআচ্ছা, একটা জিনিস জানতে চাইছিলাম — {q['question']}"
        reply = reply + interview_addition

    return {
        "reply": reply,
        "intent": intent,
        "action_taken": action_taken,
        "needs_confirmation": needs_confirmation,
    }


async def _execute_owner_action(action_data: dict, platform: str) -> bool:
    """Execute a confirmed owner action. Returns True if successful."""
    intent = action_data.get("intent", "")
    params = action_data.get("params", {})

    try:
        if intent == "set_relation":
            # Store relationship in memory service
            phone = params.get("phone", params.get("number", ""))
            relation = params.get("relation", params.get("relationship", "unknown"))
            if phone and relation:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(
                        f"{settings.memory_url}/store",
                        json={
                            "type": "contact",
                            "user": "owner",
                            "content": {"phone": phone, "relation": relation, "platform": platform},
                            "text": f"Contact {phone} is {relation}",
                        },
                    )
                return True

        elif intent == "set_priority":
            phone = params.get("phone", params.get("number", ""))
            priority = params.get("priority", "high")
            if phone:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(
                        f"{settings.memory_url}/store",
                        json={
                            "type": "preference",
                            "user": "owner",
                            "content": {"phone": phone, "priority": priority},
                            "text": f"Contact {phone} has {priority} priority",
                        },
                    )
                return True

        elif intent == "set_permanent_memory":
            content = params.get("content", params.get("text", action_data.get("original_message", "")))
            if content:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(
                        f"{settings.memory_url}/store",
                        json={
                            "type": "knowledge",
                            "user": "owner",
                            "content": {"kind": "owner_instruction", "text": content},
                            "text": f"Owner instruction: {content}",
                        },
                    )
                return True

        elif intent == "generate_report":
            # Report is generated by the LLM in the reply itself
            return True

        elif intent == "set_instruction":
            return True  # Already handled above

        elif intent == "set_preference":
            return True  # Already handled above

        elif intent == "query_info":
            return True  # LLM answers directly

        elif intent == "approve_suggestion":
            suggestion_id = params.get("suggestion_id", "")
            if suggestion_id:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        f"{settings.autonomy_engine_url}/autonomy/suggestions/{suggestion_id}/approve"
                    )
                    return resp.status_code == 200

        elif intent == "reject_suggestion":
            suggestion_id = params.get("suggestion_id", "")
            if suggestion_id:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        f"{settings.autonomy_engine_url}/autonomy/suggestions/{suggestion_id}/reject"
                    )
                    return resp.status_code == 200

        elif intent == "approve_sandbox":
            change_id = params.get("change_id", params.get("sandbox_id", ""))
            if change_id:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        f"{settings.autonomy_engine_url}/autonomy/sandbox/{change_id}/apply"
                    )
                    return resp.status_code == 200

        elif intent == "reject_sandbox":
            change_id = params.get("change_id", params.get("sandbox_id", ""))
            if change_id:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        f"{settings.autonomy_engine_url}/autonomy/sandbox/{change_id}/reject"
                    )
                    return resp.status_code == 200

        elif intent == "update_execution_rule":
            stype = params.get("suggestion_type", "")
            level = params.get("level", "")
            if stype and level:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.put(
                        f"{settings.autonomy_engine_url}/autonomy/execution-rules/{stype}",
                        json={"level": level},
                    )
                    return resp.status_code == 200

        elif intent == "restore_backup":
            backup_id = params.get("backup_id", "")
            if backup_id:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        f"{settings.autonomy_engine_url}/autonomy/backups/{backup_id}/restore"
                    )
                    return resp.status_code == 200

        # ── Identity & Interview intents ──
        elif intent == "update_profile":
            # Owner provided personal info — store in azim_profile
            profile_fields = {k: v for k, v in params.items()
                              if k not in ("execute", "description", "priority")}
            if profile_fields:
                azim_profile_update(profile_fields)
                # Also store in memory for vector search
                async with httpx.AsyncClient(timeout=10.0) as client:
                    for field, value in profile_fields.items():
                        await client.post(
                            f"{settings.memory_url}/store",
                            json={
                                "type": "knowledge",
                                "user": "owner",
                                "content": {"kind": "azim_identity", "field": field, "value": str(value)},
                                "text": f"Azim's {field}: {value}",
                            },
                        )
                    # Store in PostgreSQL knowledge table
                    for field, value in profile_fields.items():
                        category = _field_to_category(field)
                        try:
                            await client.post(
                                f"{settings.memory_url}/knowledge/store",
                                json={
                                    "category": category,
                                    "subcategory": field,
                                    "key": field,
                                    "value": str(value),
                                    "language": "auto",
                                    "source": "owner_chat",
                                },
                            )
                        except Exception as e:
                            logger.warning(f"Knowledge table store failed for {field}: {e}")
                logger.info(f"Owner profile updated: {list(profile_fields.keys())}")
                return True

        elif intent == "interview_answer":
            question = params.get("question", "")
            answer = params.get("answer", action_data.get("original_message", ""))
            profile_field = params.get("profile_field", "")
            if answer:
                interview_answer_store(question, answer)
                if profile_field:
                    azim_profile_set(profile_field, answer)
                # Pop the answered question from queue
                interview_question_pop()
                return True

        # ── Self-Development Engine intents ──
        elif intent == "scan_codebase":
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(f"{settings.autonomy_engine_url}/autonomy/self-dev/scan")
                return resp.status_code == 200

        elif intent == "list_patches":
            return True  # LLM fetches via system agent

        elif intent == "view_patch":
            return True  # LLM fetches via system agent

        elif intent == "approve_patch":
            patch_id = params.get("patch_id", "")
            if patch_id:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        f"{settings.autonomy_engine_url}/autonomy/self-dev/patch/{patch_id}/approve"
                    )
                    return resp.status_code == 200

        elif intent == "reject_patch":
            patch_id = params.get("patch_id", "")
            if patch_id:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        f"{settings.autonomy_engine_url}/autonomy/self-dev/patch/{patch_id}/reject"
                    )
                    return resp.status_code == 200

        elif intent == "apply_patch":
            patch_id = params.get("patch_id", "")
            if patch_id:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        f"{settings.autonomy_engine_url}/autonomy/self-dev/patch/{patch_id}/apply"
                    )
                    return resp.status_code == 200

        elif intent == "rollback_patch":
            patch_id = params.get("patch_id", "")
            if patch_id:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(
                        f"{settings.autonomy_engine_url}/autonomy/self-dev/patch/{patch_id}/rollback"
                    )
                    return resp.status_code == 200

        elif intent == "patch_outcome":
            patch_id = params.get("patch_id", "")
            outcome = params.get("outcome", "positive")
            if patch_id:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        f"{settings.autonomy_engine_url}/autonomy/self-dev/patch/{patch_id}/outcome",
                        params={"outcome": outcome},
                    )
                    return resp.status_code == 200

        elif intent == "selfdev_history":
            return True  # LLM fetches via system agent

        logger.info(f"Owner action executed: {intent}")
        return True

    except Exception as e:
        logger.error(f"Owner action execution failed ({intent}): {e}")
        return False


async def _store_owner_correction(message: str, memory_updates: list[dict]) -> None:
    """Store an owner correction as training data via teaching pipeline + legacy stores."""
    # Use unified teaching pipeline if available
    if teaching_pipeline:
        try:
            teaching_pipeline.teach_from_correction(
                correction_text=message,
                original_query="",
                original_reply="",
                platform="whatsapp",
            )
            logger.info("Owner correction stored via teaching pipeline")
        except Exception as e:
            logger.warning(f"Teaching pipeline correction failed: {e}")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Store in learning engine
            await client.post(
                f"{settings.learning_engine_url}/corrections",
                json={
                    "correction": message,
                    "user": "owner",
                },
            )
            # Store in memory as knowledge
            await client.post(
                f"{settings.memory_url}/store",
                json={
                    "type": "knowledge",
                    "user": "owner",
                    "content": {"kind": "owner_correction", "correction": message},
                    "text": f"Owner correction: {message}",
                },
            )
    except Exception as e:
        logger.warning(f"Owner correction storage failed: {e}")


# ── Owner Daily Report endpoint ─────────────────────────────
@app.post("/owner/report")
async def owner_daily_report():
    """Generate daily activity report for the owner, enhanced with autonomy insights."""
    # Collect stats from social engine via quick memory search
    stats = {
        "total_messages": 0,
        "whatsapp_messages": 0,
        "facebook_messages": 0,
        "unique_users": 0,
        "new_users": 0,
        "owner_messages": 0,
    }

    # Pull autonomy intelligence report
    autonomy_report = None
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{settings.autonomy_engine_url}/autonomy/intelligence-report")
            if resp.status_code == 200:
                autonomy_report = resp.json()
    except Exception as e:
        logger.warning(f"Autonomy report fetch failed: {e}")

    # Use LLM to generate natural Bangla report
    report_prompt = build_daily_report_prompt(stats)
    if autonomy_report:
        report_prompt += f"\n\n--- Autonomous Intelligence Report ---\n{autonomy_report.get('report', '')}"
        if autonomy_report.get("stats"):
            ai_stats = autonomy_report["stats"]
            report_prompt += f"\nSuggestions: {ai_stats.get('suggestions_generated', 0)} | Approved: {ai_stats.get('approved', 0)} | Rejected: {ai_stats.get('rejected', 0)} | Auto-improved: {ai_stats.get('auto_applied', 0)} | Auto-executed: {ai_stats.get('auto_executed', 0)}"
        if autonomy_report.get("execution"):
            ex = autonomy_report["execution"]
            report_prompt += f"\n--- Execution Agent ---\nLOW auto: {ex.get('auto_executed_low', 0)} | MEDIUM auto: {ex.get('auto_executed_medium', 0)} | HIGH confirmed: {ex.get('owner_confirmed_high', 0)} | Sandbox pending: {ex.get('sandbox_pending', 0)} | Failures: {ex.get('execution_failures', 0)}"
        if autonomy_report.get("medium_auto_approved"):
            report_prompt += f"\nAuto-approved types (ask-once): {autonomy_report['medium_auto_approved']}"

    messages = [
        {"role": "system", "content": "You are Azim's AI assistant. Generate a daily report in Bangla. Be concise."},
        {"role": "user", "content": report_prompt},
    ]

    try:
        result = await query_llm(messages)
        report = result.get("reply", "আজকের রিপোর্ট তৈরি করা যায়নি।")
    except Exception:
        report = "রিপোর্ট তৈরিতে সমস্যা হয়েছে।"

    return {
        "report": report,
        "stats": stats,
        "autonomy": autonomy_report.get("stats") if autonomy_report else None,
    }


# ── Autonomy-triggered follow-up endpoint ───────────────────
class FollowUpRequest(BaseModel):
    user_id: str
    platform: str = "whatsapp"
    message: Optional[str] = None


@app.post("/autonomy/trigger-followup")
async def trigger_followup(req: FollowUpRequest):
    """Called by autonomy engine when owner approves a follow-up suggestion.
    Generates a context-aware follow-up message and sends it via social engine."""
    conv_id = f"social-{req.platform}-{req.user_id}"
    conv = conversation_get(conv_id)

    # Build context from conversation history
    history_text = ""
    if conv:
        history_text = "\n".join(
            f"{'User' if m.get('role') == 'user' else 'AI'}: {m.get('content', '')[:150]}"
            for m in conv[-6:]
        )

    followup_prompt = f"""Generate a natural, friendly follow-up message in Bangla for this user.

Previous conversation:
{history_text or "No previous history"}

Guidelines:
- Be warm, not pushy
- Reference the previous conversation naturally
- Ask if they need any more help
- Stay in character as Azim's AI assistant
- Max 2-3 sentences"""

    messages = [
        {"role": "system", "content": "You are Fazle, Azim's AI. Write a natural Bangla follow-up."},
        {"role": "user", "content": followup_prompt},
    ]

    try:
        result = await query_llm(messages)
        followup_msg = result.get("reply", "")
    except Exception:
        followup_msg = "আশা করি আপনি ভালো আছেন! কোনো সাহায্য লাগলে জানাবেন।"

    if not followup_msg:
        return {"status": "skipped", "reason": "empty message"}

    # Send via social engine
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                # Social engine's outbound message endpoint
                "http://fazle-social-engine:9800/send",
                json={
                    "platform": req.platform,
                    "user_id": req.user_id,
                    "message": followup_msg,
                    "source": "autonomy-followup",
                },
            )
    except Exception as e:
        logger.warning(f"Follow-up send failed: {e}")
        return {"status": "send_failed", "message": followup_msg}

    return {"status": "sent", "message": followup_msg}


# ── Streaming Chat endpoint (for voice pipeline) ───────────
class StreamChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    user: str = "Azim"
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    relationship: Optional[str] = None
    source: str = "voice"


@app.post("/chat/stream")
async def chat_stream(request: StreamChatRequest):
    """Streaming chat endpoint — returns SSE stream of text chunks for voice TTS."""
    conversation_id = request.conversation_id or str(uuid.uuid4())
    user_name = request.user_name or request.user or "Azim"
    relationship = request.relationship or "self"
    user_id = request.user_id

    # Parallel: persona + memories (skip moderation for speed on voice)
    system_prompt_task = build_system_prompt_async(
        user_name=user_name,
        relationship=relationship,
        user_id=user_id,
        learning_engine_url=settings.learning_engine_url,
    )
    mem_task = retrieve_memories(request.message, user_id=user_id, limit=2)

    system_prompt, memories = await asyncio.gather(system_prompt_task, mem_task)

    # For voice streaming, override the response format instruction:
    # Remove JSON formatting requirement and ask for plain spoken text
    voice_override = (
        "\n\nIMPORTANT: This is a voice conversation. "
        "Respond with ONLY your spoken reply as plain text. "
        "Do NOT use JSON format. Do NOT include memory_updates or actions. "
        "Keep responses concise (1-3 sentences) for natural voice delivery."
    )

    memory_context = ""
    if memories:
        memory_context = "\n\nRelevant memories:\n" + "\n".join(
            f"- {m.get('text', str(m.get('content', '')))}" for m in memories[:2]
        )

    history = conversation_get(conversation_id)
    messages = [
        {"role": "system", "content": system_prompt + voice_override + memory_context},
        *history[-6:],
        {"role": "user", "content": request.message},
    ]

    # Choose streaming source
    if settings.voice_fast_mode:
        stream_gen = stream_llm_voice(messages)
    else:
        stream_gen = stream_llm_gateway(messages)

    async def event_stream():
        full_reply = []
        async for chunk in stream_gen:
            full_reply.append(json.loads(chunk).get("content", ""))
            yield f"data: {chunk}\n\n"
        # Background: store conversation + trigger learning
        reply_text = "".join(full_reply)
        history.append({"role": "user", "content": request.message})
        history.append({"role": "assistant", "content": reply_text})
        conversation_set(conversation_id, history)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Conversation-Id": conversation_id},
    )


# ── Intelligence Tuning Layer — Stats endpoint ──────────────
@app.get("/intelligence/stats")
async def intelligence_stats():
    """Get Intelligence Tuning Layer usage stats and configuration."""
    usage = intel_usage_stats(days=7)
    return {
        "usage": usage,
        "config": {
            "fast_path_patterns": len(_SIMPLE_PATTERNS),
            "uncertainty_markers": len(_UNCERTAINTY_MARKERS),
            "models": {
                "simple": "gpt-4o-mini",
                "medium": settings.llm_model,
                "complex": settings.llm_model,
                "voice_fast": settings.voice_fast_model,
            },
        },
        "owner_priority_active": intel_owner_priority_active(),
    }


# ── Ultra-Fast Chat endpoint (for voice, <500ms TTFB) ──────
class FastChatRequest(BaseModel):
    message: str
    source: str = "voice"


@app.post("/chat/fast")
async def chat_fast(request: FastChatRequest):
    """Ultra-fast streaming: zero preprocessing, direct Ollama /api/generate.
    Skips persona, memory, moderation, conversation history.
    Target: <500ms TTFB on CPU with qwen2.5:0.5b."""

    async def event_stream():
        async for chunk in stream_ollama_fast(request.message):
            yield f"data: {chunk}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
    )


# ── Smart Router endpoint ──────────────────────────────────
class RouteRequest(BaseModel):
    message: str
    source: str = "text"


@app.post("/route")
async def route_query(request: RouteRequest):
    """Classify a query and return the recommended route."""
    route = agent_manager.route_query(request.message, request.source)
    return {"message": request.message, "route": route.value, "source": request.source}


# ── Agent-powered Chat (full pipeline) ─────────────────────
class AgentChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    user: str = "Azim"
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    relationship: Optional[str] = None
    source: str = "text"


@app.post("/chat/agent")
async def chat_agent(request: AgentChatRequest):
    """Multi-agent chat: routes through strategy (domain) + utility layers,
    enriches context with identity enforcement, then generates LLM response."""
    conversation_id = request.conversation_id or str(uuid.uuid4())
    user_name = request.user_name or request.user or "Azim"
    relationship = request.relationship or "self"

    # Build agent context
    ctx = AgentContext(
        message=request.message,
        user_name=user_name,
        user_id=request.user_id,
        relationship=relationship,
        conversation_id=conversation_id,
        metadata={"source": request.source},
    )

    # Domain routing (strategy layer)
    domain_result = await agent_manager.process_domain(ctx)

    # Utility routing
    route = agent_manager.route_query(request.message, request.source)

    # Run agent pipeline
    agent_result = await agent_manager.process(ctx, route)

    # If fast voice, agent already generated the reply
    if route == QueryRoute.FAST_VOICE and agent_result.get("reply"):
        return {
            "reply": agent_result["reply"],
            "conversation_id": conversation_id,
            "route": route.value,
            "agents_used": agent_result["agents_used"],
        }

    # For conversation and full pipeline, use LLM with enriched context
    # Use domain-produced prompt or build with identity enforcement
    domain_prompt = domain_result.get("system_prompt")
    if domain_prompt:
        system_prompt = domain_prompt
    else:
        system_prompt = await build_system_prompt_async(
            user_name=user_name,
            relationship=relationship,
            user_id=request.user_id,
            learning_engine_url=settings.learning_engine_url,
        )
        # Enforce identity core
        identity_prompt = domain_result.get("identity_prompt", "")
        if identity_prompt:
            system_prompt = identity_prompt + "\n\n" + system_prompt

    # Build enriched context from agent results
    enriched_parts = []
    if ctx.memories:
        enriched_parts.append("Relevant memories:")
        for m in ctx.memories[:5]:
            enriched_parts.append(f"- {m.get('text', '')}")
    if ctx.search_results:
        enriched_parts.append("\nWeb search results:")
        for r in ctx.search_results[:3]:
            enriched_parts.append(f"- {r.get('title', '')}: {r.get('snippet', '')}")
    if ctx.tool_results:
        enriched_parts.append("\nTool results:")
        for t in ctx.tool_results[:3]:
            enriched_parts.append(f"- {json.dumps(t)}")

    enriched_context = "\n".join(enriched_parts) if enriched_parts else ""

    history = conversation_get(conversation_id)
    messages = [
        {"role": "system", "content": system_prompt + "\n" + enriched_context},
        *history[-10:],
        {"role": "user", "content": request.message},
    ]

    try:
        result = await query_llm(messages)
    except Exception as e:
        logger.error(f"Agent LLM error: {e}")
        raise HTTPException(status_code=502, detail="LLM service unavailable")

    reply = result.get("reply", "I'm not sure how to respond to that.")
    memory_updates = result.get("memory_updates", [])
    actions = result.get("actions", [])

    # Update conversation history
    history.append({"role": "user", "content": request.message})
    history.append({"role": "assistant", "content": reply})
    conversation_set(conversation_id, history)

    # Process side effects
    if memory_updates:
        await store_memory_updates(memory_updates, user_id=request.user_id, user_name=user_name)
    if actions:
        await execute_actions(actions)

    return {
        "reply": reply,
        "conversation_id": conversation_id,
        "route": route.value,
        "agents_used": agent_result.get("agents_used", []),
        "domain_route": domain_result.get("domain_route", ""),
        "memory_updates": memory_updates,
    }


# ── Summary Engine (Step 16) ────────────────────────────────

class SummarizeRequest(BaseModel):
    conversation_id: str
    user_phone: str = ""
    user_name: str = ""
    platform: str = "whatsapp"


@app.post("/chat/summarize")
async def summarize_conversation(request: SummarizeRequest):
    """Generate a summary of a conversation and store it.
    Called by social engine after N messages or end of conversation."""
    history = conversation_get(request.conversation_id)
    if not history or len(history) < 4:
        return {"summary": "", "status": "too_short"}

    # Build conversation text
    conv_text = "\n".join(
        f"{'User' if m.get('role') == 'user' else 'Azim'}: {m.get('content', '')[:200]}"
        for m in history[-20:]
    )

    summary_prompt = (
        f"Summarize this conversation in 2-3 sentences in Bangla.\n"
        f"Include: main topic, user intent, outcome, any commitments made.\n\n"
        f"{conv_text}"
    )

    messages = [
        {"role": "system", "content": "You are a conversation summarizer. Return ONLY the summary in Bangla. No JSON."},
        {"role": "user", "content": summary_prompt},
    ]

    try:
        result = await query_llm(messages)
        summary = result.get("reply", "")
        if not summary:
            return {"summary": "", "status": "generation_failed"}
    except Exception as e:
        logger.warning(f"Summary generation failed: {e}")
        return {"summary": "", "status": "error"}

    # Extract key topics
    key_topics = []
    topic_words = ["কাজ", "বেতন", "salary", "apply", "location", "complaint", "info"]
    for tw in topic_words:
        if tw in conv_text.lower():
            key_topics.append(tw)

    # Store summary via social engine
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{settings.social_engine_url}/internal/save-summary",
                json={
                    "conversation_id": request.conversation_id,
                    "summary": summary,
                    "user_phone": request.user_phone,
                    "user_name": request.user_name,
                    "message_count": len(history),
                    "key_topics": key_topics,
                    "platform": request.platform,
                },
            )
    except Exception as e:
        logger.debug(f"Summary storage via social engine failed: {e}")

    return {"summary": summary, "message_count": len(history), "key_topics": key_topics, "status": "ok"}


# ── Explanation Engine (Step 17) ─────────────────────────────

class ExplainRequest(BaseModel):
    topic: str
    depth: str = "simple"  # simple, medium, detailed
    language: str = "bn"  # bn = Bangla, en = English


@app.post("/chat/explain")
async def explain_topic(request: ExplainRequest):
    """Generate an explanation of a topic at the requested depth.
    Used by owner or social engine to get structured explanations."""
    depth_instructions = {
        "simple": "Explain in 1-2 simple sentences. Use everyday language.",
        "medium": "Explain in a clear paragraph with examples.",
        "detailed": "Give a thorough explanation with examples, context, and implications.",
    }
    lang_instruction = "Respond in Bangla (বাংলা)." if request.language == "bn" else "Respond in English."

    explain_prompt = (
        f"{depth_instructions.get(request.depth, depth_instructions['simple'])}\n"
        f"{lang_instruction}\n\n"
        f"Topic: {request.topic}"
    )

    messages = [
        {"role": "system", "content": "You are a knowledgeable explainer. Give clear, accurate explanations."},
        {"role": "user", "content": explain_prompt},
    ]

    try:
        result = await query_llm(messages)
        explanation = result.get("reply", "")
    except Exception as e:
        logger.warning(f"Explanation generation failed: {e}")
        explanation = "ব্যাখ্যা তৈরি করতে সমস্যা হয়েছে।"

    return {"explanation": explanation, "topic": request.topic, "depth": request.depth}


# ── Identity Confidence Score (Step 20) ─────────────────────

@app.get("/azim/identity-confidence")
async def identity_confidence():
    """Calculate identity confidence score based on profile completeness."""
    profile = azim_profile_all()
    if not profile:
        return {"confidence": 0.0, "missing_fields": ["all"], "level": "empty"}

    # Core fields that define identity
    core_fields = [
        "full_name", "role", "personality", "communication_style",
        "language", "location", "greeting_style", "humor_level",
        "strictness", "tone_variation",
    ]
    # Extended fields for deeper identity
    extended_fields = [
        "business_info", "family", "preferences", "ideology",
        "occupation", "hobbies", "education", "goals",
        "dislikes", "food", "music", "tech_stack", "religion",
    ]

    filled_core = sum(1 for f in core_fields if profile.get(f))
    filled_extended = sum(1 for f in extended_fields if profile.get(f))
    missing = [f for f in core_fields + extended_fields if not profile.get(f)]

    # Core fields worth 70%, extended worth 30%
    core_score = (filled_core / len(core_fields)) * 0.7 if core_fields else 0
    extended_score = (filled_extended / len(extended_fields)) * 0.3 if extended_fields else 0
    confidence = round(core_score + extended_score, 2)

    level = "empty"
    if confidence >= 0.8:
        level = "strong"
    elif confidence >= 0.5:
        level = "moderate"
    elif confidence >= 0.2:
        level = "weak"
    else:
        level = "minimal"

    return {
        "confidence": confidence,
        "level": level,
        "filled_core": filled_core,
        "total_core": len(core_fields),
        "filled_extended": filled_extended,
        "total_extended": len(extended_fields),
        "missing_fields": missing[:10],
    }


# ── Azim Identity Profile endpoints ─────────────────────────

@app.get("/azim/profile")
async def get_azim_profile():
    """Get the full Azim identity profile."""
    profile = azim_profile_all()
    return {"profile": profile}


@app.put("/azim/profile")
async def update_azim_profile(data: dict):
    """Update Azim's identity profile fields."""
    if not data:
        raise HTTPException(status_code=400, detail="No data provided")
    azim_profile_update(data)
    # Also store in memory service for vector search
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for field, value in data.items():
                await client.post(
                    f"{settings.memory_url}/store",
                    json={
                        "type": "knowledge",
                        "user": "owner",
                        "content": {"kind": "azim_identity", "field": field, "value": str(value)},
                        "text": f"Azim's {field}: {value}",
                    },
                )
    except Exception as e:
        logger.warning(f"Identity memory store failed: {e}")
    return {"status": "updated", "profile": azim_profile_all()}


# ── Owner Interview System endpoints ────────────────────────

@app.get("/azim/interview/pending")
async def get_pending_interviews():
    """Get pending interview questions for the owner."""
    questions = interview_questions_pending()
    return {"pending": questions, "count": len(questions)}


@app.post("/azim/interview/answer")
async def answer_interview(data: dict):
    """Store an owner's answer to an interview question and update profile."""
    question = data.get("question", "")
    answer = data.get("answer", "")
    profile_field = data.get("profile_field", "")
    if not question or not answer:
        raise HTTPException(status_code=400, detail="question and answer required")
    # Store the answer
    interview_answer_store(question, answer)
    # Update profile if field specified
    if profile_field:
        azim_profile_set(profile_field, answer)
    # Store in memory for learning
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{settings.memory_url}/store",
                json={
                    "type": "knowledge",
                    "user": "owner",
                    "content": {"kind": "interview_answer", "question": question, "answer": answer},
                    "text": f"Owner interview — Q: {question} A: {answer}",
                },
            )
    except Exception:
        pass
    return {"status": "stored"}


# ── Image/Audio processing endpoint (for social-engine) ────

@app.post("/chat/multimodal")
async def chat_multimodal(request: dict):
    """Process image or audio content from WhatsApp.
    Accepts: media_type (image/audio), media_url or base64, sender context.
    If local_extracted_text is provided (from social-engine OCR/Whisper),
    skip expensive OpenAI vision/whisper calls and use local text directly.
    Returns: extracted text/transcript + AI reply."""
    media_type = request.get("media_type", "")
    media_b64 = request.get("media_base64", "")
    sender_id = request.get("sender_id", "")
    sender_name = request.get("sender_name", "")
    platform = request.get("platform", "whatsapp")
    caption = request.get("caption", "")
    is_owner = request.get("is_owner", False)
    conversation_id = request.get("conversation_id", f"social-{platform}-{sender_id}")
    relationship = "self" if is_owner else "social"
    local_extracted_text = request.get("local_extracted_text", "")

    extracted_text = ""

    # ── Fast path: if social-engine already extracted text locally, skip OpenAI ──
    if local_extracted_text:
        extracted_text = local_extracted_text
        description = ""
        doc_type = ""

        if media_type == "image":
            description = "[Locally extracted via OCR]"
            user_msg = f"[User sent an image]\nExtracted text (OCR): {extracted_text[:1000]}"
            if caption:
                user_msg += f"\nCaption: {caption}"
        elif media_type == "audio":
            user_msg = f"[User sent a voice message]\nTranscript: {extracted_text}"
            if is_owner:
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        await client.post(
                            f"{settings.memory_url}/store",
                            json={
                                "type": "knowledge",
                                "user": "owner",
                                "content": {
                                    "kind": "owner_voice_training",
                                    "transcript": extracted_text,
                                    "platform": platform,
                                },
                                "text": f"Owner voice message (training): {extracted_text}",
                            },
                        )
                        await client.post(
                            f"{settings.learning_engine_url}/learn",
                            json={
                                "transcript": f"Owner (voice): {extracted_text}",
                                "user": "owner",
                                "conversation_id": conversation_id,
                            },
                        )
                except Exception:
                    pass
        else:
            return {"reply": "Unsupported media type", "extracted_text": "", "conversation_id": conversation_id}

        logger.info(f"Multimodal fast-path: using local extracted text ({len(extracted_text)} chars)")

    elif media_type == "image" and media_b64:
        # OCR + image understanding via GPT-4o vision
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.openai_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "gpt-4o",
                        "messages": [{
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        "Analyze this image thoroughly:\n"
                                        "1. Extract ALL text (OCR) — including handwritten text\n"
                                        "2. Describe what's in the image\n"
                                        "3. Identify document type if applicable\n"
                                        "4. Note any important details\n"
                                        f"{'User caption: ' + caption if caption else ''}\n"
                                        "Respond in JSON: {\"ocr_text\": \"extracted text\", \"description\": \"what the image shows\", \"document_type\": \"type or null\"}"
                                    ),
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{media_b64}", "detail": "high"},
                                },
                            ],
                        }],
                        "max_tokens": 1000,
                        "response_format": {"type": "json_object"},
                    },
                )
                resp.raise_for_status()
                vision_result = json.loads(resp.json()["choices"][0]["message"]["content"])
                extracted_text = vision_result.get("ocr_text", "")
                description = vision_result.get("description", "")
                doc_type = vision_result.get("document_type", "")
                # Governor STEP 3: Validate multimodal confidence
                ocr_confidence = 0.8 if extracted_text and len(extracted_text.strip()) > 10 else 0.3
                try:
                    async with httpx.AsyncClient(timeout=5.0) as gov_client:
                        gov_resp = await gov_client.post(
                            f"{settings.autonomy_engine_url}/governor/validate-multimodal",
                            json={"extracted_text": extracted_text, "media_type": "image", "confidence": ocr_confidence},
                        )
                        if gov_resp.status_code == 200 and not gov_resp.json().get("reliable", True):
                            description = f"[Low confidence] {description}"
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"GPT-4o vision failed: {e}")
            extracted_text = ""
            description = "[Image analysis failed]"
            doc_type = ""

        # Store image memory
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(
                    f"{settings.memory_url}/store",
                    json={
                        "type": "knowledge",
                        "user": "owner" if is_owner else sender_name,
                        "content": {
                            "kind": "image_analysis",
                            "ocr_text": extracted_text,
                            "description": description,
                            "document_type": doc_type,
                            "sender": sender_id,
                            "platform": platform,
                        },
                        "text": f"Image from {sender_name}: {description}. Text: {extracted_text[:500]}",
                    },
                )
        except Exception:
            pass

        # Generate contextual reply
        user_msg = f"[User sent an image]\nDescription: {description}"
        if extracted_text:
            user_msg += f"\nExtracted text: {extracted_text[:1000]}"
        if caption:
            user_msg += f"\nCaption: {caption}"

    elif media_type == "audio" and media_b64:
        # Transcribe audio via OpenAI Whisper API
        import base64 as b64mod
        audio_bytes = b64mod.b64decode(media_b64)
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    files={"file": ("audio.ogg", audio_bytes, "audio/ogg")},
                    data={"model": "whisper-1", "language": "bn"},
                )
                resp.raise_for_status()
                extracted_text = resp.json().get("text", "")
        except Exception as e:
            logger.error(f"Whisper transcription failed: {e}")
            extracted_text = ""

        # Governor STEP 3: Validate audio transcription confidence
        if extracted_text:
            audio_confidence = min(1.0, len(extracted_text.strip()) / 20)  # very short = low confidence
            try:
                async with httpx.AsyncClient(timeout=5.0) as gov_client:
                    gov_resp = await gov_client.post(
                        f"{settings.autonomy_engine_url}/governor/validate-multimodal",
                        json={"extracted_text": extracted_text, "media_type": "audio", "confidence": audio_confidence},
                    )
                    if gov_resp.status_code == 200 and not gov_resp.json().get("reliable", True):
                        extracted_text = f"[Low confidence transcript] {extracted_text}"
            except Exception:
                pass

        if not extracted_text:
            return {"reply": "দুঃখিত, অডিও বুঝতে পারলাম না। আবার পাঠান?", "extracted_text": "", "conversation_id": conversation_id}

        # If owner sent audio → store as training signal (STEP 6)
        if is_owner:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(
                        f"{settings.memory_url}/store",
                        json={
                            "type": "knowledge",
                            "user": "owner",
                            "content": {
                                "kind": "owner_voice_training",
                                "transcript": extracted_text,
                                "platform": platform,
                            },
                            "text": f"Owner voice message (training): {extracted_text}",
                        },
                    )
                    # Also send to learning engine for style analysis
                    await client.post(
                        f"{settings.learning_engine_url}/learn",
                        json={
                            "transcript": f"Owner (voice): {extracted_text}",
                            "user": "owner",
                            "conversation_id": conversation_id,
                        },
                    )
            except Exception:
                pass

        user_msg = f"[User sent a voice message]\nTranscript: {extracted_text}"
    else:
        return {"reply": "Unsupported media type", "extracted_text": "", "conversation_id": conversation_id}

    # Now route the extracted content through normal chat
    system_prompt = await build_system_prompt_async(
        user_name=sender_name or "User",
        relationship=relationship,
        user_id=sender_id,
        learning_engine_url=settings.learning_engine_url,
    )

    history = conversation_get(conversation_id)
    messages = [
        {"role": "system", "content": system_prompt},
        *history[-8:],
        {"role": "user", "content": user_msg},
    ]

    try:
        complexity = _classify_query_complexity(user_msg)
        result = await query_llm_smart(messages, complexity)
    except Exception as e:
        logger.error(f"Multimodal chat LLM error: {e}")
        return {"reply": "দুঃখিত, একটু সমস্যা হচ্ছে।", "extracted_text": extracted_text, "conversation_id": conversation_id}

    reply = result.get("reply", "")
    history.append({"role": "user", "content": user_msg})
    history.append({"role": "assistant", "content": reply})
    conversation_set(conversation_id, history)

    return {"reply": reply, "extracted_text": extracted_text, "conversation_id": conversation_id}


# ── Owner profile auto-extraction from chat ─────────────────

_FIELD_CATEGORY_MAP = {
    "full_name": "personal", "personality": "personal", "communication_style": "personal",
    "location": "personal", "occupation": "personal", "education": "education",
    "language": "personal", "religion": "religious",
    "business_info": "business", "tech_stack": "tech",
    "family": "family", "preferences": "preference", "ideology": "ideology",
    "hobbies": "social", "daily_routine": "daily", "goals": "personal",
    "dislikes": "preference", "food": "preference", "music": "preference",
    "health": "health", "financial": "financial",
}


def _field_to_category(field: str) -> str:
    """Map a profile field name to a knowledge category."""
    return _FIELD_CATEGORY_MAP.get(field, "personal")


async def _extract_owner_profile_from_message(message: str, reply: str) -> None:
    """Analyze owner messages for identity information and auto-store in profile.
    Uses LLM to detect if the message contains personal info about Azim."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.llm_gateway_url}/generate",
                json={
                    "messages": [{
                        "role": "user",
                        "content": (
                            f"Analyze this message from the owner (Azim). Extract any personal identity information.\n"
                            f"Message: {message}\n\n"
                            f"If the message contains personal info (name, preferences, business info, family details, "
                            f"habits, likes/dislikes, occupation, location, etc.), return JSON:\n"
                            f'{{"found": true, "fields": {{"field_name": "value", ...}}}}\n'
                            f"Valid field names: full_name, personality, communication_style, business_info, family, "
                            f"preferences, ideology, location, occupation, hobbies, language, religion, education, "
                            f"daily_routine, goals, dislikes, food, music, tech_stack\n"
                            f"If no personal info found, return: {{\"found\": false}}"
                        ),
                    }],
                    "response_format": "json",
                    "caller": "fazle-brain-profile-extract",
                    "temperature": 0.1,
                },
            )
            resp.raise_for_status()
            result = json.loads(resp.json()["content"])
            if result.get("found") and result.get("fields"):
                fields = result["fields"]
                # Governor STEP 2: Validate new knowledge against existing profile
                current = azim_profile_all()
                validated_fields = {}
                for field, value in fields.items():
                    is_valid = await _governor_validate_learning_check(str(value), field)
                    if is_valid:
                        existing = current.get(field, "")
                        if existing and len(str(value)) < len(existing) // 2:
                            value = f"{existing}; {value}"
                        validated_fields[field] = value
                    else:
                        governor_drift_alert(f"Learning blocked: field={field}, value={str(value)[:100]}")
                        logger.info(f"Governor blocked profile update for field: {field}")
                for field, value in validated_fields.items():
                    azim_profile_set(field, str(value))
                if validated_fields:
                    logger.info(f"Auto-extracted owner profile fields: {list(validated_fields.keys())}")
    except Exception as e:
        logger.debug(f"Profile extraction skipped: {e}")


# ── Phase-5 Autonomy Pipeline ───────────────────────────────

class AutonomyRequest(BaseModel):
    goal: str
    context: Optional[str] = None
    auto_execute: bool = False
    user_id: Optional[str] = None


@app.post("/autonomy/plan")
async def autonomy_plan(request: AutonomyRequest):
    """Proxy to Autonomy Engine — create and optionally execute a plan."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(
                f"{settings.autonomy_engine_url}/autonomy/plan",
                json=request.model_dump(),
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        except Exception as e:
            logger.error(f"Autonomy engine error: {e}")
            raise HTTPException(status_code=502, detail="Autonomy engine unreachable")


@app.get("/autonomy/plans")
async def autonomy_plans(limit: int = 20):
    """List autonomy plans."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(f"{settings.autonomy_engine_url}/autonomy/plans", params={"limit": limit})
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Autonomy list error: {e}")
            raise HTTPException(status_code=502, detail="Autonomy engine unreachable")


@app.post("/knowledge-graph/update")
async def kg_update(conversation_id: str, text: str, user_id: Optional[str] = None):
    """Update knowledge graph from conversation."""
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await client.post(
                f"{settings.knowledge_graph_url}/graph/update",
                json={"conversation_id": conversation_id, "text": text, "user_id": user_id},
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Knowledge graph update error: {e}")
            return {"error": "Knowledge graph update failed"}


# ── Contact Management API ──────────────────────────────────────

class ContactUpdateRequest(BaseModel):
    phone: str
    name: Optional[str] = None
    role: Optional[str] = None
    sub_role: Optional[str] = None
    language_pref: Optional[str] = None
    platform: str = "whatsapp"

class ContactLanguageRequest(BaseModel):
    phone: str
    language: str  # "bn", "en", "mixed"
    platform: str = "whatsapp"


@app.get("/contacts")
async def list_contacts(role: Optional[str] = None, platform: str = "whatsapp"):
    """List contacts, optionally filtered by role."""
    if not owner_policy:
        return {"contacts": []}
    try:
        if role:
            contacts = owner_policy.list_contacts_by_role(role, platform)
        else:
            # List all roles
            contacts = []
            for r in ["client", "employee", "family", "friend", "job_seeker", "unknown"]:
                contacts.extend(owner_policy.list_contacts_by_role(r, platform))
        return {
            "contacts": [
                {
                    "id": c.id,
                    "phone": c.phone,
                    "name": c.name,
                    "role": c.role,
                    "sub_role": c.sub_role,
                    "language_pref": c.language_pref,
                    "platform": c.platform,
                    "is_active": c.is_active,
                }
                for c in contacts
            ]
        }
    except Exception as e:
        logger.error(f"List contacts error: {e}")
        return {"contacts": [], "error": str(e)}


@app.post("/contacts/role")
async def set_contact_role(request: ContactUpdateRequest):
    """Set or update a contact's role and metadata."""
    if not owner_policy:
        raise HTTPException(status_code=503, detail="Owner policy not initialized")
    try:
        ok = owner_policy.set_contact_role(
            phone=request.phone,
            role=request.role or "unknown",
            name=request.name,
            sub_role=request.sub_role,
            platform=request.platform,
        )
        if request.language_pref:
            owner_policy.set_contact_language(request.phone, request.language_pref, request.platform)
        return {"status": "ok" if ok else "failed"}
    except Exception as e:
        logger.error(f"Set contact role error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/contacts/language")
async def set_contact_language(request: ContactLanguageRequest):
    """Set per-contact language preference."""
    if not owner_policy:
        raise HTTPException(status_code=503, detail="Owner policy not initialized")
    try:
        ok = owner_policy.set_contact_language(request.phone, request.language, request.platform)
        return {"status": "ok" if ok else "failed"}
    except Exception as e:
        logger.error(f"Set contact language error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/contacts/{phone}")
async def get_contact(phone: str, platform: str = "whatsapp"):
    """Get a single contact's details."""
    if not owner_policy:
        raise HTTPException(status_code=503, detail="Owner policy not initialized")
    try:
        cr = owner_policy.get_contact_role(phone, platform)
        if not cr:
            return {"contact": None}
        lang = owner_policy.get_effective_language(phone, platform)
        return {
            "contact": {
                "id": cr.id,
                "phone": cr.phone,
                "name": cr.name,
                "role": cr.role,
                "sub_role": cr.sub_role,
                "language_pref": cr.language_pref,
                "effective_language": lang,
                "platform": cr.platform,
                "is_active": cr.is_active,
            }
        }
    except Exception as e:
        logger.error(f"Get contact error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/knowledge-graph/stats")
async def kg_stats():
    """Get knowledge graph statistics."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{settings.knowledge_graph_url}/graph/stats")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Knowledge graph stats error: {e}")
            raise HTTPException(status_code=502, detail="Knowledge graph unreachable")


# ── Tree Memory Proxy Endpoints ─────────────────────────────

@app.post("/tree/store")
async def tree_store_proxy(request: dict):
    """Store a tree-tagged memory (proxied to memory service)."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(f"{settings.memory_url}/tree/store", json=request)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Tree store error: {e}")
            return {"error": "Tree store failed", "detail": str(e)}


@app.post("/tree/store-bulk")
async def tree_store_bulk_proxy(request: dict):
    """Store multiple tree memories (proxied to memory service)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(f"{settings.memory_url}/tree/store-bulk", json=request)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Tree store-bulk error: {e}")
            return {"error": "Tree store-bulk failed", "detail": str(e)}


@app.post("/tree/search")
async def tree_search_proxy(request: dict):
    """Semantic search in tree memories (proxied to memory service)."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(f"{settings.memory_url}/tree/search", json=request)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Tree search error: {e}")
            return {"error": "Tree search failed", "detail": str(e)}


@app.get("/tree/browse")
async def tree_browse_proxy():
    """Browse all tree memory paths (proxied to memory service)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{settings.memory_url}/tree/browse")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Tree browse error: {e}")
            return {"error": "Tree browse failed", "detail": str(e)}


@app.get("/tree/branch")
async def tree_branch_proxy(path: str, limit: int = 50):
    """Get memories under a tree branch (proxied to memory service)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{settings.memory_url}/tree/branch",
                params={"path": path, "limit": limit},
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Tree branch error: {e}")
            return {"error": "Tree branch failed", "detail": str(e)}


@app.get("/tree/structure")
async def tree_structure_proxy():
    """Get tree structure (proxied to knowledge graph)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{settings.knowledge_graph_url}/tree/structure")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Tree structure error: {e}")
            return {"error": "Tree structure failed", "detail": str(e)}


@app.post("/tree/add-branch")
async def tree_add_branch_proxy(request: dict):
    """Add a new tree branch (proxied to knowledge graph)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{settings.knowledge_graph_url}/tree/add-branch", json=request,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Tree add-branch error: {e}")
            return {"error": "Tree add-branch failed", "detail": str(e)}


@app.post("/self-learning/analyze")
async def sl_analyze(text: Optional[str] = None, focus_area: Optional[str] = None):
    """Trigger self-learning analysis."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                f"{settings.self_learning_url}/learning/analyze",
                json={"text": text, "focus_area": focus_area},
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Self-learning analyze error: {e}")
            raise HTTPException(status_code=502, detail="Self-learning engine unreachable")


@app.get("/self-learning/insights")
async def sl_insights(limit: int = 20):
    """Get self-learning insights."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{settings.self_learning_url}/learning/insights", params={"limit": limit},
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Self-learning insights error: {e}")
            raise HTTPException(status_code=502, detail="Self-learning engine unreachable")


# ── Agent-powered Streaming Chat ───────────────────────────
@app.post("/chat/agent/stream")
async def chat_agent_stream(request: AgentChatRequest):
    """Streaming multi-agent chat: smart router selects pipeline,
    agents enrich context, then LLM streams response."""
    conversation_id = request.conversation_id or str(uuid.uuid4())
    user_name = request.user_name or request.user or "Azim"
    relationship = request.relationship or "self"

    ctx = AgentContext(
        message=request.message,
        user_name=user_name,
        user_id=request.user_id,
        relationship=relationship,
        conversation_id=conversation_id,
        metadata={"source": request.source},
    )

    route = agent_manager.route_query(request.message, request.source)

    # Fast voice: stream directly from conversation agent
    if route == QueryRoute.FAST_VOICE:
        async def fast_stream():
            async for chunk in agent_manager.stream_fast(ctx):
                yield f"data: {json.dumps({'content': chunk, 'done': False})}\n\n"
            yield f"data: {json.dumps({'content': '', 'done': True})}\n\n"

        return StreamingResponse(
            fast_stream(),
            media_type="text/event-stream",
            headers={"X-Conversation-Id": conversation_id, "X-Route": route.value},
        )

    # Full/Conversation: run agents first, then stream LLM
    agent_result = await agent_manager.process(ctx, route)

    system_prompt = await build_system_prompt_async(
        user_name=user_name,
        relationship=relationship,
        user_id=request.user_id,
        learning_engine_url=settings.learning_engine_url,
    )

    voice_override = (
        "\n\nIMPORTANT: This is a voice conversation. "
        "Respond with ONLY your spoken reply as plain text. "
        "Do NOT use JSON format. Keep responses concise (1-3 sentences)."
    )

    enriched_parts = []
    if ctx.memories:
        enriched_parts.append("Relevant memories:")
        for m in ctx.memories[:3]:
            enriched_parts.append(f"- {m.get('text', '')}")
    if ctx.search_results:
        enriched_parts.append("\nSearch results:")
        for r in ctx.search_results[:3]:
            enriched_parts.append(f"- {r.get('title', '')}: {r.get('snippet', '')}")

    enriched_context = "\n".join(enriched_parts) if enriched_parts else ""

    history = conversation_get(conversation_id)
    messages = [
        {"role": "system", "content": system_prompt + voice_override + "\n" + enriched_context},
        *history[-6:],
        {"role": "user", "content": request.message},
    ]

    if settings.voice_fast_mode:
        stream_gen = stream_llm_voice(messages)
    else:
        stream_gen = stream_llm_gateway(messages)

    async def event_stream():
        full_reply = []
        async for chunk in stream_gen:
            full_reply.append(json.loads(chunk).get("content", ""))
            yield f"data: {chunk}\n\n"
        reply_text = "".join(full_reply)
        history.append({"role": "user", "content": request.message})
        history.append({"role": "assistant", "content": reply_text})
        conversation_set(conversation_id, history)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "X-Conversation-Id": conversation_id,
            "X-Route": route.value,
            "X-Agents-Used": ",".join(agent_result.get("agents_used", [])),
        },
    )


# ── System Status endpoint ─────────────────────────────────
@app.get("/status")
async def system_status():
    """Return comprehensive system status including multi-agent architecture info."""
    utility_agents = []
    domain_agents = []
    identity_info = None

    if agent_manager:
        for agent in agent_manager.agents:
            utility_agents.append({
                "name": agent.name,
                "description": agent.description,
            })
        for name in ("social", "voice", "system", "learning"):
            agent = agent_manager.strategy._domain_agents.get(name)
            if agent:
                domain_agents.append({
                    "name": agent.name,
                    "description": agent.description,
                })
        identity = agent_manager.identity
        identity_info = {
            "name": identity.name,
            "tone": identity.tone,
            "formality": identity.formality,
            "relationships": list(identity.communication_style.keys()),
            "behavior_rules_count": len(identity.behavior_rules),
            "overrides_active": bool(identity.owner_overrides),
        }

    from agents.strategy_agent import DomainRoute

    return {
        "service": "fazle-brain",
        "version": "3.0.0",
        "architecture": "multi-agent with identity core",
        "llm_provider": settings.llm_provider,
        "voice_fast_mode": settings.voice_fast_mode,
        "voice_fast_model": settings.voice_fast_model,
        "identity_core": identity_info,
        "strategy_agent": "active" if agent_manager else "inactive",
        "domain_agents": domain_agents,
        "utility_agents": utility_agents,
        "domain_routes": [r.value for r in DomainRoute],
        "utility_routes": [r.value for r in QueryRoute],
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── Knowledge Lifecycle API ──────────────────────────────────

class KnowledgeCreateRequest(BaseModel):
    category: str
    key: str
    value: str
    source: str = "manual_text"
    language: str = "bn"
    confidence: float = 1.0


class KnowledgeReplaceRequest(BaseModel):
    category: str
    key: str
    new_value: str
    reason: str = ""


class KnowledgeMergeRequest(BaseModel):
    category: str
    source_keys: list[str]
    merged_key: str
    merged_value: str
    reason: str = ""


@app.post("/knowledge/create")
async def knowledge_create(req: KnowledgeCreateRequest):
    """Create new knowledge item in the lifecycle engine."""
    if not knowledge_lifecycle:
        raise HTTPException(status_code=503, detail="Knowledge lifecycle not initialized")
    item = knowledge_lifecycle.create(
        category=req.category, key=req.key, value=req.value,
        source=req.source, language=req.language, confidence=req.confidence,
    )
    if item:
        return {"status": "created", "id": item.id, "category": item.category, "key": item.key}
    raise HTTPException(status_code=500, detail="Failed to create knowledge")


@app.post("/knowledge/replace")
async def knowledge_replace(req: KnowledgeReplaceRequest):
    """Replace existing knowledge with new value."""
    if not knowledge_lifecycle:
        raise HTTPException(status_code=503, detail="Knowledge lifecycle not initialized")
    item = knowledge_lifecycle.replace(
        category=req.category, key=req.key, new_value=req.new_value, reason=req.reason,
    )
    if item:
        return {"status": "replaced", "id": item.id, "version": item.version}
    raise HTTPException(status_code=500, detail="Failed to replace knowledge")


@app.post("/knowledge/deprecate")
async def knowledge_deprecate(category: str, key: str, reason: str = ""):
    """Deprecate a knowledge item."""
    if not knowledge_lifecycle:
        raise HTTPException(status_code=503, detail="Knowledge lifecycle not initialized")
    ok = knowledge_lifecycle.deprecate(category=category, key=key, reason=reason)
    return {"status": "deprecated" if ok else "not_found"}


@app.post("/knowledge/archive")
async def knowledge_archive(category: str, key: str, reason: str = ""):
    """Archive a knowledge item."""
    if not knowledge_lifecycle:
        raise HTTPException(status_code=503, detail="Knowledge lifecycle not initialized")
    ok = knowledge_lifecycle.archive(category=category, key=key, reason=reason)
    return {"status": "archived" if ok else "not_found"}


@app.post("/knowledge/merge")
async def knowledge_merge(req: KnowledgeMergeRequest):
    """Merge multiple knowledge items into one."""
    if not knowledge_lifecycle:
        raise HTTPException(status_code=503, detail="Knowledge lifecycle not initialized")
    item = knowledge_lifecycle.merge(
        category=req.category, source_keys=req.source_keys,
        merged_key=req.merged_key, merged_value=req.merged_value, reason=req.reason,
    )
    if item:
        return {"status": "merged", "id": item.id}
    raise HTTPException(status_code=500, detail="Failed to merge knowledge")


@app.get("/knowledge/search")
async def knowledge_search(q: str, category: str = "", limit: int = 20):
    """Search active knowledge items."""
    if not knowledge_lifecycle:
        raise HTTPException(status_code=503, detail="Knowledge lifecycle not initialized")
    items = knowledge_lifecycle.search(q, category=category or None, limit=limit)
    return {"results": [{"id": i.id, "category": i.category, "key": i.key, "value": i.value,
                          "version": i.version, "confidence": i.confidence, "source": i.source}
                         for i in items]}


@app.get("/knowledge/active")
async def knowledge_active(category: str = "", limit: int = 50):
    """Get all active knowledge items."""
    if not knowledge_lifecycle:
        raise HTTPException(status_code=503, detail="Knowledge lifecycle not initialized")
    items = knowledge_lifecycle.get_active(category=category or None, limit=limit)
    return {"items": [{"id": i.id, "category": i.category, "key": i.key, "value": i.value,
                        "status": i.status.value, "version": i.version, "confidence": i.confidence,
                        "source": i.source, "language": i.language, "created_at": i.created_at}
                       for i in items]}


@app.get("/knowledge/history")
async def knowledge_history(category: str, key: str):
    """Get version history of a knowledge item."""
    if not knowledge_lifecycle:
        raise HTTPException(status_code=503, detail="Knowledge lifecycle not initialized")
    items = knowledge_lifecycle.get_history(category, key)
    return {"history": [{"id": i.id, "value": i.value, "version": i.version,
                          "status": i.status.value, "created_at": i.created_at}
                         for i in items]}


# ── Teaching API ─────────────────────────────────────────────

class TeachRequest(BaseModel):
    content: str
    source: str = "manual_text"
    category: str = ""
    key: str = ""
    language: str = "bn"


class TeachCorrectionRequest(BaseModel):
    correction: str
    original_query: str = ""
    original_reply: str = ""
    platform: str = "web"


@app.post("/teach")
async def teach(req: TeachRequest):
    """Unified teaching endpoint — accepts knowledge from any source."""
    if not teaching_pipeline:
        raise HTTPException(status_code=503, detail="Teaching pipeline not initialized")
    from teaching_pipeline import TeachingInput, TeachingSource
    source_map = {
        "manual_text": TeachingSource.MANUAL_TEXT,
        "web_chat": TeachingSource.WEB_CHAT,
        "file_upload": TeachingSource.FILE_UPLOAD,
        "audio_transcript": TeachingSource.AUDIO_TRANSCRIPT,
        "image_ocr": TeachingSource.IMAGE_OCR,
        "web_scrape": TeachingSource.WEB_SCRAPE,
    }
    result = teaching_pipeline.teach(TeachingInput(
        content=req.content,
        source=source_map.get(req.source, TeachingSource.MANUAL_TEXT),
        category=req.category,
        key=req.key,
        language=req.language,
    ))
    return {"success": result.success, "knowledge_id": result.knowledge_id,
            "approval": result.approval_status.value, "message": result.message,
            "error": result.error}


@app.post("/teach/correction")
async def teach_correction(req: TeachCorrectionRequest):
    """Teach Fazle from owner correction of AI reply."""
    if not teaching_pipeline:
        raise HTTPException(status_code=503, detail="Teaching pipeline not initialized")
    result = teaching_pipeline.teach_from_correction(
        correction_text=req.correction,
        original_query=req.original_query,
        original_reply=req.original_reply,
        platform=req.platform,
    )
    return {"success": result.success, "knowledge_id": result.knowledge_id,
            "message": result.message}


@app.post("/teach/audio")
async def teach_audio(transcript: str, confidence: float = 0.8, sender_id: str = "owner"):
    """Teach from audio transcription."""
    if not teaching_pipeline:
        raise HTTPException(status_code=503, detail="Teaching pipeline not initialized")
    result = teaching_pipeline.teach_from_audio(transcript, confidence, sender_id)
    return {"success": result.success, "knowledge_id": result.knowledge_id}
