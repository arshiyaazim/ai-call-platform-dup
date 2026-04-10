CREATE TABLE IF NOT EXISTS fazle_leads (
    id SERIAL PRIMARY KEY,
    name TEXT,
    phone TEXT,
    message TEXT,
    intent TEXT,
    source TEXT,
    status TEXT DEFAULT 'new',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_fazle_leads_phone ON fazle_leads (phone);
CREATE INDEX IF NOT EXISTS idx_fazle_leads_created ON fazle_leads (created_at DESC);
