# ============================================================
# Fazle LLM Gateway — Centralized LLM Routing & Caching
# Single point for all LLM calls with caching, streaming,
# model fallback, rate limiting, batching, and usage tracking
# ============================================================
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Counter, Histogram
import httpx
import json
import logging
import hashlib
import time
import asyncio
import os
import uuid
from typing import Optional
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
import redis

from structured_log import setup_structured_logging
setup_structured_logging("fazle-llm-gateway")
logger = logging.getLogger("fazle-llm-gateway")


class Settings(BaseSettings):
    openai_api_key: str = ""
    ollama_url: str = "http://ollama:11434"
    llm_provider: str = "ollama"           # Ollama-first
    llm_model: str = "qwen2.5:1.5b"
    ollama_model: str = "qwen2.5:1.5b"
    redis_url: str = "redis://redis:6379/3"
    database_url: str = ""                 # PostgreSQL for conversation logging
    # Fallback model when primary fails or times out
    fallback_provider: str = "openai"
    fallback_model: str = "gpt-4o"
    # Ollama timeout in seconds — if exceeded, fallback to OpenAI (env: FAZLE_OLLAMA_TIMEOUT)
    ollama_timeout: int = int(os.environ.get("FAZLE_OLLAMA_TIMEOUT", "25"))
    # Cache TTL in seconds (0 = disabled)
    cache_ttl: int = 300
    # Rate limit: max requests per minute per caller
    rate_limit_rpm: int = 60
    # Per-user rate limit: max requests per second
    rate_limit_per_user_rps: int = 10
    # Max prompt tokens before compression is suggested
    max_context_tokens: int = 4096
    # Batching: collect requests for this window before sending
    batch_window_ms: int = 75  # 50-100ms sweet spot
    batch_max_size: int = 8

    class Config:
        env_prefix = ""


settings = Settings()

_redis: Optional[redis.Redis] = None


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


# ── PostgreSQL Conversation Logging ─────────────────────────

_DB_INIT_DONE = False


def _get_db_conn():
    """Get a PostgreSQL connection for logging. Returns None if no DB configured."""
    if not settings.database_url:
        return None
    return psycopg2.connect(settings.database_url)


def _ensure_log_table():
    """Create llm_conversation_log table if it doesn't exist."""
    global _DB_INIT_DONE
    if _DB_INIT_DONE or not settings.database_url:
        return
    try:
        conn = _get_db_conn()
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS llm_conversation_log (
                    id BIGSERIAL PRIMARY KEY,
                    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    caller VARCHAR(100),
                    user_id VARCHAR(200),
                    provider VARCHAR(20) NOT NULL,
                    model VARCHAR(100) NOT NULL,
                    messages JSONB NOT NULL,
                    reply TEXT NOT NULL,
                    usage_data JSONB,
                    latency_ms REAL,
                    is_fallback BOOLEAN DEFAULT FALSE,
                    trainable BOOLEAN DEFAULT FALSE,
                    request_type VARCHAR(30) DEFAULT 'user_chat',
                    fallback_reason VARCHAR(30),
                    endpoint VARCHAR(30) DEFAULT 'chat',
                    user_role VARCHAR(30),
                    message_length INT,
                    response_length INT
                );
                CREATE INDEX IF NOT EXISTS idx_llm_log_ts ON llm_conversation_log(ts);
                CREATE INDEX IF NOT EXISTS idx_llm_log_trainable ON llm_conversation_log(trainable) WHERE trainable = TRUE;
                CREATE INDEX IF NOT EXISTS idx_llm_log_request_type ON llm_conversation_log(request_type);
                CREATE INDEX IF NOT EXISTS idx_llm_log_provider ON llm_conversation_log(provider);
            """)
            # Add columns if they don't exist (for existing tables)
            for col, col_def in [
                ("request_type", "VARCHAR(30) DEFAULT 'user_chat'"),
                ("fallback_reason", "VARCHAR(30)"),
                ("endpoint", "VARCHAR(30) DEFAULT 'chat'"),
                ("user_role", "VARCHAR(30)"),
                ("message_length", "INT"),
                ("response_length", "INT"),
            ]:
                try:
                    cur.execute(f"ALTER TABLE llm_conversation_log ADD COLUMN IF NOT EXISTS {col} {col_def}")
                except Exception:
                    pass
        conn.commit()
        conn.close()
        _DB_INIT_DONE = True
        logger.info("llm_conversation_log table ready")
    except Exception as e:
        logger.warning(f"Could not init DB log table: {e}")


def _log_to_db(caller: str, user_id: str, provider: str, model: str,
               messages: list[dict], reply: str, usage: dict,
               latency_ms: float, is_fallback: bool,
               request_type: str = "user_chat", fallback_reason: str = None,
               endpoint: str = "chat", user_role: str = None,
               message_length: int = None, response_length: int = None):
    """Persist every LLM exchange to PostgreSQL (fire-and-forget)."""
    if not settings.database_url:
        return
    try:
        conn = _get_db_conn()
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO llm_conversation_log
                   (caller, user_id, provider, model, messages, reply, usage_data,
                    latency_ms, is_fallback, trainable, request_type, fallback_reason,
                    endpoint, user_role, message_length, response_length)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (caller, user_id, provider, model,
                 json.dumps(messages), reply,
                 json.dumps(usage), latency_ms,
                 is_fallback, is_fallback and provider == "openai",
                 request_type, fallback_reason,
                 endpoint, user_role, message_length, response_length),
            )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug(f"DB log write error: {e}")


app = FastAPI(title="Fazle LLM Gateway", version="2.0.0")

Instrumentator().instrument(app).expose(app, endpoint="/metrics")


@app.middleware("http")
async def request_id_middleware(request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ── Prometheus Counters & Histograms ────────────────────────

cache_hits_total = Counter(
    "llm_cache_hits_total",
    "Total cache hits in LLM Gateway",
)
cache_misses_total = Counter(
    "llm_cache_misses_total",
    "Total cache misses in LLM Gateway",
)
llm_request_latency_hist = Histogram(
    "llm_request_latency_seconds",
    "LLM provider call latency in seconds",
    ["provider"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0],
)
llm_requests_total = Counter(
    "llm_requests_total",
    "Total LLM requests by provider and status",
    ["provider", "status"],
)
rate_limited_total = Counter(
    "llm_rate_limited_total",
    "Total requests rejected by rate limiter",
    ["limiter"],
)

ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "https://fazle.iamazim.com,https://iamazim.com",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ─────────────────────────────────────────────────

def _cache_key(messages: list[dict], model: str, response_format: Optional[str]) -> str:
    """Deterministic cache key from prompt + model."""
    payload = json.dumps({"m": messages, "model": model, "fmt": response_format}, sort_keys=True)
    return f"llm_cache:{hashlib.sha256(payload.encode()).hexdigest()}"


def _check_rate_limit(caller: str) -> bool:
    """Sliding-window rate limiter. Returns True if allowed."""
    if settings.rate_limit_rpm <= 0:
        return True
    r = _get_redis()
    key = f"llm_rl:{caller}"
    now = int(time.time())
    window_start = now - 60

    pipe = r.pipeline()
    pipe.zremrangebyscore(key, 0, window_start)
    pipe.zadd(key, {str(now) + ":" + os.urandom(4).hex(): now})
    pipe.zcard(key)
    pipe.expire(key, 120)
    results = pipe.execute()
    count = results[2]
    return count <= settings.rate_limit_rpm


def _check_user_rate_limit(user_id: str) -> bool:
    """Per-user sliding-window rate limiter (10 req/s). Returns True if allowed."""
    if settings.rate_limit_per_user_rps <= 0:
        return True
    r = _get_redis()
    key = f"llm_url:{user_id}"
    now_ms = int(time.time() * 1000)
    window_start = now_ms - 1000  # 1-second window

    pipe = r.pipeline()
    pipe.zremrangebyscore(key, 0, window_start)
    pipe.zadd(key, {f"{now_ms}:{os.urandom(4).hex()}": now_ms})
    pipe.zcard(key)
    pipe.expire(key, 5)
    results = pipe.execute()
    count = results[2]
    return count <= settings.rate_limit_per_user_rps


def _estimate_tokens(messages: list[dict]) -> int:
    """Rough token estimate (4 chars ≈ 1 token)."""
    total_chars = sum(len(m.get("content", "")) for m in messages)
    return total_chars // 4


# ── Provider Calls ──────────────────────────────────────────

async def _call_openai(
    messages: list[dict],
    model: str,
    temperature: float,
    response_format: Optional[str],
    api_key: str,
    max_tokens: Optional[int] = None,
) -> dict:
    """Call OpenAI chat completions API."""
    body: dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if response_format == "json":
        body["response_format"] = {"type": "json_object"}
    if max_tokens is not None:
        body["max_tokens"] = max_tokens

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return {
            "content": content,
            "model": data.get("model", model),
            "provider": "openai",
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
        }


async def _call_ollama(
    messages: list[dict],
    model: str,
    temperature: float,
    response_format: Optional[str],
    max_tokens: Optional[int] = None,
) -> dict:
    """Call local Ollama chat API."""
    options = {"temperature": temperature, "num_ctx": 4096}
    if max_tokens is not None:
        options["num_predict"] = max_tokens
    body: dict = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": options,
    }
    # NEVER force JSON format on Ollama — causes 500 when model can't produce valid JSON

    async with httpx.AsyncClient(timeout=float(settings.ollama_timeout)) as client:
        resp = await client.post(
            f"{settings.ollama_url}/api/chat",
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["message"]["content"]
        return {
            "content": content,
            "model": data.get("model", model),
            "provider": "ollama",
            "usage": {
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            },
        }


async def _call_provider(
    provider: str,
    model: str,
    messages: list[dict],
    temperature: float,
    response_format: Optional[str],
    max_tokens: Optional[int] = None,
) -> dict:
    """Route to the correct LLM provider."""
    if provider == "ollama":
        return await _call_ollama(messages, model, temperature, response_format, max_tokens)
    elif provider == "openai":
        return await _call_openai(messages, model, temperature, response_format, settings.openai_api_key, max_tokens)
    else:
        raise ValueError(f"Unknown provider: {provider}")


# ── Streaming ───────────────────────────────────────────────

async def _stream_openai(
    messages: list[dict],
    model: str,
    temperature: float,
    response_format: Optional[str],
    api_key: str,
    max_tokens: Optional[int] = None,
):
    """Stream from OpenAI chat completions."""
    body: dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    if response_format == "json":
        body["response_format"] = {"type": "json_object"}
    if max_tokens is not None:
        body["max_tokens"] = max_tokens

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    chunk = line[6:]
                    if chunk.strip() == "[DONE]":
                        yield "data: [DONE]\n\n"
                        break
                    yield f"data: {chunk}\n\n"


async def _stream_ollama(
    messages: list[dict],
    model: str,
    temperature: float,
    response_format: Optional[str],
    max_tokens: Optional[int] = None,
):
    """Stream from Ollama chat API."""
    options = {"temperature": temperature, "num_ctx": 4096}
    if max_tokens is not None:
        options["num_predict"] = max_tokens
    body: dict = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": options,
    }
    if response_format == "json":
        body["format"] = "json"

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{settings.ollama_url}/api/chat",
            json=body,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.strip():
                    data = json.loads(line)
                    chunk_content = data.get("message", {}).get("content", "")
                    done = data.get("done", False)
                    sse = json.dumps({"content": chunk_content, "done": done})
                    yield f"data: {sse}\n\n"
                    if done:
                        break


# ── Request Batching ────────────────────────────────────────

class _BatchEntry:
    """One pending request in the batch window."""
    __slots__ = ("provider", "model", "messages", "temperature",
                 "response_format", "max_tokens", "future")

    def __init__(self, provider, model, messages, temperature, response_format, max_tokens=None):
        self.provider = provider
        self.model = model
        self.messages = messages
        self.temperature = temperature
        self.response_format = response_format
        self.max_tokens = max_tokens
        self.future: asyncio.Future = asyncio.get_event_loop().create_future()


class _RequestBatcher:
    """Collects requests within a time window and dispatches them together.

    For providers that support true batching (e.g. Ollama parallel mode),
    requests sharing the same provider+model are grouped.  For others each
    request is still dispatched individually but the window lets us coalesce
    cache key lookups and rate-limit checks.
    """

    def __init__(self):
        self._pending: list[_BatchEntry] = []
        self._timer: Optional[asyncio.TimerHandle] = None
        self._lock = asyncio.Lock()

    async def submit(self, entry: _BatchEntry):
        """Add a request and wait for its result."""
        async with self._lock:
            self._pending.append(entry)
            if len(self._pending) >= settings.batch_max_size:
                batch = list(self._pending)
                self._pending.clear()
                if self._timer:
                    self._timer.cancel()
                    self._timer = None
                asyncio.create_task(self._dispatch(batch))
            elif self._timer is None:
                loop = asyncio.get_event_loop()
                self._timer = loop.call_later(
                    settings.batch_window_ms / 1000.0,
                    lambda: asyncio.create_task(self._flush()),
                )
        return await entry.future

    async def _flush(self):
        async with self._lock:
            if not self._pending:
                return
            batch = list(self._pending)
            self._pending.clear()
            self._timer = None
        await self._dispatch(batch)

    async def _dispatch(self, batch: list[_BatchEntry]):
        """Send all collected requests concurrently."""
        tasks = []
        for entry in batch:
            tasks.append(self._call_one(entry))
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _call_one(self, entry: _BatchEntry):
        try:
            result = await _call_provider(
                entry.provider, entry.model, entry.messages,
                entry.temperature, entry.response_format, entry.max_tokens,
            )
            entry.future.set_result(result)
        except Exception as e:
            if not entry.future.done():
                entry.future.set_exception(e)


_batcher = _RequestBatcher()


# ── Request / Response Models ───────────────────────────────

class GenerateRequest(BaseModel):
    messages: list[dict] = Field(..., description="Chat messages array")
    provider: Optional[str] = Field(None, description="Override provider (openai/ollama)")
    model: Optional[str] = Field(None, description="Override model name")
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, description="Max tokens to generate (maps to num_predict for Ollama)")
    response_format: Optional[str] = Field(None, description="'json' for JSON mode")
    caller: str = Field("unknown", description="Calling service name for rate limiting")
    user_id: Optional[str] = Field(None, description="End-user ID for per-user rate limiting")
    stream: bool = Field(False, description="Enable SSE streaming")
    cache: bool = Field(True, description="Use response cache if available")
    context_inject: Optional[str] = Field(None, description="Extra context to prepend to system prompt")
    request_type: str = Field("user_chat", description="Request type: user_chat, owner_analysis, memory, system. Only user_chat gets OpenAI fallback.")


class GenerateResponse(BaseModel):
    content: str
    model: str
    provider: str
    usage: dict = Field(default_factory=dict)
    cached: bool = False
    latency_ms: float = 0


class EmbeddingRequest(BaseModel):
    text: str = Field(..., description="Text to embed")
    model: str = Field("text-embedding-3-small", description="Embedding model")


class EmbeddingResponse(BaseModel):
    embedding: list[float]
    model: str
    dimensions: int


# ── Endpoints ───────────────────────────────────────────────

@app.get("/health")
async def health():
    healthy = True
    checks = {}
    # Check Redis
    try:
        _get_redis().ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"
        healthy = False
    return {
        "status": "healthy" if healthy else "degraded",
        "service": "fazle-llm-gateway",
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest):
    """Unified LLM generation endpoint with caching, fallback, batching, and rate limiting."""
    # Per-caller rate limit (RPM)
    if not _check_rate_limit(request.caller):
        rate_limited_total.labels(limiter="caller_rpm").inc()
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    # Per-user rate limit (RPS)
    user_id = request.user_id or request.caller
    if not _check_user_rate_limit(user_id):
        rate_limited_total.labels(limiter="user_rps").inc()
        raise HTTPException(status_code=429, detail="Per-user rate limit exceeded")

    provider = request.provider or settings.llm_provider
    model = request.model or (settings.ollama_model if provider == "ollama" else settings.llm_model)
    messages = list(request.messages)

    # Context injection
    if request.context_inject and messages and messages[0].get("role") == "system":
        messages[0] = {
            "role": "system",
            "content": messages[0]["content"] + "\n\n" + request.context_inject,
        }

    # Context size warning
    estimated_tokens = _estimate_tokens(messages)
    if estimated_tokens > settings.max_context_tokens:
        logger.warning(f"Large context ({estimated_tokens} est. tokens) from {request.caller}")

    # Streaming path
    if request.stream:
        if provider == "openai":
            gen = _stream_openai(messages, model, request.temperature, request.response_format, settings.openai_api_key, request.max_tokens)
        else:
            gen = _stream_ollama(messages, model, request.temperature, request.response_format, request.max_tokens)
        return StreamingResponse(gen, media_type="text/event-stream")

    # Cache check
    cache_key = _cache_key(messages, model, request.response_format)
    if request.cache and settings.cache_ttl > 0:
        try:
            cached = _get_redis().get(cache_key)
            if cached:
                cache_hits_total.inc()
                data = json.loads(cached)
                data["cached"] = True
                return GenerateResponse(**data)
        except Exception as e:
            logger.debug(f"Cache read error: {e}")
    cache_misses_total.inc()

    # Primary call (via batcher for coalescing)
    start = time.monotonic()
    result = None
    is_fallback = False
    fallback_reason = None
    try:
        entry = _BatchEntry(provider, model, messages, request.temperature, request.response_format, request.max_tokens)
        result = await _batcher.submit(entry)
        llm_request_latency_hist.labels(provider=provider).observe(time.monotonic() - start)
        llm_requests_total.labels(provider=provider, status="success").inc()
    except Exception as primary_err:
        primary_elapsed = time.monotonic() - start
        llm_request_latency_hist.labels(provider=provider).observe(primary_elapsed)
        llm_requests_total.labels(provider=provider, status="failed").inc()
        is_timeout = isinstance(primary_err, (httpx.ReadTimeout, httpx.ConnectTimeout, asyncio.TimeoutError))
        fallback_reason = "timeout" if is_timeout else "error"
        logger.warning(f"Primary LLM failed ({provider}/{model}): {fallback_reason.upper()} | request_type={request.request_type} | caller={request.caller}")

        # Conditional fallback: only user_chat gets OpenAI fallback
        fb_provider = settings.fallback_provider
        fb_model = settings.fallback_model
        allow_fallback = request.request_type == "user_chat" and (fb_provider != provider or fb_model != model)

        if allow_fallback:
            try:
                logger.info(f"Falling back to {fb_provider}/{fb_model} (request_type={request.request_type})")
                fb_start = time.monotonic()
                result = await _call_provider(fb_provider, fb_model, messages, request.temperature, request.response_format, request.max_tokens)
                is_fallback = True
                llm_request_latency_hist.labels(provider=fb_provider).observe(time.monotonic() - fb_start)
                llm_requests_total.labels(provider=fb_provider, status="success").inc()
            except Exception as fb_err:
                llm_requests_total.labels(provider=fb_provider, status="failed").inc()
                logger.error(f"Fallback LLM also failed: {fb_err}")
                raise HTTPException(status_code=502, detail="All LLM providers unavailable") from fb_err
        else:
            # Fallback blocked — return controlled response instead of 502
            if fb_provider == provider and fb_model == model:
                raise HTTPException(status_code=502, detail="LLM service unavailable") from primary_err
            logger.info(f"Fallback BLOCKED for request_type={request.request_type} caller={request.caller} reason={fallback_reason}")
            latency_ms = (time.monotonic() - start) * 1000
            _msg_len = sum(len(m.get("content", "")) for m in messages)
            _log_to_db(
                caller=request.caller,
                user_id=user_id,
                provider=provider,
                model=model,
                messages=messages,
                reply="[fallback_blocked]",
                usage={},
                latency_ms=round(latency_ms, 1),
                is_fallback=False,
                request_type=request.request_type,
                fallback_reason=fallback_reason,
                message_length=_msg_len,
                response_length=0,
            )
            return GenerateResponse(
                content="Local model could not respond in time",
                model=model,
                provider=provider,
                usage={},
                cached=False,
                latency_ms=round(latency_ms, 1),
            )

    latency_ms = (time.monotonic() - start) * 1000

    response_data = {
        "content": result["content"],
        "model": result["model"],
        "provider": result["provider"],
        "usage": result["usage"],
        "cached": False,
        "latency_ms": round(latency_ms, 1),
    }

    # Cache store
    if request.cache and settings.cache_ttl > 0:
        try:
            _get_redis().set(cache_key, json.dumps(response_data), ex=settings.cache_ttl)
        except Exception as e:
            logger.debug(f"Cache write error: {e}")

    # Usage tracking
    try:
        r = _get_redis()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        usage_key = f"llm_usage:{today}:{request.caller}"
        pipe = r.pipeline()
        pipe.hincrby(usage_key, "requests", 1)
        pipe.hincrby(usage_key, "prompt_tokens", result["usage"].get("prompt_tokens", 0))
        pipe.hincrby(usage_key, "completion_tokens", result["usage"].get("completion_tokens", 0))
        pipe.expire(usage_key, 86400 * 7)
        pipe.execute()
    except Exception:
        pass

    # Persist every exchange to PostgreSQL (conversations for training)
    _msg_len = sum(len(m.get("content", "")) for m in messages)
    _resp_len = len(result["content"])
    _log_to_db(
        caller=request.caller,
        user_id=user_id,
        provider=result["provider"],
        model=result["model"],
        messages=messages,
        reply=result["content"],
        usage=result["usage"],
        latency_ms=round(latency_ms, 1),
        is_fallback=is_fallback,
        request_type=request.request_type,
        fallback_reason=fallback_reason,
        message_length=_msg_len,
        response_length=_resp_len,
    )

    return GenerateResponse(**response_data)


@app.post("/embeddings", response_model=EmbeddingResponse)
async def embeddings(request: EmbeddingRequest):
    """Generate embeddings via OpenAI."""
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OpenAI API key not configured")

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={"model": request.model, "input": request.text},
        )
        resp.raise_for_status()
        data = resp.json()
        vec = data["data"][0]["embedding"]
        return EmbeddingResponse(
            embedding=vec,
            model=request.model,
            dimensions=len(vec),
        )


@app.get("/usage")
async def usage(days: int = 7):
    """Return usage stats per caller per day."""
    r = _get_redis()
    keys = r.keys("llm_usage:*")
    stats: dict = {}
    for key in keys:
        parts = key.split(":", 2)
        if len(parts) == 3:
            date, caller = parts[1], parts[2]
            data = r.hgetall(key)
            stats.setdefault(date, {})[caller] = {
                "requests": int(data.get("requests", 0)),
                "prompt_tokens": int(data.get("prompt_tokens", 0)),
                "completion_tokens": int(data.get("completion_tokens", 0)),
            }
    return {"usage": stats}


@app.get("/training-data")
async def training_data(limit: int = 100, offset: int = 0):
    """Export OpenAI fallback responses as training pairs for Ollama fine-tuning."""
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="Database not configured")
    try:
        conn = _get_db_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT id, ts, messages, reply, model, latency_ms
                   FROM llm_conversation_log
                   WHERE trainable = TRUE
                   ORDER BY ts DESC LIMIT %s OFFSET %s""",
                (limit, offset),
            )
            rows = cur.fetchall()
        conn.close()
        # Format as Ollama-compatible training pairs
        pairs = []
        for row in rows:
            pairs.append({
                "id": row["id"],
                "ts": row["ts"].isoformat() if row["ts"] else None,
                "messages": row["messages"],
                "expected_reply": row["reply"],
                "source_model": row["model"],
            })
        return {"count": len(pairs), "training_pairs": pairs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── OpenAI cost estimation (per 1K tokens) ──────────────────
_OPENAI_COST_PER_1K = {
    "gpt-4o": {"prompt": 0.005, "completion": 0.015},
    "gpt-4o-mini": {"prompt": 0.00015, "completion": 0.0006},
    "text-embedding-3-small": {"prompt": 0.00002, "completion": 0.0},
    "text-embedding-3-large": {"prompt": 0.00013, "completion": 0.0},
}


def _estimate_cost(model: str, usage: dict) -> float:
    """Estimate USD cost for an OpenAI call."""
    rates = _OPENAI_COST_PER_1K.get(model, {"prompt": 0.005, "completion": 0.015})
    prompt_tokens = usage.get("prompt_tokens", 0) or 0
    completion_tokens = usage.get("completion_tokens", 0) or 0
    return (prompt_tokens / 1000) * rates["prompt"] + (completion_tokens / 1000) * rates["completion"]


@app.get("/analytics/llm-usage")
async def analytics_llm_usage(days: int = 7):
    """Comprehensive LLM usage analytics with cost estimation."""
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="Database not configured")
    try:
        conn = _get_db_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Total requests + provider breakdown
            cur.execute("""
                SELECT
                    COUNT(*) as total_requests,
                    COUNT(*) FILTER (WHERE provider = 'ollama') as ollama_requests,
                    COUNT(*) FILTER (WHERE provider = 'openai') as openai_requests,
                    COUNT(*) FILTER (WHERE is_fallback = TRUE) as fallback_count,
                    ROUND(AVG(latency_ms)::numeric, 1) as avg_latency_ms,
                    ROUND(AVG(latency_ms) FILTER (WHERE provider = 'ollama')::numeric, 1) as avg_latency_ollama,
                    ROUND(AVG(latency_ms) FILTER (WHERE provider = 'openai')::numeric, 1) as avg_latency_openai,
                    COALESCE(SUM(COALESCE(message_length, 0)), 0) as total_message_chars,
                    COALESCE(SUM(COALESCE(response_length, 0)), 0) as total_response_chars
                FROM llm_conversation_log
                WHERE ts > NOW() - INTERVAL '%s days'
            """ % int(days))
            summary = cur.fetchone()

            # Request type breakdown
            cur.execute("""
                SELECT request_type, COUNT(*) as count
                FROM llm_conversation_log
                WHERE ts > NOW() - INTERVAL '%s days'
                GROUP BY request_type ORDER BY count DESC
            """ % int(days))
            type_rows = cur.fetchall()

            # Fallback reason distribution
            cur.execute("""
                SELECT fallback_reason, COUNT(*) as count
                FROM llm_conversation_log
                WHERE ts > NOW() - INTERVAL '%s days' AND fallback_reason IS NOT NULL
                GROUP BY fallback_reason ORDER BY count DESC
            """ % int(days))
            fallback_rows = cur.fetchall()

            # Top callers
            cur.execute("""
                SELECT caller, COUNT(*) as count
                FROM llm_conversation_log
                WHERE ts > NOW() - INTERVAL '%s days'
                GROUP BY caller ORDER BY count DESC LIMIT 10
            """ % int(days))
            caller_rows = cur.fetchall()

            # Top users by request count
            cur.execute("""
                SELECT user_id, COUNT(*) as count
                FROM llm_conversation_log
                WHERE ts > NOW() - INTERVAL '%s days' AND user_id IS NOT NULL AND user_id != ''
                GROUP BY user_id ORDER BY count DESC LIMIT 10
            """ % int(days))
            user_rows = cur.fetchall()

            # Cost estimation: sum usage_data for OpenAI rows
            cur.execute("""
                SELECT model, usage_data
                FROM llm_conversation_log
                WHERE ts > NOW() - INTERVAL '%s days' AND provider = 'openai' AND usage_data IS NOT NULL
            """ % int(days))
            openai_rows = cur.fetchall()

        conn.close()

        # Compute cost
        total_cost = 0.0
        cost_by_model: dict = {}
        for row in openai_rows:
            u = row["usage_data"] if isinstance(row["usage_data"], dict) else {}
            c = _estimate_cost(row["model"], u)
            total_cost += c
            cost_by_model[row["model"]] = cost_by_model.get(row["model"], 0.0) + c

        total = summary["total_requests"] or 0
        fallback_count = summary["fallback_count"] or 0
        fallback_rate = f"{(fallback_count / total * 100):.1f}%" if total > 0 else "0%"

        # Request type percentages
        request_types = {}
        for r in type_rows:
            pct = round(r["count"] / total * 100, 1) if total > 0 else 0
            request_types[r["request_type"] or "unknown"] = {"count": r["count"], "percent": pct}

        return {
            "period_days": days,
            "total_requests": total,
            "providers": {
                "ollama": summary["ollama_requests"] or 0,
                "openai": summary["openai_requests"] or 0,
            },
            "fallback_rate": fallback_rate,
            "fallback_reasons": {r["fallback_reason"]: r["count"] for r in fallback_rows},
            "avg_latency_ms": float(summary["avg_latency_ms"] or 0),
            "avg_latency_by_provider": {
                "ollama": float(summary["avg_latency_ollama"] or 0),
                "openai": float(summary["avg_latency_openai"] or 0),
            },
            "request_types": request_types,
            "top_callers": {r["caller"]: r["count"] for r in caller_rows},
            "top_users": {r["user_id"]: r["count"] for r in user_rows},
            "cost_estimation": {
                "total_usd": round(total_cost, 4),
                "by_model": {k: round(v, 4) for k, v in cost_by_model.items()},
                "ollama_cost": 0.0,
                "note": "Ollama runs locally at zero API cost",
            },
            "total_message_chars": summary["total_message_chars"],
            "total_response_chars": summary["total_response_chars"],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.on_event("startup")
async def startup():
    _ensure_log_table()
