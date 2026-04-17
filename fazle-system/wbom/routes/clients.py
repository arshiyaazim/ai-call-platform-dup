# ============================================================
# WBOM — Client Routes
# Full CRUD for client/billing entity management
# ============================================================
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from database import insert_row, get_row, update_row, delete_row, list_rows, audit_log, count_rows
from models import ClientCreate, ClientUpdate, ClientResponse
from response import api_response, api_single
from openapi_models import ClientListResponse, SingleEnvelope

router = APIRouter(prefix="/clients", tags=["clients"])


@router.post("", status_code=201)
def create_client(data: ClientCreate):
    row = insert_row("wbom_clients", data.model_dump(exclude_none=True))
    audit_log("client.created", entity_type="client",
              entity_id=row.get("client_id"),
              payload={"name": data.name, "type": data.client_type})
    return api_single(row, entity="clients")


@router.get("", response_model=ClientListResponse)
def list_clients(
    client_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    filters = {}
    if client_type:
        filters["client_type"] = client_type
    if is_active is not None:
        filters["is_active"] = is_active
    rows = list_rows("wbom_clients", filters=filters, limit=limit, offset=offset)
    total = count_rows("wbom_clients", filters if filters else None)
    return api_response(rows, entity="clients", total=total)


@router.get("/search")
def search_clients(q: str = Query(..., min_length=1), limit: int = Query(10, le=50)):
    from database import execute_query
    rows = execute_query(
        "SELECT * FROM wbom_clients WHERE name ILIKE %s OR company_name ILIKE %s OR phone ILIKE %s LIMIT %s",
        (f"%{q}%", f"%{q}%", f"%{q}%", limit),
    )
    return api_response(rows, entity="clients")


@router.get("/{client_id}")
def get_client(client_id: int):
    row = get_row("wbom_clients", "client_id", client_id)
    if not row:
        raise HTTPException(404, "Client not found")
    return api_single(row, entity="clients")


@router.put("/{client_id}")
def update_client(client_id: int, data: ClientUpdate):
    updates = data.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields to update")
    row = update_row("wbom_clients", "client_id", client_id, updates)
    if not row:
        raise HTTPException(404, "Client not found")
    audit_log("client.updated", entity_type="client",
              entity_id=client_id, payload=updates)
    return api_single(row, entity="clients")


@router.delete("/{client_id}")
def delete_client(client_id: int):
    if not delete_row("wbom_clients", "client_id", client_id):
        raise HTTPException(404, "Client not found")
    audit_log("client.deleted", entity_type="client", entity_id=client_id)
    return {"deleted": True}
