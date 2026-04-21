# ============================================================
# WBOM — PostgreSQL Database Layer
# WhatsApp Business Operations Manager database operations
# ============================================================
import logging
from contextlib import contextmanager
from typing import Optional

import psycopg2
import psycopg2.extras
import psycopg2.pool

from config import settings as _cfg

logger = logging.getLogger("wbom")

_DSN = _cfg.database_url
_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def _get_pool():
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(2, 10, _DSN)
    return _pool


@contextmanager
def get_conn():
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


# ── Table Creation ────────────────────────────────────────────

def ensure_wbom_tables():
    """Create all WBOM tables if they don't exist (idempotent)."""
    migration_path = "/app/migrations/009_wbom_tables.sql"
    try:
        with open(migration_path) as f:
            sql = f.read()
    except FileNotFoundError:
        logger.warning("Migration file not found, using inline SQL")
        sql = _INLINE_SCHEMA
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    logger.info("WBOM tables ensured")

    # Run incremental migrations (idempotent — safe to re-run)
    _DEDUP_INDEX_SQL = """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_wbom_transactions_dedup
        ON wbom_cash_transactions (employee_id, transaction_date, amount, transaction_type, payment_method)
        WHERE status = 'Completed';
    """
    _WAMSG_DEDUP_INDEX_SQL = """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_wbom_transactions_wa_msg_dedup
        ON wbom_cash_transactions (whatsapp_message_id)
        WHERE whatsapp_message_id IS NOT NULL AND whatsapp_message_id != '';
    """
    _PAYROLL_MIGRATION_SQL = """
    ALTER TABLE wbom_employees ADD COLUMN IF NOT EXISTS bkash_number VARCHAR(20);
    ALTER TABLE wbom_employees ADD COLUMN IF NOT EXISTS nagad_number VARCHAR(20);
    ALTER TABLE wbom_employees ADD COLUMN IF NOT EXISTS basic_salary DECIMAL(10,2) DEFAULT 0;
    ALTER TABLE wbom_employees ADD COLUMN IF NOT EXISTS nid_number VARCHAR(20);
    ALTER TABLE wbom_escort_programs ADD COLUMN IF NOT EXISTS start_date DATE;
    ALTER TABLE wbom_escort_programs ADD COLUMN IF NOT EXISTS end_date DATE;
    ALTER TABLE wbom_escort_programs ADD COLUMN IF NOT EXISTS end_shift VARCHAR(1);
    ALTER TABLE wbom_escort_programs ADD COLUMN IF NOT EXISTS release_point VARCHAR(100);
    ALTER TABLE wbom_escort_programs ADD COLUMN IF NOT EXISTS day_count DECIMAL(6,1) DEFAULT 0;
    ALTER TABLE wbom_escort_programs ADD COLUMN IF NOT EXISTS conveyance DECIMAL(10,2) DEFAULT 0;
    -- Migrate day_count from INT to DECIMAL(6,1) if needed (for half-days like 2.5)
    ALTER TABLE wbom_escort_programs ALTER COLUMN day_count TYPE DECIMAL(6,1);
    ALTER TABLE wbom_escort_programs ADD COLUMN IF NOT EXISTS capacity VARCHAR(20);
    CREATE TABLE IF NOT EXISTS wbom_attendance (
        attendance_id SERIAL PRIMARY KEY,
        employee_id INT NOT NULL REFERENCES wbom_employees(employee_id),
        attendance_date DATE NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'Present',
        location VARCHAR(100),
        check_in_time TIMESTAMPTZ,
        check_out_time TIMESTAMPTZ,
        remarks TEXT,
        recorded_by VARCHAR(50),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (employee_id, attendance_date)
    );
    CREATE TABLE IF NOT EXISTS wbom_employee_requests (
        request_id SERIAL PRIMARY KEY,
        employee_id INT NOT NULL REFERENCES wbom_employees(employee_id),
        request_type VARCHAR(30) NOT NULL,
        message_body TEXT,
        sender_number VARCHAR(20),
        status VARCHAR(20) DEFAULT 'Pending',
        response_text TEXT,
        delay_hours INT DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        responded_at TIMESTAMPTZ
    );
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
    CREATE INDEX IF NOT EXISTS idx_wbom_attendance_date ON wbom_attendance(attendance_date);
    CREATE INDEX IF NOT EXISTS idx_wbom_attendance_employee ON wbom_attendance(employee_id);
    CREATE INDEX IF NOT EXISTS idx_wbom_employee_requests_employee ON wbom_employee_requests(employee_id);
    CREATE INDEX IF NOT EXISTS idx_wbom_programs_start_date ON wbom_escort_programs(start_date);
    CREATE INDEX IF NOT EXISTS idx_wbom_programs_end_date ON wbom_escort_programs(end_date);
    CREATE INDEX IF NOT EXISTS idx_wbom_employees_bkash ON wbom_employees(bkash_number);
    CREATE INDEX IF NOT EXISTS idx_wbom_employees_name_trgm ON wbom_employees USING gin (employee_name gin_trgm_ops);
    """
    for label, mig_sql in (
        ("012_dedup_index", _DEDUP_INDEX_SQL),
        ("013_wa_msg_dedup", _WAMSG_DEDUP_INDEX_SQL),
        ("014_payroll_automation", _PAYROLL_MIGRATION_SQL),
    ):
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(mig_sql)
                conn.commit()
            logger.info("Applied migration %s", label)
        except Exception as e:
            logger.warning("Migration %s failed (may already be applied): %s", label, e)

    # 015: Production hardening (audit_logs, job_applications, clients, idempotency)
    try:
        import pathlib
        _mig_015 = pathlib.Path(__file__).parent / "migrations" / "015_production_hardening.sql"
        if _mig_015.exists():
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(_mig_015.read_text())
                conn.commit()
            logger.info("Applied migration 015_production_hardening")
    except Exception as e:
        logger.warning("Migration 015 failed (may already be applied): %s", e)

    # 016: Full DB consolidation (merge legacy tables into WBOM)
    try:
        import pathlib
        _mig_016 = pathlib.Path(__file__).parent / "migrations" / "016_db_consolidation.sql"
        if _mig_016.exists():
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(_mig_016.read_text())
                conn.commit()
            logger.info("Applied migration 016_db_consolidation")
    except Exception as e:
        logger.warning("Migration 016 failed (may already be applied): %s", e)

    # 017: Master identity & message history unification
    try:
        import pathlib
        _mig_017 = pathlib.Path(__file__).parent / "migrations" / "017_master_identity.sql"
        if _mig_017.exists():
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(_mig_017.read_text())
                conn.commit()
            logger.info("Applied migration 017_master_identity")
    except Exception as e:
        logger.warning("Migration 017 failed (may already be applied): %s", e)

    # 018: Case/workflow foundation for SLA, approvals, and event timelines
    try:
        import pathlib
        _mig_018 = pathlib.Path(__file__).parent / "migrations" / "018_case_workflow_foundation.sql"
        if _mig_018.exists():
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(_mig_018.read_text())
                conn.commit()
            logger.info("Applied migration 018_case_workflow_foundation")
    except Exception as e:
        logger.warning("Migration 018 failed (may already be applied): %s", e)

    # 019: Payroll run engine — payroll_runs, run_items, approval_log (Sprint-1 P0-01/P0-02/P0-03)
    try:
        import pathlib
        _mig_019 = pathlib.Path(__file__).parent / "migrations" / "019_payroll_run_engine.sql"
        if _mig_019.exists():
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(_mig_019.read_text())
                conn.commit()
            logger.info("Applied migration 019_payroll_run_engine")
    except Exception as e:
        logger.warning("Migration 019 failed (may already be applied): %s", e)

    # 020: Dashboard & reports indexes (Sprint-2 D0-01/D0-02/D0-03)
    try:
        import pathlib
        _mig_020 = pathlib.Path(__file__).parent / "migrations" / "020_dashboard_indexes.sql"
        if _mig_020.exists():
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(_mig_020.read_text())
                conn.commit()
            logger.info("Applied migration 020_dashboard_indexes")
    except Exception as e:
        logger.warning("Migration 020 failed (may already be applied): %s", e)

    # 021: Candidate funnel tables (Sprint-3 R0-01/R0-02/R0-03)
    try:
        import pathlib
        _mig_021 = pathlib.Path(__file__).parent / "migrations" / "021_candidate_funnel.sql"
        if _mig_021.exists():
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(_mig_021.read_text())
                conn.commit()
            logger.info("Applied migration 021_candidate_funnel")
    except Exception as e:
        logger.warning("Migration 021 failed (may already be applied): %s", e)


# ── Audit helper ─────────────────────────────────────────────

def audit_log(event: str, actor: str = "system", entity_type: str | None = None,
              entity_id: int | None = None, payload: dict | None = None,
              ip_address: str | None = None):
    """Append a row to wbom_audit_logs. Non-blocking — failures are logged."""
    try:
        import json as _json
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO wbom_audit_logs
                       (event, actor, entity_type, entity_id, payload, ip_address)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (event, actor, entity_type, entity_id,
                     _json.dumps(payload or {}, default=str),
                     ip_address),
                )
            conn.commit()
    except Exception as exc:
        logger.warning("audit_log write failed: %s", exc)


# ── Generic CRUD helpers ─────────────────────────────────────

def insert_row(table: str, data: dict) -> dict:
    """Insert a row and return it with generated ID."""
    cols = list(data.keys())
    placeholders = ["%s"] * len(cols)
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(placeholders)}) RETURNING *"
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, list(data.values()))
            row = cur.fetchone()
        conn.commit()
    return dict(row)


def insert_row_dedup(table: str, data: dict, conflict_cols: list[str]) -> tuple[dict, bool]:
    """Insert a row; on conflict (duplicate) return existing row instead.

    Returns (row_dict, is_new). is_new=False means duplicate was detected.
    """
    cols = list(data.keys())
    placeholders = ["%s"] * len(cols)
    conflict = ", ".join(conflict_cols)
    sql = (
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(placeholders)}) "
        f"ON CONFLICT ({conflict}) DO NOTHING RETURNING *"
    )
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, list(data.values()))
            row = cur.fetchone()
        conn.commit()
    if row:
        return dict(row), True
    # Duplicate — fetch existing
    where = " AND ".join(f"{c} = %s" for c in conflict_cols)
    vals = [data[c] for c in conflict_cols]
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"SELECT * FROM {table} WHERE {where} LIMIT 1", vals)
            row = cur.fetchone()
    return (dict(row) if row else {}), False


@contextmanager
def atomic(conn):
    """Run multiple operations in a single DB transaction.

    Usage:
        with get_conn() as conn:
            with atomic(conn):
                cur = conn.cursor(...)
                cur.execute(...)
                cur.execute(...)
    Commits on success, rolls back on exception.
    """
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def get_row(table: str, pk_col: str, pk_val) -> Optional[dict]:
    """Get a single row by primary key."""
    sql = f"SELECT * FROM {table} WHERE {pk_col} = %s"
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (pk_val,))
            row = cur.fetchone()
    return dict(row) if row else None


def update_row(table: str, pk_col: str, pk_val, data: dict) -> Optional[dict]:
    """Update a row by primary key, return updated row."""
    if not data:
        return get_row(table, pk_col, pk_val)
    sets = [f"{k} = %s" for k in data.keys()]
    sql = f"UPDATE {table} SET {', '.join(sets)}, updated_at = NOW() WHERE {pk_col} = %s RETURNING *"
    vals = list(data.values()) + [pk_val]
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, vals)
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


def update_row_no_ts(table: str, pk_col: str, pk_val, data: dict) -> Optional[dict]:
    """Update a row without touching updated_at (for tables without it)."""
    if not data:
        return get_row(table, pk_col, pk_val)
    sets = [f"{k} = %s" for k in data.keys()]
    sql = f"UPDATE {table} SET {', '.join(sets)} WHERE {pk_col} = %s RETURNING *"
    vals = list(data.values()) + [pk_val]
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, vals)
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


def delete_row(table: str, pk_col: str, pk_val) -> bool:
    """Delete a row by primary key."""
    sql = f"DELETE FROM {table} WHERE {pk_col} = %s"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (pk_val,))
            deleted = cur.rowcount > 0
        conn.commit()
    return deleted


def list_rows(table: str, filters: Optional[dict] = None, order_by: str = "", limit: int = 50, offset: int = 0) -> list[dict]:
    """List rows with optional filters, ordering, and pagination."""
    where_parts = []
    vals = []
    if filters:
        for k, v in filters.items():
            where_parts.append(f"{k} = %s")
            vals.append(v)
    where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    order_clause = f"ORDER BY {order_by}" if order_by else ""
    sql = f"SELECT * FROM {table} {where_clause} {order_clause} LIMIT %s OFFSET %s"
    vals.extend([limit, offset])
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, vals)
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def count_rows(table: str, filters: Optional[dict] = None) -> int:
    """Count rows with optional filters."""
    where_parts = []
    vals = []
    if filters:
        for k, v in filters.items():
            where_parts.append(f"{k} = %s")
            vals.append(v)
    where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    sql = f"SELECT COUNT(*) FROM {table} {where_clause}"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, vals)
            return cur.fetchone()[0]


def search_rows(table: str, search_col: str, search_val: str, limit: int = 20) -> list[dict]:
    """Search rows using ILIKE pattern matching."""
    sql = f"SELECT * FROM {table} WHERE {search_col} ILIKE %s LIMIT %s"
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (f"%{search_val}%", limit))
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def find_row_exact(table: str, col: str, val: str) -> Optional[dict]:
    """Find a single row by exact column value (case-sensitive)."""
    sql = f"SELECT * FROM {table} WHERE {col} = %s LIMIT 1"
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (val,))
            row = cur.fetchone()
    return dict(row) if row else None


def execute_query(sql: str, params: tuple = ()) -> list[dict]:
    """Execute a raw query and return results."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            if cur.description:
                return [dict(r) for r in cur.fetchall()]
        conn.commit()
    return []


# ── Inline Schema (fallback) ─────────────────────────────────

_INLINE_SCHEMA = """
CREATE TABLE IF NOT EXISTS wbom_relation_types (
    relation_type_id SERIAL PRIMARY KEY,
    relation_name VARCHAR(50) NOT NULL,
    description TEXT,
    greeting_template TEXT,
    is_active BOOLEAN DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS wbom_business_types (
    business_type_id SERIAL PRIMARY KEY,
    business_name VARCHAR(100) NOT NULL,
    service_category VARCHAR(50),
    default_templates JSONB,
    is_active BOOLEAN DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS wbom_contacts (
    contact_id SERIAL PRIMARY KEY,
    whatsapp_number VARCHAR(20) UNIQUE NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    company_name VARCHAR(150),
    relation_type_id INT REFERENCES wbom_relation_types(relation_type_id),
    business_type_id INT REFERENCES wbom_business_types(business_type_id),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes TEXT
);
CREATE TABLE IF NOT EXISTS wbom_message_templates (
    template_id SERIAL PRIMARY KEY,
    template_name VARCHAR(100) NOT NULL,
    template_type VARCHAR(30) NOT NULL,
    template_body TEXT NOT NULL,
    required_fields JSONB,
    optional_fields JSONB,
    extraction_patterns JSONB,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS wbom_contact_templates (
    id SERIAL PRIMARY KEY,
    contact_id INT NOT NULL REFERENCES wbom_contacts(contact_id) ON DELETE CASCADE,
    template_id INT NOT NULL REFERENCES wbom_message_templates(template_id),
    is_default BOOLEAN DEFAULT FALSE,
    priority INT DEFAULT 0,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (contact_id, template_id)
);
CREATE TABLE IF NOT EXISTS wbom_employees (
    employee_id SERIAL PRIMARY KEY,
    employee_mobile VARCHAR(20) UNIQUE NOT NULL,
    employee_name VARCHAR(100) NOT NULL,
    designation VARCHAR(30) NOT NULL,
    joining_date DATE,
    status VARCHAR(20) DEFAULT 'Active',
    bank_account VARCHAR(50),
    emergency_contact VARCHAR(20),
    address TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS wbom_escort_programs (
    program_id SERIAL PRIMARY KEY,
    mother_vessel VARCHAR(100) NOT NULL,
    lighter_vessel VARCHAR(100) NOT NULL,
    master_mobile VARCHAR(20) NOT NULL,
    destination VARCHAR(100),
    escort_employee_id INT REFERENCES wbom_employees(employee_id),
    escort_mobile VARCHAR(20),
    program_date DATE NOT NULL,
    shift VARCHAR(1) NOT NULL,
    status VARCHAR(20) DEFAULT 'Assigned',
    assignment_time TIMESTAMPTZ DEFAULT NOW(),
    completion_time TIMESTAMPTZ,
    contact_id INT REFERENCES wbom_contacts(contact_id),
    whatsapp_message_id VARCHAR(100),
    reply_message_id VARCHAR(100),
    remarks TEXT
);
CREATE TABLE IF NOT EXISTS wbom_cash_transactions (
    transaction_id SERIAL PRIMARY KEY,
    employee_id INT NOT NULL REFERENCES wbom_employees(employee_id),
    program_id INT REFERENCES wbom_escort_programs(program_id),
    transaction_type VARCHAR(20) NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    payment_method VARCHAR(10) NOT NULL,
    payment_mobile VARCHAR(20),
    transaction_date DATE NOT NULL,
    transaction_time TIMESTAMPTZ DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'Completed',
    reference_number VARCHAR(50),
    remarks TEXT,
    whatsapp_message_id VARCHAR(100),
    created_by VARCHAR(50)
);
CREATE TABLE IF NOT EXISTS wbom_billing_records (
    bill_id SERIAL PRIMARY KEY,
    program_id INT NOT NULL REFERENCES wbom_escort_programs(program_id),
    contact_id INT NOT NULL REFERENCES wbom_contacts(contact_id),
    bill_date DATE NOT NULL,
    bill_number VARCHAR(50) UNIQUE,
    service_charge DECIMAL(10,2),
    other_charges DECIMAL(10,2) DEFAULT 0,
    total_amount DECIMAL(10,2),
    payment_status VARCHAR(20) DEFAULT 'Pending',
    payment_date DATE,
    remarks TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS wbom_salary_records (
    salary_id SERIAL PRIMARY KEY,
    employee_id INT NOT NULL REFERENCES wbom_employees(employee_id),
    month INT NOT NULL,
    year INT NOT NULL,
    basic_salary DECIMAL(10,2),
    total_programs INT DEFAULT 0,
    program_allowance DECIMAL(10,2) DEFAULT 0,
    other_allowance DECIMAL(10,2) DEFAULT 0,
    total_advances DECIMAL(10,2) DEFAULT 0,
    total_deductions DECIMAL(10,2) DEFAULT 0,
    net_salary DECIMAL(10,2),
    payment_date DATE,
    payment_status VARCHAR(20) DEFAULT 'Pending',
    remarks TEXT,
    UNIQUE (employee_id, month, year)
);
CREATE TABLE IF NOT EXISTS wbom_whatsapp_messages (
    message_id SERIAL PRIMARY KEY,
    whatsapp_msg_id VARCHAR(100) UNIQUE,
    contact_id INT REFERENCES wbom_contacts(contact_id),
    sender_number VARCHAR(20) NOT NULL,
    message_type VARCHAR(10) NOT NULL,
    content_type VARCHAR(10) DEFAULT 'text',
    message_body TEXT NOT NULL,
    classification VARCHAR(20) DEFAULT 'unclassified',
    is_processed BOOLEAN DEFAULT FALSE,
    template_used_id INT REFERENCES wbom_message_templates(template_id),
    received_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    related_program_id INT REFERENCES wbom_escort_programs(program_id),
    related_transaction_id INT REFERENCES wbom_cash_transactions(transaction_id)
);
CREATE TABLE IF NOT EXISTS wbom_extracted_data (
    extraction_id SERIAL PRIMARY KEY,
    message_id INT NOT NULL REFERENCES wbom_whatsapp_messages(message_id) ON DELETE CASCADE,
    field_name VARCHAR(100) NOT NULL,
    field_value TEXT,
    confidence_score DECIMAL(3,2),
    is_verified BOOLEAN DEFAULT FALSE,
    extracted_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS wbom_template_generation_log (
    log_id SERIAL PRIMARY KEY,
    message_id INT NOT NULL REFERENCES wbom_whatsapp_messages(message_id),
    template_id INT NOT NULL REFERENCES wbom_message_templates(template_id),
    generated_content TEXT NOT NULL,
    admin_modified_content TEXT,
    is_sent BOOLEAN DEFAULT FALSE,
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    sent_at TIMESTAMPTZ
);
"""
