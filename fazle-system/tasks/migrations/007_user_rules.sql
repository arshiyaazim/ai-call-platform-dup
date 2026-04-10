-- ============================================================
-- Phase 2B: Per-User Instruction Rules
-- Contact-specific behavior rules with code enforcement
-- ============================================================

-- Table: per-contact rules set by owner
CREATE TABLE IF NOT EXISTS fazle_user_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_identifier TEXT NOT NULL,       -- phone number or platform ID
    platform TEXT NOT NULL DEFAULT 'whatsapp',
    rule_type TEXT NOT NULL,                -- tone, block, auto_reply, greeting, escalate, restrict_topic
    rule_value TEXT NOT NULL,               -- the rule content
    priority INTEGER NOT NULL DEFAULT 1,    -- higher = overrides lower
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_by TEXT NOT NULL DEFAULT 'owner',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,                 -- NULL = never expires
    UNIQUE(contact_identifier, platform, rule_type)
);

CREATE INDEX IF NOT EXISTS idx_user_rules_contact
    ON fazle_user_rules (contact_identifier, platform) WHERE is_active;

CREATE INDEX IF NOT EXISTS idx_user_rules_type
    ON fazle_user_rules (rule_type) WHERE is_active;

-- Audit trail: who changed what rule and when
CREATE TABLE IF NOT EXISTS fazle_user_rules_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id UUID REFERENCES fazle_user_rules(id) ON DELETE SET NULL,
    contact_identifier TEXT NOT NULL,
    action TEXT NOT NULL,                   -- created, updated, deactivated
    old_value TEXT,
    new_value TEXT,
    changed_by TEXT NOT NULL DEFAULT 'owner',
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_rules_audit_contact
    ON fazle_user_rules_audit (contact_identifier);

-- Seed example rules (commented out — owner sets these via API)
-- INSERT INTO fazle_user_rules (contact_identifier, platform, rule_type, rule_value, priority)
-- VALUES ('01712345678', 'whatsapp', 'tone', 'Be extra polite, this is a VIP client', 2);
