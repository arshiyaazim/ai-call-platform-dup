# ============================================================
# WBOM — Advanced Search Routes
# Cross-table search across WBOM data
# Smart typeahead, full search with joins, vessel drill-down
# ============================================================
from fastapi import APIRouter, Query
from typing import Optional

from database import execute_query
from models import AdvancedSearchRequest, SearchResult

router = APIRouter(prefix="/search", tags=["search"])


# ── Typeahead suggestions ─────────────────────────────────────

@router.get("/suggest")
def search_suggest(q: str = Query(..., min_length=1), limit: int = Query(8, le=20)):
    """Fast typeahead suggestions grouped by category."""
    pattern = f"%{q}%"
    suggestions = []

    # Employees
    rows = execute_query(
        "SELECT employee_id, employee_name, employee_mobile, designation, status "
        "FROM wbom_employees WHERE employee_name ILIKE %s OR employee_mobile ILIKE %s "
        "ORDER BY employee_name LIMIT %s",
        (pattern, pattern, limit),
    )
    for r in rows:
        suggestions.append({
            "type": "employee",
            "id": r["employee_id"],
            "label": r["employee_name"],
            "sublabel": f"{r['designation']} • {r['employee_mobile']}",
            "status": r["status"],
        })

    # Mother vessels (unique)
    rows = execute_query(
        "SELECT DISTINCT mother_vessel FROM wbom_escort_programs "
        "WHERE mother_vessel ILIKE %s ORDER BY mother_vessel LIMIT %s",
        (pattern, limit),
    )
    for r in rows:
        suggestions.append({
            "type": "vessel",
            "id": None,
            "label": r["mother_vessel"],
            "sublabel": "Mother Vessel",
            "status": None,
        })

    # Lighter vessels (unique)
    rows = execute_query(
        "SELECT DISTINCT lighter_vessel FROM wbom_escort_programs "
        "WHERE lighter_vessel ILIKE %s AND lighter_vessel IS NOT NULL "
        "ORDER BY lighter_vessel LIMIT %s",
        (pattern, limit),
    )
    for r in rows:
        suggestions.append({
            "type": "lighter",
            "id": None,
            "label": r["lighter_vessel"],
            "sublabel": "Lighter Vessel",
            "status": None,
        })

    return suggestions[:limit]


# ── Full search with joins ────────────────────────────────────

@router.get("/full")
def full_search(
    q: str = Query(..., min_length=1),
    type: Optional[str] = Query(None, description="employee|vessel|lighter|all"),
):
    """Comprehensive search with joined data for employee detail or vessel drill-down."""
    pattern = f"%{q}%"
    result = {"query": q, "type": type or "all", "employees": [], "vessel_programs": []}

    # ── Employee search with programs + transactions ──
    if type in (None, "all", "employee"):
        employees = execute_query(
            "SELECT * FROM wbom_employees "
            "WHERE employee_name ILIKE %s OR employee_mobile ILIKE %s "
            "ORDER BY employee_name LIMIT 20",
            (pattern, pattern),
        )
        for emp in employees:
            eid = emp["employee_id"]
            emp["programs"] = execute_query(
                "SELECT p.*, e.employee_name "
                "FROM wbom_escort_programs p "
                "LEFT JOIN wbom_employees e ON p.escort_employee_id = e.employee_id "
                "WHERE p.escort_employee_id = %s "
                "ORDER BY "
                "  CASE WHEN p.status = 'Completed' THEN 0 "
                "       WHEN p.status = 'Running' THEN 1 "
                "       WHEN p.status = 'Assigned' THEN 2 "
                "       ELSE 3 END, "
                "  p.program_date DESC NULLS LAST",
                (eid,),
            )
            emp["transactions"] = execute_query(
                "SELECT * FROM wbom_cash_transactions "
                "WHERE employee_id = %s "
                "ORDER BY transaction_date DESC, transaction_time DESC "
                "LIMIT 50",
                (eid,),
            )
            emp["total_programs"] = len(emp["programs"])
            emp["total_transactions"] = len(emp["transactions"])
            emp["total_amount"] = sum(
                float(t.get("amount", 0)) for t in emp["transactions"]
            )
        result["employees"] = employees

    # ── Vessel search (mother or lighter) → show all related programs ──
    if type in (None, "all", "vessel", "lighter"):
        vessel_programs = execute_query(
            "SELECT p.*, e.employee_name, e.employee_mobile, e.designation "
            "FROM wbom_escort_programs p "
            "LEFT JOIN wbom_employees e ON p.escort_employee_id = e.employee_id "
            "WHERE p.mother_vessel ILIKE %s OR p.lighter_vessel ILIKE %s "
            "ORDER BY "
            "  CASE WHEN p.status = 'Completed' THEN 0 "
            "       WHEN p.status = 'Running' THEN 1 "
            "       WHEN p.status = 'Assigned' THEN 2 "
            "       ELSE 3 END, "
            "  p.program_date DESC NULLS LAST "
            "LIMIT 200",
            (pattern, pattern),
        )
        result["vessel_programs"] = vessel_programs

    return result


# ── Legacy POST endpoint ──────────────────────────────────────

@router.post("", response_model=SearchResult)
def advanced_search(req: AdvancedSearchRequest):
    results: dict = {}
    q = f"%{req.query}%"
    limit = req.limit or 20

    if not req.tables or "contacts" in req.tables:
        rows = execute_query(
            "SELECT * FROM wbom_contacts WHERE display_name ILIKE %s OR whatsapp_number ILIKE %s OR company_name ILIKE %s LIMIT %s",
            (q, q, q, limit),
        )
        if rows:
            results["contacts"] = rows

    if not req.tables or "employees" in req.tables:
        rows = execute_query(
            "SELECT * FROM wbom_employees WHERE employee_name ILIKE %s OR employee_mobile ILIKE %s LIMIT %s",
            (q, q, limit),
        )
        if rows:
            results["employees"] = rows

    if not req.tables or "programs" in req.tables:
        rows = execute_query(
            "SELECT * FROM wbom_escort_programs WHERE mother_vessel ILIKE %s OR lighter_vessel ILIKE %s OR master_mobile ILIKE %s LIMIT %s",
            (q, q, q, limit),
        )
        if rows:
            results["programs"] = rows

    if not req.tables or "transactions" in req.tables:
        rows = execute_query(
            "SELECT t.*, e.employee_name FROM wbom_cash_transactions t "
            "LEFT JOIN wbom_employees e ON t.employee_id = e.employee_id "
            "WHERE e.employee_name ILIKE %s OR t.remarks ILIKE %s LIMIT %s",
            (q, q, limit),
        )
        if rows:
            results["transactions"] = rows

    total = sum(len(v) for v in results.values())
    return SearchResult(query=req.query, total=total, results=results)


@router.get("")
def quick_search(q: str = Query(..., min_length=1), limit: int = Query(20, le=100)):
    req = AdvancedSearchRequest(query=q, limit=limit)
    return advanced_search(req)
