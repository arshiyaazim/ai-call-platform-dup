# ============================================================
# WBOM — Data Validator
# Phase 6 §6.1: Field-level validation with business rules
# ============================================================
import logging
import re
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

logger = logging.getLogger("wbom.validator")

VALIDATION_RULES = {
    "mobile_number": {
        "regex": r"^0\d{10}$",
        "preserve_leading_zero": True,
        "error_message": "Mobile number must be 11 digits starting with 0",
    },
    "vessel_name": {
        "max_length": 100,
        "allowed_chars": r"^[A-Za-z0-9\u0980-\u09FF\s\.\-]+$",
        "error_message": "Vessel name contains invalid characters",
    },
    "amount": {
        "regex": r"^\d+(\.\d{1,2})?$",
        "min_value": 0,
        "max_value": 100000,
        "type": "decimal",
        "error_message": "Amount must be a valid number",
    },
    "date": {
        "format": "%d.%m.%Y",
        "min_date": "2020-01-01",
        "max_date_offset_days": 365,
        "error_message": "Invalid date format or out of range",
    },
    "employee_name": {
        "min_length": 2,
        "max_length": 100,
        "regex": r"^[A-Za-z\u0980-\u09FF\s\.\-']+$",
        "error_message": "Employee name must contain only letters",
    },
}


def format_mobile(value: str) -> str:
    """Ensure mobile number has leading zero."""
    if not value.startswith("0") and len(value) == 10:
        return "0" + value
    return value


def normalize_vessel(value: str) -> str:
    """Collapse extra whitespace in vessel names."""
    return " ".join(value.split())


def validate_field(
    field_name: str, value: str
) -> tuple[bool, str, Optional[str]]:
    """Validate a single field against business rules.

    Returns: (is_valid, formatted_value, error_message_or_None)
    """
    if field_name not in VALIDATION_RULES:
        return True, value, None

    rules = VALIDATION_RULES[field_name]

    # ── Format / normalise first ──────────────────────────────
    if field_name == "mobile_number" and rules.get("preserve_leading_zero"):
        value = format_mobile(value)

    if field_name in ("vessel_name", "mother_vessel", "lighter_vessel"):
        value = normalize_vessel(value)

    # ── Length checks ─────────────────────────────────────────
    if "min_length" in rules and len(value) < rules["min_length"]:
        return False, value, f"Minimum length is {rules['min_length']}"
    if "max_length" in rules and len(value) > rules["max_length"]:
        return False, value, f"Maximum length is {rules['max_length']}"

    # ── Regex check ───────────────────────────────────────────
    if "regex" in rules and not re.match(rules["regex"], str(value)):
        return False, value, rules["error_message"]

    # ── Allowed chars (for vessel) ────────────────────────────
    if "allowed_chars" in rules and not re.match(rules["allowed_chars"], str(value)):
        return False, value, rules["error_message"]

    # ── Type conversion ───────────────────────────────────────
    if rules.get("type") == "decimal":
        try:
            dec_val = Decimal(value)
        except (InvalidOperation, ValueError):
            return False, value, rules["error_message"]
        value = str(dec_val)

    # ── Range checks ──────────────────────────────────────────
    if "min_value" in rules:
        try:
            if float(value) < rules["min_value"]:
                return False, value, f"Value must be at least {rules['min_value']}"
        except ValueError:
            return False, value, rules["error_message"]

    if "max_value" in rules:
        try:
            if float(value) > rules["max_value"]:
                return False, value, f"Value must not exceed {rules['max_value']}"
        except ValueError:
            return False, value, rules["error_message"]

    # ── Date validation ───────────────────────────────────────
    if field_name == "date":
        parsed = None
        for fmt in ("%d.%m.%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(value, fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            return False, value, rules["error_message"]
        min_dt = datetime.strptime(rules["min_date"], "%Y-%m-%d")
        max_dt = datetime.now() + timedelta(days=rules["max_date_offset_days"])
        if parsed < min_dt or parsed > max_dt:
            return False, value, rules["error_message"]

    return True, value, None


def validate_fields(data: dict) -> dict:
    """Validate multiple fields at once.

    Args:
        data: dict of {field_name: value}

    Returns:
        {
            "all_valid": bool,
            "results": {field_name: {valid, value, error}}
        }
    """
    results = {}
    all_valid = True

    for field_name, value in data.items():
        if value is None:
            results[field_name] = {"valid": True, "value": None, "error": None}
            continue

        is_valid, formatted, error = validate_field(field_name, str(value))
        results[field_name] = {
            "valid": is_valid,
            "value": formatted,
            "error": error,
        }
        if not is_valid:
            all_valid = False

    return {"all_valid": all_valid, "results": results}
