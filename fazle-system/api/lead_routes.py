# ============================================================
# Fazle API — Lead Capture Routes
# POST /leads/capture  — save a lead (with 24h dedup)
# GET  /leads           — list recent leads
# ============================================================
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Query, Depends
from pydantic import BaseModel

from database import _get_conn
from auth import require_admin

logger = logging.getLogger("fazle-api.leads")

router = APIRouter(tags=["leads"])


class LeadIn(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    message: str
    intent: str
    source: str = ""


def ensure_leads_table():
    """Idempotent — create table + indexes if missing."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS fazle_leads (
                    id SERIAL PRIMARY KEY,
                    name TEXT,
                    phone TEXT,
                    message TEXT,
                    intent TEXT,
                    source TEXT,
                    status TEXT DEFAULT 'new',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_leads_phone ON fazle_leads (phone);
                CREATE INDEX IF NOT EXISTS idx_leads_created ON fazle_leads (created_at DESC);
            """)
            conn.commit()
    logger.info("fazle_leads table ensured")


@router.post("/leads/capture")
def capture_lead(lead: LeadIn):
    """Save a lead with 24-hour dedup on phone number."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            # Dedup: skip if same phone within 24h
            if lead.phone:
                cur.execute(
                    "SELECT 1 FROM fazle_leads WHERE phone = %s AND created_at > %s LIMIT 1",
                    (lead.phone, datetime.utcnow() - timedelta(hours=24)),
                )
                if cur.fetchone():
                    return {"status": "duplicate", "detail": "same phone within 24h"}

            cur.execute(
                """INSERT INTO fazle_leads (name, phone, message, intent, source)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (lead.name, lead.phone, lead.message[:500], lead.intent, lead.source),
            )
            lead_id = cur.fetchone()[0]
            conn.commit()

    logger.info(f"Lead saved id={lead_id} phone={lead.phone} intent={lead.intent}")
    return {"status": "saved", "id": lead_id}


@router.get("/leads")
def list_leads(
    limit: int = Query(50, ge=1, le=500),
    status: Optional[str] = Query(None),
    _user=Depends(require_admin),
):
    """Return recent leads ordered by newest first."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            if status:
                cur.execute(
                    "SELECT id, name, phone, message, intent, source, status, created_at "
                    "FROM fazle_leads WHERE status = %s ORDER BY created_at DESC LIMIT %s",
                    (status, limit),
                )
            else:
                cur.execute(
                    "SELECT id, name, phone, message, intent, source, status, created_at "
                    "FROM fazle_leads ORDER BY created_at DESC LIMIT %s",
                    (limit,),
                )
            rows = cur.fetchall()

    return [
        {
            "id": r[0], "name": r[1], "phone": r[2], "message": r[3],
            "intent": r[4], "source": r[5], "status": r[6],
            "created_at": r[7].isoformat() if r[7] else None,
        }
        for r in rows
    ]
