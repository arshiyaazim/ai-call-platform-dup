# ============================================================
# identity_service.py — Master Contact Identity Resolution
# Used by social-engine and WBOM for unified identity
# ============================================================
import logging
from datetime import datetime, timezone

logger = logging.getLogger("fazle.identity")

# Role trust hierarchy: higher = harder to overwrite
_ROLE_TRUST = {
    "owner": 100,
    "family": 90,
    "employee": 80,
    "client": 60,
    "vendor": 50,
    "job_applicant": 20,
    "unknown": 0,
}


def upsert_master_contact(conn, canonical_phone: str, *,
                           display_name: str = "",
                           role: str = "unknown",
                           sub_role: str = "",
                           source: str = "system",
                           is_whatsapp: bool = False,
                           employee_id: int | None = None,
                           metadata: dict | None = None) -> dict:
    """Insert or update a master contact. Respects role trust hierarchy.

    Returns the current master_contacts row as a dict.
    """
    with conn.cursor() as cur:
        # Try insert first
        cur.execute("""
            INSERT INTO master_contacts
                (canonical_phone, display_name, role, sub_role, source, is_whatsapp, employee_id, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (canonical_phone) DO UPDATE SET
                display_name = CASE
                    WHEN EXCLUDED.display_name != '' AND master_contacts.display_name = ''
                    THEN EXCLUDED.display_name ELSE master_contacts.display_name END,
                role = CASE
                    WHEN %s > COALESCE(
                        (SELECT v FROM (VALUES
                            ('owner',100),('family',90),('employee',80),('client',60),
                            ('vendor',50),('job_applicant',20),('unknown',0)
                        ) AS t(r,v) WHERE t.r = master_contacts.role), 0)
                    THEN EXCLUDED.role ELSE master_contacts.role END,
                sub_role = CASE WHEN EXCLUDED.sub_role != '' THEN EXCLUDED.sub_role ELSE master_contacts.sub_role END,
                is_whatsapp = master_contacts.is_whatsapp OR EXCLUDED.is_whatsapp,
                employee_id = COALESCE(EXCLUDED.employee_id, master_contacts.employee_id),
                updated_at = NOW()
            RETURNING id, canonical_phone, display_name, role, sub_role, source,
                      is_whatsapp, employee_id, metadata, created_at, updated_at
        """, (
            canonical_phone, display_name, role, sub_role, source,
            is_whatsapp, employee_id,
            __import__("json").dumps(metadata or {}),
            _ROLE_TRUST.get(role, 0),
        ))
        row = cur.fetchone()
        conn.commit()

        if row:
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))
        return {}


def get_master_contact(conn, canonical_phone: str) -> dict | None:
    """Lookup a master contact by canonical phone."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, canonical_phone, display_name, role, sub_role, source,
                   is_whatsapp, employee_id, metadata, created_at, updated_at
            FROM master_contacts WHERE canonical_phone = %s
        """, (canonical_phone,))
        row = cur.fetchone()
        if row:
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))
    return None


def resolve_role(conn, canonical_phone: str, owner_phones: list[str] | None = None) -> str:
    """Resolve the role for a phone number by checking all sources.

    Priority: owner whitelist > employees > master_contacts > unknown
    """
    # Check owner whitelist
    if owner_phones and canonical_phone in owner_phones:
        return "owner"

    # Check employee table
    with conn.cursor() as cur:
        cur.execute(
            "SELECT employee_id FROM wbom_employees WHERE employee_mobile = %s LIMIT 1",
            (canonical_phone,),
        )
        if cur.fetchone():
            return "employee"

    # Check master record
    mc = get_master_contact(conn, canonical_phone)
    if mc:
        return mc["role"]

    return "unknown"
