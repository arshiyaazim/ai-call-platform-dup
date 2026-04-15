# ============================================================
# WBOM — Salary Routes
# Auto-generation and management of salary records
# ============================================================
from fastapi import APIRouter, HTTPException

from models import SalaryGenerateRequest, SalaryResponse
from services.salary_generator import generate_salary, get_salary_summary, mark_salary_paid

router = APIRouter(prefix="/salary", tags=["salary"])


@router.post("/generate", response_model=SalaryResponse)
def generate(req: SalaryGenerateRequest):
    record = generate_salary(req.employee_id, req.salary_month, req.rate_per_program)
    return record


@router.get("/summary/{month}")
def summary(month: str):
    rows = get_salary_summary(month)
    total = sum(r.get("net_salary", 0) for r in rows)
    return {"month": month, "records": rows, "total_payable": total}


@router.post("/mark-paid/{salary_id}")
def paid(salary_id: int):
    ok = mark_salary_paid(salary_id)
    if not ok:
        raise HTTPException(404, "Salary record not found")
    return {"paid": True}
