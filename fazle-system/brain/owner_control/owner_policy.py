# ============================================================
# Owner Policy Model — Persisted, Auditable Owner Authority
# Replaces env-only owner detection with DB-backed policy
# ============================================================
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

import psycopg2
import psycopg2.extras
import redis

logger = logging.getLogger("fazle-brain.owner-policy")

psycopg2.extras.register_uuid()

_DSN = os.getenv(
    "FAZLE_DATABASE_URL",
    "postgresql://postgres:postgres@postgres:5432/postgres",
)
_REDIS_URL = os.getenv("REDIS_URL", "redis://:redissecret@redis:6379/1")


class PolicyStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


@dataclass
class OwnerPolicy:
    id: str
    owner_phone: str
    owner_name: str
    status: PolicyStatus
    default_language: str  # "bn", "en", "mixed"
    persona_type: str  # "business_personal_mixed"
    instruction_authority: str  # "single_owner"
    automation_mode: str  # "safe_customer_facing"
    created_at: str
    updated_at: str
    metadata: dict = field(default_factory=dict)


@dataclass
class ContactRole:
    id: str
    phone: str
    name: str
    role: str  # owner, family, client, job_seeker, employee, unknown
    sub_role: str  # wife, daughter, son, parent, sibling, vip, regular, etc.
    language_pref: str  # "bn", "en", "mixed", "" = use default
    platform: str
    is_active: bool
    metadata: dict = field(default_factory=dict)


# Accepted contact roles with their hierarchy
CONTACT_ROLES = {
    "owner": {"priority": 100, "trust": "full", "automation": False},
    "family": {"priority": 90, "trust": "high", "automation": False},
    "employee": {"priority": 70, "trust": "medium", "automation": True},
    "client": {"priority": 60, "trust": "medium", "automation": True},
    "job_seeker": {"priority": 40, "trust": "low", "automation": True},
    "friend": {"priority": 50, "trust": "medium", "automation": True},
    "unknown": {"priority": 10, "trust": "none", "automation": True},
}

FAMILY_SUB_ROLES = {"wife", "daughter", "son", "parent", "sibling"}


class OwnerPolicyEngine:
    """Persisted owner policy management with Redis caching."""

    _CACHE_PREFIX = "fazle:policy:"
    _CACHE_TTL = 600  # 10 min

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

    # ── Schema bootstrap ─────────────────────────────────────

    def ensure_tables(self):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS fazle_owner_policy (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        owner_phone VARCHAR(20) NOT NULL,
                        owner_name VARCHAR(200) NOT NULL DEFAULT 'Azim',
                        status VARCHAR(20) NOT NULL DEFAULT 'active',
                        default_language VARCHAR(10) NOT NULL DEFAULT 'bn',
                        persona_type VARCHAR(50) NOT NULL DEFAULT 'business_personal_mixed',
                        instruction_authority VARCHAR(30) NOT NULL DEFAULT 'single_owner',
                        automation_mode VARCHAR(30) NOT NULL DEFAULT 'safe_customer_facing',
                        metadata JSONB DEFAULT '{}',
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    );

                    CREATE TABLE IF NOT EXISTS fazle_contact_roles (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        phone VARCHAR(20) NOT NULL,
                        name VARCHAR(200) NOT NULL DEFAULT '',
                        role VARCHAR(30) NOT NULL DEFAULT 'unknown',
                        sub_role VARCHAR(30) NOT NULL DEFAULT '',
                        language_pref VARCHAR(10) NOT NULL DEFAULT '',
                        platform VARCHAR(20) NOT NULL DEFAULT 'whatsapp',
                        is_active BOOLEAN DEFAULT TRUE,
                        metadata JSONB DEFAULT '{}',
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE(phone, platform)
                    );

                    CREATE INDEX IF NOT EXISTS idx_contact_roles_phone
                        ON fazle_contact_roles(phone);
                    CREATE INDEX IF NOT EXISTS idx_contact_roles_role
                        ON fazle_contact_roles(role);

                    CREATE TABLE IF NOT EXISTS fazle_policy_audit (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        entity_type VARCHAR(30) NOT NULL,
                        entity_id UUID,
                        action VARCHAR(30) NOT NULL,
                        old_value TEXT DEFAULT '',
                        new_value TEXT DEFAULT '',
                        changed_by VARCHAR(50) DEFAULT 'owner',
                        reason TEXT DEFAULT '',
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );

                    CREATE INDEX IF NOT EXISTS idx_policy_audit_entity
                        ON fazle_policy_audit(entity_type, entity_id);
                """)
            conn.commit()
        logger.info("Owner policy tables ensured")

    # ── Owner Policy CRUD ────────────────────────────────────

    def get_active_policy(self) -> Optional[OwnerPolicy]:
        cache_key = f"{self._CACHE_PREFIX}active"
        try:
            r = self._get_redis()
            cached = r.get(cache_key)
            if cached:
                d = json.loads(cached)
                return OwnerPolicy(**d)
        except Exception:
            pass

        try:
            with self._conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("""
                        SELECT id, owner_phone, owner_name, status,
                               default_language, persona_type, instruction_authority,
                               automation_mode, metadata,
                               created_at::text, updated_at::text
                        FROM fazle_owner_policy
                        WHERE status = 'active'
                        ORDER BY created_at DESC LIMIT 1
                    """)
                    row = cur.fetchone()
                    if not row:
                        return None
                    policy = OwnerPolicy(
                        id=str(row["id"]),
                        owner_phone=row["owner_phone"],
                        owner_name=row["owner_name"],
                        status=PolicyStatus(row["status"]),
                        default_language=row["default_language"],
                        persona_type=row["persona_type"],
                        instruction_authority=row["instruction_authority"],
                        automation_mode=row["automation_mode"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                        metadata=row["metadata"] or {},
                    )
            try:
                self._get_redis().setex(
                    cache_key, self._CACHE_TTL,
                    json.dumps({
                        "id": policy.id, "owner_phone": policy.owner_phone,
                        "owner_name": policy.owner_name, "status": policy.status.value,
                        "default_language": policy.default_language,
                        "persona_type": policy.persona_type,
                        "instruction_authority": policy.instruction_authority,
                        "automation_mode": policy.automation_mode,
                        "created_at": policy.created_at, "updated_at": policy.updated_at,
                        "metadata": policy.metadata,
                    })
                )
            except Exception:
                pass
            return policy
        except Exception:
            logger.exception("Failed to load owner policy")
            return None

    def initialize_policy(self, owner_phone: str, owner_name: str = "Azim") -> Optional[OwnerPolicy]:
        """Create or update the active owner policy. Only one active policy at a time."""
        try:
            with self._conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    # Deactivate any existing active policy
                    cur.execute("""
                        UPDATE fazle_owner_policy SET status = 'revoked', updated_at = NOW()
                        WHERE status = 'active'
                        RETURNING id, owner_phone
                    """)
                    old = cur.fetchone()
                    if old:
                        cur.execute("""
                            INSERT INTO fazle_policy_audit
                                (entity_type, entity_id, action, old_value, new_value, reason)
                            VALUES ('owner_policy', %s, 'revoked', %s, %s, 'new policy initialized')
                        """, (old["id"], old["owner_phone"], owner_phone))

                    cur.execute("""
                        INSERT INTO fazle_owner_policy
                            (owner_phone, owner_name, status, default_language,
                             persona_type, instruction_authority, automation_mode)
                        VALUES (%s, %s, 'active', 'bn', 'business_personal_mixed',
                                'single_owner', 'safe_customer_facing')
                        RETURNING id, owner_phone, owner_name, status,
                                  default_language, persona_type, instruction_authority,
                                  automation_mode, metadata, created_at::text, updated_at::text
                    """, (owner_phone, owner_name))
                    row = cur.fetchone()

                    cur.execute("""
                        INSERT INTO fazle_policy_audit
                            (entity_type, entity_id, action, new_value, reason)
                        VALUES ('owner_policy', %s, 'created', %s, 'initial policy setup')
                    """, (row["id"], owner_phone))

                    # Also register owner as a contact role
                    cur.execute("""
                        INSERT INTO fazle_contact_roles (phone, name, role, sub_role, platform)
                        VALUES (%s, %s, 'owner', 'self', 'whatsapp')
                        ON CONFLICT (phone, platform) DO UPDATE
                            SET role = 'owner', sub_role = 'self', name = EXCLUDED.name,
                                is_active = TRUE, updated_at = NOW()
                    """, (owner_phone, owner_name))

                    conn.commit()

            # Invalidate cache
            try:
                self._get_redis().delete(f"{self._CACHE_PREFIX}active")
            except Exception:
                pass

            return OwnerPolicy(
                id=str(row["id"]),
                owner_phone=row["owner_phone"],
                owner_name=row["owner_name"],
                status=PolicyStatus(row["status"]),
                default_language=row["default_language"],
                persona_type=row["persona_type"],
                instruction_authority=row["instruction_authority"],
                automation_mode=row["automation_mode"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                metadata=row["metadata"] or {},
            )
        except Exception:
            logger.exception("Failed to initialize owner policy")
            return None

    def is_owner(self, phone: str) -> bool:
        """Check if a phone number matches the active owner policy."""
        policy = self.get_active_policy()
        if not policy:
            return False
        return _normalize_phone(phone) == _normalize_phone(policy.owner_phone)

    # ── Contact Role Management ──────────────────────────────

    def get_contact_role(self, phone: str, platform: str = "whatsapp") -> Optional[ContactRole]:
        norm = _normalize_phone(phone)
        cache_key = f"{self._CACHE_PREFIX}contact:{platform}:{norm}"
        try:
            r = self._get_redis()
            cached = r.get(cache_key)
            if cached:
                d = json.loads(cached)
                return ContactRole(**d)
        except Exception:
            pass

        try:
            with self._conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("""
                        SELECT id, phone, name, role, sub_role, language_pref,
                               platform, is_active, metadata
                        FROM fazle_contact_roles
                        WHERE phone = %s AND platform = %s AND is_active = TRUE
                    """, (norm, platform))
                    row = cur.fetchone()
                    if not row:
                        return None
                    cr = ContactRole(
                        id=str(row["id"]),
                        phone=row["phone"],
                        name=row["name"],
                        role=row["role"],
                        sub_role=row["sub_role"],
                        language_pref=row["language_pref"],
                        platform=row["platform"],
                        is_active=row["is_active"],
                        metadata=row["metadata"] or {},
                    )
            try:
                self._get_redis().setex(cache_key, self._CACHE_TTL, json.dumps({
                    "id": cr.id, "phone": cr.phone, "name": cr.name,
                    "role": cr.role, "sub_role": cr.sub_role,
                    "language_pref": cr.language_pref, "platform": cr.platform,
                    "is_active": cr.is_active, "metadata": cr.metadata,
                }))
            except Exception:
                pass
            return cr
        except Exception:
            logger.exception("Failed to get contact role for %s", phone)
            return None

    def set_contact_role(
        self, phone: str, role: str, name: str = "",
        sub_role: str = "", language_pref: str = "",
        platform: str = "whatsapp", metadata: dict = None,
        changed_by: str = "owner", reason: str = "",
    ) -> Optional[ContactRole]:
        if role not in CONTACT_ROLES:
            logger.warning("Invalid role %s for %s", role, phone)
            return None
        norm = _normalize_phone(phone)
        try:
            with self._conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    # Get old role for audit
                    cur.execute("""
                        SELECT id, role, sub_role FROM fazle_contact_roles
                        WHERE phone = %s AND platform = %s
                    """, (norm, platform))
                    old = cur.fetchone()
                    old_role = old["role"] if old else ""

                    cur.execute("""
                        INSERT INTO fazle_contact_roles
                            (phone, name, role, sub_role, language_pref, platform, metadata)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (phone, platform) DO UPDATE
                            SET role = EXCLUDED.role,
                                sub_role = CASE WHEN EXCLUDED.sub_role != '' THEN EXCLUDED.sub_role ELSE fazle_contact_roles.sub_role END,
                                name = CASE WHEN EXCLUDED.name != '' THEN EXCLUDED.name ELSE fazle_contact_roles.name END,
                                language_pref = CASE WHEN EXCLUDED.language_pref != '' THEN EXCLUDED.language_pref ELSE fazle_contact_roles.language_pref END,
                                metadata = COALESCE(EXCLUDED.metadata, fazle_contact_roles.metadata),
                                is_active = TRUE,
                                updated_at = NOW()
                        RETURNING id, phone, name, role, sub_role, language_pref, platform, is_active, metadata
                    """, (norm, name, role, sub_role, language_pref, platform,
                          psycopg2.extras.Json(metadata or {})))
                    row = cur.fetchone()

                    # Audit
                    if old_role != role:
                        cur.execute("""
                            INSERT INTO fazle_policy_audit
                                (entity_type, entity_id, action, old_value, new_value, changed_by, reason)
                            VALUES ('contact_role', %s, 'role_changed', %s, %s, %s, %s)
                        """, (row["id"], old_role, role, changed_by, reason))

                    conn.commit()

            # Invalidate cache
            try:
                self._get_redis().delete(f"{self._CACHE_PREFIX}contact:{platform}:{norm}")
            except Exception:
                pass

            return ContactRole(
                id=str(row["id"]),
                phone=row["phone"], name=row["name"],
                role=row["role"], sub_role=row["sub_role"],
                language_pref=row["language_pref"],
                platform=row["platform"], is_active=row["is_active"],
                metadata=row["metadata"] or {},
            )
        except Exception:
            logger.exception("Failed to set contact role for %s", phone)
            return None

    def set_contact_language(self, phone: str, language: str, platform: str = "whatsapp") -> bool:
        """Set per-contact language preference."""
        if language not in ("bn", "en", "mixed", ""):
            return False
        norm = _normalize_phone(phone)
        try:
            with self._conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE fazle_contact_roles SET language_pref = %s, updated_at = NOW()
                        WHERE phone = %s AND platform = %s
                    """, (language, norm, platform))
                    conn.commit()
            try:
                self._get_redis().delete(f"{self._CACHE_PREFIX}contact:{platform}:{norm}")
            except Exception:
                pass
            return True
        except Exception:
            logger.exception("Failed to set language for %s", phone)
            return False

    def get_effective_language(self, phone: str, platform: str = "whatsapp") -> str:
        """Get the effective language for a contact: per-contact override or policy default."""
        cr = self.get_contact_role(phone, platform)
        if cr and cr.language_pref:
            return cr.language_pref
        policy = self.get_active_policy()
        if policy:
            return policy.default_language
        return "bn"

    def list_contacts_by_role(self, role: str, platform: str = "whatsapp") -> list[ContactRole]:
        try:
            with self._conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("""
                        SELECT id, phone, name, role, sub_role, language_pref,
                               platform, is_active, metadata
                        FROM fazle_contact_roles
                        WHERE role = %s AND platform = %s AND is_active = TRUE
                        ORDER BY name
                    """, (role, platform))
                    return [
                        ContactRole(
                            id=str(r["id"]), phone=r["phone"], name=r["name"],
                            role=r["role"], sub_role=r["sub_role"],
                            language_pref=r["language_pref"],
                            platform=r["platform"], is_active=r["is_active"],
                            metadata=r["metadata"] or {},
                        )
                        for r in cur.fetchall()
                    ]
        except Exception:
            logger.exception("Failed to list contacts by role %s", role)
            return []

    def get_audit_log(self, entity_type: str = None, limit: int = 50) -> list[dict]:
        try:
            with self._conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    sql = """
                        SELECT id::text, entity_type, entity_id::text, action,
                               old_value, new_value, changed_by, reason, created_at::text
                        FROM fazle_policy_audit
                    """
                    params = []
                    if entity_type:
                        sql += " WHERE entity_type = %s"
                        params.append(entity_type)
                    sql += " ORDER BY created_at DESC LIMIT %s"
                    params.append(limit)
                    cur.execute(sql, params)
                    return [dict(r) for r in cur.fetchall()]
        except Exception:
            logger.exception("Failed to get audit log")
            return []


def _normalize_phone(phone: str) -> str:
    p = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "").lstrip("+").strip()
    if p.startswith("0") and len(p) == 11:
        p = "88" + p
    return p
