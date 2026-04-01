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
    use_llm_gateway: bool = True
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


@app.on_event("startup")
async def init_agents():
    global agent_manager
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

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://fazle.iamazim.com,https://iamazim.com,http://localhost:3020").split(",")

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
_LLM_TIMEOUT_GATEWAY = 4.0    # Gateway: 4s per-provider cap
_LLM_TIMEOUT_OPENAI = 5.0     # Direct OpenAI: 5s per-provider cap
_LLM_TIMEOUT_OLLAMA = 5.0     # Local Ollama: 5s per-provider cap
_LLM_TIMEOUT_FAST = 4.0       # Fast model fallback: 4s cap
_LLM_PARALLEL_GLOBAL = 6.0    # Global parallel timeout: 6s max total

_FALLBACK_REPLY_BN = "দুঃখিত, একটু সমস্যা হচ্ছে। একটু পরে আবার চেষ্টা করুন।"
_FALLBACK_REPLY_EN = "Sorry, having a small issue. Please try again shortly."


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
    async with httpx.AsyncClient(timeout=_LLM_TIMEOUT_OLLAMA) as client:
        resp = await client.post(
            f"{settings.ollama_url}/api/chat",
            json={
                "model": settings.ollama_model,
                "messages": messages,
                "stream": False,
                "format": "json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return json.loads(data["message"]["content"])


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
                    "format": "json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return json.loads(data["message"]["content"])
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
    """Parallel LLM routing — fires Gateway + OpenAI + Ollama simultaneously.
    First successful response wins; others are cancelled.
    Global timeout: 6s. Falls back to fast model, then static Bangla reply."""
    model_override = None
    route_label = "full"

    if complexity == "simple":
        model_override = "gpt-4o-mini"
        route_label = "fast"
    elif complexity == "complex":
        model_override = settings.llm_model  # gpt-4o
        route_label = "complex"

    t0 = _time.monotonic()

    # ── Priority weights (lower = preferred when two finish close together) ──
    _PRIORITY = {"gateway": 0, "openai_direct": 1, "ollama": 2}

    # ── Build provider coroutines ──
    async def _provider_gateway():
        return await _query_gateway_with_model(messages, model_override)

    async def _provider_openai():
        return await _query_openai_with_model(messages, model_override)

    async def _provider_ollama():
        return await query_ollama(messages)

    providers: list[tuple[str, asyncio.Task]] = []
    if settings.use_llm_gateway:
        providers.append(("gateway", asyncio.create_task(_provider_gateway())))
    if settings.openai_api_key:
        providers.append(("openai_direct", asyncio.create_task(_provider_openai())))
    providers.append(("ollama", asyncio.create_task(_provider_ollama())))

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

    # ── Static fallback — NEVER silent ──
    intel_usage_track("static_fallback", route="emergency_static")
    logger.error(f"LLM ALL PROVIDERS FAILED — returning safe fallback. chain={failed_providers}")
    return {
        "reply": _FALLBACK_REPLY_BN,
        "memory_updates": [],
        "actions": [],
    }


async def _query_gateway_with_model(messages: list[dict], model: str = None) -> dict:
    """Call LLM Gateway with optional model override. 5s hard timeout."""
    payload = {
        "messages": messages,
        "response_format": "json",
        "caller": "fazle-brain",
        "temperature": 0.7,
    }
    if model:
        payload["model"] = model
    async with httpx.AsyncClient(timeout=_LLM_TIMEOUT_GATEWAY) as client:
        resp = await client.post(f"{settings.llm_gateway_url}/generate", json=payload)
        resp.raise_for_status()
        return json.loads(resp.json()["content"])


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
                "format": "json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return json.loads(data["message"]["content"])


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

    # ── Voice Agent: identity enforcement via strategy ──
    voice_system_prompt = system_prompt + memory_context + voice_history_ctx + voice_anti_rep
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
                voice_system_prompt = domain_prompt + memory_context + voice_history_ctx + voice_anti_rep
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

    # ── STEP 2: Owner Priority Interrupt ──
    await _check_owner_priority(relationship)

    # ── STEP 3: Fast Response Path ──
    complexity = _classify_query_complexity(request.message)

    # Ultra-simple queries: skip heavy pipeline entirely
    if complexity == "simple" and relationship in ("self", "wife", "parent", "sibling"):
        history = conversation_get(conversation_id)
        from persona_engine import build_identity_context as _bic
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
            history.append({"role": "user", "content": request.message})
            history.append({"role": "assistant", "content": reply})
            conversation_set(conversation_id, history)
            fast_presence = _compute_presence(request.message, reply, "simple", relationship)
            return {"reply": reply, "conversation_id": conversation_id, "memory_updates": [], "route": "fast", "presence": fast_presence}
        except Exception:
            pass  # Fall through to full pipeline

    # Trusted relationships skip input moderation for speed
    trusted = relationship in ("self", "wife", "parent", "sibling")

    if not trusted:
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
    if relationship == "social":
        from persona_engine import classify_social_intent
        intent = classify_social_intent(request.message)
        context_parts = [f"user_intent: {intent}"]
        if request.context:
            context_parts.append(request.context)
        social_context = "\n".join(context_parts)

    # Run persona build + memory searches in parallel (hybrid: general + knowledge + personal)
    system_prompt_task = build_system_prompt_async(
        user_name=user_name,
        relationship=relationship,
        user_id=user_id,
        learning_engine_url=settings.learning_engine_url,
        social_context=social_context,
    )
    mem_task = retrieve_memories(request.message, user_id=user_id, limit=3)
    mm_task = retrieve_multimodal_memories(request.message, user_id=user_id, limit=2)
    knowledge_task = retrieve_memories(request.message, memory_type="knowledge", user_id=user_id, limit=2)
    personal_task = retrieve_memories(request.message, memory_type="personal", user_id=user_id, limit=2)

    system_prompt, memories, mm_memories, knowledge_mems, personal_mems = await asyncio.gather(
        system_prompt_task, mem_task, mm_task, knowledge_task, personal_task,
    )
    # Merge long-term knowledge/personal memories (deduplicated) with general
    seen_texts = {m.get("text", "") for m in memories}
    for m in knowledge_mems + personal_mems:
        if m.get("text", "") not in seen_texts:
            memories.append(m)
            seen_texts.add(m.get("text", ""))
    memory_context = _format_memory_context(memories, mm_memories)

    # ── User-scoped conversation intelligence ───────────────
    # Determine platform + user identifier for memory isolation
    platform = "app"
    user_identifier = user_id or conversation_id
    if conversation_id and conversation_id.startswith("social-"):
        parts = conversation_id.split("-", 2)
        if len(parts) >= 3:
            platform = parts[1]  # whatsapp, facebook
            user_identifier = parts[2]  # sender phone/id

    # Fetch user-scoped recent history (isolated per user)
    user_history = user_history_get(platform, user_identifier, limit=10)
    user_history_context = build_user_history_context(user_history)

    # Anti-repetition: check recent AI replies for this user
    recent_replies = user_replies_get(platform, user_identifier, limit=5)
    anti_rep_context = build_anti_repetition_context(recent_replies)

    # Context awareness: new vs returning user
    user_type = detect_user_type(user_history)
    awareness_context = build_context_awareness(user_type)

    # ── Owner style learning (STEP 6) ──────────────────────
    # For social messages, search for similar owner training examples
    owner_style_context = ""
    if relationship == "social":
        try:
            owner_examples = await retrieve_memories(
                request.message, memory_type="knowledge", user_id="owner", limit=3,
            )
            # Filter to only owner_training entries
            owner_training = [
                m for m in owner_examples
                if "owner" in m.get("text", "").lower() or
                   (isinstance(m.get("content"), dict) and m["content"].get("kind") == "owner_training")
            ]
            owner_style_context = build_owner_style_context(owner_training)
        except Exception as e:
            logger.debug(f"Owner style search failed: {e}")

    # Inject all context into system prompt
    system_prompt = system_prompt + memory_context + user_history_context + anti_rep_context + awareness_context + owner_style_context

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
            # If domain agent produced an identity-enhanced prompt, use it
            domain_prompt = domain_result.get("system_prompt")
            if domain_prompt:
                system_prompt = domain_prompt + memory_context + user_history_context + anti_rep_context + awareness_context + owner_style_context
            else:
                # Enforce identity core on the existing prompt
                identity_prompt = domain_result.get("identity_prompt", "")
                if identity_prompt:
                    system_prompt = identity_prompt + "\n\n" + system_prompt
        except Exception as e:
            logger.debug(f"Domain routing skipped: {e}")

    # Build conversation history
    history = conversation_get(conversation_id)
    messages = [
        {"role": "system", "content": system_prompt},
        *history[-10:],  # Keep last 10 turns
        {"role": "user", "content": request.message},
    ]

    # ── STEP 4: Cost-optimized LLM call with failover ──
    try:
        result = await query_llm_smart(messages, complexity=complexity)
    except Exception as e:
        logger.error(f"LLM unexpected error (all failovers exhausted): {e}")
        result = {"reply": _FALLBACK_REPLY_BN, "memory_updates": [], "actions": []}

    reply = result.get("reply", _FALLBACK_REPLY_BN)
    memory_updates = result.get("memory_updates", [])
    actions = result.get("actions", [])

    # ── STEP 1: Question Strategy — confidence check ──
    if _detect_low_confidence(reply) and relationship in ("self", "wife", "parent", "sibling"):
        reply = reply.rstrip(". ") + "\n\n(আমি পুরোপুরি sure না — তুমি কি আরেকটু detail দিবে?)"

    # Content safety check on LLM output (skip for trusted users)
    if not trusted:
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
    """Store an owner correction as training data."""
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
    conv = await conversation_get(conv_id, settings.redis_url)

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

    extracted_text = ""

    if media_type == "image" and media_b64:
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
        result = await query_llm(messages)
    except Exception as e:
        logger.error(f"Multimodal chat LLM error: {e}")
        return {"reply": "দুঃখিত, একটু সমস্যা হচ্ছে।", "extracted_text": extracted_text, "conversation_id": conversation_id}

    reply = result.get("reply", "")
    history.append({"role": "user", "content": user_msg})
    history.append({"role": "assistant", "content": reply})
    conversation_set(conversation_id, history)

    return {"reply": reply, "extracted_text": extracted_text, "conversation_id": conversation_id}


# ── Owner profile auto-extraction from chat ─────────────────

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
