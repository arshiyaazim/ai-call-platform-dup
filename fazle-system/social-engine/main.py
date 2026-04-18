# ============================================================
# Fazle Social Engine — WhatsApp + Facebook Automation
# Microservice for social media interactions with AI persona
# ============================================================
from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
import asyncio
import hashlib
import hmac
import httpx
import io
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
import psycopg2.pool

from auth import encrypt_value, decrypt_value, mask_secret
from webhooks import handle_whatsapp_webhook, handle_facebook_webhook
from tasks import trigger_workflow, check_keyword_rules
import whatsapp as wa_module
import facebook as fb_module

# Shared utilities — phone normalization
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from phone_utils import normalize_phone as _normalize_phone_shared

from structured_log import setup_structured_logging
setup_structured_logging("fazle-social-engine")
logger = logging.getLogger("fazle-social-engine")

psycopg2.extras.register_uuid()


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@postgres:5432/postgres"
    brain_url: str = "http://fazle-brain:8200"
    redis_url: str = "redis://redis:6379/5"
    workflow_engine_url: str = "http://fazle-workflow-engine:9700"
    encryption_key: str = ""
    # Fallback env-based creds (overridden by DB integrations when available)
    whatsapp_api_url: str = ""
    whatsapp_api_token: str = ""
    whatsapp_phone_number_id: str = ""
    facebook_page_access_token: str = ""
    facebook_page_id: str = ""
    # Webhook security
    verify_token: str = ""  # SOCIAL_VERIFY_TOKEN
    meta_app_secret: str = ""  # SOCIAL_META_APP_SECRET — used for HMAC validation
    # Owner detection — messages from this phone/id skip AI and train the model
    owner_phone: str = ""  # SOCIAL_OWNER_PHONE — owner's WhatsApp phone number
    learning_engine_url: str = "http://fazle-learning-engine:8900"
    wbom_url: str = "http://fazle-wbom:9900"  # SOCIAL_WBOM_URL — WBOM service for business ops
    wbom_internal_key: str = ""  # SOCIAL_WBOM_INTERNAL_KEY — shared secret for WBOM calls

    class Config:
        env_prefix = "SOCIAL_"


settings = Settings()

app = FastAPI(title="Fazle Social Engine", version="2.0.0", docs_url=None, redoc_url=None)


@app.middleware("http")
async def request_id_middleware(request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ── Database ────────────────────────────────────────────────
_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(2, 10, settings.database_url)
    return _pool


@contextmanager
def _get_conn():
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)


def ensure_tables():
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS fazle_social_integrations (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    platform VARCHAR(20) NOT NULL,
                    app_id VARCHAR(500) DEFAULT '',
                    app_secret TEXT DEFAULT '',
                    access_token TEXT DEFAULT '',
                    page_id VARCHAR(500) DEFAULT '',
                    phone_number VARCHAR(50) DEFAULT '',
                    phone_number_id VARCHAR(200) DEFAULT '',
                    waba_id VARCHAR(200) DEFAULT '',
                    verify_token VARCHAR(200) DEFAULT '',
                    webhook_url TEXT DEFAULT '',
                    enabled BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE(platform)
                );

                -- NOTE: fazle_social_contacts and fazle_social_messages removed
                -- (consolidated into wbom_contacts and wbom_whatsapp_messages via migration 016)

                CREATE TABLE IF NOT EXISTS fazle_social_scheduled (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    platform VARCHAR(20) NOT NULL,
                    action_type VARCHAR(50) NOT NULL,
                    payload JSONB NOT NULL DEFAULT '{}',
                    scheduled_at TIMESTAMPTZ NOT NULL,
                    status VARCHAR(20) DEFAULT 'pending',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_social_scheduled_status
                    ON fazle_social_scheduled (status, scheduled_at);

                CREATE TABLE IF NOT EXISTS fazle_social_campaigns (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    name VARCHAR(200) NOT NULL,
                    platform VARCHAR(20) NOT NULL,
                    campaign_type VARCHAR(50) NOT NULL,
                    config JSONB NOT NULL DEFAULT '{}',
                    status VARCHAR(20) DEFAULT 'draft',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS fazle_social_posts (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    platform VARCHAR(20) NOT NULL DEFAULT 'facebook',
                    post_id VARCHAR(200),
                    content TEXT NOT NULL,
                    image_url TEXT,
                    status VARCHAR(20) DEFAULT 'published',
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_social_posts_platform
                    ON fazle_social_posts (platform, created_at DESC);

                -- NOTE: fazle_contacts removed
                -- (consolidated into wbom_contacts via migration 016)

                -- Chat reply reuse system (Steps 11, 12, 18, 19)
                CREATE TABLE IF NOT EXISTS fazle_chat_replies (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    query_hash VARCHAR(64) NOT NULL,
                    query_text TEXT NOT NULL,
                    reply_text TEXT NOT NULL,
                    category VARCHAR(100) DEFAULT '',
                    language VARCHAR(10) DEFAULT 'bn',
                    quality_score FLOAT DEFAULT 0.5,
                    usage_count INT DEFAULT 1,
                    source VARCHAR(20) DEFAULT 'llm',
                    platform VARCHAR(20) DEFAULT 'whatsapp',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_used TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_chat_replies_hash
                    ON fazle_chat_replies (query_hash);
                CREATE INDEX IF NOT EXISTS idx_chat_replies_quality
                    ON fazle_chat_replies (quality_score DESC, usage_count DESC);

                -- Owner audio profiles (Steps 13, 14)
                CREATE TABLE IF NOT EXISTS fazle_owner_audio_profiles (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    transcript TEXT NOT NULL,
                    transcript_hash VARCHAR(64) NOT NULL,
                    audio_context VARCHAR(200) DEFAULT '',
                    tone VARCHAR(50) DEFAULT 'normal',
                    language VARCHAR(10) DEFAULT 'bn',
                    usage_count INT DEFAULT 1,
                    platform VARCHAR(20) DEFAULT 'whatsapp',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_audio_profiles_hash
                    ON fazle_owner_audio_profiles (transcript_hash);

                -- Conversation summaries (Step 16)
                CREATE TABLE IF NOT EXISTS fazle_conversation_summaries (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    conversation_id VARCHAR(200) NOT NULL,
                    user_phone VARCHAR(50) DEFAULT '',
                    user_name VARCHAR(200) DEFAULT '',
                    summary TEXT NOT NULL,
                    message_count INT DEFAULT 0,
                    key_topics TEXT[] DEFAULT '{}',
                    platform VARCHAR(20) DEFAULT 'whatsapp',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_summaries_conv
                    ON fazle_conversation_summaries (conversation_id);

                -- Multimodal learning storage (Step 15)
                CREATE TABLE IF NOT EXISTS fazle_multimodal_learning (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    media_type VARCHAR(20) NOT NULL,
                    extracted_text TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    sender_phone VARCHAR(50) DEFAULT '',
                    context TEXT DEFAULT '',
                    category VARCHAR(100) DEFAULT '',
                    platform VARCHAR(20) DEFAULT 'whatsapp',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_multimodal_sender
                    ON fazle_multimodal_learning (sender_phone);

                -- Owner feedback on AI replies (Step 6)
                CREATE TABLE IF NOT EXISTS fazle_owner_feedback (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    original_query TEXT DEFAULT '',
                    ai_reply TEXT DEFAULT '',
                    feedback_type VARCHAR(20) DEFAULT 'correction',
                    correction TEXT DEFAULT '',
                    rating INT DEFAULT 0,
                    customer_phone VARCHAR(50) DEFAULT '',
                    platform VARCHAR(20) DEFAULT 'whatsapp',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)
        conn.commit()
    logger.info("Social engine tables ensured")


def upsert_contact(db_conn_fn, phone: str, name: str = "", platform: str = "whatsapp",
                   relation: str = "unknown", notes: str = "",
                   company: str = "", personality_hint: str = "") -> None:
    """Create or update a contact in the contact book (wbom_contacts)."""
    norm_phone = _normalize_phone_shared(phone) or phone.lstrip("+").replace(" ", "").strip()
    with db_conn_fn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO wbom_contacts (whatsapp_number, display_name, relation, platform, notes, company_name, personality_hint, interaction_count, last_seen, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, 1, NOW(), NOW())
                   ON CONFLICT (whatsapp_number, platform) DO UPDATE SET
                     display_name = CASE WHEN EXCLUDED.display_name != '' THEN EXCLUDED.display_name ELSE wbom_contacts.display_name END,
                     relation = CASE WHEN EXCLUDED.relation != 'unknown' THEN EXCLUDED.relation ELSE wbom_contacts.relation END,
                     notes = CASE WHEN EXCLUDED.notes != '' THEN EXCLUDED.notes ELSE wbom_contacts.notes END,
                     company_name = CASE WHEN EXCLUDED.company_name != '' THEN EXCLUDED.company_name ELSE wbom_contacts.company_name END,
                     personality_hint = CASE WHEN EXCLUDED.personality_hint != '' THEN EXCLUDED.personality_hint ELSE wbom_contacts.personality_hint END,
                     interaction_count = wbom_contacts.interaction_count + 1,
                     last_seen = NOW(),
                     updated_at = NOW()""",
                (norm_phone, name, relation, platform, notes, company, personality_hint),
            )
        conn.commit()
    # Invalidate Redis cache for this contact
    try:
        from redis_dedup import _get_redis
        r = _get_redis()
        if r:
            r.delete(f"fazle:contact:{platform}:{norm_phone}")
    except Exception:
        pass


def get_contact(db_conn_fn, phone: str, platform: str = "whatsapp") -> dict | None:
    """Retrieve contact info with Redis cache (TTL 120s)."""
    norm_phone = _normalize_phone_shared(phone) or phone.lstrip("+").replace(" ", "").strip()
    cache_key = f"fazle:contact:{platform}:{norm_phone}"

    # Try Redis cache first
    try:
        from redis_dedup import _get_redis
        r = _get_redis()
        if r:
            cached = r.get(cache_key)
            if cached:
                return json.loads(cached)
    except Exception:
        pass  # Fall through to DB

    with db_conn_fn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT whatsapp_number AS phone, display_name AS name, relation, notes,
                          company_name AS company, personality_hint,
                          interaction_count, interest_level, last_seen, updated_at AS last_updated
                   FROM wbom_contacts
                   WHERE whatsapp_number = %s AND platform = %s""",
                (norm_phone, platform),
            )
            row = cur.fetchone()
            result = dict(row) if row else None

    # Cache in Redis (120s TTL)
    if result:
        try:
            from redis_dedup import _get_redis
            r = _get_redis()
            if r:
                # Convert datetimes to strings for JSON serialization
                cacheable = {}
                for k, v in result.items():
                    if hasattr(v, "isoformat"):
                        cacheable[k] = v.isoformat()
                    else:
                        cacheable[k] = v
                r.set(cache_key, json.dumps(cacheable), ex=120)
        except Exception:
            pass

    return result


def list_all_contacts(db_conn_fn, platform: str | None = None, search: str = "",
                      limit: int = 100, offset: int = 0) -> list[dict]:
    """List contacts with optional platform filter and search."""
    with db_conn_fn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            where_parts = []
            params: list = []
            if platform:
                where_parts.append("platform = %s")
                params.append(platform)
            if search:
                where_parts.append("(display_name ILIKE %s OR whatsapp_number ILIKE %s OR relation ILIKE %s OR company_name ILIKE %s)")
                like = f"%{search}%"
                params.extend([like, like, like, like])
            where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
            params.extend([limit, offset])
            cur.execute(
                f"""SELECT contact_id AS id, whatsapp_number AS phone, display_name AS name,
                           relation, notes, company_name AS company, personality_hint,
                           platform, interaction_count, interest_level, last_seen, updated_at AS last_updated
                    FROM wbom_contacts {where_clause}
                    ORDER BY last_seen DESC NULLS LAST
                    LIMIT %s OFFSET %s""",
                params,
            )
            return [dict(r) for r in cur.fetchall()]


def update_contact(db_conn_fn, contact_id: str, updates: dict) -> bool:
    """Update specific fields of a contact by ID."""
    allowed = {"name", "relation", "notes", "company", "personality_hint", "interest_level"}
    fields = {k: v for k, v in updates.items() if k in allowed and v is not None}
    if not fields:
        return False
    # Map legacy column names to WBOM names
    col_map = {"name": "display_name", "company": "company_name"}
    mapped = {col_map.get(k, k): v for k, v in fields.items()}
    set_clause = ", ".join(f"{k} = %s" for k in mapped)
    values = list(mapped.values()) + [contact_id]
    with db_conn_fn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE wbom_contacts SET {set_clause}, updated_at = NOW() WHERE contact_id = %s::int",
                values,
            )
        conn.commit()
    return True


def delete_contact(db_conn_fn, contact_id: str) -> bool:
    """Delete a contact by ID."""
    with db_conn_fn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM wbom_contacts WHERE contact_id = %s::int", (contact_id,))
            deleted = cur.rowcount > 0
        conn.commit()
    return deleted


def update_contact_interest(db_conn_fn, phone: str, platform: str, interest: str) -> None:
    """Update interest level for a contact (hot/warm/cold/risk)."""
    norm_phone = phone.lstrip("+").replace(" ", "").strip()
    with db_conn_fn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE wbom_contacts SET interest_level = %s, updated_at = NOW() WHERE whatsapp_number = %s AND platform = %s",
                (interest, norm_phone, platform),
            )
        conn.commit()


# ── Chat Reply Reuse System (Steps 11, 12, 18) ────────────

def _query_hash(text: str) -> str:
    """Generate a normalized hash for query text to enable reply reuse."""
    import re
    normalized = re.sub(r'\s+', ' ', text.strip().lower())
    # Remove common greetings/fillers for better matching
    for filler in ["assalamu alaikum", "আসসালামু আলাইকুম", "hi", "hello", "hey", "please", "plz"]:
        normalized = normalized.replace(filler, "").strip()
    return hashlib.sha256(normalized.encode()).hexdigest()[:32]


def find_cached_reply(db_conn_fn, query: str, platform: str = "whatsapp") -> str | None:
    """Find a high-quality cached reply for a similar query. Returns reply text or None."""
    qhash = _query_hash(query)
    with db_conn_fn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT reply_text, usage_count FROM fazle_chat_replies
                   WHERE query_hash = %s AND quality_score >= 0.6
                   AND (platform = %s OR platform = 'all')
                   ORDER BY quality_score DESC, usage_count DESC LIMIT 1""",
                (qhash, platform),
            )
            row = cur.fetchone()
            if row:
                # Increment usage count
                cur.execute(
                    "UPDATE fazle_chat_replies SET usage_count = usage_count + 1, last_used = NOW() WHERE query_hash = %s",
                    (qhash,),
                )
                conn.commit()
                return row["reply_text"]
    return None


def save_chat_reply(db_conn_fn, query: str, reply: str, category: str = "",
                    platform: str = "whatsapp", source: str = "llm",
                    quality_score: float = 0.5) -> None:
    """Store a chat reply for future reuse."""
    qhash = _query_hash(query)
    with db_conn_fn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO fazle_chat_replies (query_hash, query_text, reply_text, category, platform, source, quality_score)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT DO NOTHING""",
                (qhash, query[:500], reply[:2000], category, platform, source, quality_score),
            )
        conn.commit()


def boost_reply_quality(db_conn_fn, query: str, boost: float = 0.1) -> None:
    """Boost quality score of a cached reply (owner approved it)."""
    qhash = _query_hash(query)
    with db_conn_fn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE fazle_chat_replies SET quality_score = LEAST(quality_score + %s, 1.0) WHERE query_hash = %s",
                (boost, qhash),
            )
        conn.commit()


def penalize_reply_quality(db_conn_fn, query: str, penalty: float = 0.2) -> None:
    """Penalize quality score of a cached reply (owner corrected it)."""
    qhash = _query_hash(query)
    with db_conn_fn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE fazle_chat_replies SET quality_score = GREATEST(quality_score - %s, 0.0) WHERE query_hash = %s",
                (penalty, qhash),
            )
        conn.commit()


# ── Owner Audio Profile System (Steps 13, 14) ──────────────

def save_owner_audio_profile(db_conn_fn, transcript: str, context: str = "",
                             tone: str = "normal", platform: str = "whatsapp") -> None:
    """Store owner's voice message transcript for learning tone/style."""
    thash = hashlib.sha256(transcript.strip().lower().encode()).hexdigest()[:32]
    with db_conn_fn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO fazle_owner_audio_profiles (transcript, transcript_hash, audio_context, tone, platform)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT DO NOTHING""",
                (transcript[:2000], thash, context[:200], tone, platform),
            )
        conn.commit()


def get_owner_audio_examples(db_conn_fn, limit: int = 5) -> list[dict]:
    """Get recent owner voice transcripts for style learning."""
    with db_conn_fn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT transcript, tone, audio_context FROM fazle_owner_audio_profiles ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
            return [dict(r) for r in cur.fetchall()]


# ── Conversation Summary System (Step 16) ──────────────────

def save_conversation_summary(db_conn_fn, conversation_id: str, summary: str,
                               user_phone: str = "", user_name: str = "",
                               message_count: int = 0, key_topics: list = None,
                               platform: str = "whatsapp") -> None:
    """Store a conversation summary for memory efficiency."""
    with db_conn_fn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO fazle_conversation_summaries
                   (conversation_id, summary, user_phone, user_name, message_count, key_topics, platform)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (conversation_id, summary[:2000], user_phone, user_name, message_count,
                 key_topics or [], platform),
            )
        conn.commit()


def get_conversation_summaries(db_conn_fn, user_phone: str = "", limit: int = 5) -> list[dict]:
    """Get recent conversation summaries for a user."""
    with db_conn_fn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if user_phone:
                cur.execute(
                    "SELECT * FROM fazle_conversation_summaries WHERE user_phone = %s ORDER BY created_at DESC LIMIT %s",
                    (user_phone.lstrip("+").replace(" ", "").strip(), limit),
                )
            else:
                cur.execute(
                    "SELECT * FROM fazle_conversation_summaries ORDER BY created_at DESC LIMIT %s",
                    (limit,),
                )
            return [dict(r) for r in cur.fetchall()]


# ── Multimodal Learning Storage (Step 15) ──────────────────

def save_multimodal_learning(db_conn_fn, media_type: str, extracted_text: str,
                             sender_phone: str = "", context: str = "",
                             description: str = "", category: str = "",
                             platform: str = "whatsapp") -> None:
    """Store multimodal content (image/audio/document) for learning."""
    with db_conn_fn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO fazle_multimodal_learning
                   (media_type, extracted_text, sender_phone, context, description, category, platform)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (media_type, extracted_text[:3000], sender_phone, context[:500],
                 description[:500], category, platform),
            )
        conn.commit()


# ── Owner Feedback System (Step 6) ─────────────────────────

def save_owner_feedback(db_conn_fn, original_query: str, ai_reply: str,
                        feedback_type: str = "correction", correction: str = "",
                        rating: int = 0, customer_phone: str = "",
                        platform: str = "whatsapp") -> None:
    """Store owner feedback on an AI reply."""
    with db_conn_fn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO fazle_owner_feedback
                   (original_query, ai_reply, feedback_type, correction, rating, customer_phone, platform)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (original_query[:1000], ai_reply[:2000], feedback_type, correction[:2000],
                 rating, customer_phone, platform),
            )
        conn.commit()


def get_reply_stats(db_conn_fn) -> dict:
    """Get reply reuse statistics."""
    with db_conn_fn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT COUNT(*) as total, SUM(usage_count) as total_uses FROM fazle_chat_replies")
            replies = dict(cur.fetchone())
            cur.execute("SELECT COUNT(*) as total FROM fazle_owner_feedback")
            feedback = dict(cur.fetchone())
            cur.execute("SELECT COUNT(*) as total FROM fazle_conversation_summaries")
            summaries = dict(cur.fetchone())
            cur.execute("SELECT COUNT(*) as total FROM fazle_multimodal_learning")
            multimodal = dict(cur.fetchone())
            return {
                "cached_replies": replies.get("total", 0),
                "total_reuses": replies.get("total_uses", 0),
                "owner_feedback": feedback.get("total", 0),
                "summaries": summaries.get("total", 0),
                "multimodal_items": multimodal.get("total", 0),
            }


@app.on_event("startup")
def startup():
    try:
        ensure_tables()
    except Exception as e:
        logger.error(f"Database init failed: {e}")
    # Initialise WBOM retry queue
    from wbom_retry import init_retry_worker, start_retry_loop
    init_retry_worker(settings.redis_url, settings.wbom_url, settings.wbom_internal_key)
    start_retry_loop()


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "fazle-social-engine", "timestamp": datetime.now(timezone.utc).isoformat()}


# ── Helpers ────────────────────────────────────────────────
def _verify_meta_signature(raw_body: bytes, app_secret: str, header: str) -> bool:
    """Validate X-Hub-Signature-256 from Meta. Returns False if secret missing or signature invalid."""
    if not app_secret:
        return False
    if not header or not header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)


def _get_integration_creds(platform: str) -> dict:
    """Get decrypted credentials for a platform from DB or env fallback."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM fazle_social_integrations WHERE platform = %s AND enabled = TRUE",
                (platform,),
            )
            row = cur.fetchone()
    if row:
        creds = dict(row)
        # Decrypt secrets
        for field in ("app_secret", "access_token"):
            if creds.get(field):
                try:
                    creds[field] = decrypt_value(creds[field])
                except Exception:
                    pass
        creds["id"] = str(creds["id"])
        return creds
    # Fallback to env-based creds
    if platform == "whatsapp":
        return {
            "whatsapp_api_url": settings.whatsapp_api_url,
            "access_token": settings.whatsapp_api_token,
            "phone_number_id": settings.whatsapp_phone_number_id,
        }
    elif platform == "facebook":
        return {
            "page_access_token": settings.facebook_page_access_token or "",
            "access_token": settings.facebook_page_access_token or "",
            "page_id": settings.facebook_page_id,
        }
    return {}


async def generate_ai_reply(message: str, context: str = "") -> str:
    """Use Fazle Brain to generate a persona-aware response."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{settings.brain_url}/chat",
                json={
                    "message": message,
                    "user": "Social Bot",
                    "conversation_id": f"social-{uuid.uuid4().hex[:8]}",
                    "context": context,
                },
            )
            if resp.status_code == 200:
                return resp.json().get("reply", "")
    except Exception as e:
        logger.error(f"Brain AI reply failed: {e}")
    return ""


# ── Integration Management ─────────────────────────────────

@app.get("/integrations")
async def list_integrations():
    """List all platform integrations with masked secrets."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM fazle_social_integrations ORDER BY platform")
            rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        r["id"] = str(r["id"])
        r["app_secret"] = mask_secret(r.get("app_secret", ""))
        r["access_token"] = mask_secret(r.get("access_token", ""))
    return {"integrations": rows}


@app.post("/integrations/save")
async def save_integration(body: dict):
    """Save or update a platform integration. Secrets are encrypted."""
    platform = body.get("platform", "").lower()
    if platform not in ("whatsapp", "facebook"):
        raise HTTPException(status_code=400, detail="Platform must be 'whatsapp' or 'facebook'")

    # Encrypt secrets before storage
    app_secret = body.get("app_secret", "")
    access_token = body.get("access_token", "")
    if app_secret and settings.encryption_key:
        app_secret = encrypt_value(app_secret)
    if access_token and settings.encryption_key:
        access_token = encrypt_value(access_token)

    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """INSERT INTO fazle_social_integrations
                   (platform, app_id, app_secret, access_token, page_id,
                    phone_number, phone_number_id, waba_id, verify_token, webhook_url, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                   ON CONFLICT (platform) DO UPDATE SET
                     app_id = EXCLUDED.app_id,
                     app_secret = EXCLUDED.app_secret,
                     access_token = EXCLUDED.access_token,
                     page_id = EXCLUDED.page_id,
                     phone_number = EXCLUDED.phone_number,
                     phone_number_id = EXCLUDED.phone_number_id,
                     waba_id = EXCLUDED.waba_id,
                     verify_token = EXCLUDED.verify_token,
                     webhook_url = EXCLUDED.webhook_url,
                     updated_at = NOW()
                   RETURNING id, platform, enabled""",
                (platform,
                 body.get("app_id", ""),
                 app_secret,
                 access_token,
                 body.get("page_id", ""),
                 body.get("phone_number", ""),
                 body.get("phone_number_id", ""),
                 body.get("waba_id", ""),
                 body.get("verify_token", ""),
                 body.get("webhook_url", "")),
            )
            conn.commit()
            row = dict(cur.fetchone())
            row["id"] = str(row["id"])
    return {"status": "saved", **row}


@app.post("/integrations/test")
async def test_integration(body: dict):
    """Test connectivity for a saved integration."""
    platform = body.get("platform", "").lower()
    creds = _get_integration_creds(platform)

    if platform == "whatsapp":
        api_url = creds.get("whatsapp_api_url") or settings.whatsapp_api_url
        token = creds.get("access_token", "")
        phone_id = creds.get("phone_number_id", "")
        if not api_url or not token:
            return {"connected": False, "error": "WhatsApp credentials not configured"}
        try:
            transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
            async with httpx.AsyncClient(transport=transport, timeout=10.0) as client:
                resp = await client.get(
                    f"{api_url}/{phone_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
                return {"connected": resp.status_code == 200, "status_code": resp.status_code}
        except Exception as e:
            return {"connected": False, "error": str(e)}

    elif platform == "facebook":
        token = creds.get("page_access_token") or creds.get("access_token", "")
        page_id = creds.get("page_id", "")
        if not token:
            return {"connected": False, "error": "Facebook credentials not configured"}
        try:
            transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
            async with httpx.AsyncClient(transport=transport, timeout=10.0) as client:
                resp = await client.get(
                    f"https://graph.facebook.com/v19.0/{page_id}",
                    params={"access_token": token, "fields": "id,name"},
                )
                if resp.status_code == 200:
                    return {"connected": True, "page": resp.json()}
                return {"connected": False, "status_code": resp.status_code}
        except Exception as e:
            return {"connected": False, "error": str(e)}

    return {"connected": False, "error": "Unknown platform"}


@app.post("/integrations/enable")
async def enable_integration(body: dict):
    """Enable a platform integration."""
    platform = body.get("platform", "").lower()
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE fazle_social_integrations SET enabled = TRUE, updated_at = NOW() WHERE platform = %s",
                (platform,),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Integration not found")
        conn.commit()
    return {"status": "enabled", "platform": platform}


@app.post("/integrations/disable")
async def disable_integration(body: dict):
    """Disable a platform integration."""
    platform = body.get("platform", "").lower()
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE fazle_social_integrations SET enabled = FALSE, updated_at = NOW() WHERE platform = %s",
                (platform,),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Integration not found")
        conn.commit()
    return {"status": "disabled", "platform": platform}


# ── Integration Status (Testing) ───────────────────────────

@app.get("/integration/status")
async def integration_status():
    """Return connected platforms, webhook status, last message timestamp."""
    platforms = []
    for p in ("whatsapp", "facebook"):
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT platform, enabled, webhook_url FROM fazle_social_integrations WHERE platform = %s",
                    (p,),
                )
                row = cur.fetchone()
                cur.execute(
                    "SELECT MAX(received_at) as last_message FROM wbom_whatsapp_messages WHERE platform = %s",
                    (p,),
                )
                last_msg = cur.fetchone()
        platforms.append({
            "platform": p,
            "connected": bool(row and row["enabled"]),
            "webhook_url": (row or {}).get("webhook_url", ""),
            "last_message_at": str(last_msg["last_message"]) if last_msg and last_msg["last_message"] else None,
        })
    return {"platforms": platforms, "service": "fazle-social-engine", "version": "2.0.0"}


# ── Webhook Endpoints ──────────────────────────────────────

@app.get("/whatsapp/webhook")
async def whatsapp_webhook_verify(request: Request):
    """WhatsApp webhook verification (GET). Meta sends hub.challenge."""
    params = request.query_params
    mode = params.get("hub.mode", "")
    token = params.get("hub.verify_token", "")
    challenge = params.get("hub.challenge", "")

    # Check verify_token: DB value takes priority, env is fallback
    creds = _get_integration_creds("whatsapp")
    expected_token = creds.get("verify_token") or settings.verify_token
    if not expected_token:
        raise HTTPException(status_code=403, detail="Verify token not configured")

    if mode == "subscribe" and token == expected_token:
        return int(challenge) if challenge.isdigit() else challenge
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/whatsapp/webhook")
async def whatsapp_webhook_receive(request: Request):
    """Receive incoming WhatsApp messages via Meta webhook. Validates X-Hub-Signature-256."""
    raw_body = await request.body()
    sig_header = request.headers.get("X-Hub-Signature-256", "")
    creds = _get_integration_creds("whatsapp")
    app_secret = creds.get("app_secret") or settings.meta_app_secret
    if not _verify_meta_signature(raw_body, app_secret, sig_header):
        logger.warning("WhatsApp webhook: invalid or missing HMAC signature")
        raise HTTPException(status_code=403, detail="Invalid webhook signature")
    payload = json.loads(raw_body)

    # Process in background — return 200 instantly so Meta doesn't retry
    async def _process_wa():
        try:
            result = await handle_whatsapp_webhook(
                payload, _get_conn, settings.brain_url, _get_integration_creds,
                owner_phone=settings.owner_phone, learning_engine_url=settings.learning_engine_url,
                wbom_url=settings.wbom_url,
                wbom_internal_key=settings.wbom_internal_key,
            )
            await trigger_workflow(settings.workflow_engine_url, "whatsapp.message.received", result)
        except Exception as exc:
            logger.error(f"Background WhatsApp processing error: {exc}")

    asyncio.create_task(_process_wa())
    return {"status": "ok"}


@app.get("/facebook/webhook")
async def facebook_webhook_verify(request: Request):
    """Facebook webhook verification (GET)."""
    params = request.query_params
    mode = params.get("hub.mode", "")
    token = params.get("hub.verify_token", "")
    challenge = params.get("hub.challenge", "")

    creds = _get_integration_creds("facebook")
    expected_token = creds.get("verify_token") or settings.verify_token
    if not expected_token:
        raise HTTPException(status_code=403, detail="Verify token not configured")

    if mode == "subscribe" and token == expected_token:
        return int(challenge) if challenge.isdigit() else challenge
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/facebook/webhook")
async def facebook_webhook_receive(request: Request):
    """Receive incoming Facebook events via webhook. Validates X-Hub-Signature-256."""
    raw_body = await request.body()
    sig_header = request.headers.get("X-Hub-Signature-256", "")
    creds = _get_integration_creds("facebook")
    app_secret = creds.get("app_secret") or settings.meta_app_secret
    if not _verify_meta_signature(raw_body, app_secret, sig_header):
        logger.warning("Facebook webhook: invalid or missing HMAC signature")
        raise HTTPException(status_code=403, detail="Invalid webhook signature")
    payload = json.loads(raw_body)

    async def _process_fb():
        try:
            result = await handle_facebook_webhook(
                payload, _get_conn, settings.brain_url, _get_integration_creds,
                owner_phone=settings.owner_phone, learning_engine_url=settings.learning_engine_url,
            )
            await trigger_workflow(settings.workflow_engine_url, "facebook.comment.received", result)
        except Exception as exc:
            logger.error(f"Background Facebook processing error: {exc}")

    asyncio.create_task(_process_fb())
    return {"status": "ok"}


# ── WhatsApp endpoints ─────────────────────────────────────

@app.post("/whatsapp/send")
async def whatsapp_send(body: dict):
    """Send a WhatsApp message. If auto_reply=true, generate AI reply first."""
    to = body.get("to", "")
    message = body.get("message", "")
    auto_reply = body.get("auto_reply", False)

    if not to or not message:
        raise HTTPException(status_code=400, detail="'to' and 'message' are required")

    if auto_reply:
        ai_reply = await generate_ai_reply(message)
        if ai_reply:
            message = ai_reply

    # Store message in DB
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO wbom_whatsapp_messages
                   (platform, direction, contact_identifier, message_body, metadata_json, status)
                   VALUES ('whatsapp', 'outgoing', %s, %s, %s, 'queued')""",
                (to, message, psycopg2.extras.Json(body.get("metadata", {}))),
            )
        conn.commit()

    # Send via WhatsApp Business API
    creds = _get_integration_creds("whatsapp")
    api_url = creds.get("whatsapp_api_url") or settings.whatsapp_api_url
    token = creds.get("access_token") or settings.whatsapp_api_token
    phone_id = creds.get("phone_number_id") or settings.whatsapp_phone_number_id

    result = await wa_module.send_message(api_url, token, phone_id, to, message)

    return {"status": "sent" if result.get("sent") else "queued", "to": to, "message": message}


@app.post("/whatsapp/schedule")
async def whatsapp_schedule(body: dict):
    """Schedule a WhatsApp message for later."""
    scheduled_at = body.get("scheduled_at")
    if not scheduled_at:
        raise HTTPException(status_code=400, detail="'scheduled_at' is required")

    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """INSERT INTO fazle_social_scheduled
                   (platform, action_type, payload, scheduled_at)
                   VALUES ('whatsapp', 'send', %s, %s)
                   RETURNING id, scheduled_at, status""",
                (psycopg2.extras.Json(body), scheduled_at),
            )
            conn.commit()
            row = dict(cur.fetchone())
            row["id"] = str(row["id"])

    return {"status": "scheduled", **row}


@app.post("/whatsapp/broadcast")
async def whatsapp_broadcast(body: dict):
    """Broadcast a message to multiple contacts."""
    contacts = body.get("contacts", [])
    message = body.get("message", "")

    if not contacts or not message:
        raise HTTPException(status_code=400, detail="'contacts' and 'message' are required")

    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """INSERT INTO fazle_social_campaigns
                   (name, platform, campaign_type, config, status)
                   VALUES (%s, 'whatsapp', 'broadcast', %s, 'running')
                   RETURNING id""",
                (body.get("name", f"Broadcast {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"),
                 psycopg2.extras.Json({"contacts": contacts, "message": message})),
            )
            conn.commit()
            campaign_id = str(cur.fetchone()["id"])

    await trigger_workflow(settings.workflow_engine_url, "social.campaign.started",
                           {"campaign_id": campaign_id, "platform": "whatsapp"})
    return {"status": "broadcast_queued", "campaign_id": campaign_id, "contact_count": len(contacts)}


@app.get("/whatsapp/messages")
async def whatsapp_messages(limit: int = 50):
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT message_id AS id, direction, contact_identifier, message_body AS content,
                          message_body AS message_text, ai_response, status, received_at AS created_at
                   FROM wbom_whatsapp_messages
                   WHERE platform = 'whatsapp'
                   ORDER BY received_at DESC LIMIT %s""",
                (limit,),
            )
            messages = [dict(r) for r in cur.fetchall()]
            for m in messages:
                m["id"] = str(m["id"])
    return {"messages": messages}


@app.get("/whatsapp/scheduled")
async def whatsapp_scheduled():
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT id, action_type, payload, scheduled_at, status, created_at
                   FROM fazle_social_scheduled
                   WHERE platform = 'whatsapp' AND status = 'pending'
                   ORDER BY scheduled_at""",
            )
            scheduled = [dict(r) for r in cur.fetchall()]
            for s in scheduled:
                s["id"] = str(s["id"])
    return {"scheduled": scheduled}


# ── Facebook endpoints ─────────────────────────────────────

@app.post("/facebook/post")
async def facebook_post(body: dict):
    """Create or schedule a Facebook post. If ai_generate=true, use Brain."""
    content = body.get("content", "")
    ai_generate = body.get("ai_generate", False)
    schedule_at = body.get("schedule_at")

    if ai_generate:
        prompt = body.get("prompt", "Create an engaging social media post")
        content = await generate_ai_reply(prompt, context="Facebook post generation")
        if not content:
            content = body.get("content", "")

    if not content:
        raise HTTPException(status_code=400, detail="Content is required")

    if schedule_at:
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """INSERT INTO fazle_social_scheduled
                       (platform, action_type, payload, scheduled_at)
                       VALUES ('facebook', 'post', %s, %s)
                       RETURNING id, scheduled_at, status""",
                    (psycopg2.extras.Json({"content": content, "image_url": body.get("image_url")}), schedule_at),
                )
                conn.commit()
                row = dict(cur.fetchone())
                row["id"] = str(row["id"])
        return {"status": "scheduled", **row}

    # Post immediately via Graph API
    creds = _get_integration_creds("facebook")
    token = creds.get("page_access_token") or creds.get("access_token", "")
    page_id = creds.get("page_id") or settings.facebook_page_id
    result = await fb_module.create_post(page_id, token, content, body.get("image_url"))
    post_id = result.get("post_id")

    # Store in DB
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """INSERT INTO fazle_social_posts (platform, post_id, content, image_url, status)
                   VALUES ('facebook', %s, %s, %s, %s)
                   RETURNING id""",
                (post_id, content, body.get("image_url"), "published" if post_id else "draft"),
            )
            conn.commit()
            db_id = str(cur.fetchone()["id"])

    await trigger_workflow(settings.workflow_engine_url, "facebook.post.created",
                           {"post_id": post_id, "content": content[:200]})
    return {"status": "published" if post_id else "draft", "id": db_id, "post_id": post_id, "content": content}


@app.post("/facebook/comment")
async def facebook_comment(body: dict):
    """Reply to a Facebook comment. If auto_reply=true, use Brain."""
    post_id = body.get("post_id", "")
    comment_id = body.get("comment_id", "")
    message = body.get("message", "")
    auto_reply = body.get("auto_reply", False)

    if not (post_id or comment_id):
        raise HTTPException(status_code=400, detail="'post_id' or 'comment_id' required")

    if auto_reply and body.get("original_comment"):
        message = await generate_ai_reply(
            body["original_comment"],
            context="Facebook comment reply. Be brief, friendly, and engaging."
        )

    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    target = comment_id or post_id
    creds = _get_integration_creds("facebook")
    token = creds.get("page_access_token") or creds.get("access_token", "")
    result = await fb_module.reply_to_comment(target, token, message)

    return {"status": "sent" if result.get("sent") else "queued", "target": target, "message": message}


@app.post("/facebook/react")
async def facebook_react(body: dict):
    """React to a Facebook post or comment."""
    target_id = body.get("target_id", "")
    reaction_type = body.get("reaction_type", "LIKE")

    if not target_id:
        raise HTTPException(status_code=400, detail="'target_id' is required")

    creds = _get_integration_creds("facebook")
    token = creds.get("page_access_token") or creds.get("access_token", "")
    result = await fb_module.react_to_post(target_id, token, reaction_type)

    return {"status": "sent" if result.get("sent") else "queued", "target_id": target_id, "reaction": reaction_type}


@app.get("/facebook/posts")
async def facebook_posts(limit: int = 50):
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT id, post_id, content, image_url, status, created_at
                   FROM fazle_social_posts
                   WHERE platform = 'facebook'
                   ORDER BY created_at DESC LIMIT %s""",
                (limit,),
            )
            posts = [dict(r) for r in cur.fetchall()]
            for p in posts:
                p["id"] = str(p["id"])
    return {"posts": posts}


@app.get("/facebook/scheduled")
async def facebook_scheduled():
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT id, action_type, payload, scheduled_at, status, created_at
                   FROM fazle_social_scheduled
                   WHERE platform = 'facebook' AND status = 'pending'
                   ORDER BY scheduled_at""",
            )
            scheduled = [dict(r) for r in cur.fetchall()]
            for s in scheduled:
                s["id"] = str(s["id"])
    return {"scheduled": scheduled}


# ── Contacts ───────────────────────────────────────────────

@app.get("/contacts")
async def list_contacts(platform: Optional[str] = None):
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if platform:
                cur.execute(
                    "SELECT contact_id AS id, display_name AS name, platform, whatsapp_number AS identifier FROM wbom_contacts WHERE platform = %s ORDER BY display_name",
                    (platform,),
                )
            else:
                cur.execute("SELECT contact_id AS id, display_name AS name, platform, whatsapp_number AS identifier FROM wbom_contacts ORDER BY display_name")
            contacts = [dict(r) for r in cur.fetchall()]
            for c in contacts:
                c["id"] = str(c["id"])
    return {"contacts": contacts}


@app.post("/contacts")
async def add_contact(body: dict):
    name = body.get("name", "")
    platform = body.get("platform", "")
    identifier = body.get("identifier", "")

    if not name or not platform or not identifier:
        raise HTTPException(status_code=400, detail="'name', 'platform', 'identifier' are required")

    if platform not in ("whatsapp", "facebook"):
        raise HTTPException(status_code=400, detail="Platform must be 'whatsapp' or 'facebook'")

    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """INSERT INTO wbom_contacts
                   (display_name, platform, whatsapp_number, notes)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (whatsapp_number, platform) DO UPDATE SET display_name = EXCLUDED.display_name
                   RETURNING contact_id AS id, display_name AS name, platform, whatsapp_number AS identifier""",
                (name, platform, identifier, psycopg2.extras.Json(body.get("metadata", {}))),
            )
            conn.commit()
            contact = dict(cur.fetchone())
            contact["id"] = str(contact["id"])

    return {"status": "created", "contact": contact}


# ── Contact Lookup (used by brain for persona injection) ──

@app.get("/contacts/lookup")
async def contact_lookup(phone: str, platform: str = "whatsapp"):
    """Lookup a contact by phone+platform. Used by brain service internally."""
    contact = get_contact(_get_conn, phone, platform)
    return {"contact": contact}


# ── Contact Book (wbom_contacts) — full management ────────

@app.get("/contacts/book")
async def contacts_book_list(
    platform: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """List contacts from contact book with optional search/filter."""
    contacts = list_all_contacts(_get_conn, platform, search or "", limit, offset)
    for c in contacts:
        c["id"] = str(c["id"])
        if c.get("last_seen"):
            c["last_seen"] = c["last_seen"].isoformat()
        if c.get("last_updated"):
            c["last_updated"] = c["last_updated"].isoformat()
    return {"contacts": contacts}


@app.get("/contacts/book/{contact_id}")
async def contacts_book_get(contact_id: str):
    """Get a single contact by ID."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT contact_id AS id, whatsapp_number AS phone, display_name AS name,
                          relation, notes, company_name AS company, personality_hint,
                          platform, interaction_count, interest_level, last_seen, updated_at AS last_updated,
                          created_at
                   FROM wbom_contacts WHERE contact_id = %s::int""",
                (contact_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Contact not found")
            c = dict(row)
            c["id"] = str(c["id"])
            if c.get("last_seen"):
                c["last_seen"] = c["last_seen"].isoformat()
            if c.get("last_updated"):
                c["last_updated"] = c["last_updated"].isoformat()
            if c.get("created_at"):
                c["created_at"] = c["created_at"].isoformat()
    return c


@app.put("/contacts/book/{contact_id}")
async def contacts_book_update(contact_id: str, body: dict):
    """Update contact fields (name, relation, notes, company, personality_hint, interest_level)."""
    ok = update_contact(_get_conn, contact_id, body)
    if not ok:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    return {"status": "updated"}


@app.delete("/contacts/book/{contact_id}")
async def contacts_book_delete(contact_id: str):
    """Delete a contact."""
    ok = delete_contact(_get_conn, contact_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Contact not found")
    return {"status": "deleted"}


@app.post("/contacts/import")
async def contacts_import(request: Request):
    """Import contacts from CSV. Columns: phone, name, relation, notes, company (optional).
    Accepts raw CSV text in the request body with Content-Type text/csv,
    or a JSON body with a 'csv' field containing the CSV text."""
    import csv as csv_mod
    content_type = request.headers.get("content-type", "")
    if "text/csv" in content_type:
        raw = (await request.body()).decode("utf-8", errors="replace")
    else:
        body = await request.json()
        raw = body.get("csv", "")
    if not raw.strip():
        raise HTTPException(status_code=400, detail="No CSV data provided")

    reader = csv_mod.DictReader(io.StringIO(raw))
    imported = 0
    errors = []
    for i, row in enumerate(reader, start=2):
        phone = (row.get("phone") or "").strip()
        if not phone:
            errors.append(f"Row {i}: missing phone")
            continue
        name = (row.get("name") or "").strip()
        relation = (row.get("relation") or "unknown").strip()
        notes = (row.get("notes") or "").strip()
        company = (row.get("company") or "").strip()
        personality = (row.get("personality_hint") or row.get("personality") or "").strip()
        platform = (row.get("platform") or "whatsapp").strip()
        try:
            upsert_contact(_get_conn, phone, name, platform, relation, notes, company, personality)
            imported += 1
        except Exception as e:
            errors.append(f"Row {i}: {e}")
    return {"status": "imported", "imported": imported, "errors": errors}


# ── Campaigns ──────────────────────────────────────────────

@app.get("/campaigns")
async def list_campaigns():
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM fazle_social_campaigns ORDER BY created_at DESC"
            )
            campaigns = [dict(r) for r in cur.fetchall()]
            for c in campaigns:
                c["id"] = str(c["id"])
    return {"campaigns": campaigns}


@app.post("/campaigns")
async def create_campaign(body: dict):
    name = body.get("name", "")
    platform = body.get("platform", "")
    campaign_type = body.get("campaign_type", "broadcast")

    if not name or not platform:
        raise HTTPException(status_code=400, detail="'name' and 'platform' are required")

    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """INSERT INTO fazle_social_campaigns (name, platform, campaign_type, config)
                   VALUES (%s, %s, %s, %s)
                   RETURNING id, name, platform, campaign_type, status""",
                (name, platform, campaign_type, psycopg2.extras.Json(body.get("config", {}))),
            )
            conn.commit()
            campaign = dict(cur.fetchone())
            campaign["id"] = str(campaign["id"])

    return {"status": "created", "campaign": campaign}


# ── Stats ──────────────────────────────────────────────────

@app.get("/stats")
async def social_stats():
    try:
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT COUNT(*) as total FROM wbom_contacts")
                total_contacts = cur.fetchone()["total"]

                cur.execute("SELECT COUNT(*) as total FROM wbom_whatsapp_messages WHERE platform = 'whatsapp'")
                whatsapp_messages = cur.fetchone()["total"]

                cur.execute("SELECT COUNT(*) as total FROM fazle_social_posts WHERE platform = 'facebook'")
                facebook_posts = cur.fetchone()["total"]

                cur.execute("SELECT COUNT(*) as total FROM fazle_social_scheduled WHERE status = 'pending'")
                pending_scheduled = cur.fetchone()["total"]

                cur.execute("SELECT COUNT(*) as total FROM fazle_social_campaigns WHERE status = 'running'")
                active_campaigns = cur.fetchone()["total"]

        return {
            "total_contacts": total_contacts,
            "whatsapp_messages": whatsapp_messages,
            "facebook_posts": facebook_posts,
            "pending_scheduled": pending_scheduled,
            "active_campaigns": active_campaigns,
        }
    except Exception as e:
        logger.error(f"Stats query failed: {e}")
        return {
            "total_contacts": 0,
            "whatsapp_messages": 0,
            "facebook_posts": 0,
            "pending_scheduled": 0,
            "active_campaigns": 0,
        }


# ── Reply Reuse & Learning Stats (Steps 11, 12, 16, 18) ───

@app.get("/reply-stats")
async def reply_stats():
    """Get reply reuse, feedback, summary, and multimodal stats."""
    try:
        stats = get_reply_stats(_get_conn)
        return stats
    except Exception as e:
        logger.error(f"Reply stats query failed: {e}")
        return {
            "cached_replies": 0,
            "total_reuses": 0,
            "owner_feedback": 0,
            "summaries": 0,
            "multimodal_items": 0,
        }


@app.get("/summaries")
async def list_summaries(phone: str = "", limit: int = 20):
    """Get conversation summaries, optionally filtered by phone."""
    try:
        summaries = get_conversation_summaries(_get_conn, user_phone=phone, limit=limit)
        for s in summaries:
            s["id"] = str(s["id"])
            if s.get("created_at"):
                s["created_at"] = s["created_at"].isoformat()
        return {"summaries": summaries}
    except Exception as e:
        logger.error(f"Summaries query failed: {e}")
        return {"summaries": []}


@app.get("/owner/audio-examples")
async def owner_audio_examples(limit: int = 10):
    """Get recent owner audio transcripts for style learning."""
    try:
        examples = get_owner_audio_examples(_get_conn, limit=limit)
        return {"examples": examples}
    except Exception as e:
        logger.error(f"Owner audio examples query failed: {e}")
        return {"examples": []}


@app.get("/feedback")
async def list_feedback(limit: int = 50):
    """Get owner feedback on AI replies."""
    try:
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM fazle_owner_feedback ORDER BY created_at DESC LIMIT %s",
                    (limit,),
                )
                rows = [dict(r) for r in cur.fetchall()]
                for r in rows:
                    r["id"] = str(r["id"])
                    if r.get("created_at"):
                        r["created_at"] = r["created_at"].isoformat()
        return {"feedback": rows}
    except Exception as e:
        logger.error(f"Feedback query failed: {e}")
        return {"feedback": []}


# ── Internal Endpoints (called by Brain service) ──────────

@app.post("/internal/save-summary")
async def internal_save_summary(request: Request):
    """Save a conversation summary (called by brain /chat/summarize)."""
    data = await request.json()
    conversation_id = data.get("conversation_id", "")
    user_phone = data.get("user_phone", "")
    summary = data.get("summary", "")
    message_count = data.get("message_count", 0)
    key_topics = data.get("key_topics", [])
    if not summary:
        return {"ok": False, "error": "summary is required"}
    save_conversation_summary(
        _get_conn,
        conversation_id=conversation_id,
        user_phone=user_phone,
        summary=summary,
        message_count=message_count,
        key_topics=key_topics,
    )
    return {"ok": True}
