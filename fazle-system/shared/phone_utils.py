# ============================================================
# phone_utils.py — Universal Bangladesh phone normalization
# Shared across ALL Fazle services (social-engine, wbom, api)
# ============================================================
"""
One Person = One Canonical Phone.

Canonical format: 01XXXXXXXXX (11 digits, starts with 01, no country code)

Examples:
    +8801958122300  → 01958122300
    8801958122300   → 01958122300
    1958122300      → 01958122300
    01958-122300    → 01958122300
    01958 122 300   → 01958122300
    880 1958 122300 → 01958122300
    447878758751    → None  (not a BD number)
"""
import re

_NON_DIGIT = re.compile(r"\D")


def normalize_phone(value) -> str | None:
    """Normalize any phone input to canonical BD local format: 01XXXXXXXXX.

    Returns None if the input cannot be resolved to a valid BD mobile number.
    """
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None

    # Step 1-4: remove spaces, +, -, and all non-digits
    digits = _NON_DIGIT.sub("", raw)

    if not digits:
        return None

    # Step 5-6: strip leading country code 880
    if digits.startswith("880") and len(digits) >= 13:
        digits = digits[3:]
    # Also handle 88 without the leading 0 being doubled
    elif digits.startswith("880") and len(digits) == 13:
        digits = digits[3:]

    # Step 7: if starts with 1 and length == 10, add leading 0
    if digits.startswith("1") and len(digits) == 10:
        digits = "0" + digits

    # Step 8: if still too long, keep last 11 digits
    if len(digits) > 11:
        digits = digits[-11:]

    # Step 9: re-check after truncation
    if digits.startswith("1") and len(digits) == 10:
        digits = "0" + digits

    # Final validation: must be 11 digits starting with 01
    if len(digits) == 11 and digits.startswith("01"):
        return digits

    return None


def normalize_phone_or_keep(value) -> str:
    """Normalize to canonical format. If not a BD number, return cleaned original.

    Use this for fields that may contain international numbers (e.g. contacts).
    """
    result = normalize_phone(value)
    if result:
        return result
    # Return cleaned but un-normalized value for international numbers
    if value is None:
        return ""
    return str(value).strip()


def phones_match(a: str, b: str) -> bool:
    """Check if two phone values refer to the same person."""
    na = normalize_phone(a)
    nb = normalize_phone(b)
    if na and nb:
        return na == nb
    return False
