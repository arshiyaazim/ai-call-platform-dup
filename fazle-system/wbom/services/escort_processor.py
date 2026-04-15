# ============================================================
# WBOM — Escort Order Processor
# Phase 5 §5.1: 7-step workflow for escort order messages
# ============================================================
import logging
import re
from datetime import datetime, date
from typing import Optional

from database import (
    get_conn, get_row, insert_row, update_row, list_rows,
    search_rows, execute_query,
)
import psycopg2.extras

logger = logging.getLogger("wbom.escort_processor")


class EscortOrderProcessor:
    """Process escort order messages through a 7-step pipeline.

    Steps:
    1. Extract vessel/mobile/destination/capacity from message
    2. Select and populate template
    3. Present to admin for review
    4. Validate completed template
    5. Send reply via WhatsApp
    6. Save escort program record
    7. Log the template generation
    """

    def __init__(self):
        from config import settings
        self._cfg = settings

    REQUIRED_FIELDS = [
        "mother_vessel", "lighter_vessel", "mobile_number",
        "destination", "capacity",
    ]

    def process_order(
        self,
        message_id: int,
        sender_number: str,
        message_body: str,
        contact_id: Optional[int] = None,
    ) -> dict:
        """Full escort order processing pipeline.

        Returns dict with template draft, extracted data, and validation status.
        """
        from services.data_extractor import extract_all_fields
        from services.template_engine import (
            select_template_for_contact, generate_template,
        )

        # Step 1: Extract data
        extracted = extract_all_fields(message_body, self.REQUIRED_FIELDS)

        # Step 2: Select and populate template
        template = select_template_for_contact(contact_id, "escort_order")
        draft_reply = None
        unfilled_fields = []
        confidence_scores = {}

        if template:
            result = generate_template(
                template, extracted, {"sender": sender_number}
            )
            draft_reply = result["template"]
            unfilled_fields = result["unfilled_fields"]
            confidence_scores = result["confidence_scores"]

        # Step 3: Determine if admin input is needed
        missing = [
            f for f in self.REQUIRED_FIELDS
            if not extracted.get(f, {}).get("value")
        ]
        requires_admin = bool(missing) or bool(unfilled_fields)

        return {
            "message_id": message_id,
            "classification": "escort_order",
            "extracted_data": extracted,
            "suggested_template": template,
            "draft_reply": draft_reply,
            "requires_admin_input": requires_admin,
            "missing_fields": missing,
            "unfilled_fields": unfilled_fields,
            "confidence_scores": confidence_scores,
        }

    def validate_completed_template(self, template_text: str) -> dict:
        """Step 4: Validate a completed template before sending.

        Checks that all placeholders are filled and required data is present.
        Returns: {valid: bool, errors: list[str]}
        """
        errors = []

        # Check for unfilled placeholders
        unfilled = re.findall(r"\{([^}]+)\}", template_text)
        if unfilled:
            errors.append(f"Unfilled placeholders: {', '.join(unfilled)}")

        # Check for mobile number format
        mobiles = re.findall(r"0\d{10}", template_text)
        for mob in mobiles:
            if len(mob) != 11:
                errors.append(f"Invalid mobile format: {mob}")

        # Check template is not empty/too short
        if len(template_text.strip()) < 20:
            errors.append("Template content too short")

        return {"valid": len(errors) == 0, "errors": errors}

    def save_escort_program(
        self,
        message_id: int,
        extracted_data: dict,
        contact_id: Optional[int] = None,
        admin_overrides: Optional[dict] = None,
    ) -> dict:
        """Step 6: Save escort program record from extracted data.

        Gets or creates employee, then inserts the program record.
        """
        # Merge extracted values with admin overrides
        fields = {}
        for key, info in extracted_data.items():
            val = info.get("value") if isinstance(info, dict) else info
            if val:
                fields[key] = val
        if admin_overrides:
            fields.update(admin_overrides)

        # Get or create employee by mobile
        employee_id = None
        mobile = fields.get("mobile_number")
        if mobile:
            mobile = self._normalize_mobile(mobile)
            employee_id = self._get_or_create_employee(mobile)

        # Determine shift using config thresholds
        now = datetime.now()
        shift = self._cfg.get_shift(now.hour)

        mother_vessel = fields.get("mother_vessel", "").strip()
        lighter_vessel = fields.get("lighter_vessel", "").strip()

        # Reject empty/unknown vessel names
        missing_vessels = []
        if not mother_vessel or mother_vessel.lower() == "unknown":
            missing_vessels.append("mother_vessel")
        if not lighter_vessel or lighter_vessel.lower() == "unknown":
            missing_vessels.append("lighter_vessel")

        if missing_vessels:
            logger.warning(
                "Escort program missing vessel names: %s (message_id=%s)",
                missing_vessels, message_id,
            )
            return {
                "requires_admin_input": True,
                "missing_fields": missing_vessels,
                "message_id": message_id,
            }

        program_data = {
            "mother_vessel": mother_vessel,
            "lighter_vessel": lighter_vessel,
            "master_mobile": mobile or "",
            "destination": fields.get("destination"),
            "escort_employee_id": employee_id,
            "escort_mobile": mobile,
            "program_date": fields.get("date", date.today().isoformat()),
            "shift": fields.get("shift", shift),
            "contact_id": contact_id,
            "status": "Assigned",
        }

        program = insert_row("wbom_escort_programs", program_data)
        logger.info(
            "Saved escort program %s for vessel %s",
            program["program_id"], program_data["mother_vessel"],
        )
        return program

    def log_template_generation(
        self,
        message_id: int,
        template_id: int,
        generated_text: str,
        was_sent: bool = False,
    ) -> dict:
        """Step 7: Log the template generation event."""
        log_data = {
            "message_id": message_id,
            "template_id": template_id,
            "generated_text": generated_text,
            "was_sent": was_sent,
            "generated_at": datetime.utcnow().isoformat(),
        }
        return insert_row("wbom_template_generation_log", log_data)

    # ── Multi-lighter support (Phase 8 §Scenario 3) ──────────

    def process_multi_lighter_order(
        self,
        message_id: int,
        sender_number: str,
        message_body: str,
        contact_id: Optional[int] = None,
    ) -> dict:
        """Process an escort order that contains multiple lighter entries.

        Detects numbered entries, extracts per-lighter data,
        generates a combined template, and returns all data.
        """
        from services.data_extractor import extract_multiple_lighters
        from services.template_engine import (
            select_template_for_contact, generate_multi_lighter_template,
        )

        # Extract shared + per-lighter data
        multi = extract_multiple_lighters(message_body)

        # Select template for the contact
        template = select_template_for_contact(contact_id, "escort_order")

        # Generate combined template
        draft_reply = None
        if template:
            draft_reply = generate_multi_lighter_template(
                template, multi["mother_vessel"], multi["date"], multi["lighters"],
            )

        # Determine which lighter entries have missing fields
        all_missing = []
        for idx, lighter in enumerate(multi["lighters"]):
            entry_missing = [
                f for f in ("lighter_vessel", "mobile_number", "destination", "capacity")
                if not lighter.get(f, {}).get("value")
            ]
            if entry_missing:
                all_missing.append({"lighter_index": idx + 1, "missing": entry_missing})

        return {
            "message_id": message_id,
            "classification": "escort_order",
            "is_multi_lighter": True,
            "lighter_count": multi["lighter_count"],
            "mother_vessel": multi["mother_vessel"],
            "date": multi["date"],
            "lighters": multi["lighters"],
            "suggested_template": template,
            "draft_reply": draft_reply,
            "requires_admin_input": bool(all_missing),
            "missing_by_lighter": all_missing,
        }

    def save_multi_lighter_programs(
        self,
        message_id: int,
        multi_data: dict,
        contact_id: Optional[int] = None,
        admin_overrides: Optional[list] = None,
    ) -> list:
        """Save N separate program records for a multi-lighter message.

        All programs share the same mother_vessel and contact_id.
        Returns list of saved program dicts.
        """
        mother_vessel = multi_data.get("mother_vessel", {}).get("value", "")
        if not mother_vessel or mother_vessel.lower() == "unknown":
            return []  # Cannot save without mother vessel
        program_date = multi_data.get("date", {}).get("value", date.today().isoformat())

        now = datetime.now()
        shift = self._cfg.get_shift(now.hour)

        saved = []
        for idx, lighter in enumerate(multi_data.get("lighters", [])):
            # Apply per-lighter admin overrides if provided
            overrides = {}
            if admin_overrides and idx < len(admin_overrides):
                overrides = admin_overrides[idx] or {}

            mobile = lighter.get("mobile_number", {}).get("value")
            if overrides.get("mobile_number"):
                mobile = overrides["mobile_number"]

            if mobile:
                mobile = self._normalize_mobile(mobile)

            employee_id = None
            if mobile:
                employee_id = self._get_or_create_employee(mobile)

            lighter_vessel = overrides.get(
                "lighter_vessel",
                lighter.get("lighter_vessel", {}).get("value", ""),
            )
            if not lighter_vessel or lighter_vessel.lower() == "unknown":
                logger.warning("Skipping lighter #%d — no vessel name", idx + 1)
                continue

            program_data = {
                "mother_vessel": mother_vessel,
                "lighter_vessel": lighter_vessel,
                "master_mobile": mobile or "",
                "destination": overrides.get(
                    "destination",
                    lighter.get("destination", {}).get("value"),
                ),
                "escort_employee_id": employee_id,
                "escort_mobile": mobile,
                "program_date": program_date,
                "shift": shift,
                "contact_id": contact_id,
                "status": "Assigned",
            }

            program = insert_row("wbom_escort_programs", program_data)
            logger.info(
                "Saved multi-lighter program %s (entry %d) for MV %s lighter %s",
                program["program_id"], idx + 1,
                mother_vessel, program_data["lighter_vessel"],
            )
            saved.append(program)

        return saved

    # ── Helper ────────────────────────────────────────────────

    def _get_or_create_employee(self, mobile: str) -> Optional[int]:
        """Find employee by mobile. Returns None if not found (no auto-creation)."""
        # Normalize mobile
        mobile = self._normalize_mobile(mobile)
        if not mobile:
            return None

        from database import find_row_exact
        row = find_row_exact("wbom_employees", "employee_mobile", mobile)
        if row:
            return row["employee_id"]

        # Try with/without leading zero
        if mobile.startswith("0"):
            alt = mobile[1:]
        else:
            alt = "0" + mobile
        row = find_row_exact("wbom_employees", "employee_mobile", alt)
        if row:
            return row["employee_id"]

        logger.warning("Employee not found for mobile %s — will NOT auto-create", mobile)
        return None

    @staticmethod
    def _normalize_mobile(mobile: str) -> str:
        """Normalize mobile number to 11-digit format starting with 0."""
        if not mobile:
            return ""
        mobile = mobile.replace("-", "").replace(" ", "").replace("+880", "0").strip()
        if not mobile.startswith("0") and len(mobile) == 10:
            mobile = "0" + mobile
        return mobile
