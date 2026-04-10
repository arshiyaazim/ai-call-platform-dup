# ============================================================
# Phase 1B: Knowledge Governance — API Routes
# CRUD for canonical facts, phrasing rules, and corrections
# ============================================================
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional
import logging
import os

import psycopg2
import psycopg2.extras

from auth import require_admin

logger = logging.getLogger("fazle-api.governance")

router = APIRouter(prefix="/governance", tags=["Knowledge Governance"])

psycopg2.extras.register_uuid()

_DSN = os.getenv(
    "FAZLE_DATABASE_URL",
    "postgresql://postgres:postgres@postgres:5432/postgres",
)


def _conn():
    return psycopg2.connect(_DSN)


# ── Schemas ──────────────────────────────────────────────────

class FactCreate(BaseModel):
    category: str = Field(..., max_length=50)
    fact_key: str = Field(..., max_length=100)
    fact_value: str = Field(..., max_length=2000)
    language: str = Field(default="bn", max_length=10)


class FactUpdate(BaseModel):
    new_value: str = Field(..., max_length=2000)
    reason: str = Field(default="", max_length=500)


class PhrasingCreate(BaseModel):
    topic: str = Field(..., max_length=100)
    preferred_phrasing: str = Field(..., max_length=1000)
    prohibited_phrasing: Optional[str] = Field(default=None, max_length=1000)
    language: str = Field(default="bn", max_length=10)


class CorrectionOut(BaseModel):
    id: str
    category: str
    fact_key: str
    old_value: str
    new_value: str
    reason: Optional[str]
    corrected_by: str
    corrected_at: Optional[str]


# ── Ensure tables exist ─────────────────────────────────────

def ensure_governance_tables():
    """Run the migration to create governance tables if missing."""
    migration = os.path.join(
        os.path.dirname(__file__),
        "..", "tasks", "migrations", "006_knowledge_governance.sql",
    )
    if not os.path.exists(migration):
        logger.warning("Governance migration not found at %s", migration)
        return
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(open(migration, encoding="utf-8").read())
            conn.commit()
        logger.info("Governance tables ensured")
    except Exception:
        logger.exception("Failed to run governance migration")


# ── Facts CRUD ───────────────────────────────────────────────

@router.get("/facts")
def list_facts(category: Optional[str] = None, status: str = "active"):
    """List canonical facts, optionally filtered by category."""
    sql = """
        SELECT id, category, fact_key, fact_value, language, version,
               status, created_by, created_at::text, updated_at::text
        FROM fazle_knowledge_governance WHERE status = %s
    """
    params: list = [status]
    if category:
        sql += " AND category = %s"
        params.append(category)
    sql += " ORDER BY category, fact_key"

    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                for r in rows:
                    r["id"] = str(r["id"])
                return {"facts": rows, "count": len(rows)}
    except Exception as e:
        logger.exception("list_facts failed")
        raise HTTPException(500, str(e))


@router.post("/facts", status_code=201)
def create_fact(body: FactCreate, _=Depends(require_admin)):
    """Create a new canonical fact (admin only)."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO fazle_knowledge_governance
                        (category, fact_key, fact_value, language, created_by)
                    VALUES (%s, %s, %s, %s, 'owner')
                    RETURNING id, category, fact_key, fact_value, language, version, status
                """, (body.category, body.fact_key, body.fact_value, body.language))
                row = cur.fetchone()
                row["id"] = str(row["id"])
            conn.commit()
            return row
    except psycopg2.errors.UniqueViolation:
        raise HTTPException(409, "Fact already exists for this category/key/version")
    except Exception as e:
        logger.exception("create_fact failed")
        raise HTTPException(500, str(e))


@router.put("/facts/{category}/{fact_key}")
def update_fact(category: str, fact_key: str, body: FactUpdate, _=Depends(require_admin)):
    """Update a canonical fact — creates new version, deprecates old (admin only)."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Get current
                cur.execute("""
                    SELECT id, fact_value, version FROM fazle_knowledge_governance
                    WHERE category = %s AND fact_key = %s AND status = 'active'
                    ORDER BY version DESC LIMIT 1
                """, (category, fact_key))
                old = cur.fetchone()
                if not old:
                    raise HTTPException(404, "Active fact not found")

                old_version = old["version"]
                old_value = old["fact_value"]

                # Deprecate old
                cur.execute("""
                    UPDATE fazle_knowledge_governance
                    SET status = 'deprecated', deprecated_at = now(),
                        deprecation_reason = %s
                    WHERE id = %s
                """, (body.reason or "superseded", old["id"]))

                # Insert new version
                cur.execute("""
                    INSERT INTO fazle_knowledge_governance
                        (category, fact_key, fact_value, version, created_by)
                    VALUES (%s, %s, %s, %s, 'owner')
                    RETURNING id, category, fact_key, fact_value, language, version, status
                """, (category, fact_key, body.new_value, old_version + 1))
                new_row = cur.fetchone()

                # Record correction
                cur.execute("""
                    INSERT INTO fazle_knowledge_corrections
                        (governance_id, old_value, new_value, reason, corrected_by)
                    VALUES (%s, %s, %s, %s, 'owner')
                """, (new_row["id"], old_value, body.new_value, body.reason))

            conn.commit()
            new_row["id"] = str(new_row["id"])
            return new_row
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("update_fact failed")
        raise HTTPException(500, str(e))


@router.get("/facts/{category}/{fact_key}/history")
def fact_history(category: str, fact_key: str):
    """Return version history for a canonical fact."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, fact_value, version, status,
                           created_by, created_at::text,
                           deprecated_at::text, deprecation_reason
                    FROM fazle_knowledge_governance
                    WHERE category = %s AND fact_key = %s
                    ORDER BY version DESC
                """, (category, fact_key))
                rows = cur.fetchall()
                for r in rows:
                    r["id"] = str(r["id"])
                return {"category": category, "fact_key": fact_key, "versions": rows}
    except Exception as e:
        logger.exception("fact_history failed")
        raise HTTPException(500, str(e))


# ── Phrasing Rules ──────────────────────────────────────────

@router.get("/phrasing")
def list_phrasing():
    """List active phrasing rules."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, topic, preferred_phrasing, prohibited_phrasing,
                           language, status, created_at::text
                    FROM fazle_knowledge_phrasing WHERE status = 'active'
                    ORDER BY topic
                """)
                rows = cur.fetchall()
                for r in rows:
                    r["id"] = str(r["id"])
                return {"rules": rows, "count": len(rows)}
    except Exception as e:
        logger.exception("list_phrasing failed")
        raise HTTPException(500, str(e))


@router.post("/phrasing", status_code=201)
def create_phrasing(body: PhrasingCreate, _=Depends(require_admin)):
    """Create a new phrasing rule (admin only)."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO fazle_knowledge_phrasing
                        (topic, preferred_phrasing, prohibited_phrasing, language)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, topic, preferred_phrasing, prohibited_phrasing, language, status
                """, (body.topic, body.preferred_phrasing,
                      body.prohibited_phrasing, body.language))
                row = cur.fetchone()
                row["id"] = str(row["id"])
            conn.commit()
            return row
    except Exception as e:
        logger.exception("create_phrasing failed")
        raise HTTPException(500, str(e))


# ── Corrections ─────────────────────────────────────────────

@router.get("/corrections", response_model=list[CorrectionOut])
def list_corrections(category: Optional[str] = None, limit: int = 20):
    """List recent corrections, optionally filtered by category."""
    sql = """
        SELECT c.id, c.old_value, c.new_value, c.reason,
               c.corrected_by, c.corrected_at::text,
               g.category, g.fact_key
        FROM fazle_knowledge_corrections c
        JOIN fazle_knowledge_governance g ON g.id = c.governance_id
    """
    params: list = []
    if category:
        sql += " WHERE g.category = %s"
        params.append(category)
    sql += " ORDER BY c.corrected_at DESC LIMIT %s"
    params.append(min(limit, 100))

    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                for r in rows:
                    r["id"] = str(r["id"])
                return rows
    except Exception as e:
        logger.exception("list_corrections failed")
        raise HTTPException(500, str(e))


# ── Governance prompt (for brain consumption) ────────────────

@router.get("/prompt")
def governance_prompt():
    """Return the governance prompt block for the brain service."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Facts
                cur.execute("""
                    SELECT category, fact_key, fact_value
                    FROM fazle_knowledge_governance WHERE status = 'active'
                    ORDER BY category, fact_key
                """)
                facts = cur.fetchall()

                # Phrasing
                cur.execute("""
                    SELECT topic, preferred_phrasing, prohibited_phrasing
                    FROM fazle_knowledge_phrasing WHERE status = 'active'
                    ORDER BY topic
                """)
                rules = cur.fetchall()

        lines = ["━━━ KNOWLEDGE GOVERNANCE (MANDATORY) ━━━",
                 "You MUST use these canonical facts. Never contradict them.", ""]

        by_cat: dict[str, list] = {}
        for f in facts:
            by_cat.setdefault(f["category"], []).append(f)

        for cat, cat_facts in sorted(by_cat.items()):
            lines.append(f"[{cat.upper()}]")
            for f in cat_facts:
                lines.append(f"  {f['fact_key']}: {f['fact_value']}")
            lines.append("")

        if rules:
            lines.append("[PHRASING RULES]")
            for r in rules:
                line = f"  ✅ {r['topic']}: Say \"{r['preferred_phrasing']}\""
                if r["prohibited_phrasing"]:
                    line += f"  ❌ Never say: {r['prohibited_phrasing']}"
                lines.append(line)
            lines.append("")

        lines.append("━━━ END GOVERNANCE ━━━")
        prompt = "\n".join(lines)
        return {"prompt": prompt, "facts_count": len(facts), "rules_count": len(rules)}
    except Exception as e:
        logger.exception("governance_prompt failed")
        raise HTTPException(500, str(e))


# ── Phase 2C: Knowledge Lifecycle ────────────────────────────

class FactExpiry(BaseModel):
    expires_at: Optional[str] = Field(None, description="ISO timestamp or null to clear")


@router.put("/facts/{category}/{fact_key}/expiry")
def set_fact_expiry(category: str, fact_key: str, body: FactExpiry, _=Depends(require_admin)):
    """Set or clear an expiry date on a canonical fact."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    UPDATE fazle_knowledge_governance
                    SET expires_at = %s, updated_at = NOW()
                    WHERE category = %s AND fact_key = %s AND status = 'active'
                    RETURNING id, category, fact_key, fact_value, expires_at::text
                """, (body.expires_at, category, fact_key))
                row = cur.fetchone()
                if not row:
                    raise HTTPException(404, "Active fact not found")
                row["id"] = str(row["id"])
                conn.commit()
                return row
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("set_fact_expiry failed")
        raise HTTPException(500, str(e))


@router.get("/facts/expiring")
def expiring_facts(
    days: int = Query(7, ge=1, le=90, description="Facts expiring within N days"),
    _=Depends(require_admin),
):
    """List facts that will expire within N days."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, category, fact_key, fact_value, expires_at::text,
                           version, status
                    FROM fazle_knowledge_governance
                    WHERE status = 'active'
                      AND expires_at IS NOT NULL
                      AND expires_at <= NOW() + INTERVAL '%s days'
                    ORDER BY expires_at ASC
                """, (days,))
                rows = cur.fetchall()
                for r in rows:
                    r["id"] = str(r["id"])

                # Also find already-expired but still active
                cur.execute("""
                    SELECT id, category, fact_key, fact_value, expires_at::text
                    FROM fazle_knowledge_governance
                    WHERE status = 'active' AND expires_at IS NOT NULL AND expires_at <= NOW()
                """)
                expired = cur.fetchall()
                for r in expired:
                    r["id"] = str(r["id"])

                return {
                    "expiring_within_days": days,
                    "expiring": rows,
                    "already_expired": expired,
                }
    except Exception as e:
        logger.exception("expiring_facts failed")
        raise HTTPException(500, str(e))


# ── Conflict Detection & Resolution ─────────────────────────

class ConflictReport(BaseModel):
    fact_a_category: str
    fact_a_key: str
    fact_b_category: str
    fact_b_key: str
    conflict_type: str = Field(default="value_mismatch")
    description: str = Field(..., max_length=500)


class ConflictResolve(BaseModel):
    resolution: str = Field(..., max_length=1000)
    status: str = Field(default="resolved", description="resolved or dismissed")


@router.get("/conflicts")
def list_conflicts(
    status: str = Query("open"),
    _=Depends(require_admin),
):
    """List knowledge conflicts."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT c.id, c.conflict_type, c.description, c.resolution,
                           c.resolved_by, c.status,
                           c.detected_at::text, c.resolved_at::text,
                           a.category AS fact_a_category, a.fact_key AS fact_a_key,
                           a.fact_value AS fact_a_value,
                           b.category AS fact_b_category, b.fact_key AS fact_b_key,
                           b.fact_value AS fact_b_value
                    FROM fazle_knowledge_conflicts c
                    JOIN fazle_knowledge_governance a ON a.id = c.fact_a_id
                    JOIN fazle_knowledge_governance b ON b.id = c.fact_b_id
                    WHERE c.status = %s
                    ORDER BY c.detected_at DESC
                """, (status,))
                rows = cur.fetchall()
                for r in rows:
                    r["id"] = str(r["id"])
                return {"conflicts": rows, "count": len(rows)}
    except psycopg2.errors.UndefinedTable:
        return {"conflicts": [], "count": 0, "note": "conflicts table not created yet"}
    except Exception as e:
        logger.exception("list_conflicts failed")
        return {"conflicts": [], "count": 0, "error": str(e)}


@router.post("/conflicts", status_code=201)
def report_conflict(body: ConflictReport, _=Depends(require_admin)):
    """Report a knowledge conflict between two facts."""
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Find fact A
                cur.execute("""
                    SELECT id FROM fazle_knowledge_governance
                    WHERE category = %s AND fact_key = %s AND status = 'active'
                    ORDER BY version DESC LIMIT 1
                """, (body.fact_a_category, body.fact_a_key))
                fact_a = cur.fetchone()
                if not fact_a:
                    raise HTTPException(404, f"Fact A not found: {body.fact_a_category}/{body.fact_a_key}")

                # Find fact B
                cur.execute("""
                    SELECT id FROM fazle_knowledge_governance
                    WHERE category = %s AND fact_key = %s AND status = 'active'
                    ORDER BY version DESC LIMIT 1
                """, (body.fact_b_category, body.fact_b_key))
                fact_b = cur.fetchone()
                if not fact_b:
                    raise HTTPException(404, f"Fact B not found: {body.fact_b_category}/{body.fact_b_key}")

                cur.execute("""
                    INSERT INTO fazle_knowledge_conflicts
                        (fact_a_id, fact_b_id, conflict_type, description)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, conflict_type, description, status, detected_at::text
                """, (fact_a["id"], fact_b["id"], body.conflict_type, body.description))
                row = cur.fetchone()
                row["id"] = str(row["id"])
                conn.commit()
                return row
    except HTTPException:
        raise
    except psycopg2.errors.UniqueViolation:
        raise HTTPException(409, "Conflict already reported for these facts")
    except psycopg2.errors.UndefinedTable:
        raise HTTPException(500, "Conflicts table not created — run migration 008_knowledge_lifecycle.sql")
    except Exception as e:
        logger.exception("report_conflict failed")
        raise HTTPException(500, str(e))


@router.put("/conflicts/{conflict_id}/resolve")
def resolve_conflict(conflict_id: str, body: ConflictResolve, _=Depends(require_admin)):
    """Resolve or dismiss a knowledge conflict."""
    if body.status not in ("resolved", "dismissed"):
        raise HTTPException(400, "status must be 'resolved' or 'dismissed'")
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    UPDATE fazle_knowledge_conflicts
                    SET resolution = %s, resolved_by = 'owner',
                        status = %s, resolved_at = NOW()
                    WHERE id = %s AND status = 'open'
                    RETURNING id, conflict_type, description, resolution, status, resolved_at::text
                """, (body.resolution, body.status, conflict_id))
                row = cur.fetchone()
                if not row:
                    raise HTTPException(404, "Open conflict not found")
                row["id"] = str(row["id"])
                conn.commit()
                return row
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("resolve_conflict failed")
        raise HTTPException(500, str(e))
