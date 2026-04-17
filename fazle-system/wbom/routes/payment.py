# ============================================================
# WBOM — Payment Approval Routes
# Staging → Approve → Execute flow with idempotency
# ============================================================
import uuid
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from database import (
    insert_row, insert_row_dedup, get_row, execute_query,
    update_row_no_ts, get_conn, audit_log,
)
from models import (
    PaymentInitiateRequest, PaymentApproveRequest,
    PaymentExecuteResponse, TransactionResponse,
)

router = APIRouter(prefix="/payment", tags=["payment"])


@router.post("/initiate", response_model=PaymentExecuteResponse, status_code=201)
def initiate_payment(data: PaymentInitiateRequest):
    """Create a staged payment (status=pending). Does NOT execute."""
    idem_key = data.idempotency_key or f"pay-{uuid.uuid4().hex[:16]}"

    # Check idempotency on staging table
    existing = execute_query(
        "SELECT * FROM wbom_staging_payments WHERE idempotency_key = %s LIMIT 1",
        (idem_key,),
    )
    if existing:
        row = existing[0]
        return PaymentExecuteResponse(
            staging_id=row["id"],
            status=row.get("status", "pending"),
            message="Duplicate request — existing staging payment returned.",
        )

    # Look up employee for draft message
    emp = get_row("wbom_employees", "employee_id", data.employee_id)
    if not emp:
        raise HTTPException(404, f"Employee {data.employee_id} not found")

    staging_row = insert_row("wbom_staging_payments", {
        "employee_id": data.employee_id,
        "employee_name": emp.get("employee_name", ""),
        "amount": str(data.amount),
        "payment_method": data.payment_method,
        "bkash_number": emp.get("bkash_number") or "",
        "status": "pending",
        "idempotency_key": idem_key,
    })

    audit_log(
        "payment.initiated", actor=data.source or "system",
        entity_type="staging_payment", entity_id=staging_row.get("id"),
        payload={
            "employee_id": data.employee_id,
            "amount": str(data.amount),
            "type": data.transaction_type,
            "idempotency_key": idem_key,
        },
    )

    return PaymentExecuteResponse(
        staging_id=staging_row["id"],
        status="pending",
        message=f"Payment ৳{data.amount} for {emp.get('employee_name', '')} staged. Awaiting approval.",
    )


@router.post("/approve", response_model=PaymentExecuteResponse)
def approve_payment(data: PaymentApproveRequest):
    """Approve a staged payment (sets status=approved)."""
    row = get_row("wbom_staging_payments", "id", data.staging_id)
    if not row:
        raise HTTPException(404, "Staging payment not found")
    if row.get("status") != "pending":
        return PaymentExecuteResponse(
            staging_id=data.staging_id,
            status=row["status"],
            message=f"Payment already {row['status']}.",
        )

    update_row_no_ts("wbom_staging_payments", "id", data.staging_id, {
        "status": "approved",
        "reviewed_by": data.approved_by,
    })

    audit_log(
        "payment.approved", actor=data.approved_by,
        entity_type="staging_payment", entity_id=data.staging_id,
        payload={"amount": str(row.get("amount", 0)), "employee_id": row.get("employee_id")},
    )

    return PaymentExecuteResponse(
        staging_id=data.staging_id,
        status="approved",
        message="Payment approved. Ready to execute.",
    )


@router.post("/execute/{staging_id}", response_model=PaymentExecuteResponse)
def execute_payment(staging_id: int, executed_by: str = Query("system")):
    """Execute an approved staging payment → creates a real transaction."""
    row = get_row("wbom_staging_payments", "id", staging_id)
    if not row:
        raise HTTPException(404, "Staging payment not found")
    if row.get("status") != "approved":
        return PaymentExecuteResponse(
            staging_id=staging_id,
            status=row.get("status", "unknown"),
            message=f"Cannot execute — current status is '{row.get('status')}'.",
        )

    idem_key = row.get("idempotency_key") or f"exec-{staging_id}-{uuid.uuid4().hex[:8]}"
    today = date.today().isoformat()

    # Create the real transaction with idempotency
    tx_data = {
        "employee_id": row["employee_id"],
        "transaction_type": "Advance",  # default; can be extended
        "amount": str(row["amount"]),
        "payment_method": row.get("payment_method", "Bkash"),
        "transaction_date": today,
        "remarks": f"Approved staging #{staging_id}",
        "created_by": executed_by,
        "idempotency_key": idem_key,
        "source": "staging",
        "status": "Completed",
        "approved_by": row.get("reviewed_by", ""),
    }
    tx_row, is_new = insert_row_dedup("wbom_cash_transactions", tx_data, ["idempotency_key"])

    if not is_new:
        # Already executed (double-click protection)
        update_row_no_ts("wbom_staging_payments", "id", staging_id, {"status": "executed"})
        return PaymentExecuteResponse(
            staging_id=staging_id,
            transaction_id=tx_row.get("transaction_id"),
            status="duplicate",
            message="Payment was already executed.",
        )

    # Mark staging as executed and link to transaction
    update_row_no_ts("wbom_staging_payments", "id", staging_id, {
        "status": "executed",
        "final_transaction_id": tx_row.get("transaction_id"),
    })

    audit_log(
        "payment.executed", actor=executed_by,
        entity_type="transaction", entity_id=tx_row.get("transaction_id"),
        payload={
            "staging_id": staging_id,
            "amount": str(row["amount"]),
            "employee_id": row["employee_id"],
            "idempotency_key": idem_key,
        },
    )

    return PaymentExecuteResponse(
        staging_id=staging_id,
        transaction_id=tx_row.get("transaction_id"),
        status="executed",
        message=f"৳{row['amount']} paid to {row.get('employee_name', '')}. Transaction #{tx_row.get('transaction_id')}.",
    )


@router.get("/pending")
def list_pending(limit: int = Query(50, le=200)):
    """List all pending staging payments."""
    from response import api_response
    from openapi_models import PaymentListResponse
    rows = execute_query(
        "SELECT * FROM wbom_staging_payments WHERE status = 'pending' ORDER BY created_at DESC LIMIT %s",
        (limit,),
    )
    return api_response(rows, entity="payments")


@router.post("/reject/{staging_id}", response_model=PaymentExecuteResponse)
def reject_payment(staging_id: int, rejected_by: str = Query("system"), reason: str = Query("")):
    """Reject a staged payment."""
    row = get_row("wbom_staging_payments", "id", staging_id)
    if not row:
        raise HTTPException(404, "Staging payment not found")
    if row.get("status") not in ("pending", "approved"):
        return PaymentExecuteResponse(
            staging_id=staging_id,
            status=row.get("status", "unknown"),
            message=f"Cannot reject — status is '{row.get('status')}'.",
        )
    update_row_no_ts("wbom_staging_payments", "id", staging_id, {
        "status": "rejected",
        "reviewed_by": rejected_by,
    })
    audit_log("payment.rejected", actor=rejected_by,
              entity_type="staging_payment", entity_id=staging_id,
              payload={"reason": reason, "amount": str(row.get("amount", 0))})
    return PaymentExecuteResponse(
        staging_id=staging_id, status="rejected",
        message=f"Payment rejected by {rejected_by}.",
    )
