-- Migration 003: Business Intelligence Layer
-- Adds rate configuration table for auto-calculation

-- ── Rate Configuration Table ──
CREATE TABLE IF NOT EXISTS ops_rates (
  id SERIAL PRIMARY KEY,
  rate_type VARCHAR(20) NOT NULL CHECK (rate_type IN ('daily', 'transport')),
  destination TEXT,
  amount INT NOT NULL,
  effective_from DATE NOT NULL DEFAULT CURRENT_DATE,
  active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ops_rates_type_dest
  ON ops_rates (rate_type, destination);

-- ── Seed Default Rates ──
INSERT INTO ops_rates (rate_type, destination, amount) VALUES
  ('daily', NULL, 150),
  ('transport', 'Narayanganj', 600),
  ('transport', 'Nuwapara', 1000),
  ('transport', 'Nagarbari', 900),
  ('transport', 'Chittagong', 800),
  ('transport', 'Dhaka', 700)
ON CONFLICT DO NOTHING;

-- ── Add salary_calculated flag to programs ──
ALTER TABLE ops_programs ADD COLUMN IF NOT EXISTS salary_calculated BOOLEAN DEFAULT false;
