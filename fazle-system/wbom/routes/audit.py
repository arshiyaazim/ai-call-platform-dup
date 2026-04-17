# ============================================================
# WBOM — Audit Log Routes (read-only)
# Query trail for all system mutations
# ============================================================
from fastapi import APIRouter, Query
from typing import Optional

from database import execute_query
from models import AuditLogResponse

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditLogResponse])
def list_audit_logs(
    event: Optional[str] = None,
    actor: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
):
    """Read-only: query audit trail with optional filters."""
    clauses = []
    params: list = []
    if event:
        clauses.append("event = %s")
        params.append(event)
    if actor:
        clauses.append("actor = %s")
        params.append(actor)
    if entity_type:
        clauses.append("entity_type = %s")
        params.append(entity_type)
    if entity_id is not None:
        clauses.append("entity_id = %s")
        params.append(entity_id)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params += [limit, offset]

    return execute_query(
        f"SELECT * FROM wbom_audit_logs {where} ORDER BY created_at DESC LIMIT %s OFFSET %s",
        tuple(params),
    )
