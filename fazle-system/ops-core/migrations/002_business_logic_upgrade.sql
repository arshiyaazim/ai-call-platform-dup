-- ops-core-service: Migration 002
-- Adds: ops_users table, program_id FK on payments, end_date + food + transport on programs,
--        changed_by on program_history, client filter on attendance
-- Extends existing tables without breaking them.

BEGIN;

-- ============================================================
-- 1. OPS_USERS — role-based WhatsApp access control
-- ============================================================
CREATE TABLE IF NOT EXISTS ops_users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    whatsapp_number VARCHAR(20) NOT NULL UNIQUE,
    role TEXT NOT NULL DEFAULT 'viewer' CHECK (role IN ('admin', 'operator', 'viewer')),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ops_users_wa ON ops_users (whatsapp_number);

-- ============================================================
-- 2. PROGRAMS — add end_date, food, transport, total_cost
-- ============================================================
ALTER TABLE ops_programs ADD COLUMN IF NOT EXISTS end_date DATE;
ALTER TABLE ops_programs ADD COLUMN IF NOT EXISTS food INT DEFAULT 0;
ALTER TABLE ops_programs ADD COLUMN IF NOT EXISTS transport INT DEFAULT 0;
ALTER TABLE ops_programs ADD COLUMN IF NOT EXISTS total_cost INT DEFAULT 0;

-- ============================================================
-- 3. PAYMENTS — link to program
-- ============================================================
ALTER TABLE ops_payments ADD COLUMN IF NOT EXISTS program_id INT REFERENCES ops_programs(id);
ALTER TABLE ops_payments ADD COLUMN IF NOT EXISTS paid_by VARCHAR(20);
ALTER TABLE ops_payments ADD COLUMN IF NOT EXISTS category TEXT DEFAULT 'general'
    CHECK (category IN ('food', 'transport', 'general', 'salary', 'advance'));

CREATE INDEX IF NOT EXISTS idx_ops_payments_pid ON ops_payments (program_id);

-- ============================================================
-- 4. PROGRAM_HISTORY — add changed_by
-- ============================================================
ALTER TABLE ops_program_history ADD COLUMN IF NOT EXISTS changed_by TEXT DEFAULT 'system';

-- ============================================================
-- 5. ATTENDANCE — add shift column
-- ============================================================
ALTER TABLE ops_attendance ADD COLUMN IF NOT EXISTS shift CHAR(1) CHECK (shift IN ('D', 'N'));

-- ============================================================
-- 6. PENDING_ACTIONS — correction flow state machine
-- ============================================================
CREATE TABLE IF NOT EXISTS ops_pending_actions (
    id SERIAL PRIMARY KEY,
    sender_id VARCHAR(20) NOT NULL,
    intent TEXT NOT NULL,
    parsed_data JSONB NOT NULL,
    preview_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'confirmed', 'cancelled', 'expired')),
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP DEFAULT (NOW() + INTERVAL '10 minutes')
);

CREATE INDEX IF NOT EXISTS idx_ops_pending_sender ON ops_pending_actions (sender_id, status);

-- ============================================================
-- 7. Seed default admin user (owner phone)
-- ============================================================
-- Will be inserted via application if SOCIAL_OWNER_PHONE env is set.

COMMIT;
