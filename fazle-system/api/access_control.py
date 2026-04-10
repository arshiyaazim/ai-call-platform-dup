# ============================================================
# Fazle API — Access Control for Knowledge Data
# Role-based access rules with DB-backed permissions
# ============================================================
import logging
from typing import Optional
from database import _get_conn
import psycopg2.extras

logger = logging.getLogger("fazle-api.access")

# Roles that can see personal/sensitive data
_PERSONAL_ROLES = frozenset({"self", "wife", "daughter"})
# Roles that can see business data
_BUSINESS_ROLES = frozenset({"self", "wife", "daughter", "employee", "admin"})


def check_access(user_role: str, data_type: str) -> bool:
    """Check if a user role can access a given data type.

    Returns True if allowed, False if denied.
    """
    if not user_role or not data_type:
        return False

    if data_type == "personal":
        return user_role in _PERSONAL_ROLES
    if data_type == "business":
        return user_role in _BUSINESS_ROLES
    # Default: allow non-sensitive categories
    return True


def check_access_db(user_id: str, data_type: str) -> bool:
    """Check access from the fazle_access_rules table.

    Falls back to role-based check if no DB rule found.
    """
    try:
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT allowed FROM fazle_access_rules "
                    "WHERE user_id = %s AND data_type = %s LIMIT 1",
                    (user_id, data_type),
                )
                row = cur.fetchone()
                if row is not None:
                    return bool(row["allowed"])
    except Exception as e:
        logger.warning(f"access_rules DB check failed: {e}")

    # No rule found — look up user role and use static check
    try:
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT role FROM fazle_knowledge_users WHERE id = %s LIMIT 1",
                    (user_id,),
                )
                row = cur.fetchone()
                if row:
                    return check_access(row["role"], data_type)
    except Exception as e:
        logger.warning(f"user role lookup failed: {e}")

    return False


def get_user_by_phone(phone: str) -> Optional[dict]:
    """Lookup a knowledge user by phone number."""
    try:
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT id, name, phone, role, access_level, created_at "
                    "FROM fazle_knowledge_users WHERE phone = %s LIMIT 1",
                    (phone,),
                )
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"get_user_by_phone failed: {e}")
        return None


def get_user_access_rules(user_id: str) -> list[dict]:
    """List all access rules for a user."""
    try:
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT id, data_type, allowed FROM fazle_access_rules "
                    "WHERE user_id = %s ORDER BY data_type",
                    (user_id,),
                )
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error(f"get_user_access_rules failed: {e}")
        return []
