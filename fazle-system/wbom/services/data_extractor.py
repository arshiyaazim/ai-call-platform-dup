# ============================================================
# WBOM — Data Extraction Engine
# Multi-pattern extraction with confidence scoring
# Phase 3: AI Processing Logic §3.2
# ============================================================
import logging
import re
from typing import Optional

from database import list_rows

logger = logging.getLogger("wbom.data_extractor")

# ── Extraction patterns (Phase 3 spec §3.2) ──────────────────

EXTRACTION_PATTERNS = {
    "mother_vessel": [
        r"(?i)m\.?v\.?\s*([a-zA-Z0-9\u0980-\u09FF\s\-\.]+?)(?=\s*(?:/|lighter|capacity|cap|mob|\n|dest|a/c))",
        r"(?i)(?:mother\s*vessel|m\s*v|এমভি)[:\s]*([a-zA-Z0-9\u0980-\u09FF\s\-\.]+?)(?=\s*lighter|\n)",
    ],
    "lighter_vessel": [
        r"(?i)(?:lighter[:\s]*|mv[:\.\s]+)([a-zA-Z0-9\u0980-\u09FF\s\-\.]+?)(?=\s*(?:cap|capacity|mob|dest|\d{10,}|m\.?t))",
        r"(?i)\d+[.)]\s*(?:mv\s*)?([a-zA-Z0-9\u0980-\u09FF\s\-\.]+?)(?=\s*(?:cap|mob|dest|\d{10,}|m\.?t))",
    ],
    "mobile_number": [
        r"\b(0\d{10})\b",
        r"\+880(0?\d{10})\b",
        r"(?:mob|mobile|m\s*no)[:\s]*(0\d{10})",
    ],
    "destination": [
        r"(?i)(?:dest|destination|place)[:\s]*([a-z\s\-\.]+?)(?=\s*(?:mob|capacity|a/c|\n))",
        r"(?i)(?:at|to)[:\s]*([a-z\s\-\.]+?)(?=\s*(?:mob|capacity|a/c|\n))",
    ],
    "capacity": [
        r"(?i)capacity[:\s]*(\d+)\s*m\.?t",
        r"(?i)cap[:\s]*(\d+)\s*m\.?t",
        r"(\d+)\s*m\.?t",
    ],
    "employee_name": [
        r"(?:ID:\s*\d+\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*?)(?=\s*\d{10,}|\s*SG|\s*MAX|\s*\()",
    ],
    "amount": [
        r"(\d+)/-",
        r"(\d+)\s*tk",
        r"(?:amount|amt)[:\s]*(\d+)",
    ],
    "payment_method": [
        r"\(([BbNnRr])\)",
    ],
    "date": [
        r"(\d{2}[-/.]\d{2}[-/.]\d{2,4})",
        r"(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})",
    ],
}


def extract_data_from_message(message_text: str, field_name: str) -> tuple[Optional[str], float]:
    """Extract specific field from message using multiple patterns (Phase 3 §3.2).

    Returns: (extracted_value, confidence_score)
    """
    if field_name not in EXTRACTION_PATTERNS:
        return None, 0.0

    patterns = EXTRACTION_PATTERNS[field_name]
    results = []

    for pattern in patterns:
        matches = re.findall(pattern, message_text, re.IGNORECASE)
        if matches:
            for match in matches:
                value = match if isinstance(match, str) else (match[0] if match[0] else match[1])
                value = value.strip()

                # Normalize mobile numbers to 11-digit format
                if field_name == "mobile_number":
                    value = value.replace("-", "").replace(" ", "").replace("+880", "0")
                    if not value.startswith("0") and len(value) == 10:
                        value = "0" + value
                    # Validate: must be exactly 11 digits starting with 0
                    if not re.match(r"^0\d{10}$", value):
                        continue

                results.append(value)

    if results:
        # Return most common result; confidence = fraction of patterns that matched
        most_common = max(set(results), key=results.count)
        matches_count = results.count(most_common)
        confidence = min(matches_count / max(len(patterns), 1), 1.0)
        return most_common, confidence

    return None, 0.0


def extract_all_fields(message_text: str, required_fields: list[str]) -> dict:
    """Extract all required fields from message (Phase 3 §3.2).

    Returns: dict with field_name → {value, confidence, verified}
    """
    extracted = {}

    for field in required_fields:
        value, confidence = extract_data_from_message(message_text, field)
        extracted[field] = {
            "value": value,
            "confidence": confidence,
            "verified": False,
        }

    # Also try template-specific patterns from database
    _apply_template_patterns(message_text, extracted)

    return extracted


def _apply_template_patterns(body: str, extracted: dict):
    """Apply template-specific extraction patterns from database."""
    try:
        templates = list_rows("wbom_message_templates", {"is_active": True})
        for tpl in templates:
            patterns = tpl.get("extraction_patterns")
            if not patterns or not isinstance(patterns, dict):
                continue
            for field_name, pattern in patterns.items():
                if field_name in extracted and extracted[field_name].get("value"):
                    continue
                try:
                    match = re.search(pattern, body, re.IGNORECASE)
                    if match:
                        extracted[field_name] = {
                            "value": match.group(1) if match.groups() else match.group(0),
                            "confidence": 0.75,
                            "verified": False,
                            "source": f"template:{tpl['template_id']}",
                        }
                except re.error:
                    pass
    except Exception as e:
        logger.debug(f"Template pattern extraction failed: {e}")


# ── Multi-lighter extraction (Phase 8 §Scenario 3) ───────────

# Patterns that identify numbered lighter entries in a single message
_MULTI_LIGHTER_SPLIT = re.compile(
    r"(?:^|\n)\s*(\d{1,2})[.)]\s*",
    re.MULTILINE,
)

# Per-entry extraction patterns
_ENTRY_PATTERNS = {
    "lighter_vessel": [
        r"(?i)(?:mv[:\.\s]+|lighter[:\s]*)([a-zA-Z0-9\u0980-\u09FF\s\-\.]+?)(?=\s*(?:cap|mob|dest|\d{10,}|m\.?t))",
        r"(?i)([a-zA-Z\u0980-\u09FF][a-zA-Z0-9\u0980-\u09FF\s\-\.]+?)(?=\s*(?:cap|mob|dest|\d{10,}|m\.?t))",
    ],
    "capacity": [
        r"(?i)cap(?:acity)?[:\s]*(\d+)\s*m\.?t",
        r"(\d+)\s*m\.?t",
    ],
    "destination": [
        r"(?i)dest(?:ination)?[:\s]*([a-z\s\-\.]+?)(?=\s*(?:mob|cap|\d{10,}|\n|$))",
    ],
    "mobile_number": [
        r"(?:mob[:\s]*)?(\d{5}[-\s]?\d{6})",
        r"\b(0\d{10})\b",
    ],
}


def detect_multi_lighter(message_text: str) -> bool:
    """Check if a message contains multiple numbered lighter entries."""
    matches = _MULTI_LIGHTER_SPLIT.findall(message_text)
    return len(matches) >= 2


def extract_multiple_lighters(message_text: str) -> dict:
    """Extract data for each lighter from a multi-lighter message.

    Returns:
        {
            "mother_vessel": {value, confidence},
            "date": {value, confidence},
            "lighter_count": int,
            "lighters": [
                {
                    "lighter_vessel": {value, confidence},
                    "capacity": {value, confidence},
                    "destination": {value, confidence},
                    "mobile_number": {value, confidence},
                },
                ...
            ]
        }
    """
    # Extract shared fields from the header (before first numbered entry)
    first_num = _MULTI_LIGHTER_SPLIT.search(message_text)
    header = message_text[:first_num.start()] if first_num else message_text

    mother_vessel_val, mother_vessel_conf = extract_data_from_message(header, "mother_vessel")
    date_val, date_conf = extract_data_from_message(message_text, "date")

    # Split message into numbered entries
    parts = _MULTI_LIGHTER_SPLIT.split(message_text)
    # parts = [header, "1", entry1_text, "2", entry2_text, ...]
    entries = []
    i = 1  # skip header (index 0)
    while i < len(parts) - 1:
        _num = parts[i]       # entry number
        entry_text = parts[i + 1]  # entry body
        entry_data = _extract_entry_fields(entry_text)
        entries.append(entry_data)
        i += 2

    return {
        "mother_vessel": {"value": mother_vessel_val, "confidence": mother_vessel_conf},
        "date": {"value": date_val, "confidence": date_conf},
        "lighter_count": len(entries),
        "lighters": entries,
    }


def _extract_entry_fields(entry_text: str) -> dict:
    """Extract fields from a single numbered lighter entry."""
    result = {}
    for field_name, patterns in _ENTRY_PATTERNS.items():
        value = None
        conf = 0.0
        for pattern in patterns:
            match = re.search(pattern, entry_text, re.IGNORECASE)
            if match:
                raw = match.group(1).strip()
                # Normalize mobile — remove dashes/spaces, enforce 11-digit
                if field_name == "mobile_number":
                    raw = raw.replace("-", "").replace(" ", "").replace("+880", "0")
                    if not raw.startswith("0") and len(raw) == 10:
                        raw = "0" + raw
                    if not re.match(r"^0\d{10}$", raw):
                        continue
                value = raw
                conf = 0.9
                break
        result[field_name] = {"value": value, "confidence": conf}
    return result
