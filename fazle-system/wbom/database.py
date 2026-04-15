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
