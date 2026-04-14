-- ops-core-service: Database Migration 001
-- Tables: employees, programs, program_history, payments, attendance, notes
-- Run against existing PostgreSQL (ai-postgres)

BEGIN;

-- ============================================================
-- 1. EMPLOYEES
-- ============================================================
CREATE TABLE IF NOT EXISTS ops_employees (
    id SERIAL PRIMARY KEY,
    employee_id VARCHAR(20) NOT NULL UNIQUE,  -- mobile number (leading zero kept)
    name TEXT NOT NULL,
    mobile VARCHAR(20) NOT NULL,
    role TEXT NOT NULL DEFAULT 'escort' CHECK (role IN ('escort', 'guard', 'admin')),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_ops_employees_mobile ON ops_employees (mobile);
CREATE INDEX idx_ops_employees_name ON ops_employees USING gin (name gin_trgm_ops);

-- ============================================================
-- 2. PROGRAMS
-- ============================================================
CREATE TABLE IF NOT EXISTS ops_programs (
    id SERIAL PRIMARY KEY,
    mother_vessel TEXT NOT NULL,
    lighter_vessel TEXT,
    master_mobile VARCHAR(20),
    destination TEXT,
    escort_name TEXT,
    escort_mobile VARCHAR(20),
    start_date DATE,
    shift CHAR(1) CHECK (shift IN ('D', 'N')),
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'completed')),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_ops_programs_status ON ops_programs (status);
CREATE INDEX idx_ops_programs_vessel ON ops_programs USING gin (mother_vessel gin_trgm_ops);
CREATE INDEX idx_ops_programs_date ON ops_programs (start_date);

-- ============================================================
-- 3. PROGRAM HISTORY (append-only snapshots)
-- ============================================================
CREATE TABLE IF NOT EXISTS ops_program_history (
    id SERIAL PRIMARY KEY,
    program_id INT NOT NULL REFERENCES ops_programs(id),
    snapshot JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_ops_program_history_pid ON ops_program_history (program_id);

-- ============================================================
-- 4. PAYMENTS
-- ============================================================
CREATE TABLE IF NOT EXISTS ops_payments (
    id SERIAL PRIMARY KEY,
    employee_id VARCHAR(20) NOT NULL,
    name TEXT,
    payment_number VARCHAR(30),
    method TEXT CHECK (method IN ('B', 'N')),  -- Bkash / Nagad
    amount INT NOT NULL CHECK (amount > 0),
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'completed')),
    remarks TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_ops_payments_eid ON ops_payments (employee_id);
CREATE INDEX idx_ops_payments_date ON ops_payments (created_at);

-- ============================================================
-- 5. ATTENDANCE
-- ============================================================
CREATE TABLE IF NOT EXISTS ops_attendance (
    id SERIAL PRIMARY KEY,
    employee_id VARCHAR(20) NOT NULL,
    name TEXT,
    location TEXT,
    client_name TEXT,
    date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_ops_attendance_eid ON ops_attendance (employee_id);
CREATE INDEX idx_ops_attendance_date ON ops_attendance (date);

-- ============================================================
-- 6. NOTES
-- ============================================================
CREATE TABLE IF NOT EXISTS ops_notes (
    id SERIAL PRIMARY KEY,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('employee', 'program', 'payment')),
    entity_id INT NOT NULL,
    note TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_ops_notes_entity ON ops_notes (entity_type, entity_id);

-- ============================================================
-- 7. Enable trigram extension (for fuzzy text search)
-- ============================================================
CREATE EXTENSION IF NOT EXISTS pg_trgm;

COMMIT;
