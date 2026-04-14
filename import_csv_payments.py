#!/usr/bin/env python3
"""Import cashPayment March April CSV into ops_payments table.
Normalizes messy data formats: employee_id, amounts, methods, dates.
Generates a SQL file for execution on VPS.
"""

import csv
import re
import os
from datetime import datetime

CSV_FILE = os.path.join(os.path.dirname(__file__), "cashPayment March April.csv")
SQL_FILE = os.path.join(os.path.dirname(__file__), "import_payments.sql")


def normalize_employee_id(eid):
    eid = str(eid).strip()
    if eid == '?' or not eid:
        return None
    # Handle scientific notation like 8.80185E+12
    if 'E+' in eid.upper():
        try:
            eid = str(int(float(eid)))
        except (ValueError, OverflowError):
            return None
    # Remove non-digit chars (hyphens, spaces)
    eid = re.sub(r'[^0-9]', '', eid)
    if not eid:
        return None
    # BD phone numbers should be 11 digits starting with 0
    if len(eid) == 10:
        eid = '0' + eid
    return eid


def normalize_payment_number(pn):
    pn = str(pn).strip()
    if pn == '?' or not pn:
        return None
    if 'E+' in pn.upper():
        try:
            pn = str(int(float(pn)))
        except (ValueError, OverflowError):
            return None
    pn = re.sub(r'[^0-9]', '', pn)
    if not pn:
        return None
    if len(pn) == 10:
        pn = '0' + pn
    return pn


def normalize_amount(amt):
    amt = str(amt).strip().strip('"')
    amt = amt.replace(',', '')
    try:
        return int(round(float(amt)))
    except (ValueError, TypeError):
        return 0


def normalize_method(method_raw):
    """Return (method, extra_remarks) tuple."""
    method = str(method_raw).strip()
    if not method:
        return (None, None)

    # Combined: "(N), Conv.", "(B), Food bill", "(N), Day Shift", "(B), Agent"
    combo = re.match(r'^\(?([BbNn])\)?\s*,\s*(.+)$', method)
    if combo:
        m = combo.group(1).upper()
        extra = combo.group(2).strip()
        return ('B' if m == 'B' else 'N', extra)

    # "(N), (B)" dual
    if method.strip() == '(N), (B)':
        return ('B', 'also Nagad')

    # "b agent", "b agent" patterns
    b_agent = re.match(r'^[Bb]\s+(\w.+)$', method)
    if b_agent:
        return ('B', b_agent.group(1).strip())

    # Clean method value
    m_clean = method.lower().strip().strip('()')

    # Bkash variants
    if m_clean in ('b', 'bkash'):
        return ('B', None)
    # Nagad variants
    if m_clean in ('n', 'nagad', 'nagod-agent'):
        return ('N', None)
    # Cash → NULL method (not in CHECK constraint)
    if m_clean in ('cash', 'cash payment'):
        return (None, 'Cash')
    # Recharge
    if m_clean == 'recharge':
        return (None, 'Recharge')

    # Non-method values → put in remarks
    non_methods = [
        'night shift', 'day shift', 'max duty', 'max duty day',
        'duty max', 'self', 'master', 'con', 'convence', 'boat',
        'advance',
    ]
    if m_clean in non_methods:
        return (None, method.strip())

    # Food/conv patterns
    if re.search(r'food|conv', m_clean):
        return (None, method.strip())
    # sukani patterns
    if 'sukani' in m_clean:
        return (None, method.strip())
    # Calculation notes: (2700+1920+30), (21?150), (27?150)
    if re.match(r'^\(.+\)$', method) and not re.match(r'^\([BbNn]\)$', method):
        return (None, method.strip())
    # Mamun Vai (person name in method field)
    if 'mamun' in m_clean:
        return (None, method.strip())
    # Salary
    if 'salary' in m_clean:
        return (None, method.strip())
    # Date reference in method
    if re.search(r'\d{2}[./]\d{2}[./]\d{4}', method):
        return (None, method.strip())
    # Name in method (Shariar, Hridoy prog.)
    if re.match(r'^[A-Z][a-z]', method.strip()) and not re.match(r'^(Bkash|Nagad|Cash)', method.strip()):
        return (None, method.strip())
    # Parenthesized names
    if re.match(r'^\(.+\)$', method):
        return (None, method.strip('() '))

    # Fallback
    return (None, method.strip())


def normalize_date(date_str):
    d = str(date_str).strip()
    if not d:
        return None
    # Fix "14,03.2026" → "14.03.2026"
    d_fixed = d.replace(',', '.')

    for date_input in [d, d_fixed]:
        for fmt in ['%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y']:
            try:
                return datetime.strptime(date_input, fmt).strftime('%Y-%m-%d')
            except ValueError:
                continue
    # Try fixing double-dot from comma replacement: "14.03.2026" already handled
    # Last resort: try stripping extra dots
    dots = d_fixed.split('.')
    if len(dots) == 3:
        try:
            return datetime.strptime(f"{dots[0]}.{dots[1]}.{dots[2]}", '%d.%m.%Y').strftime('%Y-%m-%d')
        except ValueError:
            pass
    return None


def escape_sql(s):
    if s is None:
        return 'NULL'
    s = str(s).replace("'", "''")
    return f"'{s}'"


def main():
    rows_processed = 0
    rows_skipped = 0
    sql_lines = []

    sql_lines.append("-- Auto-generated payment import from cashPayment March April.csv")
    sql_lines.append(f"-- Generated: {datetime.now().isoformat()}")
    sql_lines.append("")
    sql_lines.append("-- Ensure payment_date column exists")
    sql_lines.append("ALTER TABLE ops_payments ADD COLUMN IF NOT EXISTS payment_date DATE DEFAULT CURRENT_DATE;")
    sql_lines.append("CREATE INDEX IF NOT EXISTS idx_ops_payments_payment_date ON ops_payments(payment_date);")
    sql_lines.append("")
    sql_lines.append("BEGIN;")
    sql_lines.append("")

    with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        header = next(reader)
        print(f"Header ({len(header)} cols): {header}")

        for i, row in enumerate(reader, start=2):
            if not row or all(c.strip() == '' for c in row):
                continue
            if len(row) < 3:
                rows_skipped += 1
                print(f"  Line {i}: SKIP (too few columns)")
                continue

            # Pad to 11 columns
            while len(row) < 11:
                row.append('')

            raw_eid = row[0]
            raw_name = row[1]
            raw_amount = row[2]
            raw_method = row[3]
            raw_category = row[4]
            raw_date = row[5]
            raw_status = row[6]
            raw_remarks = row[7]
            raw_program_id = row[8]
            raw_paid_by = row[9]
            raw_payment_number = row[10]

            employee_id = normalize_employee_id(raw_eid)
            if not employee_id:
                rows_skipped += 1
                print(f"  Line {i}: SKIP (bad employee_id: '{raw_eid}') - {raw_name}")
                continue

            name = raw_name.strip()
            if not name:
                rows_skipped += 1
                continue

            amount = normalize_amount(raw_amount)
            if amount <= 0:
                rows_skipped += 1
                print(f"  Line {i}: SKIP (bad amount: '{raw_amount}') - {name}")
                continue

            method, method_remark = normalize_method(raw_method)

            payment_date = normalize_date(raw_date)
            if not payment_date:
                rows_skipped += 1
                print(f"  Line {i}: SKIP (bad date: '{raw_date}') - {name}")
                continue

            payment_number = normalize_payment_number(raw_payment_number)

            # Build remarks
            remarks_parts = []
            if method_remark:
                remarks_parts.append(method_remark)
            if raw_remarks.strip():
                remarks_parts.append(raw_remarks.strip())
            remarks = '; '.join(remarks_parts) if remarks_parts else None

            status = raw_status.strip() if raw_status.strip() else 'running'
            category = raw_category.strip() if raw_category.strip() else 'general'
            paid_by = raw_paid_by.strip() if raw_paid_by.strip() else None

            sql = (
                f"INSERT INTO ops_payments "
                f"(employee_id, name, payment_number, method, amount, "
                f"status, remarks, category, paid_by, payment_date) VALUES ("
                f"{escape_sql(employee_id)}, {escape_sql(name)}, {escape_sql(payment_number)}, "
                f"{escape_sql(method)}, {amount}, {escape_sql(status)}, {escape_sql(remarks)}, "
                f"{escape_sql(category)}, {escape_sql(paid_by)}, {escape_sql(payment_date)});"
            )
            sql_lines.append(sql)
            rows_processed += 1

    sql_lines.append("")
    sql_lines.append("COMMIT;")
    sql_lines.append("")
    sql_lines.append(f"-- Total rows inserted: {rows_processed}")
    sql_lines.append(f"-- Total rows skipped: {rows_skipped}")

    with open(SQL_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(sql_lines))

    print(f"\nDone! {rows_processed} rows → {SQL_FILE}")
    print(f"Skipped: {rows_skipped} rows")


if __name__ == '__main__':
    main()
