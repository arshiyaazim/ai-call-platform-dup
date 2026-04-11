# ============================================================
# Fazle API — Maintenance Console Routes
# Admin-only endpoints for controlled database table management
# ============================================================
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import require_admin
from audit import log_action
from admin_data_access.metadata import (
    list_exposed_tables,
    get_table_schema,
    get_table_meta,
)
from admin_data_access.repository import MaintenanceRepository
from admin_data_access.permissions import check_access
from admin_data_access.adapters import get_adapter

logger = logging.getLogger("fazle-api")

router = APIRouter(
    prefix="/fazle/admin/maintenance",
    dependencies=[Depends(require_admin)],
    tags=["maintenance"],
)


# ── Schemas ─────────────────────────────────────────────────

class RowCreateRequest(BaseModel):
    data: dict = Field(..., description="Column name → value pairs")


class RowUpdateRequest(BaseModel):
    data: dict = Field(..., description="Column name → value pairs to update")


# ── Table Discovery ─────────────────────────────────────────

@router.get("/tables")
async def get_tables(admin: dict = Depends(require_admin)):
    """List all tables available in the maintenance console."""
    return {"tables": list_exposed_tables()}


@router.get("/tables/{table_name}/schema")
async def get_schema(table_name: str, admin: dict = Depends(require_admin)):
    """Get full schema metadata for a table (columns, types, permissions)."""
    schema = get_table_schema(table_name)
    if schema is None:
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found or not accessible")
    return schema


# ── Row Operations ──────────────────────────────────────────

@router.get("/tables/{table_name}/rows")
async def list_rows(
    table_name: str,
    search: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
    sort_by: Optional[str] = None,
    sort_dir: str = "asc",
    admin: dict = Depends(require_admin),
):
    """List rows with pagination, search, and sorting."""
    if per_page > 100:
        per_page = 100
    if page < 1:
        page = 1

    return MaintenanceRepository.list_rows(
        table_name=table_name,
        search=search,
        page=page,
        per_page=per_page,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


@router.get("/tables/{table_name}/rows/{row_id}")
async def get_row(
    table_name: str,
    row_id: str,
    admin: dict = Depends(require_admin),
):
    """Get a single row by primary key."""
    check_access(table_name, "read")
    row = MaintenanceRepository.get_row(table_name, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Row not found")
    return row


@router.post("/tables/{table_name}/rows")
async def create_row(
    table_name: str,
    body: RowCreateRequest,
    request: Request,
    admin: dict = Depends(require_admin),
):
    """Create a new row in the table."""
    meta = check_access(table_name, "create")

    # Check for adapter override
    adapter = get_adapter(meta.adapter)
    if adapter and "create" in adapter:
        row = adapter["create"](table_name, body.data)
    else:
        row = MaintenanceRepository.create_row(table_name, body.data)

    # Audit log
    log_action(
        admin,
        f"{meta.audit_event_prefix}_create",
        target_type=table_name,
        target_id=str(row.get(meta.primary_key, "")),
        detail=f"Created row via maintenance console",
        ip_address=request.client.host if request.client else "",
    )

    return row


@router.put("/tables/{table_name}/rows/{row_id}")
async def update_row(
    table_name: str,
    row_id: str,
    body: RowUpdateRequest,
    request: Request,
    admin: dict = Depends(require_admin),
):
    """Update an existing row."""
    meta = check_access(table_name, "update")

    # Check for adapter override
    adapter = get_adapter(meta.adapter)
    if adapter and "update" in adapter:
        row = adapter["update"](table_name, row_id, body.data)
    else:
        row = MaintenanceRepository.update_row(table_name, row_id, body.data)

    if row is None:
        raise HTTPException(status_code=404, detail="Row not found")

    # Audit log
    changed_fields = list(body.data.keys())
    log_action(
        admin,
        f"{meta.audit_event_prefix}_update",
        target_type=table_name,
        target_id=str(row_id),
        detail=f"Updated fields: {', '.join(changed_fields)}",
        ip_address=request.client.host if request.client else "",
    )

    return row


@router.delete("/tables/{table_name}/rows/{row_id}")
async def delete_row(
    table_name: str,
    row_id: str,
    request: Request,
    admin: dict = Depends(require_admin),
):
    """Delete or archive a row based on table policy."""
    meta = check_access(table_name, "delete")

    # Check for adapter override
    adapter = get_adapter(meta.adapter)
    if adapter and "delete" in adapter:
        success = adapter["delete"](table_name, row_id)
    else:
        success = MaintenanceRepository.delete_row(table_name, row_id)

    if not success:
        raise HTTPException(status_code=404, detail="Row not found")

    # Audit log
    log_action(
        admin,
        f"{meta.audit_event_prefix}_delete",
        target_type=table_name,
        target_id=str(row_id),
        detail=f"Deleted/archived row via maintenance console (policy: {meta.delete_policy.value})",
        ip_address=request.client.host if request.client else "",
    )

    return {"status": "deleted", "policy": meta.delete_policy.value}
