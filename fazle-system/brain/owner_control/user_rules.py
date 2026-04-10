# ============================================================
# Phase 2B: Per-User Instruction Rules Engine
# Loads contact-specific rules and builds prompt blocks
# ============================================================
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import psycopg2
import psycopg2.extras
import redis

logger = logging.getLogger("fazle-brain.user-rules")

psycopg2.extras.register_uuid()

_DSN = os.getenv(
    "FAZLE_DATABASE_URL",
    "postgresql://postgres:postgres@postgres:5432/postgres",
)

_REDIS_URL = os.getenv("REDIS_URL", "redis://:redissecret@redis:6379/1")
_RULE_CACHE_PREFIX = "fazle:user_rule:"
_RULE_CACHE_TTL = 300  # 5 minutes


@dataclass
class UserRule:
    id: str
    contact_identifier: str
    platform: str
    rule_type: str
    rule_value: str
    priority: int
    is_active: bool
    expires_at: Optional[str]


# Valid rule types and their prompt behavior
RULE_TYPES = {
    "tone": "Adjust conversation tone for this contact",
    "block": "Block all responses to this contact",
    "auto_reply": "Send a fixed auto-reply instead of AI response",
    "greeting": "Use a specific greeting for this contact",
    "escalate": "Flag messages from this contact for owner review",
    "restrict_topic": "Do not discuss certain topics with this contact",
}


class UserRulesEngine:
    """Load and apply per-contact rules from DB with Redis caching."""

    def __init__(self, dsn: str = None, redis_url: str = None):
        self._dsn = dsn or _DSN
        self._redis_url = redis_url or _REDIS_URL
        self._redis: Optional[redis.Redis] = None

    def _conn(self):
        return psycopg2.connect(self._dsn)

    def _get_redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.Redis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    def _cache_key(self, contact_id: str, platform: str) -> str:
        return f"{_RULE_CACHE_PREFIX}{platform}:{contact_id}"

    # ── Load rules ───────────────────────────────────────────

    def get_rules(self, contact_id: str, platform: str = "whatsapp") -> list[UserRule]:
        """Get active rules for a contact. Uses Redis cache."""
        # Check cache first
        try:
            r = self._get_redis()
            cached = r.get(self._cache_key(contact_id, platform))
            if cached:
                data = json.loads(cached)
                return [UserRule(**d) for d in data]
        except Exception:
            pass

        # Query DB
        sql = """
            SELECT id, contact_identifier, platform, rule_type, rule_value,
                   priority, is_active, expires_at::text
            FROM fazle_user_rules
            WHERE contact_identifier = %s AND platform = %s AND is_active = true
              AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY priority DESC
        """
        try:
            with self._conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, (contact_id, platform))
                    rows = cur.fetchall()
                    rules = [UserRule(id=str(r["id"]), **{k: v for k, v in r.items() if k != "id"})
                             for r in rows]

            # Cache result
            try:
                cache_data = json.dumps([{
                    "id": rule.id,
                    "contact_identifier": rule.contact_identifier,
                    "platform": rule.platform,
                    "rule_type": rule.rule_type,
                    "rule_value": rule.rule_value,
                    "priority": rule.priority,
                    "is_active": rule.is_active,
                    "expires_at": rule.expires_at,
                } for rule in rules])
                self._get_redis().setex(
                    self._cache_key(contact_id, platform),
                    _RULE_CACHE_TTL,
                    cache_data,
                )
            except Exception:
                pass

            return rules
        except Exception:
            logger.exception("Failed to load user rules for %s", contact_id)
            return []

    def get_rule_by_type(
        self, contact_id: str, rule_type: str, platform: str = "whatsapp"
    ) -> Optional[UserRule]:
        """Get a specific rule type for a contact."""
        rules = self.get_rules(contact_id, platform)
        for rule in rules:
            if rule.rule_type == rule_type:
                return rule
        return None

    # ── Apply rules ──────────────────────────────────────────

    def should_block(self, contact_id: str, platform: str = "whatsapp") -> bool:
        """Check if this contact is blocked."""
        rule = self.get_rule_by_type(contact_id, "block", platform)
        return rule is not None

    def get_auto_reply(self, contact_id: str, platform: str = "whatsapp") -> Optional[str]:
        """Get fixed auto-reply if one is set."""
        rule = self.get_rule_by_type(contact_id, "auto_reply", platform)
        return rule.rule_value if rule else None

    def should_escalate(self, contact_id: str, platform: str = "whatsapp") -> bool:
        """Check if messages should be flagged for owner."""
        rule = self.get_rule_by_type(contact_id, "escalate", platform)
        return rule is not None

    def build_rules_prompt(self, contact_id: str, platform: str = "whatsapp") -> str:
        """Build a prompt block with contact-specific instructions.

        Returns empty string if no rules are active.
        Only includes prompt-affecting rules (tone, greeting, restrict_topic).
        """
        rules = self.get_rules(contact_id, platform)
        if not rules:
            return ""

        prompt_rules = [r for r in rules if r.rule_type in ("tone", "greeting", "restrict_topic")]
        if not prompt_rules:
            return ""

        lines = [
            "━━━ CONTACT-SPECIFIC RULES (MANDATORY) ━━━",
            f"Rules for contact: {contact_id}",
        ]
        for r in prompt_rules:
            if r.rule_type == "tone":
                lines.append(f"  TONE: {r.rule_value}")
            elif r.rule_type == "greeting":
                lines.append(f"  GREETING: Always greet with: {r.rule_value}")
            elif r.rule_type == "restrict_topic":
                lines.append(f"  RESTRICTED: Do NOT discuss: {r.rule_value}")
        lines.append("━━━ END CONTACT RULES ━━━")
        return "\n".join(lines)

    # ── CRUD (for brain-side use) ────────────────────────────

    def set_rule(
        self,
        contact_id: str,
        rule_type: str,
        rule_value: str,
        platform: str = "whatsapp",
        priority: int = 1,
        expires_at: Optional[str] = None,
    ) -> Optional[UserRule]:
        """Create or update a rule for a contact."""
        if rule_type not in RULE_TYPES:
            return None

        try:
            with self._conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    # Check existing
                    cur.execute("""
                        SELECT id, rule_value FROM fazle_user_rules
                        WHERE contact_identifier = %s AND platform = %s AND rule_type = %s
                    """, (contact_id, platform, rule_type))
                    existing = cur.fetchone()

                    if existing:
                        old_value = existing["rule_value"]
                        cur.execute("""
                            UPDATE fazle_user_rules
                            SET rule_value = %s, priority = %s, is_active = true,
                                updated_at = NOW(), expires_at = %s
                            WHERE id = %s
                            RETURNING id, contact_identifier, platform, rule_type,
                                      rule_value, priority, is_active, expires_at::text
                        """, (rule_value, priority, expires_at, existing["id"]))
                        # Audit
                        cur.execute("""
                            INSERT INTO fazle_user_rules_audit
                                (rule_id, contact_identifier, action, old_value, new_value)
                            VALUES (%s, %s, 'updated', %s, %s)
                        """, (existing["id"], contact_id, old_value, rule_value))
                    else:
                        cur.execute("""
                            INSERT INTO fazle_user_rules
                                (contact_identifier, platform, rule_type, rule_value, priority, expires_at)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            RETURNING id, contact_identifier, platform, rule_type,
                                      rule_value, priority, is_active, expires_at::text
                        """, (contact_id, platform, rule_type, rule_value, priority, expires_at))
                        row = cur.fetchone()
                        # Audit
                        cur.execute("""
                            INSERT INTO fazle_user_rules_audit
                                (rule_id, contact_identifier, action, new_value)
                            VALUES (%s, %s, 'created', %s)
                        """, (row["id"], contact_id, rule_value))

                    row = cur.fetchone() if existing else row
                    conn.commit()

            # Invalidate cache
            try:
                self._get_redis().delete(self._cache_key(contact_id, platform))
            except Exception:
                pass

            return UserRule(id=str(row["id"]), **{k: v for k, v in row.items() if k != "id"})
        except Exception:
            logger.exception("Failed to set rule for %s", contact_id)
            return None

    def deactivate_rule(
        self, contact_id: str, rule_type: str, platform: str = "whatsapp"
    ) -> bool:
        """Deactivate a rule for a contact."""
        try:
            with self._conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE fazle_user_rules SET is_active = false, updated_at = NOW()
                        WHERE contact_identifier = %s AND platform = %s AND rule_type = %s AND is_active = true
                        RETURNING id, rule_value
                    """, (contact_id, platform, rule_type))
                    row = cur.fetchone()
                    if row:
                        cur.execute("""
                            INSERT INTO fazle_user_rules_audit
                                (rule_id, contact_identifier, action, old_value)
                            VALUES (%s, %s, 'deactivated', %s)
                        """, (row[0], contact_id, row[1]))
                    conn.commit()

            # Invalidate cache
            try:
                self._get_redis().delete(self._cache_key(contact_id, platform))
            except Exception:
                pass

            return row is not None
        except Exception:
            logger.exception("Failed to deactivate rule for %s", contact_id)
            return False
