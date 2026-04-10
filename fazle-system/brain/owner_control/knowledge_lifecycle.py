# ============================================================
# Knowledge Lifecycle Management
# Create, replace, deprecate, merge, archive semantics
# ============================================================
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

import psycopg2
import psycopg2.extras

logger = logging.getLogger("fazle-brain.knowledge-lifecycle")

psycopg2.extras.register_uuid()

_DSN = os.getenv(
    "FAZLE_DATABASE_URL",
    "postgresql://postgres:postgres@postgres:5432/postgres",
)


class KnowledgeStatus(str, Enum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"
    MERGED = "merged"
    PENDING_REVIEW = "pending_review"


class KnowledgePersistence(str, Enum):
    PERMANENT = "permanent"
    TEMPORARY = "temporary"
    SESSION = "session"


@dataclass
class KnowledgeItem:
    id: str
    category: str  # business, personal, pricing, employee_rules, client_info, etc.
    key: str
    value: str
    source: str  # owner_chat, web_upload, file_upload, whatsapp_teach, audio_transcript, web_scrape
    status: KnowledgeStatus
    persistence: KnowledgePersistence
    version: int
    confidence: float  # 0-1, owner-taught = 1.0
    language: str  # bn, en, mixed
    created_by: str
    supersedes_id: Optional[str]
    created_at: str
    updated_at: str
    expires_at: Optional[str]
    metadata: dict


class KnowledgeLifecycleEngine:
    """Manages knowledge with full CRUD + replace/deprecate/merge/archive lifecycle."""

    def __init__(self, dsn: str = None):
        self._dsn = dsn or _DSN

    def _conn(self):
        return psycopg2.connect(self._dsn)

    def ensure_tables(self):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS fazle_knowledge_items (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        category VARCHAR(50) NOT NULL,
                        key VARCHAR(500) NOT NULL,
                        value TEXT NOT NULL,
                        source VARCHAR(50) NOT NULL DEFAULT 'owner_chat',
                        status VARCHAR(20) NOT NULL DEFAULT 'active',
                        persistence VARCHAR(20) NOT NULL DEFAULT 'permanent',
                        version INT NOT NULL DEFAULT 1,
                        confidence FLOAT NOT NULL DEFAULT 1.0,
                        language VARCHAR(10) NOT NULL DEFAULT 'bn',
                        created_by VARCHAR(50) NOT NULL DEFAULT 'owner',
                        supersedes_id UUID REFERENCES fazle_knowledge_items(id),
                        expires_at TIMESTAMPTZ,
                        metadata JSONB DEFAULT '{}',
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    );

                    CREATE INDEX IF NOT EXISTS idx_knowledge_category_key
                        ON fazle_knowledge_items(category, key);
                    CREATE INDEX IF NOT EXISTS idx_knowledge_status
                        ON fazle_knowledge_items(status);
                    CREATE INDEX IF NOT EXISTS idx_knowledge_source
                        ON fazle_knowledge_items(source);

                    CREATE TABLE IF NOT EXISTS fazle_knowledge_audit (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        knowledge_id UUID REFERENCES fazle_knowledge_items(id),
                        action VARCHAR(30) NOT NULL,
                        old_value TEXT DEFAULT '',
                        new_value TEXT DEFAULT '',
                        changed_by VARCHAR(50) DEFAULT 'owner',
                        reason TEXT DEFAULT '',
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );

                    CREATE INDEX IF NOT EXISTS idx_knowledge_audit_item
                        ON fazle_knowledge_audit(knowledge_id);
                """)
            conn.commit()
        logger.info("Knowledge lifecycle tables ensured")

    # ── CREATE ───────────────────────────────────────────────

    def create(
        self, category: str, key: str, value: str,
        source: str = "owner_chat", persistence: str = "permanent",
        confidence: float = 1.0, language: str = "bn",
        created_by: str = "owner", expires_at: str = None,
        metadata: dict = None,
    ) -> Optional[KnowledgeItem]:
        """Create new knowledge. Checks for duplicates first."""
        try:
            with self._conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    # Check for existing active knowledge with same category+key
                    cur.execute("""
                        SELECT id, value, version FROM fazle_knowledge_items
                        WHERE category = %s AND key = %s AND status = 'active'
                        ORDER BY version DESC LIMIT 1
                    """, (category, key))
                    existing = cur.fetchone()

                    if existing:
                        # Auto-replace if same key exists
                        return self._replace_internal(
                            cur, conn, existing, category, key, value,
                            source, persistence, confidence, language,
                            created_by, expires_at, metadata,
                            reason="auto-replaced on create with existing key",
                        )

                    # Create fresh
                    cur.execute("""
                        INSERT INTO fazle_knowledge_items
                            (category, key, value, source, status, persistence,
                             version, confidence, language, created_by, expires_at, metadata)
                        VALUES (%s, %s, %s, %s, 'active', %s, 1, %s, %s, %s, %s, %s)
                        RETURNING *
                    """, (category, key, value, source, persistence, confidence,
                          language, created_by, expires_at,
                          psycopg2.extras.Json(metadata or {})))
                    row = cur.fetchone()

                    cur.execute("""
                        INSERT INTO fazle_knowledge_audit
                            (knowledge_id, action, new_value, changed_by, reason)
                        VALUES (%s, 'created', %s, %s, 'new knowledge item')
                    """, (row["id"], value[:500], created_by))

                    conn.commit()
                    return self._row_to_item(row)
        except Exception:
            logger.exception("Failed to create knowledge %s/%s", category, key)
            return None

    # ── REPLACE ──────────────────────────────────────────────

    def replace(
        self, category: str, key: str, new_value: str,
        reason: str = "", replaced_by: str = "owner",
        source: str = "owner_chat", confidence: float = 1.0,
    ) -> Optional[KnowledgeItem]:
        """Replace existing knowledge with new value. Old version gets deprecated."""
        try:
            with self._conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("""
                        SELECT id, value, version FROM fazle_knowledge_items
                        WHERE category = %s AND key = %s AND status = 'active'
                        ORDER BY version DESC LIMIT 1
                    """, (category, key))
                    existing = cur.fetchone()

                    if not existing:
                        # No existing, create new
                        return self.create(
                            category, key, new_value, source=source,
                            confidence=confidence, created_by=replaced_by,
                        )

                    return self._replace_internal(
                        cur, conn, existing, category, key, new_value,
                        source, "permanent", confidence, "bn",
                        replaced_by, None, None, reason,
                    )
        except Exception:
            logger.exception("Failed to replace knowledge %s/%s", category, key)
            return None

    def _replace_internal(
        self, cur, conn, existing, category, key, new_value,
        source, persistence, confidence, language,
        created_by, expires_at, metadata, reason,
    ) -> Optional[KnowledgeItem]:
        old_version = existing["version"]
        old_value = existing["value"]

        # Deprecate old
        cur.execute("""
            UPDATE fazle_knowledge_items
            SET status = 'deprecated', updated_at = NOW()
            WHERE id = %s
        """, (existing["id"],))

        # Insert new version
        cur.execute("""
            INSERT INTO fazle_knowledge_items
                (category, key, value, source, status, persistence,
                 version, confidence, language, created_by, supersedes_id,
                 expires_at, metadata)
            VALUES (%s, %s, %s, %s, 'active', %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """, (category, key, new_value, source, persistence,
              old_version + 1, confidence, language, created_by,
              existing["id"], expires_at,
              psycopg2.extras.Json(metadata or {})))
        row = cur.fetchone()

        # Audit
        cur.execute("""
            INSERT INTO fazle_knowledge_audit
                (knowledge_id, action, old_value, new_value, changed_by, reason)
            VALUES (%s, 'replaced', %s, %s, %s, %s)
        """, (row["id"], old_value[:500], new_value[:500], created_by,
              reason or "replaced with newer info"))

        conn.commit()
        return self._row_to_item(row)

    # ── DEPRECATE ────────────────────────────────────────────

    def deprecate(
        self, category: str, key: str,
        reason: str = "", deprecated_by: str = "owner",
    ) -> bool:
        """Deprecate knowledge — it's still queryable but won't be used in prompts."""
        try:
            with self._conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE fazle_knowledge_items
                        SET status = 'deprecated', updated_at = NOW()
                        WHERE category = %s AND key = %s AND status = 'active'
                        RETURNING id, value
                    """, (category, key))
                    row = cur.fetchone()
                    if row:
                        cur.execute("""
                            INSERT INTO fazle_knowledge_audit
                                (knowledge_id, action, old_value, changed_by, reason)
                            VALUES (%s, 'deprecated', %s, %s, %s)
                        """, (row[0], str(row[1])[:500], deprecated_by, reason))
                    conn.commit()
                    return row is not None
        except Exception:
            logger.exception("Failed to deprecate %s/%s", category, key)
            return False

    # ── MERGE ────────────────────────────────────────────────

    def merge(
        self, category: str, source_keys: list[str],
        merged_key: str, merged_value: str,
        reason: str = "", merged_by: str = "owner",
    ) -> Optional[KnowledgeItem]:
        """Merge multiple knowledge items into one new item."""
        try:
            with self._conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    # Mark source items as merged
                    source_ids = []
                    for sk in source_keys:
                        cur.execute("""
                            UPDATE fazle_knowledge_items
                            SET status = 'merged', updated_at = NOW()
                            WHERE category = %s AND key = %s AND status = 'active'
                            RETURNING id, value
                        """, (category, sk))
                        row = cur.fetchone()
                        if row:
                            source_ids.append(str(row["id"]))

                    # Create merged item
                    cur.execute("""
                        INSERT INTO fazle_knowledge_items
                            (category, key, value, source, status, persistence,
                             version, confidence, language, created_by, metadata)
                        VALUES (%s, %s, %s, 'merge', 'active', 'permanent',
                                1, 1.0, 'bn', %s, %s)
                        RETURNING *
                    """, (category, merged_key, merged_value, merged_by,
                          psycopg2.extras.Json({"merged_from": source_ids})))
                    row = cur.fetchone()

                    cur.execute("""
                        INSERT INTO fazle_knowledge_audit
                            (knowledge_id, action, old_value, new_value, changed_by, reason)
                        VALUES (%s, 'merged', %s, %s, %s, %s)
                    """, (row["id"], json.dumps(source_keys), merged_value[:500],
                          merged_by, reason or f"merged from {len(source_keys)} items"))

                    conn.commit()
                    return self._row_to_item(row)
        except Exception:
            logger.exception("Failed to merge knowledge in %s", category)
            return None

    # ── ARCHIVE ──────────────────────────────────────────────

    def archive(
        self, category: str, key: str,
        reason: str = "", archived_by: str = "owner",
    ) -> bool:
        """Archive knowledge — removes it from active use but keeps for history."""
        try:
            with self._conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE fazle_knowledge_items
                        SET status = 'archived', updated_at = NOW()
                        WHERE category = %s AND key = %s AND status IN ('active', 'deprecated')
                        RETURNING id, value
                    """, (category, key))
                    row = cur.fetchone()
                    if row:
                        cur.execute("""
                            INSERT INTO fazle_knowledge_audit
                                (knowledge_id, action, old_value, changed_by, reason)
                            VALUES (%s, 'archived', %s, %s, %s)
                        """, (row[0], str(row[1])[:500], archived_by, reason))
                    conn.commit()
                    return row is not None
        except Exception:
            logger.exception("Failed to archive %s/%s", category, key)
            return False

    # ── QUERY ────────────────────────────────────────────────

    def get_active(
        self, category: str = None, limit: int = 100,
    ) -> list[KnowledgeItem]:
        try:
            with self._conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    sql = """
                        SELECT * FROM fazle_knowledge_items
                        WHERE status = 'active'
                    """
                    params = []
                    if category:
                        sql += " AND category = %s"
                        params.append(category)
                    sql += " ORDER BY confidence DESC, version DESC LIMIT %s"
                    params.append(limit)
                    cur.execute(sql, params)
                    return [self._row_to_item(r) for r in cur.fetchall()]
        except Exception:
            logger.exception("Failed to get active knowledge")
            return []

    def get_by_key(self, category: str, key: str) -> Optional[KnowledgeItem]:
        try:
            with self._conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM fazle_knowledge_items
                        WHERE category = %s AND key = %s AND status = 'active'
                        ORDER BY version DESC LIMIT 1
                    """, (category, key))
                    row = cur.fetchone()
                    return self._row_to_item(row) if row else None
        except Exception:
            logger.exception("Failed to get knowledge %s/%s", category, key)
            return None

    def search(self, query: str, category: str = None, limit: int = 20) -> list[KnowledgeItem]:
        """Full-text search across active knowledge items."""
        try:
            with self._conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    sql = """
                        SELECT * FROM fazle_knowledge_items
                        WHERE status = 'active'
                          AND (key ILIKE %s OR value ILIKE %s)
                    """
                    pattern = f"%{query}%"
                    params = [pattern, pattern]
                    if category:
                        sql += " AND category = %s"
                        params.append(category)
                    sql += " ORDER BY confidence DESC, version DESC LIMIT %s"
                    params.append(limit)
                    cur.execute(sql, params)
                    return [self._row_to_item(r) for r in cur.fetchall()]
        except Exception:
            logger.exception("Failed to search knowledge")
            return []

    def get_history(self, category: str, key: str) -> list[KnowledgeItem]:
        """Get full version history of a knowledge item."""
        try:
            with self._conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM fazle_knowledge_items
                        WHERE category = %s AND key = %s
                        ORDER BY version DESC
                    """, (category, key))
                    return [self._row_to_item(r) for r in cur.fetchall()]
        except Exception:
            logger.exception("Failed to get knowledge history")
            return []

    def build_knowledge_prompt(self, categories: list[str] = None, limit: int = 30) -> str:
        """Build a prompt block from active knowledge for LLM injection."""
        items = []
        if categories:
            for cat in categories:
                items.extend(self.get_active(category=cat, limit=limit // len(categories)))
        else:
            items = self.get_active(limit=limit)

        if not items:
            return ""

        lines = ["━━━ KNOWLEDGE BASE (MANDATORY) ━━━"]
        by_cat: dict[str, list[KnowledgeItem]] = {}
        for item in items:
            by_cat.setdefault(item.category, []).append(item)

        for cat, cat_items in sorted(by_cat.items()):
            lines.append(f"\n[{cat.upper()}]")
            for item in cat_items:
                confidence_marker = "★" if item.confidence >= 0.9 else "○"
                lines.append(f"  {confidence_marker} {item.key}: {item.value}")

        lines.append("\n━━━ END KNOWLEDGE BASE ━━━")
        return "\n".join(lines)

    def _row_to_item(self, row: dict) -> KnowledgeItem:
        return KnowledgeItem(
            id=str(row["id"]),
            category=row["category"],
            key=row["key"],
            value=row["value"],
            source=row["source"],
            status=KnowledgeStatus(row["status"]),
            persistence=KnowledgePersistence(row["persistence"]),
            version=row["version"],
            confidence=row["confidence"],
            language=row["language"],
            created_by=row["created_by"],
            supersedes_id=str(row["supersedes_id"]) if row.get("supersedes_id") else None,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            expires_at=str(row["expires_at"]) if row.get("expires_at") else None,
            metadata=row.get("metadata") or {},
        )
