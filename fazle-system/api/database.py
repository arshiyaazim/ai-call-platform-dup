# ============================================================
# Fazle API — PostgreSQL Database Layer
# User management with async connection pool
# ============================================================
import logging
import uuid
from datetime import datetime
from typing import Optional

import psycopg2
import psycopg2.extras
import psycopg2.pool
from contextlib import contextmanager
from pydantic_settings import BaseSettings

logger = logging.getLogger("fazle-api")

psycopg2.extras.register_uuid()


class DBSettings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@postgres:5432/postgres"

    class Config:
        env_prefix = "FAZLE_"


db_settings = DBSettings()

_DSN = db_settings.database_url

# Connection pool: min 2, max 10 connections
_pool = psycopg2.pool.ThreadedConnectionPool(2, 10, _DSN)


@contextmanager
def _get_conn():
    conn = _pool.getconn()
    try:
        yield conn
    finally:
        _pool.putconn(conn)


def _put_conn(conn):
    _pool.putconn(conn)


@contextmanager
def _rls_conn(user_id: Optional[str] = None, is_admin: bool = False):
    """Get a connection with RLS session variables set."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            if user_id:
                cur.execute("SET LOCAL app.current_user_id = %s", (str(user_id),))
            if is_admin:
                cur.execute("SET LOCAL app.is_admin = 'true'")
        yield conn
    finally:
        _put_conn(conn)


def ensure_users_table():
    """Create users and conversations tables if they don't exist (idempotent)."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS fazle_users (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    email VARCHAR(255) UNIQUE NOT NULL,
                    hashed_password VARCHAR(255) NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    relationship_to_azim VARCHAR(50) NOT NULL DEFAULT 'self',
                    role VARCHAR(20) NOT NULL DEFAULT 'member',
                    is_active BOOLEAN DEFAULT true,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_fazle_users_email ON fazle_users (email);

                CREATE TABLE IF NOT EXISTS fazle_conversations (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL REFERENCES fazle_users(id) ON DELETE CASCADE,
                    conversation_id VARCHAR(100) NOT NULL,
                    title VARCHAR(200) DEFAULT '',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE(conversation_id)
                );
                CREATE INDEX IF NOT EXISTS idx_fazle_conv_user ON fazle_conversations (user_id);

                CREATE TABLE IF NOT EXISTS fazle_messages (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    conversation_id UUID NOT NULL REFERENCES fazle_conversations(id) ON DELETE CASCADE,
                    role VARCHAR(20) NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_fazle_msg_conv ON fazle_messages (conversation_id);
            """)
        conn.commit()
    logger.info("fazle_users, fazle_conversations, fazle_messages tables ensured")


def create_user(
    email: str,
    hashed_password: str,
    name: str,
    relationship_to_azim: str = "self",
    role: str = "member",
) -> dict:
    """Insert a new user, return the user dict (without password)."""
    user_id = uuid.uuid4()
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO fazle_users (id, email, hashed_password, name, relationship_to_azim, role)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, email, name, relationship_to_azim, role, is_active, created_at
                """,
                (user_id, email, hashed_password, name, relationship_to_azim, role),
            )
            conn.commit()
            return dict(cur.fetchone())


def get_user_by_email(email: str) -> Optional[dict]:
    """Fetch user by email (includes hashed_password for verification)."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, email, hashed_password, name, relationship_to_azim, role, is_active, created_at FROM fazle_users WHERE email = %s",
                (email,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def get_user_by_id(user_id: str) -> Optional[dict]:
    """Fetch user by ID (without password)."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, email, name, relationship_to_azim, role, is_active, created_at FROM fazle_users WHERE id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def list_family_members() -> list[dict]:
    """List all family members (without passwords)."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, email, name, relationship_to_azim, role, is_active, created_at FROM fazle_users ORDER BY created_at"
            )
            return [dict(row) for row in cur.fetchall()]


def update_user(user_id: str, **fields) -> Optional[dict]:
    """Update user fields. Returns updated user or None."""
    allowed = {"name", "relationship_to_azim", "role", "is_active"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_user_by_id(user_id)

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [user_id]

    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"UPDATE fazle_users SET {set_clause}, updated_at = NOW() WHERE id = %s "
                "RETURNING id, email, name, relationship_to_azim, role, is_active, created_at",
                values,
            )
            conn.commit()
            row = cur.fetchone()
            return dict(row) if row else None


def delete_user(user_id: str) -> bool:
    """Delete a user. Returns True if deleted."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM fazle_users WHERE id = %s", (user_id,))
            conn.commit()
            return cur.rowcount > 0


def count_users() -> int:
    """Count total users."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM fazle_users")
            return cur.fetchone()[0]


# ── Conversation persistence ────────────────────────────────

def save_message(user_id: str, conversation_id: str, role: str, content: str, title: str = ""):
    """Save a chat message. Creates or updates the conversation record."""
    with _rls_conn(user_id) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Upsert conversation
            cur.execute(
                """
                INSERT INTO fazle_conversations (user_id, conversation_id, title)
                VALUES (%s, %s, %s)
                ON CONFLICT (conversation_id) DO UPDATE SET updated_at = NOW()
                RETURNING id
                """,
                (user_id, conversation_id, title[:200] if title else ""),
            )
            conv_row = cur.fetchone()
            conv_uuid = conv_row["id"]
            # Insert message
            cur.execute(
                """
                INSERT INTO fazle_messages (conversation_id, role, content)
                VALUES (%s, %s, %s)
                """,
                (conv_uuid, role, content),
            )
        conn.commit()


def get_user_conversations(user_id: str, limit: int = 30) -> list[dict]:
    """List conversations for a user, newest first."""
    with _rls_conn(user_id) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT c.conversation_id, c.title, c.created_at, c.updated_at,
                       (SELECT content FROM fazle_messages WHERE conversation_id = c.id ORDER BY created_at DESC LIMIT 1) AS last_message
                FROM fazle_conversations c
                WHERE c.user_id = %s
                ORDER BY c.updated_at DESC
                LIMIT %s
                """,
                (user_id, limit),
            )
            return [dict(r) for r in cur.fetchall()]


def get_conversation_messages(conversation_id: str, user_id: str = None) -> list[dict]:
    """Get messages for a conversation. If user_id given, verify ownership."""
    with _rls_conn(user_id) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if user_id:
                cur.execute(
                    """
                    SELECT m.role, m.content, m.created_at
                    FROM fazle_messages m
                    JOIN fazle_conversations c ON c.id = m.conversation_id
                    WHERE c.conversation_id = %s AND c.user_id = %s
                    ORDER BY m.created_at
                    """,
                    (conversation_id, user_id),
                )
            else:
                # Admin: no user filter
                cur.execute(
                    """
                    SELECT m.role, m.content, m.created_at
                    FROM fazle_messages m
                    JOIN fazle_conversations c ON c.id = m.conversation_id
                    WHERE c.conversation_id = %s
                    ORDER BY m.created_at
                    """,
                    (conversation_id,),
                )
            return [dict(r) for r in cur.fetchall()]


def get_all_conversations(limit: int = 50) -> list[dict]:
    """Admin: list all conversations across all users."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT c.conversation_id, c.title, c.created_at, c.updated_at,
                       u.name AS user_name, u.relationship_to_azim,
                       (SELECT content FROM fazle_messages WHERE conversation_id = c.id ORDER BY created_at DESC LIMIT 1) AS last_message
                FROM fazle_conversations c
                JOIN fazle_users u ON u.id = c.user_id
                ORDER BY c.updated_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(r) for r in cur.fetchall()]


def delete_conversation(conversation_id: str) -> bool:
    """Delete a conversation and its messages. Returns True if deleted."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM fazle_conversations WHERE conversation_id = %s",
                (conversation_id,),
            )
            conn.commit()
            return cur.rowcount > 0


# ── Admin config tables ─────────────────────────────────────

def ensure_admin_tables():
    """Create admin config tables for agents, plugins, tasks, persona."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS fazle_admin_agents (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    name VARCHAR(100) NOT NULL,
                    model VARCHAR(100) NOT NULL DEFAULT 'gpt-4o-mini',
                    priority INTEGER NOT NULL DEFAULT 1,
                    description TEXT DEFAULT '',
                    status VARCHAR(20) NOT NULL DEFAULT 'active',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS fazle_admin_plugins (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    name VARCHAR(100) NOT NULL,
                    description TEXT DEFAULT '',
                    version VARCHAR(30) DEFAULT '1.0.0',
                    status VARCHAR(20) NOT NULL DEFAULT 'enabled',
                    manifest JSONB DEFAULT '{}',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS fazle_admin_tasks (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    title VARCHAR(200) NOT NULL,
                    task_type VARCHAR(50) NOT NULL DEFAULT 'reminder',
                    schedule VARCHAR(100) DEFAULT '',
                    scheduled_at TIMESTAMPTZ,
                    description TEXT DEFAULT '',
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS fazle_admin_persona (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    name VARCHAR(100) NOT NULL DEFAULT 'Azim',
                    tone TEXT DEFAULT 'Warm, caring, knowledgeable',
                    language VARCHAR(50) DEFAULT 'English',
                    speaking_style TEXT DEFAULT '',
                    knowledge_notes TEXT DEFAULT '',
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT single_persona CHECK (id = 1)
                );

                INSERT INTO fazle_admin_persona (id, name, tone, language, speaking_style, knowledge_notes)
                VALUES (1, 'Azim', 'Warm, caring, knowledgeable', 'English',
                        'Natural conversational tone with occasional humor. Speaks like a thoughtful friend.',
                        'Family AI assistant with deep personal knowledge.')
                ON CONFLICT (id) DO NOTHING;
            """)
        conn.commit()
    logger.info("Admin config tables ensured (agents, plugins, tasks, persona)")


# ── Agent CRUD ──────────────────────────────────────────────

def list_agents() -> list[dict]:
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM fazle_admin_agents ORDER BY priority, created_at")
            return [dict(r) for r in cur.fetchall()]


def get_agent(agent_id: str) -> Optional[dict]:
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM fazle_admin_agents WHERE id = %s", (agent_id,))
            row = cur.fetchone()
            return dict(row) if row else None


def create_agent(name: str, model: str, priority: int, description: str, status: str = "active") -> dict:
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """INSERT INTO fazle_admin_agents (name, model, priority, description, status)
                   VALUES (%s, %s, %s, %s, %s) RETURNING *""",
                (name, model, priority, description, status),
            )
            conn.commit()
            return dict(cur.fetchone())


def update_agent(agent_id: str, **fields) -> Optional[dict]:
    allowed = {"name", "model", "priority", "description", "status"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_agent(agent_id)
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [agent_id]
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"UPDATE fazle_admin_agents SET {set_clause}, updated_at = NOW() WHERE id = %s RETURNING *",
                values,
            )
            conn.commit()
            row = cur.fetchone()
            return dict(row) if row else None


def delete_agent(agent_id: str) -> bool:
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM fazle_admin_agents WHERE id = %s", (agent_id,))
            conn.commit()
            return cur.rowcount > 0


# ── Plugin CRUD ─────────────────────────────────────────────

def list_plugins() -> list[dict]:
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM fazle_admin_plugins ORDER BY created_at")
            return [dict(r) for r in cur.fetchall()]


def create_plugin(name: str, description: str, version: str, status: str = "enabled", manifest: dict = None) -> dict:
    import json
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """INSERT INTO fazle_admin_plugins (name, description, version, status, manifest)
                   VALUES (%s, %s, %s, %s, %s) RETURNING *""",
                (name, description, version, status, json.dumps(manifest or {})),
            )
            conn.commit()
            return dict(cur.fetchone())


def update_plugin(plugin_id: str, **fields) -> Optional[dict]:
    import json
    allowed = {"name", "description", "version", "status"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if "manifest" in fields and fields["manifest"] is not None:
        updates["manifest"] = json.dumps(fields["manifest"])
    if not updates:
        return get_plugin(plugin_id)
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [plugin_id]
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"UPDATE fazle_admin_plugins SET {set_clause}, updated_at = NOW() WHERE id = %s RETURNING *",
                values,
            )
            conn.commit()
            row = cur.fetchone()
            return dict(row) if row else None


def get_plugin(plugin_id: str) -> Optional[dict]:
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM fazle_admin_plugins WHERE id = %s", (plugin_id,))
            row = cur.fetchone()
            return dict(row) if row else None


def delete_plugin(plugin_id: str) -> bool:
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM fazle_admin_plugins WHERE id = %s", (plugin_id,))
            conn.commit()
            return cur.rowcount > 0


# ── Admin Task CRUD ─────────────────────────────────────────

def list_admin_tasks() -> list[dict]:
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM fazle_admin_tasks ORDER BY created_at DESC")
            return [dict(r) for r in cur.fetchall()]


def create_admin_task(title: str, task_type: str, schedule: str = "",
                      scheduled_at: str = None, description: str = "", status: str = "pending") -> dict:
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """INSERT INTO fazle_admin_tasks (title, task_type, schedule, scheduled_at, description, status)
                   VALUES (%s, %s, %s, %s, %s, %s) RETURNING *""",
                (title, task_type, schedule, scheduled_at, description, status),
            )
            conn.commit()
            return dict(cur.fetchone())


def update_admin_task(task_id: str, **fields) -> Optional[dict]:
    allowed = {"title", "task_type", "schedule", "scheduled_at", "description", "status"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_admin_task(task_id)
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [task_id]
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"UPDATE fazle_admin_tasks SET {set_clause}, updated_at = NOW() WHERE id = %s RETURNING *",
                values,
            )
            conn.commit()
            row = cur.fetchone()
            return dict(row) if row else None


def get_admin_task(task_id: str) -> Optional[dict]:
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM fazle_admin_tasks WHERE id = %s", (task_id,))
            row = cur.fetchone()
            return dict(row) if row else None


def delete_admin_task(task_id: str) -> bool:
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM fazle_admin_tasks WHERE id = %s", (task_id,))
            conn.commit()
            return cur.rowcount > 0


# ── Persona ─────────────────────────────────────────────────

def get_persona() -> dict:
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM fazle_admin_persona WHERE id = 1")
            row = cur.fetchone()
            if row:
                return dict(row)
            return {
                "name": "Azim", "tone": "Warm, caring, knowledgeable",
                "language": "English",
                "speaking_style": "Natural conversational tone with occasional humor.",
                "knowledge_notes": "Family AI assistant with deep personal knowledge.",
            }


def update_persona(**fields) -> dict:
    allowed = {"name", "tone", "language", "speaking_style", "knowledge_notes"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return get_persona()
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values())
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"UPDATE fazle_admin_persona SET {set_clause}, updated_at = NOW() WHERE id = 1 RETURNING *",
                values,
            )
            conn.commit()
            row = cur.fetchone()
            return dict(row) if row else get_persona()


# ── Dashboard stats ─────────────────────────────────────────

def get_dashboard_stats() -> dict:
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM fazle_admin_agents WHERE status = 'active'")
            active_agents = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM fazle_admin_agents")
            total_agents = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM fazle_admin_plugins WHERE status = 'enabled'")
            active_plugins = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM fazle_admin_tasks WHERE status IN ('pending', 'running')")
            active_tasks = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM fazle_admin_tasks")
            total_tasks = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM fazle_conversations")
            total_conversations = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM fazle_users")
            total_users = cur.fetchone()[0]
            return {
                "active_agents": active_agents,
                "total_agents": total_agents,
                "active_plugins": active_plugins,
                "active_tasks": active_tasks,
                "total_tasks": total_tasks,
                "total_conversations": total_conversations,
                "total_users": total_users,
            }


# ── Password Management ────────────────────────────────────

def ensure_password_reset_table():
    """Create the password_reset_tokens table (idempotent)."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS fazle_password_reset_tokens (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL REFERENCES fazle_users(id) ON DELETE CASCADE,
                    token_hash VARCHAR(255) NOT NULL,
                    expires_at TIMESTAMPTZ NOT NULL,
                    used BOOLEAN DEFAULT false,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_pw_reset_user ON fazle_password_reset_tokens (user_id);
                CREATE INDEX IF NOT EXISTS idx_pw_reset_expires ON fazle_password_reset_tokens (expires_at);
            """)
        conn.commit()
    logger.info("fazle_password_reset_tokens table ensured")


def update_user_password(user_id: str, hashed_password: str) -> bool:
    """Update a user's hashed password. Returns True if updated."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE fazle_users SET hashed_password = %s, updated_at = NOW() WHERE id = %s",
                (hashed_password, user_id),
            )
            conn.commit()
            return cur.rowcount > 0


def create_password_reset_token(user_id: str, token_hash: str, expires_at) -> dict:
    """Store a hashed password reset token."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Invalidate any existing tokens for this user
            cur.execute(
                "UPDATE fazle_password_reset_tokens SET used = true WHERE user_id = %s AND used = false",
                (user_id,),
            )
            cur.execute(
                """INSERT INTO fazle_password_reset_tokens (user_id, token_hash, expires_at)
                   VALUES (%s, %s, %s) RETURNING id, user_id, expires_at, created_at""",
                (user_id, token_hash, expires_at),
            )
            conn.commit()
            return dict(cur.fetchone())


def get_valid_reset_token(token_hash: str) -> Optional[dict]:
    """Find a valid (unused, non-expired) reset token by hash."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT t.id, t.user_id, t.expires_at, u.email
                   FROM fazle_password_reset_tokens t
                   JOIN fazle_users u ON u.id = t.user_id
                   WHERE t.token_hash = %s AND t.used = false AND t.expires_at > NOW()""",
                (token_hash,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def mark_reset_token_used(token_id: str) -> None:
    """Mark a reset token as used."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE fazle_password_reset_tokens SET used = true WHERE id = %s",
                (token_id,),
            )
            conn.commit()


# ── GDPR Compliance Tables ──────────────────────────────────

def ensure_gdpr_tables():
    """Create GDPR-related tables (idempotent)."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS gdpr_requests (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID,
                    request_type VARCHAR(30) NOT NULL,
                    status VARCHAR(30) NOT NULL DEFAULT 'pending',
                    confirmation_code VARCHAR(64),
                    fb_user_id VARCHAR(100),
                    deleted_tables TEXT DEFAULT '',
                    error_message TEXT DEFAULT '',
                    retry_count INTEGER DEFAULT 0,
                    encryption_key_hint VARCHAR(16) DEFAULT '',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    completed_at TIMESTAMPTZ,
                    scheduled_at TIMESTAMPTZ
                );
                CREATE INDEX IF NOT EXISTS idx_gdpr_req_user ON gdpr_requests (user_id);
                CREATE INDEX IF NOT EXISTS idx_gdpr_req_code ON gdpr_requests (confirmation_code);
                CREATE INDEX IF NOT EXISTS idx_gdpr_req_status ON gdpr_requests (status);

                CREATE TABLE IF NOT EXISTS gdpr_audit_logs (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL,
                    action VARCHAR(100) NOT NULL,
                    details TEXT DEFAULT '',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_gdpr_audit_user ON gdpr_audit_logs (user_id);

                CREATE TABLE IF NOT EXISTS user_consents (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL REFERENCES fazle_users(id) ON DELETE CASCADE,
                    terms_accepted BOOLEAN NOT NULL DEFAULT false,
                    privacy_accepted BOOLEAN NOT NULL DEFAULT false,
                    accepted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE(user_id)
                );

                CREATE TABLE IF NOT EXISTS user_identities (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL REFERENCES fazle_users(id) ON DELETE CASCADE,
                    email VARCHAR(255),
                    facebook_id VARCHAR(100),
                    whatsapp_id VARCHAR(100),
                    phone_number VARCHAR(30),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE(user_id)
                );
                CREATE INDEX IF NOT EXISTS idx_identity_fb ON user_identities (facebook_id);
                CREATE INDEX IF NOT EXISTS idx_identity_wa ON user_identities (whatsapp_id);
                CREATE INDEX IF NOT EXISTS idx_identity_phone ON user_identities (phone_number);
            """)
            # Add columns if missing (for upgrades from old schema)
            gdpr_cols = [
                ("confirmation_code", "VARCHAR(64)"),
                ("fb_user_id", "VARCHAR(100)"),
                ("deleted_tables", "TEXT DEFAULT ''"),
                ("error_message", "TEXT DEFAULT ''"),
                ("retry_count", "INTEGER DEFAULT 0"),
                ("encryption_key_hint", "VARCHAR(16) DEFAULT ''"),
                ("scheduled_at", "TIMESTAMPTZ"),
            ]
            for col, typ in gdpr_cols:
                try:
                    cur.execute(
                        f"ALTER TABLE gdpr_requests ADD COLUMN IF NOT EXISTS {col} {typ}"
                    )
                except Exception:
                    conn.rollback()
        conn.commit()
    logger.info("GDPR tables ensured (gdpr_requests, gdpr_audit_logs, user_consents, user_identities)")


def create_gdpr_request(user_id: str, request_type: str) -> dict:
    """Create a new GDPR request (access/export/delete)."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO gdpr_requests (user_id, request_type)
                VALUES (%s, %s)
                RETURNING id, user_id, request_type, status, created_at, completed_at
                """,
                (user_id, request_type),
            )
            conn.commit()
            return dict(cur.fetchone())


def complete_gdpr_request(request_id: str, status: str = "completed") -> None:
    """Mark a GDPR request as completed or failed."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE gdpr_requests SET status = %s, completed_at = NOW() WHERE id = %s",
                (status, request_id),
            )
            conn.commit()


def get_gdpr_requests(user_id: str) -> list[dict]:
    """Get all GDPR requests for a user."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, request_type, status, created_at, completed_at FROM gdpr_requests WHERE user_id = %s ORDER BY created_at DESC",
                (user_id,),
            )
            return [dict(r) for r in cur.fetchall()]


def log_gdpr_action(user_id: str, action: str, details: str = "") -> None:
    """Log a GDPR audit action."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO gdpr_audit_logs (user_id, action, details) VALUES (%s, %s, %s)",
                    (user_id, action, details[:2000]),
                )
                conn.commit()
    except Exception as e:
        logger.error(f"GDPR audit log write failed: {e}")


def save_consent(user_id: str, terms: bool, privacy: bool) -> dict:
    """Upsert user consent record."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO user_consents (user_id, terms_accepted, privacy_accepted, accepted_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (user_id) DO UPDATE
                    SET terms_accepted = EXCLUDED.terms_accepted,
                        privacy_accepted = EXCLUDED.privacy_accepted,
                        accepted_at = NOW()
                RETURNING id, user_id, terms_accepted, privacy_accepted, accepted_at
                """,
                (user_id, terms, privacy),
            )
            conn.commit()
            return dict(cur.fetchone())


def get_consent(user_id: str) -> Optional[dict]:
    """Get user consent record."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT terms_accepted, privacy_accepted, accepted_at FROM user_consents WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def get_user_all_data(user_id: str) -> dict:
    """Collect all data associated with a user for GDPR access/export."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Profile
            cur.execute(
                "SELECT id, email, name, relationship_to_azim, role, is_active, created_at FROM fazle_users WHERE id = %s",
                (user_id,),
            )
            profile = cur.fetchone()
            if not profile:
                return {}
            profile = dict(profile)

            # Conversations + messages
            cur.execute(
                """
                SELECT c.conversation_id, c.title, c.created_at,
                       json_agg(json_build_object('role', m.role, 'content', m.content, 'created_at', m.created_at) ORDER BY m.created_at) AS messages
                FROM fazle_conversations c
                LEFT JOIN fazle_messages m ON m.conversation_id = c.id
                WHERE c.user_id = %s
                GROUP BY c.id ORDER BY c.created_at
                """,
                (user_id,),
            )
            conversations = [dict(r) for r in cur.fetchall()]

            # Consent
            cur.execute(
                "SELECT terms_accepted, privacy_accepted, accepted_at FROM user_consents WHERE user_id = %s",
                (user_id,),
            )
            consent_row = cur.fetchone()
            consent = dict(consent_row) if consent_row else None

            # Audit logs
            cur.execute(
                "SELECT action, details, created_at FROM gdpr_audit_logs WHERE user_id = %s ORDER BY created_at",
                (user_id,),
            )
            audit_logs = [dict(r) for r in cur.fetchall()]

            return {
                "profile": profile,
                "conversations": conversations,
                "consent": consent,
                "audit_logs": audit_logs,
            }


def delete_user_all_data(user_id: str) -> list[str]:
    """Delete all data associated with a user (GDPR right to erasure).
    Returns list of tables data was deleted from, or empty list on failure."""
    deleted_from: list[str] = []
    with _get_conn() as conn:
        with conn.cursor() as cur:
            # Tables with user_id column to delete from (order matters for FK)
            optional_tables = [
                "social_messages",
                "social_contacts",
                "memory_logs",
                "workflow_history",
                "password_reset_tokens",
            ]
            for table in optional_tables:
                try:
                    cur.execute(
                        "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = %s)",
                        (table,),
                    )
                    if cur.fetchone()[0]:
                        cur.execute(f"DELETE FROM {table} WHERE user_id = %s", (user_id,))
                        if cur.rowcount > 0:
                            deleted_from.append(table)
                except Exception:
                    conn.rollback()

            # Consent
            try:
                cur.execute("DELETE FROM user_consents WHERE user_id = %s", (user_id,))
                if cur.rowcount > 0:
                    deleted_from.append("user_consents")
            except Exception:
                conn.rollback()

            # GDPR audit logs — keep for legal compliance, anonymize
            try:
                cur.execute(
                    "UPDATE gdpr_audit_logs SET details = '[REDACTED]' WHERE user_id = %s",
                    (user_id,),
                )
                if cur.rowcount > 0:
                    deleted_from.append("gdpr_audit_logs (anonymized)")
            except Exception:
                conn.rollback()

            # Conversations + messages (cascade via FK)
            try:
                cur.execute("DELETE FROM fazle_conversations WHERE user_id = %s", (user_id,))
                if cur.rowcount > 0:
                    deleted_from.append("fazle_conversations")
            except Exception:
                conn.rollback()

            # User record
            try:
                cur.execute("DELETE FROM fazle_users WHERE id = %s", (user_id,))
                if cur.rowcount > 0:
                    deleted_from.append("fazle_users")
            except Exception:
                conn.rollback()

            conn.commit()
    return deleted_from


def find_user_by_facebook_id(fb_user_id: str) -> Optional[dict]:
    """Try to find an internal user linked to a Facebook user ID."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Check social_contacts table for FB user mapping
            try:
                cur.execute(
                    "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = 'social_contacts')"
                )
                if cur.fetchone()["exists"]:
                    cur.execute(
                        """SELECT u.id, u.email FROM fazle_users u
                           JOIN social_contacts sc ON sc.user_id = u.id
                           WHERE sc.platform = 'facebook' AND sc.platform_user_id = %s
                           LIMIT 1""",
                        (fb_user_id,),
                    )
                    row = cur.fetchone()
                    if row:
                        return dict(row)
            except Exception:
                pass

            # Fallback: check fazle_users metadata column if it exists
            try:
                cur.execute(
                    "SELECT id, email FROM fazle_users WHERE metadata->>'facebook_id' = %s LIMIT 1",
                    (fb_user_id,),
                )
                row = cur.fetchone()
                if row:
                    return dict(row)
            except Exception:
                pass
    return None


def create_facebook_deletion_request(
    fb_user_id: str, confirmation_code: str, deleted_tables: list[str]
) -> None:
    """Store a Facebook data deletion request for status tracking."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO gdpr_requests
                   (user_id, request_type, status, confirmation_code, fb_user_id, deleted_tables, completed_at)
                   VALUES (%s, 'facebook_deletion', 'completed', %s, %s, %s, NOW())""",
                (
                    "00000000-0000-0000-0000-000000000000",
                    confirmation_code,
                    fb_user_id,
                    ", ".join(deleted_tables) if deleted_tables else "none",
                ),
            )
            conn.commit()


def get_gdpr_request_by_code(confirmation_code: str) -> Optional[dict]:
    """Look up a GDPR request by its confirmation code."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, request_type, status, created_at, completed_at FROM gdpr_requests WHERE confirmation_code = %s LIMIT 1",
                (confirmation_code,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


# ── Soft Delete ─────────────────────────────────────────────

def soft_delete_user(user_id: str, delay_days: int = 7) -> dict:
    """Mark user as pending_deletion instead of immediate delete."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """UPDATE fazle_users
                   SET is_active = false,
                       status = 'pending_deletion',
                       deletion_scheduled_at = NOW() + INTERVAL '%s days'
                   WHERE id = %s
                   RETURNING id, email, status, deletion_scheduled_at""",
                (delay_days, user_id),
            )
            conn.commit()
            row = cur.fetchone()
            return dict(row) if row else {}


def get_users_pending_deletion() -> list[dict]:
    """Get all users scheduled for permanent deletion whose delay has passed."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT id, email, status, deletion_scheduled_at
                   FROM fazle_users
                   WHERE status = 'pending_deletion'
                     AND deletion_scheduled_at <= NOW()"""
            )
            return [dict(r) for r in cur.fetchall()]


def cancel_deletion(user_id: str) -> bool:
    """Cancel pending deletion and reactivate user."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE fazle_users
                   SET is_active = true, status = 'active', deletion_scheduled_at = NULL
                   WHERE id = %s AND status = 'pending_deletion'""",
                (user_id,),
            )
            conn.commit()
            return cur.rowcount > 0


def ensure_soft_delete_columns():
    """Add soft-delete columns to fazle_users if missing."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            for col, typ in [
                ("status", "VARCHAR(30) DEFAULT 'active'"),
                ("deletion_scheduled_at", "TIMESTAMPTZ"),
            ]:
                try:
                    cur.execute(
                        f"ALTER TABLE fazle_users ADD COLUMN IF NOT EXISTS {col} {typ}"
                    )
                except Exception:
                    conn.rollback()
        conn.commit()


# ── User Identity Mapping ──────────────────────────────────

def upsert_user_identity(
    user_id: str,
    email: str = None,
    facebook_id: str = None,
    whatsapp_id: str = None,
    phone_number: str = None,
) -> dict:
    """Create or update user identity mapping."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """INSERT INTO user_identities (user_id, email, facebook_id, whatsapp_id, phone_number)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (user_id) DO UPDATE SET
                       email = COALESCE(EXCLUDED.email, user_identities.email),
                       facebook_id = COALESCE(EXCLUDED.facebook_id, user_identities.facebook_id),
                       whatsapp_id = COALESCE(EXCLUDED.whatsapp_id, user_identities.whatsapp_id),
                       phone_number = COALESCE(EXCLUDED.phone_number, user_identities.phone_number),
                       updated_at = NOW()
                   RETURNING id, user_id, email, facebook_id, whatsapp_id, phone_number, updated_at""",
                (user_id, email, facebook_id, whatsapp_id, phone_number),
            )
            conn.commit()
            return dict(cur.fetchone())


def get_user_identity(user_id: str) -> Optional[dict]:
    """Get identity mapping for a user."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM user_identities WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def find_user_by_identity(
    facebook_id: str = None, whatsapp_id: str = None, phone: str = None
) -> Optional[dict]:
    """Find a user by any identity field."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            conditions = []
            params = []
            if facebook_id:
                conditions.append("facebook_id = %s")
                params.append(facebook_id)
            if whatsapp_id:
                conditions.append("whatsapp_id = %s")
                params.append(whatsapp_id)
            if phone:
                conditions.append("phone_number = %s")
                params.append(phone)
            if not conditions:
                return None
            cur.execute(
                f"SELECT * FROM user_identities WHERE {' OR '.join(conditions)} LIMIT 1",
                params,
            )
            row = cur.fetchone()
            return dict(row) if row else None


# ── Admin GDPR Queries ─────────────────────────────────────

def get_all_gdpr_requests_admin(
    limit: int = 50, offset: int = 0, status_filter: str = None
) -> dict:
    """Get all GDPR requests for admin monitoring."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            where = ""
            params: list = []
            if status_filter and status_filter != "all":
                where = "WHERE status = %s"
                params.append(status_filter)

            cur.execute(
                f"SELECT COUNT(*) as total FROM gdpr_requests {where}", params
            )
            total = cur.fetchone()["total"]

            cur.execute(
                f"""SELECT id, user_id, request_type, status, confirmation_code,
                           fb_user_id, deleted_tables, error_message, retry_count,
                           created_at, completed_at, scheduled_at
                    FROM gdpr_requests {where}
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s""",
                params + [limit, offset],
            )
            rows = [dict(r) for r in cur.fetchall()]
            return {"requests": rows, "total": total}


def get_gdpr_stats() -> dict:
    """Get aggregated GDPR statistics for admin dashboard."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    COUNT(*) AS total_requests,
                    COUNT(*) FILTER (WHERE status = 'completed') AS completed,
                    COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                    COUNT(*) FILTER (WHERE status = 'pending' OR status = 'processing') AS pending,
                    COUNT(*) FILTER (WHERE request_type = 'delete') AS total_deletions,
                    COUNT(*) FILTER (WHERE request_type = 'export') AS total_exports,
                    COUNT(*) FILTER (WHERE request_type = 'facebook_deletion') AS total_fb_deletions,
                    AVG(EXTRACT(EPOCH FROM (completed_at - created_at)))
                        FILTER (WHERE completed_at IS NOT NULL) AS avg_completion_secs
                FROM gdpr_requests
            """)
            return dict(cur.fetchone())


def update_gdpr_request_error(request_id: str, error: str) -> None:
    """Store error details on a failed GDPR request."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE gdpr_requests
                   SET status = 'failed', error_message = %s,
                       retry_count = retry_count + 1, completed_at = NOW()
                   WHERE id = %s""",
                (error[:2000], request_id),
            )
            conn.commit()


def get_failed_gdpr_requests(max_retries: int = 3) -> list[dict]:
    """Get failed requests eligible for retry."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT id, user_id, request_type, retry_count, error_message, created_at
                   FROM gdpr_requests
                   WHERE status = 'failed' AND retry_count < %s
                   ORDER BY created_at ASC""",
                (max_retries,),
            )
            return [dict(r) for r in cur.fetchall()]


def reset_gdpr_request_for_retry(request_id: str) -> None:
    """Reset a failed request to pending for retry."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE gdpr_requests SET status = 'processing', completed_at = NULL WHERE id = %s",
                (request_id,),
            )
            conn.commit()
