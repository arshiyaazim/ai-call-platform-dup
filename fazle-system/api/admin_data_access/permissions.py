# ============================================================
# Admin Data Access — Permission checks
# Enforces access modes and column-level restrictions
# ============================================================
from __future__ import annotations

from fastapi import HTTPException

from admin_data_access.metadata import (
    AccessMode,
    DeletePolicy,
    TableMeta,
    get_table_meta,
    BLOCKED_TABLES,
)


def check_table_exposed(table_name: str) -> TableMeta:
    """Verify a table is registered and not blocked. Returns its metadata."""
    if table_name in BLOCKED_TABLES:
        raise HTTPException(status_code=403, detail=f"Table '{table_name}' is not accessible")

    meta = get_table_meta(table_name)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' is not registered")

    if meta.access_mode == AccessMode.BLOCKED:
        raise HTTPException(status_code=403, detail=f"Table '{table_name}' is not accessible")

    return meta


def check_access(table_name: str, operation: str) -> TableMeta:
    """
    Verify a table supports the requested operation.
    operation: 'read' | 'create' | 'update' | 'delete'
    Returns the table metadata if allowed.
    """
    meta = check_table_exposed(table_name)

    if operation == "read":
        return meta

    if meta.access_mode == AccessMode.READ_ONLY:
        raise HTTPException(status_code=403, detail=f"Table '{meta.display_name}' is read-only")

    if operation == "create":
        if meta.singleton:
            raise HTTPException(status_code=403, detail=f"Cannot create rows in singleton table '{meta.display_name}'")
        return meta

    if operation == "delete":
        if meta.delete_policy == DeletePolicy.DISALLOW:
            raise HTTPException(status_code=403, detail=f"Deletion is not allowed for '{meta.display_name}'")
        return meta

    return meta


def check_column_allowed(meta: TableMeta, field_name: str, operation: str) -> None:
    """
    Verify a specific column can be written.
    operation: 'create' | 'update'
    Raises HTTPException if the column is hidden, immutable (on update), or unknown.
    """
    col = None
    for c in meta.columns:
        if c.name == field_name:
            col = c
            break

    if col is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown column '{field_name}' for table '{meta.display_name}'"
        )

    if col.hidden:
        raise HTTPException(
            status_code=403,
            detail=f"Column '{field_name}' cannot be written"
        )

    if operation == "update" and col.immutable:
        raise HTTPException(
            status_code=403,
            detail=f"Column '{field_name}' is immutable and cannot be updated"
        )
