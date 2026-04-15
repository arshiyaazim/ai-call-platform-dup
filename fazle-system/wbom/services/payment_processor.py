# ============================================================
# WBOM — Payment Processor
# Phase 5 §5.2: Payment extraction, recording, program completion
# ============================================================
import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from typing import Optional

from database import (
    get_conn, get_row, insert_row, update_row, update_row_no_ts,
    list_rows, search_rows, execute_query, find_row_exact,
)
import psycopg2.extras

logger = logging.getLogger("wbom.payment_processor")

# Minimum name match ratio to accept a payment without admin review
NAME_MATCH_THRESHOLD = 0.80

# Payment method abbreviation mapping
PAYMENT_METHOD_MAP = {
    "B": "Bkash",
    "b": "Bkash",
    "N": "Nagad",
    "n": "Nagad",
    "R": "Rocket",
    "r": "Rocket",
}


class PaymentProcessor:
    """Process payment messages through the WBOM pipeline.

    Steps:
    1. Extract payment data (employee, amount, method, mobile)
    2. Find employee by mobile
    3. Record cash transaction
    4. Complete associated program (if any)
    5. Update salary accruals
    6. Send confirmation
    """

    REQUIRED_FIELDS = [
        "employee_name", "amount", "payment_method", "mobile_number",
    ]

    def process_payment(
        self,
        message_id: int,
        sender_number: str,
        message_body: str,
        contact_id: Optional[int] = None,
    ) -> dict:
        """Full payment processing pipeline.

        Returns processing result with transaction details.
        """
        from services.data_extractor import extract_all_fields

        # Step 1: Extract payment data
        extracted = extract_all_fields(message_body, self.REQUIRED_FIELDS)

        mobile = self._get_field(extracted, "mobile_number")
        amount_str = self._get_field(extracted, "amount")
        method_abbr = self._get_field(extracted, "payment_method")
        emp_name = self._get_field(extracted, "employee_name")

        # Step 2: Find employee by mobile (exact match first)
        employee = None
        if mobile:
            employee = self.find_employee_by_mobile(mobile)

        # Step 2b: Name-match validation
        name_match_ok = True
        name_match_ratio = 0.0
        if employee and emp_name:
            name_match_ratio = SequenceMatcher(
                None,
                emp_name.lower().strip(),
                employee["employee_name"].lower().strip(),
            ).ratio()
            if name_match_ratio < NAME_MATCH_THRESHOLD:
                name_match_ok = False
                logger.warning(
                    "Name mismatch: extracted '%s' vs DB '%s' (ratio=%.2f) for mobile %s",
                    emp_name, employee["employee_name"], name_match_ratio, mobile,
                )

        # Determine transaction type from context
        transaction_type = self.determine_transaction_type(message_body)

        # Expand payment method abbreviation
        payment_method = PAYMENT_METHOD_MAP.get(method_abbr, "Cash")

        # Parse & validate amount
        amount = None
        if amount_str:
            try:
                amount = Decimal(amount_str)
                if amount <= 0 or amount > 100000:
                    logger.warning("Amount out of range: %s (message_id=%s)", amount, message_id)
                    amount = None
            except (InvalidOperation, ValueError):
                logger.warning("Invalid amount '%s' (message_id=%s)", amount_str, message_id)

        # Step 3: Record transaction (if we have enough data AND name validated)
        transaction = None
        if employee and amount and name_match_ok:
            transaction = self.record_cash_transaction(
                employee_id=employee["employee_id"],
                amount=amount,
                payment_method=payment_method,
                payment_mobile=mobile,
                transaction_type=transaction_type,
                message_id=message_id,
            )

            # Step 4: Complete associated program if this is a salary/completion payment
            if transaction_type in ("Salary", "Advance"):
                self._try_complete_program(employee["employee_id"])

        # Build missing/rejected fields list
        missing = []
        if not employee:
            missing.append("employee (mobile not found)")
        if not amount:
            missing.append("amount")
        if not method_abbr:
            missing.append("payment_method")
        if not name_match_ok:
            missing.append(f"name_mismatch (extracted='{emp_name}', db='{employee['employee_name']}', ratio={name_match_ratio:.2f})")

        # Audit log rejected/incomplete payments
        if missing:
            logger.warning(
                "Payment requires admin review (message_id=%s): %s",
                message_id, ", ".join(missing),
            )

        return {
            "message_id": message_id,
            "classification": "payment",
            "extracted_data": extracted,
            "employee": employee,
            "transaction": transaction,
            "transaction_type": transaction_type,
            "payment_method": payment_method,
            "amount": str(amount) if amount else None,
            "name_match_ratio": name_match_ratio,
            "requires_admin_input": bool(missing),
            "missing_fields": missing,
        }

    def find_employee_by_mobile(self, mobile: str) -> Optional[dict]:
        """Find employee by mobile number (exact match).

        Handles leading zero preservation.
        """
        # Normalize: strip spaces/dashes
        mobile = mobile.replace("-", "").replace(" ", "").strip()

        # Exact match first
        row = find_row_exact("wbom_employees", "employee_mobile", mobile)
        if row:
            return row

        # Try with/without leading zero
        if mobile.startswith("0"):
            alt = mobile[1:]
        else:
            alt = "0" + mobile
        row = find_row_exact("wbom_employees", "employee_mobile", alt)
        return row

    def determine_transaction_type(self, message_body: str) -> str:
        """Determine transaction type from message context.

        Returns one of: Advance, Food, Conveyance, Salary, Deduction, Other
        """
        text = message_body.lower()

        type_keywords = {
            "Advance": ["advance", "অগ্রিম", "adv"],
            "Food": ["food", "খাবার", "meal"],
            "Conveyance": ["conveyance", "transport", "যাতায়াত", "conv"],
            "Salary": ["salary", "বেতন", "sal"],
            "Deduction": ["deduction", "কর্তন", "ded", "fine"],
        }

        for tx_type, keywords in type_keywords.items():
            if any(kw in text for kw in keywords):
                return tx_type

        return "Advance"  # Default for payment messages

    def record_cash_transaction(
        self,
        employee_id: int,
        amount: Decimal,
        payment_method: str,
        payment_mobile: Optional[str] = None,
        transaction_type: str = "Advance",
        program_id: Optional[int] = None,
        message_id: Optional[int] = None,
    ) -> dict:
        """Step 3: Record a cash transaction.

        Preserves leading zeros for payment_mobile.
        """
        tx_data = {
            "employee_id": employee_id,
            "transaction_type": transaction_type,
            "amount": amount,
            "payment_method": payment_method,
            "transaction_date": date.today().isoformat(),
            "status": "Completed",
        }
        if payment_mobile:
            tx_data["payment_mobile"] = payment_mobile
        if program_id:
            tx_data["program_id"] = program_id
        if message_id:
            tx_data["whatsapp_message_id"] = str(message_id)

        transaction = insert_row("wbom_cash_transactions", tx_data)
        logger.info(
            "Recorded %s transaction #%s: %s %s for employee %s",
            transaction_type, transaction["transaction_id"],
            amount, payment_method, employee_id,
        )
        return transaction

    def _try_complete_program(self, employee_id: int):
        """Step 4: Complete any Running programs for this employee."""
        running = list_rows(
            "wbom_escort_programs",
            {"escort_employee_id": employee_id, "status": "Running"},
            order_by="program_date DESC",
            limit=1,
        )
        if running:
            program = running[0]
            update_row(
                "wbom_escort_programs", "program_id", program["program_id"],
                {"status": "Completed", "completion_time": datetime.utcnow().isoformat()},
            )
            logger.info("Completed program %s for employee %s",
                         program["program_id"], employee_id)

    # ── Helper ────────────────────────────────────────────────

    @staticmethod
    def _get_field(extracted: dict, field_name: str) -> Optional[str]:
        """Get value from extracted data dict."""
        info = extracted.get(field_name, {})
        if isinstance(info, dict):
            return info.get("value")
        return info
