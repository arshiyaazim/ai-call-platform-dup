# ============================================================
# Phase 2A: Owner Query APIs
# Structured DB queries — who messaged, lead stats, contacts
# ============================================================
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Query, Depends
from pydantic import BaseModel
import psycopg2
import psycopg2.extras

from auth import require_admin
from database import _get_conn

logger = logging.getLogger("fazle-api.owner-query")

router = APIRouter(prefix="/owner", tags=["Owner Queries"])


# ── Who Messaged ────────────────────────────────────────────

@router.get("/messages")
def who_messaged(
    platform: Optional[str] = Query(None, description="whatsapp or facebook"),
    hours: int = Query(24, ge=1, le=168, description="Look back N hours"),
    limit: int = Query(50, ge=1, le=500),
    _=Depends(require_admin),
):
    """List recent incoming messages with sender info."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    sql = """
        SELECT sm.id, sm.platform, sm.direction, sm.contact_identifier,
               sm.content, sm.metadata, sm.status,
               sm.created_at::text,
               sc.name AS sender_name, sm.contact_identifier AS phone_number
        FROM fazle_social_messages sm
        LEFT JOIN fazle_social_contacts sc
            ON sc.identifier = sm.contact_identifier AND sc.platform = sm.platform
        WHERE sm.direction = 'incoming'
          AND sm.created_at >= %s
    """
    params: list = [cutoff]
    if platform:
        sql += " AND sm.platform = %s"
        params.append(platform)
    sql += " ORDER BY sm.created_at DESC LIMIT %s"
    params.append(limit)

    try:
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                for r in rows:
                    r["id"] = str(r["id"])
                    if r.get("metadata"):
                        import json
                        try:
                            r["metadata"] = json.loads(r["metadata"]) if isinstance(r["metadata"], str) else r["metadata"]
                        except Exception:
                            pass
                return {"messages": rows, "count": len(rows), "hours": hours}
    except psycopg2.errors.UndefinedTable:
        return {"messages": [], "count": 0, "hours": hours, "note": "social_messages table not found"}
    except Exception as e:
        logger.exception("who_messaged failed")
        return {"messages": [], "count": 0, "error": str(e)}


# ── Unique Senders ──────────────────────────────────────────

@router.get("/senders")
def unique_senders(
    hours: int = Query(24, ge=1, le=168),
    _=Depends(require_admin),
):
    """Count unique senders in the last N hours."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    sql = """
        SELECT sm.platform, sm.contact_identifier,
               sc.name AS sender_name, sm.contact_identifier AS phone_number,
               COUNT(*) AS message_count,
               MAX(sm.created_at)::text AS last_message_at
        FROM fazle_social_messages sm
        LEFT JOIN fazle_social_contacts sc
            ON sc.identifier = sm.contact_identifier AND sc.platform = sm.platform
        WHERE sm.direction = 'incoming'
          AND sm.created_at >= %s
        GROUP BY sm.platform, sm.contact_identifier, sc.name
        ORDER BY MAX(sm.created_at) DESC
    """
    try:
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (cutoff,))
                rows = cur.fetchall()
                return {"senders": rows, "unique_count": len(rows), "hours": hours}
    except psycopg2.errors.UndefinedTable:
        return {"senders": [], "unique_count": 0, "hours": hours, "note": "table not found"}
    except Exception as e:
        logger.exception("unique_senders failed")
        return {"senders": [], "unique_count": 0, "error": str(e)}


# ── Lead Statistics ─────────────────────────────────────────

@router.get("/leads/stats")
def lead_stats(
    days: int = Query(7, ge=1, le=90),
    _=Depends(require_admin),
):
    """Aggregate lead statistics by intent and status."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    try:
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Total count
                cur.execute(
                    "SELECT COUNT(*) AS total FROM fazle_leads WHERE created_at >= %s",
                    (cutoff,),
                )
                total = cur.fetchone()["total"]

                # By intent
                cur.execute("""
                    SELECT intent, COUNT(*) AS count
                    FROM fazle_leads WHERE created_at >= %s
                    GROUP BY intent ORDER BY count DESC
                """, (cutoff,))
                by_intent = cur.fetchall()

                # By status
                cur.execute("""
                    SELECT status, COUNT(*) AS count
                    FROM fazle_leads WHERE created_at >= %s
                    GROUP BY status ORDER BY count DESC
                """, (cutoff,))
                by_status = cur.fetchall()

                # Daily trend
                cur.execute("""
                    SELECT created_at::date::text AS day, COUNT(*) AS count
                    FROM fazle_leads WHERE created_at >= %s
                    GROUP BY created_at::date ORDER BY day DESC
                """, (cutoff,))
                daily = cur.fetchall()

                return {
                    "total": total,
                    "days": days,
                    "by_intent": by_intent,
                    "by_status": by_status,
                    "daily_trend": daily,
                }
    except psycopg2.errors.UndefinedTable:
        return {"total": 0, "days": days, "note": "leads table not found"}
    except Exception as e:
        logger.exception("lead_stats failed")
        return {"total": 0, "error": str(e)}


# ── Contacts ────────────────────────────────────────────────

@router.get("/contacts")
def list_contacts(
    relation: Optional[str] = Query(None, description="friend/family/customer/prospect"),
    interest: Optional[str] = Query(None, description="hot/warm/cold/risk"),
    limit: int = Query(50, ge=1, le=500),
    _=Depends(require_admin),
):
    """List contacts from the contact book with optional filters."""
    sql = """
        SELECT id, phone, name, relation, notes, company,
               personality_hint, platform, interaction_count,
               interest_level, last_seen::text, created_at::text
        FROM fazle_contacts WHERE 1=1
    """
    params: list = []
    if relation:
        sql += " AND relation = %s"
        params.append(relation)
    if interest:
        sql += " AND interest_level = %s"
        params.append(interest)
    sql += " ORDER BY last_seen DESC NULLS LAST LIMIT %s"
    params.append(limit)

    try:
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                for r in rows:
                    r["id"] = str(r["id"])
                return {"contacts": rows, "count": len(rows)}
    except psycopg2.errors.UndefinedTable:
        return {"contacts": [], "count": 0, "note": "contacts table not found"}
    except Exception as e:
        logger.exception("list_contacts failed")
        return {"contacts": [], "count": 0, "error": str(e)}


# ── Daily Report ────────────────────────────────────────────

@router.get("/daily-report")
def daily_report(
    date: Optional[str] = Query(None, description="YYYY-MM-DD, defaults to today"),
    _=Depends(require_admin),
):
    """Aggregate daily report — messages, leads, contacts activity."""
    if date:
        try:
            report_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            return {"error": "Invalid date format. Use YYYY-MM-DD"}
    else:
        report_date = datetime.utcnow().date()

    day_start = datetime.combine(report_date, datetime.min.time())
    day_end = day_start + timedelta(days=1)

    report = {"date": str(report_date)}

    try:
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Messages count
                try:
                    cur.execute("""
                        SELECT direction, COUNT(*) AS count
                        FROM fazle_social_messages
                        WHERE created_at >= %s AND created_at < %s
                        GROUP BY direction
                    """, (day_start, day_end))
                    msg_rows = cur.fetchall()
                    report["messages"] = {
                        "incoming": next((r["count"] for r in msg_rows if r["direction"] == "incoming"), 0),
                        "outgoing": next((r["count"] for r in msg_rows if r["direction"] == "outgoing"), 0),
                    }
                except psycopg2.errors.UndefinedTable:
                    conn.rollback()
                    report["messages"] = {"incoming": 0, "outgoing": 0, "note": "table not found"}

                # Unique senders
                try:
                    cur.execute("""
                        SELECT COUNT(DISTINCT contact_identifier) AS unique_senders
                        FROM fazle_social_messages
                        WHERE direction = 'incoming'
                          AND created_at >= %s AND created_at < %s
                    """, (day_start, day_end))
                    report["unique_senders"] = cur.fetchone()["unique_senders"]
                except psycopg2.errors.UndefinedTable:
                    conn.rollback()
                    report["unique_senders"] = 0

                # Lead count
                try:
                    cur.execute("""
                        SELECT intent, COUNT(*) AS count
                        FROM fazle_leads
                        WHERE created_at >= %s AND created_at < %s
                        GROUP BY intent
                    """, (day_start, day_end))
                    lead_rows = cur.fetchall()
                    report["leads"] = {
                        "total": sum(r["count"] for r in lead_rows),
                        "by_intent": lead_rows,
                    }
                except psycopg2.errors.UndefinedTable:
                    conn.rollback()
                    report["leads"] = {"total": 0, "note": "table not found"}

                # New contacts
                try:
                    cur.execute("""
                        SELECT COUNT(*) AS new_contacts
                        FROM fazle_contacts
                        WHERE created_at >= %s AND created_at < %s
                    """, (day_start, day_end))
                    report["new_contacts"] = cur.fetchone()["new_contacts"]
                except psycopg2.errors.UndefinedTable:
                    conn.rollback()
                    report["new_contacts"] = 0

        return report
    except Exception as e:
        logger.exception("daily_report failed")
        report["error"] = str(e)
        return report
