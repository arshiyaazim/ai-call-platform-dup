-- ============================================================
-- Phase 2C: Knowledge Lifecycle Extensions
-- Adds expiry, conflict tracking, and lifecycle management
-- ============================================================

-- Add expires_at column to governance facts
ALTER TABLE fazle_knowledge_governance
    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;

-- Add source column to track where facts originate
ALTER TABLE fazle_knowledge_governance
    ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'manual';

-- Index for finding expiring/expired facts
CREATE INDEX IF NOT EXISTS idx_kg_expires
    ON fazle_knowledge_governance(expires_at) WHERE expires_at IS NOT NULL;

-- Table: track knowledge conflicts (two facts contradicting each other)
CREATE TABLE IF NOT EXISTS fazle_knowledge_conflicts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fact_a_id UUID NOT NULL REFERENCES fazle_knowledge_governance(id),
    fact_b_id UUID NOT NULL REFERENCES fazle_knowledge_governance(id),
    conflict_type TEXT NOT NULL DEFAULT 'value_mismatch',
        -- value_mismatch, semantic_overlap, stale_data
    description TEXT NOT NULL,
    resolution TEXT,                -- NULL until resolved
    resolved_by TEXT,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'resolved', 'dismissed')),
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    UNIQUE(fact_a_id, fact_b_id)
);

CREATE INDEX IF NOT EXISTS idx_kconflict_status
    ON fazle_knowledge_conflicts(status) WHERE status = 'open';
