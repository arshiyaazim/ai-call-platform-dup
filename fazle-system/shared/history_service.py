# ============================================================
# history_service.py — Unified Message History with Role-Based Context
# ============================================================
"""
Policy:
    owner/family/client/employee → FULL history forever
    job_applicant/unknown → keep all in DB, but AI context = last 3 messages
"""
import logging

logger = logging.getLogger("fazle.history")

# Role → max messages for AI context window
_CONTEXT_LIMITS = {
    "owner": 100,
    "family": 50,
    "employee": 20,
    "client": 20,
    "vendor": 10,
    "job_applicant": 3,
    "unknown": 3,
}


def save_message(conn, canonical_phone: str, *, direction: str, message_text: str,
                 platform: str = "whatsapp", role_snapshot: str = "unknown",
                 wa_message_id: str = "", raw_payload: dict | None = None) -> int:
    """Save a message to unified history. Returns the new message ID."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO message_history
                (canonical_phone, platform, direction, message_text, wa_message_id, raw_payload, role_snapshot)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
            RETURNING id
        """, (
            canonical_phone, platform, direction, message_text,
            wa_message_id,
            __import__("json").dumps(raw_payload or {}),
            role_snapshot,
        ))
        row = cur.fetchone()
        conn.commit()
        return row[0] if row else 0


def get_messages(conn, canonical_phone: str, *, limit: int = 50,
                 offset: int = 0, platform: str | None = None) -> list[dict]:
    """Get message history for a phone (newest first). Used for dashboard UI."""
    sql = """
        SELECT id, canonical_phone, platform, direction, message_text,
               wa_message_id, role_snapshot, created_at
        FROM message_history
        WHERE canonical_phone = %s
    """
    params = [canonical_phone]
    if platform:
        sql += " AND platform = %s"
        params.append(platform)
    sql += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_ai_context(conn, canonical_phone: str, role: str = "unknown") -> list[dict]:
    """Get messages formatted for AI context window. Respects role-based limits.

    Trusted roles: up to 20 msgs + summary.
    Untrusted roles: last 3 messages only.
    """
    limit = _CONTEXT_LIMITS.get(role, 3)

    with conn.cursor() as cur:
        cur.execute("""
            SELECT direction, message_text, created_at
            FROM message_history
            WHERE canonical_phone = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (canonical_phone, limit))
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]

    # Return in chronological order (oldest first) for AI context
    rows.reverse()
    return rows


def count_messages(conn, canonical_phone: str | None = None) -> int:
    """Count messages, optionally filtered by phone."""
    sql = "SELECT COUNT(*) FROM message_history"
    params = []
    if canonical_phone:
        sql += " WHERE canonical_phone = %s"
        params.append(canonical_phone)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0]
