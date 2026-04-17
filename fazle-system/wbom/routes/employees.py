# ============================================================
# WBOM — Employee Routes
# CRUD + search for security personnel
# ============================================================
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from database import insert_row, get_row, update_row, delete_row, list_rows, search_rows, execute_query, count_rows
from models import EmployeeCreate, EmployeeUpdate, EmployeeResponse
from response import api_response, api_single
from openapi_models import EmployeeListResponse, SingleEnvelope

router = APIRouter(prefix="/employees", tags=["employees"])


@router.post("", status_code=201)
def create_employee(data: EmployeeCreate):
    row = insert_row("wbom_employees", data.model_dump(exclude_none=True))
    return api_single(row, entity="employees")


@router.get("/count")
def employee_count(
    status: Optional[str] = None,
    designation: Optional[str] = None,
    search: Optional[str] = None,
):
    """Get total count for pagination."""
    conditions = []
    params = []
    if status:
        conditions.append("status = %s")
        params.append(status)
    if designation:
        conditions.append("designation = %s")
        params.append(designation)
    if search:
        conditions.append("(employee_name ILIKE %s OR employee_mobile ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = execute_query(f"SELECT COUNT(*) as total FROM wbom_employees {where}", tuple(params))
    return {"total": rows[0]["total"] if rows else 0}


@router.get("/search/{query}")
def search_employees(query: str, limit: int = Query(20, le=100)):
    by_name = search_rows("wbom_employees", "employee_name", query, limit)
    by_mobile = search_rows("wbom_employees", "employee_mobile", query, limit)
    seen = set()
    results = []
    for row in by_name + by_mobile:
        if row["employee_id"] not in seen:
            seen.add(row["employee_id"])
            results.append(row)
    return api_response(results[:limit], entity="employees")


@router.get("/by-mobile/{mobile}")
def get_by_mobile(mobile: str):
    rows = search_rows("wbom_employees", "employee_mobile", mobile, 1)
    if not rows:
        raise HTTPException(404, "Employee not found")
    return api_single(rows[0], entity="employees")


@router.get("/{employee_id}")
def get_employee(employee_id: int):
    row = get_row("wbom_employees", "employee_id", employee_id)
    if not row:
        raise HTTPException(404, "Employee not found")
    return api_single(row, entity="employees")


@router.get("/{employee_id}/detail")
def get_employee_detail(employee_id: int):
    """Get employee with all programs and transactions."""
    emp = get_row("wbom_employees", "employee_id", employee_id)
    if not emp:
        raise HTTPException(404, "Employee not found")

    emp["programs"] = execute_query(
        "SELECT * FROM wbom_escort_programs "
        "WHERE escort_employee_id = %s "
        "ORDER BY CASE WHEN status = 'Completed' THEN 0 "
        "              WHEN status = 'Running' THEN 1 ELSE 2 END, "
        "         program_date DESC NULLS LAST",
        (employee_id,),
    )
    emp["transactions"] = execute_query(
        "SELECT * FROM wbom_cash_transactions "
        "WHERE employee_id = %s "
        "ORDER BY transaction_date DESC, transaction_time DESC",
        (employee_id,),
    )
    emp["total_programs"] = len(emp["programs"])
    emp["total_transactions"] = len(emp["transactions"])
    emp["total_amount"] = sum(float(t.get("amount", 0)) for t in emp["transactions"])
    return emp


@router.put("/{employee_id}")
def update_employee(employee_id: int, data: EmployeeUpdate):
    fields = data.model_dump(exclude_none=True)
    row = update_row("wbom_employees", "employee_id", employee_id, fields)
    if not row:
        raise HTTPException(404, "Employee not found")
    return api_single(row, entity="employees")


@router.delete("/{employee_id}")
def remove_employee(employee_id: int):
    if not delete_row("wbom_employees", "employee_id", employee_id):
        raise HTTPException(404, "Employee not found")
    return {"deleted": True}


@router.get("", response_model=EmployeeListResponse)
def list_employees(
    status: Optional[str] = None,
    designation: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    """List employees with optional search, filter, and pagination."""
    if search:
        conditions = ["(employee_name ILIKE %s OR employee_mobile ILIKE %s)"]
        params = [f"%{search}%", f"%{search}%"]
        if status:
            conditions.append("status = %s")
            params.append(status)
        if designation:
            conditions.append("designation = %s")
            params.append(designation)
        where = f"WHERE {' AND '.join(conditions)}"
        sql = f"SELECT * FROM wbom_employees {where} ORDER BY employee_name LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        rows = execute_query(sql, tuple(params))
        total = count_rows("wbom_employees")
        return api_response(rows, entity="employees", total=total)

    filters = {}
    if status:
        filters["status"] = status
    if designation:
        filters["designation"] = designation
    rows = list_rows("wbom_employees", filters, "employee_name", limit, offset)
    total = count_rows("wbom_employees", filters if filters else None)
    return api_response(rows, entity="employees", total=total)
