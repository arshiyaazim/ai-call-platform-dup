# ============================================================
# WBOM — CSV Import Routes
# Table-name-based CSV upload with smart employee auto-creation
# ============================================================
import csv
import io
import logging
from datetime import datetime
from decimal import InvalidOperation
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File

from database import execute_query, insert_row, audit_log

logger = logging.getLogger("wbom")
router = APIRouter(prefix="/csv-import", tags=["csv-import"])

# Whitelist of importable tables
_IMPORTABLE_TABLES = {
    "wbom_employees": "employee_id",
    "wbom_cash_transactions": "transaction_id",
    "wbom_escort_programs": "program_id",
    "wbom_contacts": "contact_id",
    "wbom_attendance": "attendance_id",
}

# Columns to skip during import (auto-generated)
_SKIP_COLUMNS = frozenset([
    "created_at", "updated_at", "transaction_time", "assignment_time",
    "completion_time", "approved_at", "responded_at",
])

# Column aliases: CSV header → DB column name
_COLUMN_ALIASES = {
    "wbom_cash_transactions": {
        "method": "payment_method",
        "payment_date": "transaction_date",
        "paid_by": "created_by",
        "payment_number": "payment_mobile",
        "category": "transaction_type",
    },
}

# Method normalization sets
_BKASH_VALS = frozenset({"bkash", "b", "(b)"})
_NAGAD_VALS = frozenset({"nagad", "n", "(n)"})

# Shared office expense employee
_OFFICE_EXPENSE_MOBILE = "01958122300"


@router.get("/tables")
def list_importable_tables():
    """Return the list of tables available for CSV import."""
    result = []
    for table, pk in _IMPORTABLE_TABLES.items():
        label = table.replace("wbom_", "").replace("_", " ").title()
        result.append({"table": table, "pk": pk, "label": label})
    return {"tables": result}


@router.get("/tables/{table}/columns")
def get_table_columns(table: str):
    """Return column metadata for a given table from information_schema."""
    if table not in _IMPORTABLE_TABLES:
        raise HTTPException(400, f"Table '{table}' is not importable")

    rows = execute_query(
        """SELECT column_name, data_type, is_nullable, column_default,
                  character_maximum_length
           FROM information_schema.columns
           WHERE table_name = %s
           ORDER BY ordinal_position""",
        (table,),
    )
    pk = _IMPORTABLE_TABLES[table]
    columns = []
    for r in rows:
        col = r["column_name"]
        columns.append({
            "column": col,
            "type": r["data_type"],
            "nullable": r["is_nullable"] == "YES",
            "has_default": r["column_default"] is not None,
            "max_length": r["character_maximum_length"],
            "is_pk": col == pk,
            "skip": col in _SKIP_COLUMNS or col == pk,
        })
    return {"table": table, "columns": columns}


@router.post("/tables/{table}/upload")
async def upload_csv(table: str, file: UploadFile = File(...)):
    """Upload a CSV file and insert rows into the specified table.

    Rules:
    - Empty numeric fields → 0
    - Empty text fields → NULL (stored as 'NUL' sentinel gets converted)
    - Transactions: auto-create missing employees (designation=Labor, status=Active)
    - Escort programs: SKIP row if escort_mobile not found in employees (returned in failures list)
    - Escort programs: auto-derive status from end_date (date→Complete, blank/0→Running)
    """
    if table not in _IMPORTABLE_TABLES:
        raise HTTPException(400, f"Table '{table}' is not importable")

    # Read and decode CSV
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")  # handle BOM
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(400, "CSV file has no header row")

    # Get column metadata for type-aware handling
    col_meta = {}
    rows_meta = execute_query(
        """SELECT column_name, data_type, is_nullable
           FROM information_schema.columns
           WHERE table_name = %s""",
        (table,),
    )
    for r in rows_meta:
        col_meta[r["column_name"]] = {
            "type": r["data_type"],
            "nullable": r["is_nullable"] == "YES",
        }

    pk = _IMPORTABLE_TABLES[table]
    inserted = 0
    skipped = 0
    errors = []
    failures = []  # rows skipped due to business rules (not DB errors)
    auto_created_employees = []

    for row_num, raw_row in enumerate(reader, start=2):  # row 1 is header
        try:
            # Pre-process transactions: aliases, employee, method, mobile, dates
            _txn_emp_info = None
            if table == "wbom_cash_transactions":
                processed, skip_reason, _txn_emp_info = _pre_process_transaction(raw_row)
                if skip_reason:
                    failures.append({
                        "row": row_num,
                        "reason": skip_reason,
                        "data": {k: v for k, v in raw_row.items() if v and v.strip()},
                    })
                    continue
                raw_row = processed

            cleaned = _clean_row(raw_row, col_meta, pk)
            if not cleaned:
                skipped += 1
                continue

            # Transaction: collect auto-created employees + dedup
            if table == "wbom_cash_transactions":
                if _txn_emp_info:
                    auto_created_employees.append(_txn_emp_info)
                # Dedup: skip if (employee_id, amount, transaction_date) already in DB
                _dup = execute_query(
                    "SELECT transaction_id FROM wbom_cash_transactions "
                    "WHERE employee_id = %s AND amount = %s AND transaction_date = %s LIMIT 1",
                    (cleaned.get("employee_id", 0), cleaned.get("amount", 0),
                     cleaned.get("transaction_date")),
                )
                if _dup:
                    skipped += 1
                    continue

            # Smart handling for escort programs
            if table == "wbom_escort_programs":
                cleaned, fail_reason = _handle_escort_employee(cleaned)
                if fail_reason:
                    # Collect the original row data for failure report
                    failures.append({
                        "row": row_num,
                        "reason": fail_reason,
                        "data": {k: v for k, v in raw_row.items() if v and v.strip()},
                    })
                    continue
                if cleaned is None:
                    # Silently skip rows with no escort_mobile (no employee data)
                    skipped += 1
                    continue

            insert_row(table, cleaned)
            inserted += 1
        except Exception as e:
            err_msg = str(e)
            # Truncate very long error messages
            if len(err_msg) > 200:
                err_msg = err_msg[:200] + "..."
            errors.append({"row": row_num, "error": err_msg})
            if len(errors) >= 50:
                errors.append({"row": 0, "error": "Too many errors, stopping at 50"})
                break

    audit_log(
        "csv_import",
        actor="admin",
        entity_type=table,
        payload={
            "filename": file.filename,
            "inserted": inserted,
            "skipped": skipped,
            "errors": len(errors),
            "failures": len(failures),
            "auto_created_employees": len(auto_created_employees),
        },
    )

    return {
        "table": table,
        "filename": file.filename,
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors[:20],  # return max 20 error details
        "total_errors": len(errors),
        "failures": failures[:50],  # rows skipped by business rules
        "total_failures": len(failures),
        "auto_created_employees": auto_created_employees,
    }


# ── Helpers ──────────────────────────────────────────────────


def _clean_row(raw_row: dict, col_meta: dict, pk: str) -> Optional[dict]:
    """Clean a CSV row: handle empty values, type coercion, skip auto columns."""
    cleaned = {}
    for col, val in raw_row.items():
        col = col.strip().lower()

        # Skip PK and auto-generated columns
        if col == pk or col in _SKIP_COLUMNS:
            continue

        # Skip columns not in the table
        if col not in col_meta:
            continue

        meta = col_meta[col]
        dtype = meta["type"]
        nullable = meta["nullable"]

        # Handle empty / sentinel values
        val = val.strip() if val else ""

        if val == "" or val.upper() == "NUL":
            if _is_numeric_type(dtype):
                cleaned[col] = None if nullable else 0
            elif nullable:
                cleaned[col] = None
            else:
                cleaned[col] = ""
            continue

        if val == "0" and _is_numeric_type(dtype):
            cleaned[col] = 0
            continue

        # Type coercion
        if _is_numeric_type(dtype):
            cleaned[col] = _to_number(val, dtype)
        elif dtype == "date":
            cleaned[col] = _to_date(val)
        elif dtype in ("timestamp with time zone", "timestamp without time zone"):
            cleaned[col] = _to_datetime(val)
        elif dtype == "boolean":
            cleaned[col] = val.lower() in ("true", "1", "yes", "t")
        else:
            cleaned[col] = val

    return cleaned if cleaned else None


def _is_numeric_type(dtype: str) -> bool:
    return dtype in ("integer", "bigint", "smallint", "numeric", "real",
                     "double precision", "decimal")


def _to_number(val: str, dtype: str):
    """Convert string to appropriate numeric type."""
    val = val.replace(",", "").strip()
    try:
        if dtype in ("integer", "bigint", "smallint"):
            return int(float(val))
        return float(val)
    except (ValueError, InvalidOperation):
        return 0


def _to_date(val: str) -> Optional[str]:
    """Try common date formats and return ISO date string.
    Handles 2-digit years (DD.MM.YY, DD-MM-YY) by expanding to 4-digit.
    """
    val = val.strip()
    if not val:
        return None
    # Fix comma used as separator (e.g. "14,03.2026" → "14.03.2026")
    val = val.replace(",", ".")
    # Expand 2-digit year → 4-digit (e.g. 18.01.26 → 18.01.2026)
    for sep in (".", "-", "/"):
        parts = val.split(sep)
        if len(parts) == 3 and len(parts[2]) == 2:
            parts[2] = "20" + parts[2]
            val = sep.join(parts)
            break
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(val, fmt).date().isoformat()
        except ValueError:
            continue
    return val  # return as-is and let DB handle it


def _to_datetime(val: str) -> Optional[str]:
    """Try common datetime formats."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M:%S",
                "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(val.strip(), fmt).isoformat()
        except ValueError:
            continue
    return val


def _handle_transaction_employee(cleaned: dict) -> tuple[dict, Optional[dict]]:
    """For transaction imports: if employee_id is a mobile number or name,
    find or auto-create the employee."""
    emp_id_val = cleaned.get("employee_id")
    if emp_id_val is None:
        return cleaned, None

    # If it's already a valid integer employee_id, check it exists
    try:
        emp_id = int(emp_id_val)
        existing = execute_query(
            "SELECT employee_id FROM wbom_employees WHERE employee_id = %s",
            (emp_id,),
        )
        if existing:
            cleaned["employee_id"] = emp_id
            return cleaned, None
    except (ValueError, TypeError):
        pass

    # It might be a mobile number — look up by mobile
    emp_id_str = str(emp_id_val).strip()
    found = execute_query(
        "SELECT employee_id, employee_name FROM wbom_employees WHERE employee_mobile = %s LIMIT 1",
        (emp_id_str,),
    )
    if found:
        cleaned["employee_id"] = found[0]["employee_id"]
        return cleaned, None

    # Auto-create employee with mobile number
    new_emp = insert_row("wbom_employees", {
        "employee_mobile": emp_id_str,
        "employee_name": f"Auto-{emp_id_str}",
        "designation": "Labor",
        "status": "Active",
    })
    cleaned["employee_id"] = new_emp["employee_id"]
    logger.info("Auto-created employee %s for CSV transaction import", emp_id_str)
    return cleaned, {
        "employee_id": new_emp["employee_id"],
        "employee_mobile": emp_id_str,
        "employee_name": new_emp["employee_name"],
    }


def _pre_process_transaction(raw_row: dict) -> tuple[dict | None, str | None, dict | None]:
    """Pre-process a cash transaction CSV row before _clean_row().
    Applies column aliases, resolves employee, normalizes method,
    cleans payment mobile, fixes date issues.
    Returns (processed_row, skip_reason, auto_created_emp_info).
    """
    # 1. Apply column aliases
    aliases = _COLUMN_ALIASES.get("wbom_cash_transactions", {})
    aliased = {}
    for col, val in raw_row.items():
        col_lower = col.strip().lower()
        mapped = aliases.get(col_lower, col_lower)
        aliased[mapped] = val if val else ""

    # 2. Skip rows with "?" or empty employee_id
    emp_raw = aliased.get("employee_id", "").strip()
    if not emp_raw or emp_raw == "?":
        return None, f"employee_id='{emp_raw}'", None

    # 3. Determine mobile number
    core = emp_raw.lstrip("0")
    if core.startswith("195812230") and len(core) == 10:
        # Shared office expense IDs (19581223xx) → single OfficeExpance employee
        mobile = _OFFICE_EXPENSE_MOBILE
    elif len(emp_raw) == 10 and emp_raw.isdigit():
        mobile = "0" + emp_raw
    elif len(emp_raw) == 11 and emp_raw.startswith("0") and emp_raw.isdigit():
        mobile = emp_raw
    else:
        return None, f"invalid employee_id='{emp_raw}'", None

    # 4. Lookup or auto-create employee
    found = execute_query(
        "SELECT employee_id FROM wbom_employees WHERE employee_mobile = %s LIMIT 1",
        (mobile,),
    )
    emp_info = None
    if found:
        aliased["employee_id"] = str(found[0]["employee_id"])
    else:
        emp_name = "OfficeExpance" if mobile == _OFFICE_EXPENSE_MOBILE else f"Auto-{mobile}"
        new_emp = insert_row("wbom_employees", {
            "employee_mobile": mobile,
            "employee_name": emp_name,
            "designation": "Labor",
            "status": "Active",
        })
        aliased["employee_id"] = str(new_emp["employee_id"])
        emp_info = {
            "employee_id": new_emp["employee_id"],
            "employee_mobile": mobile,
            "employee_name": emp_name,
        }
        logger.info("Auto-created employee %s (%s) for transaction import", mobile, emp_name)

    # 5. Normalize payment_method
    _normalize_transaction_method(aliased)

    # 6. Clean payment_mobile
    pm = aliased.get("payment_mobile", "").strip()
    aliased["payment_mobile"] = _clean_payment_mobile(pm)

    # 7. Fix comma in dates (e.g. "14,03.2026" → "14.03.2026")
    date_val = aliased.get("transaction_date", "").strip()
    if "," in date_val:
        aliased["transaction_date"] = date_val.replace(",", ".")

    return aliased, None, emp_info


def _normalize_transaction_method(row: dict):
    """Normalize payment_method: B/(B)/Bkash→Bkash, N/(N)/Nagad→Nagad, Cash→Cash.
    Non-payment-method values (SG, sukani, Food-18, etc.) move to remarks."""
    method = row.get("payment_method", "").strip()
    if not method:
        return
    method_lower = method.lower().strip()
    if method_lower in _BKASH_VALS:
        row["payment_method"] = "Bkash"
    elif method_lower in _NAGAD_VALS:
        row["payment_method"] = "Nagad"
    elif method_lower == "cash":
        row["payment_method"] = "Cash"
    else:
        # Not a recognized payment method — move to remarks
        existing = row.get("remarks", "").strip()
        row["remarks"] = f"{existing}; method: {method}".lstrip("; ") if existing else f"method: {method}"
        row["payment_method"] = ""


def _clean_payment_mobile(val: str) -> str:
    """Clean payment_mobile: strip dashes, handle scientific notation,
    remove method annotations, handle country codes, add 0-prefix."""
    if not val or val == "?":
        return ""
    # Remove method annotations at end, e.g. " (N)", "(B)"
    for suffix in (" (N)", " (B)", " (n)", " (b)", "(N)", "(B)"):
        if val.endswith(suffix):
            val = val[:-len(suffix)].strip()
            break
    # Handle scientific notation (e.g. 8.80185E+12)
    if "e" in val.lower() and "+" in val:
        try:
            val = str(int(float(val)))
        except (ValueError, OverflowError):
            pass
    # Strip dashes
    val = val.replace("-", "")
    # Handle country code +88 or 88 prefix
    if val.startswith("+88"):
        val = val[3:]
    elif val.startswith("88") and len(val) >= 13:
        val = val[2:]
    # Prepend 0 if 10-digit
    if len(val) == 10 and val.isdigit():
        val = "0" + val
    return val


def _handle_escort_employee(cleaned: dict) -> tuple[dict | None, str | None]:
    """For escort program CSV imports:
    - Dedup: skip row if (program_date, lighter_vessel, escort_mobile) already exists
    - Resolve escort_mobile to escort_employee_id
    - SKIP row if escort_mobile doesn't match any employee
    - Auto-derive status from end_date (date→Complete, blank/0→Running)
    - Default shift to 'D' if missing
    - Auto-calculate day_count from start_date/end_date + shifts
    - Auto-calculate conveyance from destination/release_point
    Returns (cleaned_row, failure_reason). If failure_reason is set, row is skipped.
    """
    escort_mobile = cleaned.get("escort_mobile")

    # ── Map shift words → single char: Day→D, Night→N ──
    _SHIFT_MAP = {"day": "D", "night": "N", "d": "D", "n": "N"}
    raw_shift = str(cleaned.get("shift", "")).strip().lower()
    raw_end_shift = str(cleaned.get("end_shift", "")).strip().lower()

    # Default: shift (start) → N (Night), end_shift → D (Day)
    cleaned["shift"] = _SHIFT_MAP.get(raw_shift, "N") if raw_shift and raw_shift != "0" else "N"
    cleaned["end_shift"] = _SHIFT_MAP.get(raw_end_shift, "D") if raw_end_shift and raw_end_shift != "0" else "D"

    # If escort_mobile is provided and non-empty, it MUST match an employee
    if escort_mobile:
        escort_mobile = str(escort_mobile).strip()
        if escort_mobile and escort_mobile != "0":
            found = execute_query(
                "SELECT employee_id FROM wbom_employees WHERE employee_mobile = %s LIMIT 1",
                (escort_mobile,),
            )
            if found:
                cleaned["escort_employee_id"] = found[0]["employee_id"]
            else:
                return None, f"escort_mobile '{escort_mobile}' not found in employees"
        else:
            # Mobile was whitespace-only or "0" — treat as missing
            return None, None
    # If escort_mobile is empty/absent, skip row entirely (no employee data)
    else:
        return None, None

    # ── Dedup check: (program_date, lighter_vessel, escort_mobile) ──
    p_date = cleaned.get("program_date")
    lighter = cleaned.get("lighter_vessel")
    e_mobile = cleaned.get("escort_mobile") or escort_mobile
    if p_date and lighter and e_mobile:
        existing = execute_query(
            "SELECT program_id FROM wbom_escort_programs "
            "WHERE program_date = %s AND lighter_vessel = %s AND escort_mobile = %s LIMIT 1",
            (p_date, lighter, e_mobile),
        )
        if existing:
            return None, f"Duplicate: program_date={p_date}, lighter={lighter}, escort_mobile={e_mobile} already exists"

    # ── Auto-derive status from end_date ──
    end_date = cleaned.get("end_date")
    if end_date and str(end_date).strip() not in ("", "0", "None"):
        cleaned["status"] = "Complete"
    else:
        cleaned["status"] = "Running"

    # ── Auto-calculate day_count from dates + shifts ──
    cleaned["day_count"] = _calc_day_count(cleaned)

    # ── Auto-calculate conveyance from destination / release_point ──
    cleaned["conveyance"] = _calc_conveyance(cleaned)

    return cleaned, None


# ── Conveyance lookup table ──────────────────────────────────

_CONVEYANCE_MAP = {
    # 0 conveyance
    "cancel": 0, "ctg": 0, "chattogram": 0, "chittagong": 0,
    # 600 conveyance
    "n. gonj": 600, "n.gonj": 600, "narayanganj": 600, "n gonj": 600,
    "rupshi": 600, "kachpur": 600, "demra": 600,
    "aricha": 600, "ashugonj": 600, "bhairov": 600, "bhairab": 600,
    "ghorashal": 600, "nitaigonj": 600,
    # 800 conveyance
    "n. bari": 800, "n.bari": 800, "n bari": 800, "narsingdi": 800,
    "j. kathi": 800, "j.kathi": 800, "jhalokathi": 800, "jhalokati": 800,
    "barishal": 800, "b. shal": 800, "b.shal": 800, "barisal": 800,
    # 1000 conveyance
    "khulna": 1000, "noapara": 1000, "n. para": 1000, "n.para": 1000, "n para": 1000,
}


def _lookup_conveyance(place: str) -> int | None:
    """Look up conveyance amount for a destination/release_point."""
    if not place:
        return None
    place_lower = place.strip().lower()
    # Exact match first
    if place_lower in _CONVEYANCE_MAP:
        return _CONVEYANCE_MAP[place_lower]
    # Partial match
    for key, val in _CONVEYANCE_MAP.items():
        if key in place_lower or place_lower in key:
            return val
    return None


def _calc_conveyance(cleaned: dict) -> float:
    """Auto-calculate conveyance from destination or release_point."""
    # If conveyance already explicitly provided and is a valid number > 0, keep it
    existing = cleaned.get("conveyance")
    if existing:
        try:
            val = float(existing)
            if val > 0:
                return val
        except (ValueError, TypeError):
            pass  # #REF!, "Mongla", "Day Labor" etc — ignore, auto-calc below
    # Clear invalid conveyance so it doesn't persist in the row
    cleaned.pop("conveyance", None)

    # Try release_point first, then destination
    for field in ("release_point", "destination"):
        place = cleaned.get(field)
        if place:
            val = _lookup_conveyance(str(place))
            if val is not None:
                return float(val)
    return 0.0


def _calc_day_count(cleaned: dict) -> float:
    """Auto-calculate day_count from start_date, end_date, shift, end_shift.
    Half-days are preserved as 0.5 increments. If day_count is already set
    and looks like a valid half-day value (e.g. 2.5), keep it as-is.
    """
    # If day_count already explicitly provided and > 0, keep it (preserve half-days)
    existing = cleaned.get("day_count")
    if existing:
        try:
            val = float(existing)
            if val > 0:
                return val
        except (ValueError, TypeError):
            pass

    start_date = cleaned.get("start_date")
    end_date = cleaned.get("end_date")

    if not start_date or not end_date:
        return 0.0

    try:
        from datetime import date as date_type
        if isinstance(start_date, str):
            start = date_type.fromisoformat(start_date)
        else:
            start = start_date
        if isinstance(end_date, str):
            end = date_type.fromisoformat(end_date)
        else:
            end = end_date

        delta_days = (end - start).days  # difference in calendar days
        if delta_days < 0:
            return 0.0

        # Base: full days between dates (inclusive of start)
        day_count = float(delta_days)  # end - start gives full-day spans

        # Adjust for half-day shifts
        shift = str(cleaned.get("shift", "D")).strip().upper()
        end_shift = str(cleaned.get("end_shift", "D")).strip().upper()

        # If start shift is Night (started mid-day), the first day is a half
        if shift == "N":
            day_count += 0.5
        else:
            day_count += 1.0  # full first day

        # If end shift is Day (ended mid-day of the last day), subtract half
        if end_shift == "D" and delta_days > 0:
            day_count -= 0.5

        return max(day_count, 0.0)
    except (ValueError, TypeError):
        return 0.0
