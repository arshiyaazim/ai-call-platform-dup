# ============================================================
# WBOM — Escort Program Routes
# CRUD for escort/security program assignments
# ============================================================
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import date

from database import insert_row, get_row, update_row, delete_row, list_rows, search_rows, execute_query, count_rows
from models import ProgramCreate, ProgramUpdate, ProgramResponse

router = APIRouter(prefix="/programs", tags=["programs"])


@router.post("", response_model=ProgramResponse, status_code=201)
def create_program(data: ProgramCreate):
    row = insert_row("wbom_escort_programs", data.model_dump(exclude_none=True))
    return row


@router.get("/count")
def program_count(
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    search: Optional[str] = None,
):
    """Get total count for pagination."""
    conditions = []
    params = []
    if status:
        conditions.append("status = %s")
        params.append(status)
    if date_from:
        conditions.append("program_date >= %s")
        params.append(str(date_from))
    if date_to:
        conditions.append("program_date <= %s")
        params.append(str(date_to))
    if search:
        conditions.append("(mother_vessel ILIKE %s OR lighter_vessel ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = execute_query(f"SELECT COUNT(*) as total FROM wbom_escort_programs {where}", tuple(params))
    return {"total": rows[0]["total"] if rows else 0}


@router.get("/{program_id}", response_model=ProgramResponse)
def get_program(program_id: int):
    row = get_row("wbom_escort_programs", "program_id", program_id)
    if not row:
        raise HTTPException(404, "Program not found")
    return row


@router.put("/{program_id}", response_model=ProgramResponse)
def update_program(program_id: int, data: ProgramUpdate):
    fields = data.model_dump(exclude_none=True)
    row = update_row("wbom_escort_programs", "program_id", program_id, fields)
    if not row:
        raise HTTPException(404, "Program not found")
    return row


@router.delete("/{program_id}")
def remove_program(program_id: int):
    if not delete_row("wbom_escort_programs", "program_id", program_id):
        raise HTTPException(404, "Program not found")
    return {"deleted": True}


@router.get("")
def list_programs(
    status: Optional[str] = None,
    contact_id: Optional[int] = None,
    shift: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    search: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    """List programs: completed first, then ongoing, all sorted by date desc."""
    conditions = []
    params = []
    if status:
        conditions.append("p.status = %s")
        params.append(status)
    if contact_id:
        conditions.append("p.contact_id = %s")
        params.append(contact_id)
    if shift:
        conditions.append("p.shift = %s")
        params.append(shift)
    if date_from:
        conditions.append("p.program_date >= %s")
        params.append(str(date_from))
    if date_to:
        conditions.append("p.program_date <= %s")
        params.append(str(date_to))
    if search:
        conditions.append("(p.mother_vessel ILIKE %s OR p.lighter_vessel ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"""
        SELECT p.*, e.employee_name, e.employee_mobile
        FROM wbom_escort_programs p
        LEFT JOIN wbom_employees e ON p.escort_employee_id = e.employee_id
        {where}
        ORDER BY
            CASE WHEN p.status = 'Completed' THEN 0
                 WHEN p.status = 'Running' THEN 1
                 WHEN p.status = 'Assigned' THEN 2
                 ELSE 3 END,
            p.program_date DESC NULLS LAST
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    return execute_query(sql, tuple(params))


@router.get("/by-employee/{employee_id}")
def programs_by_employee(employee_id: int, limit: int = Query(50, le=200)):
    return execute_query(
        "SELECT p.*, e.employee_name FROM wbom_escort_programs p "
        "LEFT JOIN wbom_employees e ON p.escort_employee_id = e.employee_id "
        "WHERE p.escort_employee_id = %s "
        "ORDER BY CASE WHEN p.status = 'Completed' THEN 0 ELSE 1 END, p.program_date DESC NULLS LAST "
        "LIMIT %s",
        (employee_id, limit),
    )


@router.get("/by-vessel/{vessel_name}")
def programs_by_vessel(vessel_name: str, limit: int = Query(50, le=200)):
    return search_rows("wbom_escort_programs", "mother_vessel", vessel_name, limit)
