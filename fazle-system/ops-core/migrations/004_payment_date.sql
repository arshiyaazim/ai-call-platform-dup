-- Migration 004: Add payment_date column to ops_payments
-- Enables date-wise tracking for CSV-imported transaction history

-- ── Add payment_date (defaults to current date for new records) ──
ALTER TABLE ops_payments ADD COLUMN IF NOT EXISTS payment_date DATE DEFAULT CURRENT_DATE;

-- ── Backfill existing rows: use created_at date ──
UPDATE ops_payments SET payment_date = created_at::date WHERE payment_date IS NULL;

-- ── Index for date-range queries ──
CREATE INDEX IF NOT EXISTS idx_ops_payments_date ON ops_payments (payment_date);

-- ── Composite index for employee + date lookups ──
CREATE INDEX IF NOT EXISTS idx_ops_payments_eid_date ON ops_payments (employee_id, payment_date);
