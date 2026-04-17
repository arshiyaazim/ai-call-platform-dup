# ============================================================
# WBOM — Cash Transaction Routes
# CRUD + daily summary for cash flow tracking
# ============================================================
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import date

from database import insert_row, insert_row_dedup, get_row, delete_row, list_rows, execute_query, audit_log
from models import TransactionCreate, TransactionResponse
from response import api_response, api_single
from openapi_models import TransactionListResponse, SingleEnvelope

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("", status_code=201)
def create_transaction(data: TransactionCreate):
    payload = data.model_dump(exclude_none=True)

    # Idempotency: if key provided, use dedup insert
    if data.idempotency_key:
        row, is_new = insert_row_dedup(
            "wbom_cash_transactions", payload, ["idempotency_key"],
        )
        if not is_new:
            # Duplicate — return existing without creating a new one
            audit_log("transaction.duplicate_blocked", actor=data.created_by or "system",
                      entity_type="transaction", payload={"idempotency_key": data.idempotency_key})
            return row
    else:
        row = insert_row("wbom_cash_transactions", payload)

    audit_log("transaction.created", actor=data.created_by or "system",
              entity_type="transaction", entity_id=row.get("transaction_id"),
              payload={"amount": str(data.amount), "type": data.transaction_type,
                       "employee_id": data.employee_id, "source": data.source})
    return api_single(row, entity="transactions")


@router.get("/count")
def transaction_count(
    transaction_type: Optional[str] = None,
    payment_method: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    search: Optional[str] = None,
):
    """Get total count for pagination."""
    conditions = []
    params = []
    joins = ""
    if search:
        joins = "LEFT JOIN wbom_employees e ON t.employee_id = e.employee_id"
        conditions.append("(e.employee_name ILIKE %s OR t.remarks ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    if transaction_type:
        conditions.append("t.transaction_type = %s")
        params.append(transaction_type)
    if payment_method:
        conditions.append("t.payment_method = %s")
        params.append(payment_method)
    if date_from:
        conditions.append("t.transaction_date >= %s")
        params.append(str(date_from))
    if date_to:
        conditions.append("t.transaction_date <= %s")
        params.append(str(date_to))
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = execute_query(
        f"SELECT COUNT(*) as total FROM wbom_cash_transactions t {joins} {where}",
        tuple(params),
    )
    return {"total": rows[0]["total"] if rows else 0}


@router.get("/daily-summary/{day}")
def daily_summary(day: date):
    sql = """
        SELECT
            transaction_type,
            payment_method,
            COUNT(*) AS count,
            COALESCE(SUM(amount), 0) AS total
        FROM wbom_cash_transactions
        WHERE transaction_date = %s
        GROUP BY transaction_type, payment_method
        ORDER BY transaction_type, payment_method
    """
    rows = execute_query(sql, (str(day),))
    income = sum(r["total"] for r in rows if r["transaction_type"] == "Income")
    expense = sum(r["total"] for r in rows if r["transaction_type"] == "Expense")
    return {"date": str(day), "breakdown": rows, "total_income": income, "total_expense": expense, "net": income - expense}


@router.get("/by-employee/{employee_id}")
def transactions_by_employee(employee_id: int, limit: int = Query(50, le=200)):
    rows = execute_query(
        "SELECT t.*, e.employee_name FROM wbom_cash_transactions t "
        "LEFT JOIN wbom_employees e ON t.employee_id = e.employee_id "
        "WHERE t.employee_id = %s ORDER BY t.transaction_date DESC, t.transaction_time DESC LIMIT %s",
        (employee_id, limit),
    )
    return api_response(rows, entity="transactions")


@router.get("/{transaction_id}")
def get_transaction(transaction_id: int):
    row = get_row("wbom_cash_transactions", "transaction_id", transaction_id)
    if not row:
        raise HTTPException(404, "Transaction not found")
    return api_single(row, entity="transactions")


@router.put("/{transaction_id}")
def update_transaction_status(
    transaction_id: int,
    status: str = Query(..., pattern=r"^(Pending|Completed|Failed)$"),
    approved_by: Optional[str] = None,
):
    """Update transaction status (Pending → Completed or Failed)."""
    from database import update_row_no_ts
    update_data: dict = {"status": status}
    if approved_by:
        from datetime import datetime as _dt
        update_data["approved_by"] = approved_by
        update_data["approved_at"] = _dt.now().isoformat()
    row = update_row_no_ts("wbom_cash_transactions", "transaction_id", transaction_id, update_data)
    if not row:
        raise HTTPException(404, "Transaction not found")
    audit_log("transaction.status_updated", actor=approved_by or "system",
              entity_type="transaction", entity_id=transaction_id,
              payload={"new_status": status})
    return row


@router.delete("/{transaction_id}")
def remove_transaction(transaction_id: int):
    existing = get_row("wbom_cash_transactions", "transaction_id", transaction_id)
    if not existing:
        raise HTTPException(404, "Transaction not found")
    if not delete_row("wbom_cash_transactions", "transaction_id", transaction_id):
        raise HTTPException(404, "Transaction not found")
    audit_log("transaction.deleted", entity_type="transaction", entity_id=transaction_id,
              payload={"amount": str(existing.get("amount", 0)), "employee_id": existing.get("employee_id")})
    return {"deleted": True}


@router.get("", response_model=TransactionListResponse)
def list_transactions(
    transaction_type: Optional[str] = None,
    payment_method: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    search: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    """List transactions with employee name join, date range, and search."""
    conditions = []
    params = []
    joins = "LEFT JOIN wbom_employees e ON t.employee_id = e.employee_id"
    if transaction_type:
        conditions.append("t.transaction_type = %s")
        params.append(transaction_type)
    if payment_method:
        conditions.append("t.payment_method = %s")
        params.append(payment_method)
    if date_from:
        conditions.append("t.transaction_date >= %s")
        params.append(str(date_from))
    if date_to:
        conditions.append("t.transaction_date <= %s")
        params.append(str(date_to))
    if search:
        conditions.append("(e.employee_name ILIKE %s OR t.remarks ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"""
        SELECT t.*, e.employee_name, e.employee_mobile
        FROM wbom_cash_transactions t {joins}
        {where}
        ORDER BY t.transaction_date DESC, t.transaction_time DESC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    rows = execute_query(sql, tuple(params))
    # Get total count for pagination
    count_conditions = list(conditions)  # reuse same filters
    count_params = list(params[:-2])  # strip limit/offset
    count_where = f"WHERE {' AND '.join(count_conditions)}" if count_conditions else ""
    total_rows = execute_query(
        f"SELECT COUNT(*) as total FROM wbom_cash_transactions t {joins} {count_where}",
        tuple(count_params),
    )
    total = total_rows[0]["total"] if total_rows else len(rows)
    return api_response(rows, entity="transactions", total=total)
