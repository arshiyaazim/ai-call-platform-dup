# ============================================================
# Admin Data Access — Table-Specific Adapters
# Custom logic for tables where generic CRUD is insufficient
# ============================================================
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import HTTPException

from admin_data_access.core import get_conn
from admin_data_access.metadata import get_table_meta
from admin_data_access.repository import MaintenanceRepository, _serialize_row

logger = logging.getLogger("fazle-api")

# Registry of adapter overrides: adapter_name → { operation → callable }
_ADAPTERS: dict[str, dict] = {}


def get_adapter(adapter_name: str | None) -> dict | None:
    if adapter_name is None:
        return None
    return _ADAPTERS.get(adapter_name)


# ─────────────────────────────────────────────────────────────
# Adapter: users
# Prevents editing email/password through generic interface,
# enforces enum validation on role/relationship
# ─────────────────────────────────────────────────────────────

def _users_update(table_name: str, row_id: str, data: dict) -> dict | None:
    """Users can only update name, relationship_to_azim, role, is_active through maintenance."""
    allowed_fields = {"name", "relationship_to_azim", "role", "is_active"}
    filtered = {k: v for k, v in data.items() if k in allowed_fields and v is not None}

    if not filtered:
        return MaintenanceRepository.get_row(table_name, row_id)

    # Use the generic update but with filtered data
    return MaintenanceRepository.update_row(table_name, row_id, filtered)


def _users_create(table_name: str, data: dict) -> dict:
    """Block user creation through maintenance — use the dedicated registration endpoint."""
    raise HTTPException(
        status_code=403,
        detail="Users must be created through the registration endpoint, not the maintenance console"
    )


_ADAPTERS["users"] = {
    "create": _users_create,
    "update": _users_update,
}


# ─────────────────────────────────────────────────────────────
# Adapter: user_rules
# Preserves unique constraint, audit trail, and soft delete
# ─────────────────────────────────────────────────────────────

def _user_rules_create(table_name: str, data: dict) -> dict:
    """Upsert user rule: if contact+platform+type exists, update it instead."""
    import psycopg2.extras

    meta = get_table_meta(table_name)
    required = {"contact_identifier", "platform", "rule_type", "rule_value"}
    missing = required - set(data.keys())
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required fields: {', '.join(missing)}")

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Upsert: insert or update on conflict
            cur.execute(
                """
                INSERT INTO fazle_user_rules
                    (contact_identifier, platform, rule_type, rule_value, priority, is_active, created_by)
                VALUES (%s, %s, %s, %s, %s, true, %s)
                ON CONFLICT (contact_identifier, platform, rule_type)
                DO UPDATE SET
                    rule_value = EXCLUDED.rule_value,
                    priority = EXCLUDED.priority,
                    is_active = true,
                    updated_at = NOW()
                RETURNING *
                """,
                (
                    data["contact_identifier"],
                    data.get("platform", "whatsapp"),
                    data["rule_type"],
                    data["rule_value"],
                    data.get("priority", 1),
                    data.get("created_by", "admin"),
                ),
            )
            conn.commit()
            row = cur.fetchone()
            return _serialize_row(dict(row), meta)


def _user_rules_delete(table_name: str, row_id: str) -> bool:
    """Soft-delete: deactivate instead of hard delete, and write audit."""
    import psycopg2.extras

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Get the rule first for audit
            cur.execute("SELECT * FROM fazle_user_rules WHERE id = %s", (row_id,))
            rule = cur.fetchone()
            if not rule:
                return False

            # Soft delete
            cur.execute(
                "UPDATE fazle_user_rules SET is_active = false, updated_at = NOW() WHERE id = %s",
                (row_id,),
            )
            # Write audit record
            cur.execute(
                """
                INSERT INTO fazle_user_rules_audit
                    (rule_id, contact_identifier, action, old_value, new_value, changed_by)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    row_id,
                    rule["contact_identifier"],
                    "deactivate_maintenance",
                    rule["rule_value"],
                    None,
                    "admin",
                ),
            )
            conn.commit()
            return True


_ADAPTERS["user_rules"] = {
    "create": _user_rules_create,
    "delete": _user_rules_delete,
}


# ─────────────────────────────────────────────────────────────
# Adapter: knowledge_governance
# Preserves versioning, deprecation semantics
# ─────────────────────────────────────────────────────────────

def _governance_delete(table_name: str, row_id: str) -> bool:
    """Archive governance fact: set status to deprecated instead of deleting."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE fazle_knowledge_governance
                SET status = 'deprecated', deprecated_at = NOW(),
                    deprecation_reason = 'Deprecated via maintenance console',
                    updated_at = NOW()
                WHERE id = %s AND status = 'active'
                """,
                (row_id,),
            )
            conn.commit()
            return cur.rowcount > 0


_ADAPTERS["knowledge_governance"] = {
    "delete": _governance_delete,
}
