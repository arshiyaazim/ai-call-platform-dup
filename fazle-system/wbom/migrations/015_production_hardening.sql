-- ============================================================
-- 015: Production Hardening Migration
-- Adds: audit_logs, job_applications, transaction idempotency,
--        payment status lifecycle, client table
-- ============================================================

-- ── 1. WBOM Audit Logs (append-only) ────────────────────────
CREATE TABLE IF NOT EXISTS wbom_audit_logs (
    audit_id    BIGSERIAL PRIMARY KEY,
    event       VARCHAR(80) NOT NULL,          -- e.g. "transaction.created"
    actor       VARCHAR(80) NOT NULL DEFAULT 'system',  -- user/role/service
    entity_type VARCHAR(50),                   -- "transaction", "employee", etc.
    entity_id   INT,
    payload     JSONB DEFAULT '{}',
    ip_address  VARCHAR(45),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_event      ON wbom_audit_logs(event);
CREATE INDEX IF NOT EXISTS idx_audit_entity     ON wbom_audit_logs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_created_at ON wbom_audit_logs(created_at);

-- ── 2. Job Applications ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS wbom_job_applications (
    application_id SERIAL PRIMARY KEY,
    applicant_name VARCHAR(100) NOT NULL,
    phone          VARCHAR(20) NOT NULL,
    position       VARCHAR(80),
    experience     TEXT,
    status         VARCHAR(30) NOT NULL DEFAULT 'Applied',  -- Applied|Screened|Interviewed|Hired|Rejected
    notes          TEXT,
    source         VARCHAR(30) DEFAULT 'whatsapp',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_job_app_phone  ON wbom_job_applications(phone);
CREATE INDEX IF NOT EXISTS idx_job_app_status ON wbom_job_applications(status);

-- ── 3. Client entity table ──────────────────────────────────
CREATE TABLE IF NOT EXISTS wbom_clients (
    client_id      SERIAL PRIMARY KEY,
    name           VARCHAR(100) NOT NULL,
    phone          VARCHAR(20),
    company_name   VARCHAR(150),
    client_type    VARCHAR(30) DEFAULT 'Standard', -- Standard|VIP|Corporate
    outstanding_balance DECIMAL(12,2) DEFAULT 0,
    credit_terms   VARCHAR(100),
    notes          TEXT,
    is_active      BOOLEAN DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_clients_phone ON wbom_clients(phone) WHERE phone IS NOT NULL;

-- ── 4. Transaction idempotency key + status lifecycle ───────
ALTER TABLE wbom_cash_transactions
    ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(64);
ALTER TABLE wbom_cash_transactions
    ADD COLUMN IF NOT EXISTS approved_by VARCHAR(80);
ALTER TABLE wbom_cash_transactions
    ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ;
ALTER TABLE wbom_cash_transactions
    ADD COLUMN IF NOT EXISTS source VARCHAR(30) DEFAULT 'web';

CREATE UNIQUE INDEX IF NOT EXISTS idx_txn_idempotency
    ON wbom_cash_transactions(idempotency_key)
    WHERE idempotency_key IS NOT NULL;

-- ── 5. Staging payments: add reference to final transaction ──
ALTER TABLE wbom_staging_payments
    ADD COLUMN IF NOT EXISTS final_transaction_id INT
    REFERENCES wbom_cash_transactions(transaction_id);
ALTER TABLE wbom_staging_payments
    ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(64);
