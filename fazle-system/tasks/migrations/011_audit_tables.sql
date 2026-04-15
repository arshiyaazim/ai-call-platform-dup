-- ============================================================
-- Migration 011: Audit & staging tables for WBOM
-- Adds rejected payments log and staging table
-- ============================================================

-- Audit log for rejected/unverified payments
CREATE TABLE IF NOT EXISTS wbom_rejected_payments (
    rejection_id    SERIAL PRIMARY KEY,
    message_id      INTEGER,
    sender_number   VARCHAR(20),
    extracted_name  VARCHAR(100),
    extracted_mobile VARCHAR(20),
    extracted_amount VARCHAR(20),
    matched_employee_id INTEGER,
    matched_employee_name VARCHAR(100),
    rejection_reason TEXT NOT NULL,
    name_match_ratio NUMERIC(4,2),
    raw_message     TEXT,
    reviewed        BOOLEAN DEFAULT FALSE,
    reviewed_by     VARCHAR(100),
    reviewed_at     TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rejected_payments_reviewed
    ON wbom_rejected_payments(reviewed);
CREATE INDEX IF NOT EXISTS idx_rejected_payments_created
    ON wbom_rejected_payments(created_at DESC);

-- Staging table for unverified payments needing admin review
CREATE TABLE IF NOT EXISTS wbom_staging_payments (
    staging_id      SERIAL PRIMARY KEY,
    message_id      INTEGER,
    sender_number   VARCHAR(20),
    extracted_name  VARCHAR(100),
    extracted_mobile VARCHAR(20),
    amount          NUMERIC(12,2),
    payment_method  VARCHAR(20),
    transaction_type VARCHAR(30),
    matched_employee_id INTEGER,
    name_match_ratio NUMERIC(4,2),
    status          VARCHAR(20) DEFAULT 'pending',  -- pending, approved, rejected
    approved_by     VARCHAR(100),
    approved_at     TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_staging_payments_status
    ON wbom_staging_payments(status);
