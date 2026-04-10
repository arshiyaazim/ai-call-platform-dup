# ============================================================
# Redis-backed Dedup + DLQ for WhatsApp Webhook Hardening
# Replaces in-memory _SEEN_MSG_IDS and _SENDER_LOCKS
# ============================================================
import json
import logging
import os
import time
from typing import Optional

logger = logging.getLogger("fazle-social-engine.dedup")

REDIS_URL = os.getenv("SOCIAL_REDIS_URL", os.getenv("REDIS_URL", "redis://redis:6379/5"))

_redis = None


def _get_redis():
    global _redis
    if _redis is None:
        try:
            import redis as redis_lib
            _redis = redis_lib.Redis.from_url(REDIS_URL, decode_responses=True)
            _redis.ping()
        except Exception as e:
            logger.warning("Redis unavailable for dedup: %s", e)
            _redis = None
    return _redis


# ── Dedup keys ──────────────────────────────────────────────
_DEDUP_PREFIX = "fazle:dedup:msg:"
_DEDUP_TTL = 300  # 5 minutes

_LOCK_PREFIX = "fazle:dedup:lock:"
_SENDER_COOLDOWN = 2  # seconds

_DLQ_KEY = "fazle:dlq:webhook"
_DLQ_MAX_LEN = 500


def is_duplicate_message(message_id: str) -> bool:
    """Check if message_id was already processed. Redis-backed, survives restarts."""
    if not message_id:
        return False
    r = _get_redis()
    if r is None:
        # Fallback: no dedup if Redis down (better than crashing)
        return False
    try:
        key = f"{_DEDUP_PREFIX}{message_id}"
        # SET NX with TTL — atomic check-and-set
        was_set = r.set(key, "1", nx=True, ex=_DEDUP_TTL)
        if was_set:
            return False  # First time seeing this message
        return True  # Already existed
    except Exception as e:
        logger.warning("Dedup check failed: %s", e)
        return False


def is_sender_locked(sender_id: str) -> bool:
    """Check if sender is in cooldown. Redis-backed."""
    r = _get_redis()
    if r is None:
        return False
    try:
        key = f"{_LOCK_PREFIX}{sender_id}"
        return r.exists(key) > 0
    except Exception:
        return False


def lock_sender(sender_id: str, cooldown: int = _SENDER_COOLDOWN):
    """Lock sender for cooldown period."""
    r = _get_redis()
    if r is None:
        return
    try:
        key = f"{_LOCK_PREFIX}{sender_id}"
        r.setex(key, cooldown, "1")
    except Exception as e:
        logger.warning("Sender lock failed: %s", e)


def unlock_sender(sender_id: str):
    """Remove sender lock."""
    r = _get_redis()
    if r is None:
        return
    try:
        key = f"{_LOCK_PREFIX}{sender_id}"
        r.delete(key)
    except Exception as e:
        logger.warning("Sender unlock failed: %s", e)


# ── Dead Letter Queue ───────────────────────────────────────

def push_to_dlq(message_data: dict, error: str, platform: str = "whatsapp"):
    """Push a failed webhook message to the dead-letter queue for later retry."""
    r = _get_redis()
    if r is None:
        logger.error("DLQ unavailable: cannot store failed message")
        return
    try:
        entry = json.dumps({
            "message": message_data,
            "error": str(error)[:500],
            "platform": platform,
            "timestamp": time.time(),
            "retries": 0,
        })
        r.lpush(_DLQ_KEY, entry)
        # Trim to max length to prevent unbounded growth
        r.ltrim(_DLQ_KEY, 0, _DLQ_MAX_LEN - 1)
        logger.info("Message pushed to DLQ: %s", str(error)[:100])
    except Exception as e:
        logger.error("DLQ push failed: %s", e)


def pop_from_dlq() -> Optional[dict]:
    """Pop a message from the DLQ for retry processing."""
    r = _get_redis()
    if r is None:
        return None
    try:
        entry = r.rpop(_DLQ_KEY)
        if entry:
            return json.loads(entry)
    except Exception as e:
        logger.warning("DLQ pop failed: %s", e)
    return None


def dlq_length() -> int:
    """Get the current DLQ size."""
    r = _get_redis()
    if r is None:
        return 0
    try:
        return r.llen(_DLQ_KEY)
    except Exception:
        return 0


def dlq_peek(count: int = 10) -> list[dict]:
    """Peek at DLQ entries without removing them."""
    r = _get_redis()
    if r is None:
        return []
    try:
        entries = r.lrange(_DLQ_KEY, 0, count - 1)
        return [json.loads(e) for e in entries]
    except Exception:
        return []


def dlq_clear() -> int:
    """Clear all DLQ entries. Returns count cleared."""
    r = _get_redis()
    if r is None:
        return 0
    try:
        length = r.llen(_DLQ_KEY)
        r.delete(_DLQ_KEY)
        return length
    except Exception:
        return 0
