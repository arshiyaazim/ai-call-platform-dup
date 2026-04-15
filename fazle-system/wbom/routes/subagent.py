# ============================================================
# WBOM — Subagent API Routes
# Phase 7 §7.1: Integration endpoints for core module
# ============================================================
from fastapi import APIRouter, HTTPException

from database import update_row_no_ts, execute_query
from models import (
    SubagentMessageRequest, SubagentMessageResponse,
    TemplateCompletionRequest, TemplateCompletionResponse,
    FieldValidationRequest, FieldValidationResponse, FieldValidationResult,
)
from services.message_processor import process_incoming_message
from services.validator import validate_fields
from services.core_integration import CoreModuleIntegration
from services.wbom_logger import handle_errors

router = APIRouter(prefix="/subagent/wbom", tags=["subagent"])

core = CoreModuleIntegration()


@router.post("/process-message", response_model=SubagentMessageResponse)
@handle_errors
def subagent_process_message(req: SubagentMessageRequest):
    """Main entry point for message processing from core module."""
    result = process_incoming_message(
        sender_number=req.sender_number,
        message_body=req.message_body,
        whatsapp_msg_id=req.whatsapp_msg_id,
    )

    # Notify core module (fire-and-forget)
    core.notify_message_processed(
        result["message_id"],
        result["classification"],
        result.get("confidence", 0.5),
    )

    return SubagentMessageResponse(
        status="success",
        message_id=result["message_id"],
        classification=result["classification"],
        confidence=result.get("confidence", 0.5),
        template=result.get("suggested_template"),
        requires_admin_input=result.get("unfilled_fields", []),
    )


@router.post("/complete-template", response_model=TemplateCompletionResponse)
@handle_errors
def subagent_complete_template(req: TemplateCompletionRequest):
    """Process admin-completed template and save data."""
    from services.escort_processor import EscortOrderProcessor
    from services.payment_processor import PaymentProcessor

    # Validate the completed template
    processor = EscortOrderProcessor()
    validation = processor.validate_completed_template(req.completed_message)
    if not validation["valid"]:
        raise HTTPException(400, detail={"errors": validation["errors"]})

    # Save to appropriate tables based on message type
    db_result = None
    if req.message_type == "escort_order":
        db_result = processor.save_escort_program(
            message_id=req.message_id,
            extracted_data=req.template_data,
        )
        processor.log_template_generation(
            req.message_id, req.template_id, req.completed_message, was_sent=True,
        )
    elif req.message_type == "payment":
        pay_processor = PaymentProcessor()
        employee = None
        mobile = req.template_data.get("mobile_number")
        if mobile:
            employee = pay_processor.find_employee_by_mobile(mobile)
        if not employee:
            raise HTTPException(400, detail="Employee not found for mobile")
        # Name validation
        extracted_name = req.template_data.get("employee_name", "")
        if extracted_name:
            from difflib import SequenceMatcher
            ratio = SequenceMatcher(
                None,
                extracted_name.lower().strip(),
                employee["employee_name"].lower().strip(),
            ).ratio()
            if ratio < 0.80:
                raise HTTPException(400, detail={
                    "error": "name_mismatch",
                    "extracted": extracted_name,
                    "database": employee["employee_name"],
                    "ratio": round(ratio, 2),
                })
        from decimal import Decimal, InvalidOperation
        amount_str = req.template_data.get("amount", "")
        if not amount_str:
            raise HTTPException(400, detail="Amount is required")
        try:
            amount = Decimal(amount_str)
        except (InvalidOperation, ValueError):
            raise HTTPException(400, detail=f"Invalid amount: {amount_str}")
        if amount <= 0:
            raise HTTPException(400, detail="Amount must be positive")
        db_result = pay_processor.record_cash_transaction(
            employee_id=employee["employee_id"],
            amount=amount,
            payment_method=req.template_data.get("payment_method", "Cash"),
            payment_mobile=mobile,
            message_id=req.message_id,
        )

    # Update message status
    update_row_no_ts("wbom_whatsapp_messages", "message_id", req.message_id, {
        "is_processed": True,
    })

    # Notify core module
    core.log_activity("template_completed", {
        "message_id": req.message_id,
        "message_type": req.message_type,
    })

    return TemplateCompletionResponse(
        status="success",
        database_records=db_result,
    )


@router.get("/contact/{contact_id}/templates")
def get_contact_templates(contact_id: int):
    """Get assigned templates for a contact."""
    templates = execute_query("""
        SELECT t.*, ct.is_default, ct.priority
        FROM wbom_message_templates t
        JOIN wbom_contact_templates ct ON t.template_id = ct.template_id
        WHERE ct.contact_id = %s AND t.is_active = TRUE
        ORDER BY ct.priority DESC
    """, (contact_id,))
    return {"templates": templates}


@router.post("/validate-fields", response_model=FieldValidationResponse)
def validate_data_fields(req: FieldValidationRequest):
    """Validate arbitrary fields against business rules (§6.1)."""
    result = validate_fields(req.fields)
    items = [
        FieldValidationResult(
            field=field,
            valid=info["valid"],
            value=info["value"],
            error=info["error"],
        )
        for field, info in result["results"].items()
    ]
    return FieldValidationResponse(all_valid=result["all_valid"], results=items)


@router.get("/search")
def subagent_search(
    search_type: str,
    query: str,
    limit: int = 20,
):
    """Universal search endpoint for core module."""
    from database import search_rows

    table_map = {
        "programs": ("wbom_escort_programs", "mother_vessel"),
        "employees": ("wbom_employees", "employee_name"),
        "transactions": ("wbom_cash_transactions", "remarks"),
        "contacts": ("wbom_contacts", "display_name"),
    }

    if search_type not in table_map:
        raise HTTPException(400, f"Invalid search_type: {search_type}")

    table, col = table_map[search_type]
    results = search_rows(table, col, query, limit)
    return {"results": results, "total": len(results)}
