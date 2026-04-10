# ============================================================
# Phase 1B: Knowledge Governance — Brain-side Engine
# Validates AI responses against canonical facts & phrasing
# ============================================================
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import psycopg2
import psycopg2.extras

logger = logging.getLogger("fazle-brain.governance")

psycopg2.extras.register_uuid()


@dataclass
class CanonicalFact:
    id: str
    category: str
    fact_key: str
    fact_value: str
    language: str
    version: int
    status: str


@dataclass
class PhrasingRule:
    topic: str
    preferred: str
    prohibited: Optional[str]
    language: str


class KnowledgeGovernance:
    """Loads canonical facts and phrasing rules for prompt injection."""

    def __init__(self, dsn: str):
        self._dsn = dsn

    def _conn(self):
        return psycopg2.connect(self._dsn)

    # ── Canonical facts ──────────────────────────────────────

    def get_active_facts(self, category: Optional[str] = None) -> list[CanonicalFact]:
        sql = """
            SELECT id, category, fact_key, fact_value, language, version, status
            FROM fazle_knowledge_governance
            WHERE status = 'active'
        """
        params: list = []
        if category:
            sql += " AND category = %s"
            params.append(category)
        sql += " ORDER BY category, fact_key"

        try:
            with self._conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, params)
                    return [CanonicalFact(**row) for row in cur.fetchall()]
        except Exception:
            logger.exception("Failed to load governance facts")
            return []

    def get_fact(self, category: str, key: str) -> Optional[CanonicalFact]:
        sql = """
            SELECT id, category, fact_key, fact_value, language, version, status
            FROM fazle_knowledge_governance
            WHERE category = %s AND fact_key = %s AND status = 'active'
            ORDER BY version DESC LIMIT 1
        """
        try:
            with self._conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, (category, key))
                    row = cur.fetchone()
                    return CanonicalFact(**row) if row else None
        except Exception:
            logger.exception("Failed to load fact %s/%s", category, key)
            return None

    def update_fact(
        self,
        category: str,
        key: str,
        new_value: str,
        reason: str = "",
        updated_by: str = "owner",
    ) -> Optional[CanonicalFact]:
        """Create a new version of a fact and deprecate the old one."""
        try:
            with self._conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    # Get current version
                    cur.execute("""
                        SELECT id, fact_value, version FROM fazle_knowledge_governance
                        WHERE category = %s AND fact_key = %s AND status = 'active'
                        ORDER BY version DESC LIMIT 1
                    """, (category, key))
                    old = cur.fetchone()
                    old_version = old["version"] if old else 0
                    old_value = old["fact_value"] if old else ""

                    # Deprecate old
                    if old:
                        cur.execute("""
                            UPDATE fazle_knowledge_governance
                            SET status = 'deprecated',
                                deprecated_at = now(),
                                deprecation_reason = %s
                            WHERE id = %s
                        """, (reason or "superseded", old["id"]))

                    # Insert new version
                    cur.execute("""
                        INSERT INTO fazle_knowledge_governance
                            (category, fact_key, fact_value, version, created_by)
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING id, category, fact_key, fact_value, language, version, status
                    """, (category, key, new_value, old_version + 1, updated_by))
                    new_row = cur.fetchone()

                    # Record correction
                    if old_value:
                        cur.execute("""
                            INSERT INTO fazle_knowledge_corrections
                                (governance_id, old_value, new_value, reason, corrected_by)
                            VALUES (%s, %s, %s, %s, %s)
                        """, (new_row["id"], old_value, new_value, reason, updated_by))

                    conn.commit()
                    return CanonicalFact(**new_row)
        except Exception:
            logger.exception("Failed to update fact %s/%s", category, key)
            return None

    # ── Phrasing rules ───────────────────────────────────────

    def get_phrasing_rules(self) -> list[PhrasingRule]:
        sql = """
            SELECT topic, preferred_phrasing, prohibited_phrasing, language
            FROM fazle_knowledge_phrasing WHERE status = 'active'
            ORDER BY topic
        """
        try:
            with self._conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql)
                    return [
                        PhrasingRule(
                            topic=r["topic"],
                            preferred=r["preferred_phrasing"],
                            prohibited=r["prohibited_phrasing"],
                            language=r["language"],
                        )
                        for r in cur.fetchall()
                    ]
        except Exception:
            logger.exception("Failed to load phrasing rules")
            return []

    # ── Prompt block builder ─────────────────────────────────

    def build_governance_prompt(self) -> str:
        """Build a prompt section the LLM must follow.

        Returns a block that can be prepended to the system prompt
        so the LLM uses canonical values and avoids prohibited phrasing.
        """
        facts = self.get_active_facts()
        rules = self.get_phrasing_rules()

        if not facts and not rules:
            return ""

        lines = [
            "━━━ KNOWLEDGE GOVERNANCE (MANDATORY) ━━━",
            "You MUST use these canonical facts. Never contradict them.",
            "",
        ]

        # Group facts by category
        by_cat: dict[str, list[CanonicalFact]] = {}
        for f in facts:
            by_cat.setdefault(f.category, []).append(f)

        for cat, cat_facts in sorted(by_cat.items()):
            lines.append(f"[{cat.upper()}]")
            for f in cat_facts:
                lines.append(f"  {f.fact_key}: {f.fact_value}")
            lines.append("")

        if rules:
            lines.append("[PHRASING RULES]")
            for r in rules:
                line = f"  ✅ {r.topic}: Say \"{r.preferred}\""
                if r.prohibited:
                    line += f"  ❌ Never say: {r.prohibited}"
                lines.append(line)
            lines.append("")

        lines.append("━━━ END GOVERNANCE ━━━")
        return "\n".join(lines)

    # ── Correction history ───────────────────────────────────

    def get_corrections(
        self, category: Optional[str] = None, limit: int = 20
    ) -> list[dict]:
        sql = """
            SELECT c.id, c.old_value, c.new_value, c.reason,
                   c.corrected_by, c.corrected_at,
                   g.category, g.fact_key
            FROM fazle_knowledge_corrections c
            JOIN fazle_knowledge_governance g ON g.id = c.governance_id
        """
        params: list = []
        if category:
            sql += " WHERE g.category = %s"
            params.append(category)
        sql += " ORDER BY c.corrected_at DESC LIMIT %s"
        params.append(limit)

        try:
            with self._conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, params)
                    rows = cur.fetchall()
                    return [
                        {
                            "id": str(r["id"]),
                            "category": r["category"],
                            "fact_key": r["fact_key"],
                            "old_value": r["old_value"],
                            "new_value": r["new_value"],
                            "reason": r["reason"],
                            "corrected_by": r["corrected_by"],
                            "corrected_at": r["corrected_at"].isoformat()
                            if r["corrected_at"] else None,
                        }
                        for r in rows
                    ]
        except Exception:
            logger.exception("Failed to load corrections")
            return []
