# ============================================================
# Fazle Brain — Redis-backed Conversation Memory Manager
# Replaces in-memory dict with persistent Redis storage
# ============================================================
import json
import logging
import os
from datetime import datetime
from typing import Optional

import redis

logger = logging.getLogger("fazle-brain")

REDIS_URL = os.getenv(
    "REDIS_URL",
    "redis://:redissecret@redis:6379/1",
)

_redis_client: Optional[redis.Redis] = None


def _get_redis() -> redis.Redis:
    """Lazy-initialize Redis connection."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


def _conversation_key(session_id: str) -> str:
    return f"fazle:conv:{session_id}"


def _json_serializer(obj):
    """Handle datetime objects during JSON serialization."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def conversation_set(session_id: str, data: list[dict], ttl: int = 86400) -> None:
    """Store conversation history in Redis with a TTL (default 24h)."""
    r = _get_redis()
    serialized = json.dumps(data, default=_json_serializer)
    r.setex(_conversation_key(session_id), ttl, serialized)


def conversation_get(session_id: str) -> list[dict]:
    """Retrieve conversation history from Redis. Returns empty list if not found."""
    r = _get_redis()
    raw = r.get(_conversation_key(session_id))
    if raw is None:
        return []
    return json.loads(raw)
