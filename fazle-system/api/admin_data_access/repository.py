# ============================================================
# Admin Data Access — Generic Repository
# Metadata-driven CRUD operations with parameterized SQL
# ============================================================
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Optional

import psycopg2.extras

from admin_data_access.core import get_conn
from admin_data_access.metadata import (
    AccessMode,
    DeletePolicy,
    TableMeta,
    get_table_meta,
)
from admin_data_access.permissions import check_access, check_column_allowed

logger = logging.getLogger("fazle-api")


def _serialize_row(row: dict, meta: TableMeta) -> dict:
    """Serialize a database row for JSON output, applying masking and hiding."""
    hidden = {c.name for c in meta.columns if c.hidden}
    masked = {c.name for c in meta.columns if c.masked}

    result = {}
    for k, v in row.items():
        if k in hidden:
            continue
        if k in masked:
            result[k] = "***"
            continue
        if isinstance(v, uuid.UUID):
            result[k] = str(v)
        elif isinstance(v, datetime):
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result


def _writable_columns(meta: TableMeta, operation: str) -> set[str]:
    """Return the set of column names that can be written for create or update."""
    result = set()
    for col in meta.columns:
        if col.hidden:
            continue
        if col.immutable and operation == "update":
            continue
        if col.immutable and operation == "create" and col.name == meta.primary_key:
            continue
        result.add(col.name)
    return result


def _validate_field_value(meta: TableMeta, field_name: str, value: Any) -> Any:
    """Basic validation of a field value against column metadata."""
    col = None
    for c in meta.columns:
        if c.name == field_name:
            col = c
            break
    if col is None:
        return value

    if col.enum_values and value is not None:
        if str(value) not in col.enum_values:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=400,
                detail=f"Invalid value '{value}' for {col.display_name}. "
                       f"Allowed: {', '.join(col.enum_values)}"
            )

    if col.max_length and isinstance(value, str) and len(value) > col.max_length:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=f"{col.display_name} exceeds maximum length of {col.max_length}"
        )

    if col.col_type == "json" and isinstance(value, (dict, list)):
        return json.dumps(value)

    return value


class MaintenanceRepository:
    """Generic CRUD operations driven by the metadata registry."""

    @staticmethod
    def list_rows(
        table_name: str,
        search: Optional[str] = None,
        page: int = 1,
        per_page: int = 50,
        sort_by: Optional[str] = None,
        sort_dir: str = "asc",
    ) -> dict:
        """List rows with pagination, search, and sorting."""
        meta = check_access(table_name, "read")

        # Build SELECT (exclude hidden columns)
        visible_cols = [c.name for c in meta.columns if not c.hidden]
        select = ", ".join(visible_cols)

        params: list[Any] = []
        where_clauses: list[str] = []

        # Search across searchable columns
        if search:
            searchable = [c.name for c in meta.columns if c.searchable]
            if searchable:
                search_parts = []
                for col_name in searchable:
                    search_parts.append(f"CAST({col_name} AS TEXT) ILIKE %s")
                    params.append(f"%{search}%")
                where_clauses.append(f"({' OR '.join(search_parts)})")

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        # Sorting
        if sort_by and sort_by in {c.name for c in meta.columns if not c.hidden}:
            direction = "DESC" if sort_dir.lower() == "desc" else "ASC"
            order_sql = f"ORDER BY {sort_by} {direction}"
        else:
            order_sql = f"ORDER BY {meta.order_by}"

        # Count total
        count_sql = f"SELECT COUNT(*) FROM {meta.table_name} {where_sql}"

        # Paginate
        offset = (page - 1) * per_page
        data_sql = f"SELECT {select} FROM {meta.table_name} {where_sql} {order_sql} LIMIT %s OFFSET %s"
        data_params = params + [per_page, offset]

        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(count_sql, params or None)
                total = cur.fetchone()["count"]

                cur.execute(data_sql, data_params)
                rows = [_serialize_row(dict(r), meta) for r in cur.fetchall()]

        return {
            "rows": rows,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": max(1, (total + per_page - 1) // per_page),
        }

    @staticmethod
    def get_row(table_name: str, row_id: str) -> dict | None:
        """Get a single row by primary key."""
        meta = check_access(table_name, "read")
        visible_cols = [c.name for c in meta.columns if not c.hidden]
        select = ", ".join(visible_cols)

        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"SELECT {select} FROM {meta.table_name} WHERE {meta.primary_key} = %s",
                    (row_id,),
                )
                row = cur.fetchone()
                return _serialize_row(dict(row), meta) if row else None

    @staticmethod
    def create_row(table_name: str, data: dict) -> dict:
        """Insert a new row. Validates against metadata."""
        meta = check_access(table_name, "create")
        writable = _writable_columns(meta, "create")

        # Filter to allowed columns and validate
        insert_data = {}
        for field_name, value in data.items():
            check_column_allowed(meta, field_name, "create")
            if field_name not in writable:
                continue
            insert_data[field_name] = _validate_field_value(meta, field_name, value)

        # Check required fields
        for col in meta.columns:
            if col.required and col.name not in insert_data and col.default is None and col.name != meta.primary_key:
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required field: {col.display_name}"
                )

        if not insert_data:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="No valid fields provided")

        columns = list(insert_data.keys())
        placeholders = ", ".join(["%s"] * len(columns))
        col_sql = ", ".join(columns)
        values = list(insert_data.values())

        visible_cols = [c.name for c in meta.columns if not c.hidden]
        returning = ", ".join(visible_cols)

        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"INSERT INTO {meta.table_name} ({col_sql}) VALUES ({placeholders}) RETURNING {returning}",
                    values,
                )
                conn.commit()
                row = cur.fetchone()
                return _serialize_row(dict(row), meta)

    @staticmethod
    def update_row(table_name: str, row_id: str, data: dict) -> dict | None:
        """Update an existing row. Validates against metadata."""
        meta = check_access(table_name, "update")
        writable = _writable_columns(meta, "update")

        update_data = {}
        for field_name, value in data.items():
            if value is None:
                continue
            check_column_allowed(meta, field_name, "update")
            if field_name not in writable:
                continue
            update_data[field_name] = _validate_field_value(meta, field_name, value)

        if not update_data:
            return MaintenanceRepository.get_row(table_name, row_id)

        # Add updated_at if the table has it
        has_updated_at = any(c.name == "updated_at" for c in meta.columns)
        if has_updated_at:
            update_data["updated_at"] = datetime.utcnow()

        set_clause = ", ".join(f"{k} = %s" for k in update_data)
        values = list(update_data.values()) + [row_id]

        visible_cols = [c.name for c in meta.columns if not c.hidden]
        returning = ", ".join(visible_cols)

        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"UPDATE {meta.table_name} SET {set_clause} WHERE {meta.primary_key} = %s RETURNING {returning}",
                    values,
                )
                conn.commit()
                row = cur.fetchone()
                return _serialize_row(dict(row), meta) if row else None

    @staticmethod
    def delete_row(table_name: str, row_id: str) -> bool:
        """Delete or archive a row based on table policy."""
        meta = check_access(table_name, "delete")

        with get_conn() as conn:
            with conn.cursor() as cur:
                if meta.delete_policy == DeletePolicy.SOFT_DELETE:
                    cur.execute(
                        f"UPDATE {meta.table_name} SET is_active = false, updated_at = NOW() "
                        f"WHERE {meta.primary_key} = %s",
                        (row_id,),
                    )
                elif meta.delete_policy == DeletePolicy.ARCHIVE:
                    cur.execute(
                        f"UPDATE {meta.table_name} SET status = 'archived', updated_at = NOW() "
                        f"WHERE {meta.primary_key} = %s",
                        (row_id,),
                    )
                else:
                    cur.execute(
                        f"DELETE FROM {meta.table_name} WHERE {meta.primary_key} = %s",
                        (row_id,),
                    )
                conn.commit()
                return cur.rowcount > 0
