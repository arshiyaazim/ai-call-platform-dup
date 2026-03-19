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
