# ============================================================
# Fazle API — Knowledge Base Routes
# Search, user lookup, access-controlled data retrieval
# ============================================================
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

import psycopg2
import psycopg2.extras
from database import _get_conn
from access_control import check_access, check_access_db, get_user_by_phone, get_user_access_rules

logger = logging.getLogger("fazle-api.knowledge")
router = APIRouter(prefix="/knowledge", tags=["knowledge"])


# ── Table creation (idempotent) ──────────────────────────────

def ensure_knowledge_tables():
    """Create knowledge tables if they don't exist. Called on startup."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS fazle_knowledge_users (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    phone TEXT UNIQUE,
                    role TEXT,
                    access_level TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_fku_phone
                    ON fazle_knowledge_users (phone);

                CREATE TABLE IF NOT EXISTS fazle_access_rules (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT REFERENCES fazle_knowledge_users(id) ON DELETE CASCADE,
                    data_type TEXT NOT NULL,
                    allowed BOOLEAN DEFAULT FALSE
                );
                CREATE INDEX IF NOT EXISTS idx_far_user
                    ON fazle_access_rules (user_id);

                CREATE TABLE IF NOT EXISTS fazle_knowledge_base (
                    id SERIAL PRIMARY KEY,
                    category TEXT NOT NULL,
                    subcategory TEXT,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    language TEXT DEFAULT 'bn-en',
                    confidence FLOAT DEFAULT 1.0,
                    tags TEXT[],
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_fkb_category
                    ON fazle_knowledge_base (category);
                CREATE INDEX IF NOT EXISTS idx_fkb_key
                    ON fazle_knowledge_base (key);

                CREATE TABLE IF NOT EXISTS fazle_feedback_learning (
                    id SERIAL PRIMARY KEY,
                    original_query TEXT NOT NULL,
                    ai_reply TEXT,
                    corrected_reply TEXT,
                    rating INT CHECK (rating BETWEEN 1 AND 5),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
        conn.commit()
    logger.info("Knowledge tables ensured (users, access_rules, knowledge_base, feedback_learning)")


def seed_knowledge_data():
    """Insert seed data (idempotent). Only inserts if tables are empty."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            # Only seed if no users exist yet
            cur.execute("SELECT COUNT(*) FROM fazle_knowledge_users")
            if cur.fetchone()[0] > 0:
                return

            # Users
            cur.execute("""
                INSERT INTO fazle_knowledge_users (id, name, phone, role, access_level) VALUES
                ('+8801848144841', 'Sajeda Yesmin', '+8801848144841', 'wife', 'full'),
                ('+8801772274173', 'Arshiya Wafiqah', '+8801772274173', 'daughter', 'full')
                ON CONFLICT (phone) DO NOTHING
            """)

            # Access rules
            cur.execute("""
                INSERT INTO fazle_access_rules (user_id, data_type, allowed) VALUES
                ('+8801848144841', 'personal', TRUE),
                ('+8801772274173', 'personal', TRUE)
            """)

            # Personal knowledge
            cur.execute("""
                INSERT INTO fazle_knowledge_base (category, key, value, language, confidence) VALUES
                ('personal', 'full_name', 'Azim', 'bn-en', 1.0),
                ('personal', 'father_name', 'A. K. M. Shah Alam', 'bn-en', 1.0),
                ('personal', 'mother_name', 'Akter Jahan Alo', 'bn-en', 1.0),
                ('personal', 'spouse_name', 'Sajeda Yesmin', 'bn-en', 1.0),
                ('personal', 'date_of_birth', '1980-11-30', 'bn-en', 1.0),
                ('personal', 'birth_place', 'Khagrachari', 'bn-en', 1.0),
                ('personal', 'nid_number', '1595708912924', 'bn-en', 1.0),
                ('personal', 'blood_group', 'AB+', 'bn-en', 1.0),
                ('personal', 'passport_number', 'A02235098', 'bn-en', 1.0),
                ('personal', 'passport_expiry', '2031-11-13', 'bn-en', 1.0),
                ('personal', 'address', 'Faruk Villa, Arakan Housing Society, Chandgaon, Chattogram', 'bn-en', 1.0)
            """)

            # Business knowledge
            cur.execute("""
                INSERT INTO fazle_knowledge_base (category, key, value, language, confidence) VALUES
                ('business', 'company_name', 'AL-AQSA SECURITY & LOGISTICS SERVICES LTD.', 'bn-en', 1.0),
                ('business', 'tin', '250686246674', 'bn-en', 1.0),
                ('business', 'company_address', 'Akborsha, Chattogram', 'bn-en', 1.0),
                ('business', 'brac_account', '20604039890001', 'bn-en', 1.0),
                ('business', 'one_bank_account', '06310200007495', 'bn-en', 1.0)
            """)
        conn.commit()
    logger.info("Knowledge seed data inserted")


# ── Pydantic models ──────────────────────────────────────────

class KnowledgeSearchResult(BaseModel):
    id: int
    category: str
    key: str
    value: str
    confidence: float


class FeedbackSubmit(BaseModel):
    original_query: str
    ai_reply: str
    corrected_reply: Optional[str] = None
    rating: int


class KnowledgeInsert(BaseModel):
    category: str
    key: str
    value: str
    subcategory: Optional[str] = None
    language: str = "bn-en"
    confidence: float = 1.0
    tags: Optional[list[str]] = None


# ── Search endpoint ──────────────────────────────────────────

@router.get("/search")
def search_knowledge(
    q: str = Query(..., min_length=1, max_length=200, description="Search query"),
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(20, ge=1, le=100),
    caller_id: Optional[str] = Query(None, description="Phone or user ID for access check"),
):
    """Search knowledge base. Personal data requires access check."""
    results = _search_knowledge_db(q, category, limit)

    # Filter out personal data if caller has no access
    if caller_id:
        has_personal_access = check_access_db(caller_id, "personal")
    else:
        has_personal_access = False

    filtered = []
    for row in results:
        if row["category"] == "personal" and not has_personal_access:
            continue
        filtered.append(row)

    return {"results": filtered, "count": len(filtered)}


def _search_knowledge_db(q: str, category: Optional[str], limit: int) -> list[dict]:
    """Search knowledge_base with ILIKE. Parameterized to prevent SQL injection."""
    try:
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if category:
                    cur.execute(
                        "SELECT id, category, subcategory, key, value, confidence, created_at "
                        "FROM fazle_knowledge_base "
                        "WHERE (value ILIKE %s OR key ILIKE %s) AND category = %s "
                        "ORDER BY confidence DESC LIMIT %s",
                        (f"%{q}%", f"%{q}%", category, limit),
                    )
                else:
                    cur.execute(
                        "SELECT id, category, subcategory, key, value, confidence, created_at "
                        "FROM fazle_knowledge_base "
                        "WHERE value ILIKE %s OR key ILIKE %s "
                        "ORDER BY confidence DESC LIMIT %s",
                        (f"%{q}%", f"%{q}%", limit),
                    )
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error(f"knowledge search failed: {e}")
        return []


# ── User lookup ──────────────────────────────────────────────

@router.get("/user/{phone}")
def get_knowledge_user(phone: str):
    """Lookup a user by phone number."""
    user = get_user_by_phone(phone)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# ── Feedback submission ──────────────────────────────────────

@router.post("/feedback")
def submit_feedback(fb: FeedbackSubmit):
    """Submit feedback on AI response for learning."""
    try:
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "INSERT INTO fazle_feedback_learning "
                    "(original_query, ai_reply, corrected_reply, rating) "
                    "VALUES (%s, %s, %s, %s) RETURNING id, created_at",
                    (fb.original_query, fb.ai_reply, fb.corrected_reply, fb.rating),
                )
                conn.commit()
                row = cur.fetchone()
                return {"status": "saved", "id": row["id"]}
    except Exception as e:
        logger.error(f"feedback save failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to save feedback")


# ── Knowledge insert (admin) ─────────────────────────────────

@router.post("/insert")
def insert_knowledge(entry: KnowledgeInsert):
    """Insert a new knowledge entry. For admin/internal use."""
    try:
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "INSERT INTO fazle_knowledge_base "
                    "(category, subcategory, key, value, language, confidence, tags) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (
                        entry.category,
                        entry.subcategory,
                        entry.key,
                        entry.value,
                        entry.language,
                        entry.confidence,
                        entry.tags,
                    ),
                )
                conn.commit()
                row = cur.fetchone()
                return {"status": "inserted", "id": row["id"]}
    except Exception as e:
        logger.error(f"knowledge insert failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to insert knowledge")


# ── Knowledge add (with duplicate check) ─────────────────────

@router.post("/add")
def add_knowledge(data: dict):
    """Add a knowledge entry with duplicate check on key. Returns exists/inserted."""
    key = data.get("key")
    if not key:
        raise HTTPException(status_code=400, detail="key is required")
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM fazle_knowledge_base WHERE key = %s",
                    (key,),
                )
                if cur.fetchone():
                    return {"status": "exists", "key": key}

                cur.execute(
                    "INSERT INTO fazle_knowledge_base "
                    "(category, key, value, language, confidence) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (
                        data.get("category", "general"),
                        key,
                        data.get("value", ""),
                        data.get("language", "bn-en"),
                        data.get("confidence", 1.0),
                    ),
                )
            conn.commit()
        return {"status": "inserted", "key": key}
    except Exception as e:
        logger.error(f"knowledge add failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Context builder for AI prompt injection ──────────────────

def build_knowledge_context(message: str, caller_id: Optional[str] = None, caller_role: Optional[str] = None) -> str:
    """Build a knowledge context string for AI prompt injection.

    Scans the message for keywords and fetches relevant knowledge
    from the database, respecting access control.
    """
    context_parts = []
    msg_lower = message.lower()

    # Determine access
    has_personal_access = False
    if caller_role:
        has_personal_access = check_access(caller_role, "personal")
    elif caller_id:
        has_personal_access = check_access_db(caller_id, "personal")

    # Personal data triggers
    personal_triggers = ["nid", "passport", "জাতীয় পরিচয়", "পাসপোর্ট", "birthday",
                         "জন্মদিন", "blood", "রক্ত", "address", "ঠিকানা",
                         "father", "mother", "বাবা", "মা", "wife", "স্ত্রী"]
    if has_personal_access and any(t in msg_lower for t in personal_triggers):
        personal_data = _fetch_category("personal")
        if personal_data:
            context_parts.append("--- PERSONAL DATA (AUTHORIZED) ---")
            for row in personal_data:
                context_parts.append(f"  {row['key']}: {row['value']}")
            context_parts.append("--- END PERSONAL DATA ---")

    # Business data triggers
    business_triggers = ["company", "business", "কোম্পানি", "tin", "টিন",
                         "bank", "ব্যাংক", "account", "একাউন্ট", "al-aqsa",
                         "security", "logistics"]
    if any(t in msg_lower for t in business_triggers):
        business_data = _fetch_category("business")
        if business_data:
            context_parts.append("--- BUSINESS DATA ---")
            for row in business_data:
                context_parts.append(f"  {row['key']}: {row['value']}")
            context_parts.append("--- END BUSINESS DATA ---")

    if not context_parts:
        return ""
    return "\n".join(context_parts)


def _fetch_category(category: str) -> list[dict]:
    """Fetch all knowledge entries for a category."""
    try:
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT key, value FROM fazle_knowledge_base "
                    "WHERE category = %s ORDER BY key LIMIT 50",
                    (category,),
                )
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error(f"fetch category {category} failed: {e}")
        return []
