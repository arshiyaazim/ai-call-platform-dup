# ============================================================
# WBOM — Master Contacts Routes
# Unified identity + role management + message history + search
# ============================================================
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from database import get_conn, execute_query

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
from phone_utils import normalize_phone
from identity_service import upsert_master_contact, get_master_contact
from history_service import get_messages, count_messages

router = APIRouter(prefix="/master", tags=["master_contacts"])


# ── Master Contact CRUD ──────────────────────────────────────

@router.get("/contacts")
def list_master_contacts(
    role: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    """List master contacts with optional role/name filter."""
    clauses = []
    params: list = []
    if role:
        clauses.append("role = %s")
        params.append(role)
    if search:
        clauses.append("(display_name ILIKE %s OR canonical_phone ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([limit, offset])
    rows = execute_query(
        f"SELECT * FROM master_contacts {where} ORDER BY updated_at DESC LIMIT %s OFFSET %s",
        tuple(params),
    )
    return rows


@router.get("/contacts/count")
def count_master_contacts(role: Optional[str] = None, search: Optional[str] = None):
    clauses = []
    params: list = []
    if role:
        clauses.append("role = %s")
        params.append(role)
    if search:
        clauses.append("(display_name ILIKE %s OR canonical_phone ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = execute_query(
        f"SELECT COUNT(*) as total FROM master_contacts {where}",
        tuple(params),
    )
    return {"total": rows[0]["total"] if rows else 0}


@router.get("/contacts/{phone}")
def get_contact_by_phone(phone: str):
    """Lookup a master contact by any phone format."""
    cp = normalize_phone(phone)
    if not cp:
        raise HTTPException(400, "Invalid phone number")
    with get_conn() as conn:
        mc = get_master_contact(conn, cp)
    if not mc:
        raise HTTPException(404, "Contact not found")
    return mc


@router.put("/contacts/{phone}")
def update_master_contact(phone: str, data: dict):
    """Update a master contact's role, name, sub_role, metadata."""
    cp = normalize_phone(phone)
    if not cp:
        raise HTTPException(400, "Invalid phone number")
    allowed = {"display_name", "role", "sub_role", "is_whatsapp", "metadata"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        raise HTTPException(400, "No valid fields to update")
    with get_conn() as conn:
        result = upsert_master_contact(conn, cp, **updates)
    return result


@router.post("/contacts")
def create_or_upsert_contact(data: dict):
    """Create or update a master contact. Phone is required."""
    raw_phone = data.get("phone") or data.get("canonical_phone")
    if not raw_phone:
        raise HTTPException(400, "phone is required")
    cp = normalize_phone(str(raw_phone))
    if not cp:
        raise HTTPException(400, "Invalid phone number")
    with get_conn() as conn:
        result = upsert_master_contact(
            conn, cp,
            display_name=data.get("display_name", ""),
            role=data.get("role", "unknown"),
            sub_role=data.get("sub_role", ""),
            source=data.get("source", "dashboard"),
            is_whatsapp=data.get("is_whatsapp", False),
        )
    return result


# ── Role Management ──────────────────────────────────────────

@router.get("/roles")
def list_roles():
    """List all distinct roles and counts."""
    rows = execute_query(
        "SELECT role, COUNT(*) as count FROM master_contacts GROUP BY role ORDER BY count DESC"
    )
    return rows


@router.put("/contacts/{phone}/role")
def set_role(phone: str, role: str = Query(...)):
    """Set role for a contact."""
    valid_roles = {"owner", "family", "employee", "client", "vendor", "job_applicant", "unknown"}
    if role not in valid_roles:
        raise HTTPException(400, f"Invalid role. Must be one of: {', '.join(sorted(valid_roles))}")
    cp = normalize_phone(phone)
    if not cp:
        raise HTTPException(400, "Invalid phone number")
    with get_conn() as conn:
        result = upsert_master_contact(conn, cp, role=role, source="dashboard")
    return result


# ── Message History ──────────────────────────────────────────

@router.get("/messages/{phone}")
def get_message_history(
    phone: str,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    platform: Optional[str] = None,
):
    """Get message history for a contact."""
    cp = normalize_phone(phone)
    if not cp:
        raise HTTPException(400, "Invalid phone number")
    with get_conn() as conn:
        msgs = get_messages(conn, cp, limit=limit, offset=offset, platform=platform)
        total = count_messages(conn, cp)
    return {"messages": msgs, "total": total, "phone": cp}


@router.get("/messages")
def list_recent_messages(
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    """List recent messages across all contacts."""
    rows = execute_query(
        """SELECT mh.*, mc.display_name, mc.role
           FROM message_history mh
           LEFT JOIN master_contacts mc ON mh.canonical_phone = mc.canonical_phone
           ORDER BY mh.created_at DESC LIMIT %s OFFSET %s""",
        (limit, offset),
    )
    return rows


# ── Unified Search ───────────────────────────────────────────

@router.get("/search")
def unified_search(q: str = Query(..., min_length=1), limit: int = Query(20, le=100)):
    """Search across master_contacts, employees, and messages."""
    phone_query = normalize_phone(q)
    results = {"contacts": [], "employees": [], "messages": []}

    # Search master_contacts by name or phone
    contact_clauses = ["display_name ILIKE %s"]
    contact_params: list = [f"%{q}%"]
    if phone_query:
        contact_clauses.append("canonical_phone = %s")
        contact_params.append(phone_query)
    results["contacts"] = execute_query(
        f"SELECT * FROM master_contacts WHERE {' OR '.join(contact_clauses)} ORDER BY updated_at DESC LIMIT %s",
        tuple(contact_params + [limit]),
    )

    # Search employees
    results["employees"] = execute_query(
        "SELECT * FROM wbom_employees WHERE employee_name ILIKE %s OR employee_mobile ILIKE %s LIMIT %s",
        (f"%{q}%", f"%{q}%", limit),
    )

    # Search message content
    results["messages"] = execute_query(
        "SELECT * FROM message_history WHERE message_text ILIKE %s ORDER BY created_at DESC LIMIT %s",
        (f"%{q}%", min(limit, 10)),
    )

    return results
