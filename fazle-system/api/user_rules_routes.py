# ============================================================
# Phase 2B: Per-User Instruction Rules — API Routes
# CRUD for contact-specific behavior rules
# ============================================================
import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
import psycopg2
import psycopg2.extras

from auth import require_admin
from database import _get_conn

logger = logging.getLogger("fazle-api.user-rules")

router = APIRouter(prefix="/user-rules", tags=["User Rules"])

_DSN = os.getenv(
    "FAZLE_DATABASE_URL",
    "postgresql://postgres:postgres@postgres:5432/postgres",
)


def _conn():
    return psycopg2.connect(_DSN)


VALID_RULE_TYPES = {"tone", "block", "auto_reply", "greeting", "escalate", "restrict_topic"}


# ── Schemas ──────────────────────────────────────────────────

class RuleCreate(BaseModel):
    contact_identifier: str = Field(..., max_length=50)
    platform: str = Field(default="whatsapp", max_length=20)
    rule_type: str = Field(..., max_length=30)
    rule_value: str = Field(..., max_length=2000)
    priority: int = Field(default=1, ge=1, le=10)
    expires_at: Optional[str] = Field(default=None, description="ISO timestamp or null")


class RuleUpdate(BaseModel):
    rule_value: str = Field(..., max_length=2000)
    priority: Optional[int] = Field(default=None, ge=1, le=10)
    expires_at: Optional[str] = Field(default=None)


# ── Ensure tables ────────────────────────────────────────────

def ensure_user_rules_tables():
    """Run the migration to create user rules tables if missing."""
    migration = os.path.join(
        os.path.dirname(__file__),
        "..", "tasks", "migrations", "007_user_rules.sql",
    )
    if not os.path.exists(migration):
        logger.warning("User rules migration not found at %s", migration)
        return
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(open(migration, encoding="utf-8").read())
            conn.commit()
        logger.info("User rules tables ensured")
    except Exception:
        logger.exception("Failed to run user rules migration")


# ── List rules ───────────────────────────────────────────────

@router.get("/rules")
def list_rules(
    contact: Optional[str] = Query(None, description="Filter by contact identifier"),
    rule_type: Optional[str] = Query(None),
    active_only: bool = Query(True),
    limit: int = Query(50, ge=1, le=500),
    _=Depends(require_admin),
):
    """List per-user rules, optionally filtered."""
    sql = "SELECT * FROM fazle_user_rules WHERE 1=1"
    params: list = []
    if active_only:
        sql += " AND is_active = true AND (expires_at IS NULL OR expires_at > NOW())"
    if contact:
        sql += " AND contact_identifier = %s"
        params.append(contact)
    if rule_type:
        sql += " AND rule_type = %s"
        params.append(rule_type)
    sql += " ORDER BY contact_identifier, priority DESC LIMIT %s"
    params.append(limit)

    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                for r in rows:
                    r["id"] = str(r["id"])
                    if r.get("created_at"):
                        r["created_at"] = r["created_at"].isoformat()
                    if r.get("updated_at"):
                        r["updated_at"] = r["updated_at"].isoformat()
                    if r.get("expires_at"):
                        r["expires_at"] = r["expires_at"].isoformat()
                return {"rules": rows, "count": len(rows)}
    except psycopg2.errors.UndefinedTable:
        return {"rules": [], "count": 0, "note": "user_rules table not found"}
    except Exception as e:
        logger.exception("list_rules failed")
        raise HTTPException(500, str(e))


# ── Create rule ──────────────────────────────────────────────

@router.post("/rules", status_code=201)
def create_rule(body: RuleCreate, _=Depends(require_admin)):
    """Create a new per-user rule (admin only). Upserts on contact+platform+type."""
    if body.rule_type not in VALID_RULE_TYPES:
        raise HTTPException(400, f"Invalid rule_type. Must be one of: {VALID_RULE_TYPES}")

    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Check existing
                cur.execute("""
                    SELECT id, rule_value FROM fazle_user_rules
                    WHERE contact_identifier = %s AND platform = %s AND rule_type = %s
                """, (body.contact_identifier, body.platform, body.rule_type))
                existing = cur.fetchone()

                if existing:
                    old_value = existing["rule_value"]
                    cur.execute("""
                        UPDATE fazle_user_rules
                        SET rule_value = %s, priority = %s, is_active = true,
                            updated_at = NOW(), expires_at = %s
                        WHERE id = %s
                        RETURNING id, contact_identifier, platform, rule_type,
                                  rule_value, priority, is_active,
                                  created_at::text, updated_at::text, expires_at::text
                    """, (body.rule_value, body.priority, body.expires_at, existing["id"]))
                    row = cur.fetchone()
                    row["id"] = str(row["id"])
                    # Audit
                    cur.execute("""
                        INSERT INTO fazle_user_rules_audit
                            (rule_id, contact_identifier, action, old_value, new_value)
                        VALUES (%s, %s, 'updated', %s, %s)
                    """, (existing["id"], body.contact_identifier, old_value, body.rule_value))
                else:
                    cur.execute("""
                        INSERT INTO fazle_user_rules
                            (contact_identifier, platform, rule_type, rule_value, priority, expires_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id, contact_identifier, platform, rule_type,
                                  rule_value, priority, is_active,
                                  created_at::text, updated_at::text, expires_at::text
                    """, (body.contact_identifier, body.platform, body.rule_type,
                          body.rule_value, body.priority, body.expires_at))
                    row = cur.fetchone()
                    row["id"] = str(row["id"])
                    # Audit
                    cur.execute("""
                        INSERT INTO fazle_user_rules_audit
                            (rule_id, contact_identifier, action, new_value)
                        VALUES (%s, %s, 'created', %s)
                    """, (row["id"], body.contact_identifier, body.rule_value))

                conn.commit()
                return row
    except Exception as e:
        logger.exception("create_rule failed")
        raise HTTPException(500, str(e))


# ── Update rule ──────────────────────────────────────────────

@router.put("/rules/{contact}/{rule_type}")
def update_rule(
    contact: str,
    rule_type: str,
    body: RuleUpdate,
    platform: str = Query("whatsapp"),
    _=Depends(require_admin),
):
    """Update an existing rule."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, rule_value FROM fazle_user_rules
                    WHERE contact_identifier = %s AND platform = %s AND rule_type = %s AND is_active = true
                """, (contact, platform, rule_type))
                existing = cur.fetchone()
                if not existing:
                    raise HTTPException(404, "Rule not found")

                updates = ["rule_value = %s", "updated_at = NOW()"]
                params = [body.rule_value]
                if body.priority is not None:
                    updates.append("priority = %s")
                    params.append(body.priority)
                if body.expires_at is not None:
                    updates.append("expires_at = %s")
                    params.append(body.expires_at)

                params.append(existing["id"])
                cur.execute(
                    f"UPDATE fazle_user_rules SET {', '.join(updates)} WHERE id = %s "
                    "RETURNING id, contact_identifier, platform, rule_type, "
                    "rule_value, priority, is_active, created_at::text, updated_at::text, expires_at::text",
                    params,
                )
                row = cur.fetchone()
                row["id"] = str(row["id"])

                # Audit
                cur.execute("""
                    INSERT INTO fazle_user_rules_audit
                        (rule_id, contact_identifier, action, old_value, new_value)
                    VALUES (%s, %s, 'updated', %s, %s)
                """, (existing["id"], contact, existing["rule_value"], body.rule_value))

                conn.commit()
                return row
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("update_rule failed")
        raise HTTPException(500, str(e))


# ── Deactivate rule ──────────────────────────────────────────

@router.delete("/rules/{contact}/{rule_type}")
def deactivate_rule(
    contact: str,
    rule_type: str,
    platform: str = Query("whatsapp"),
    _=Depends(require_admin),
):
    """Deactivate a rule (soft delete)."""
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE fazle_user_rules SET is_active = false, updated_at = NOW()
                    WHERE contact_identifier = %s AND platform = %s AND rule_type = %s AND is_active = true
                    RETURNING id, rule_value
                """, (contact, platform, rule_type))
                row = cur.fetchone()
                if not row:
                    raise HTTPException(404, "Active rule not found")

                # Audit
                cur.execute("""
                    INSERT INTO fazle_user_rules_audit
                        (rule_id, contact_identifier, action, old_value)
                    VALUES (%s, %s, 'deactivated', %s)
                """, (row[0], contact, row[1]))
                conn.commit()

                return {"status": "deactivated", "contact": contact, "rule_type": rule_type}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("deactivate_rule failed")
        raise HTTPException(500, str(e))


# ── Audit trail ──────────────────────────────────────────────

@router.get("/audit")
def rule_audit(
    contact: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    _=Depends(require_admin),
):
    """View rule change audit trail."""
    sql = """
        SELECT id, rule_id, contact_identifier, action,
               old_value, new_value, changed_by, changed_at::text
        FROM fazle_user_rules_audit
    """
    params: list = []
    if contact:
        sql += " WHERE contact_identifier = %s"
        params.append(contact)
    sql += " ORDER BY changed_at DESC LIMIT %s"
    params.append(limit)

    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                for r in rows:
                    r["id"] = str(r["id"])
                    if r.get("rule_id"):
                        r["rule_id"] = str(r["rule_id"])
                return {"audit": rows, "count": len(rows)}
    except psycopg2.errors.UndefinedTable:
        return {"audit": [], "count": 0, "note": "audit table not found"}
    except Exception as e:
        logger.exception("rule_audit failed")
        return {"audit": [], "count": 0, "error": str(e)}
