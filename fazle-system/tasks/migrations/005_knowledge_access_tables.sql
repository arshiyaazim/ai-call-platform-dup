-- ============================================================
-- Migration 005: Knowledge Base, Access Rules, Feedback Learning
-- Production knowledge layer for Fazle AI
-- IDEMPOTENT — safe to re-run
-- ============================================================

-- ── 1. Users (phone-indexed, role-based) ────────────────────
CREATE TABLE IF NOT EXISTS fazle_knowledge_users (
    id TEXT PRIMARY KEY,
    name TEXT,
    phone TEXT UNIQUE,
    role TEXT,
    access_level TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_fku_phone ON fazle_knowledge_users (phone);

-- ── 2. Access Rules ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fazle_access_rules (
    id SERIAL PRIMARY KEY,
    user_id TEXT REFERENCES fazle_knowledge_users(id) ON DELETE CASCADE,
    data_type TEXT NOT NULL,
    allowed BOOLEAN DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_far_user ON fazle_access_rules (user_id);
CREATE INDEX IF NOT EXISTS idx_far_type ON fazle_access_rules (data_type);

-- ── 3. Knowledge Base ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS fazle_knowledge_base (
    id SERIAL PRIMARY KEY,
    category TEXT NOT NULL,
    subcategory TEXT,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    language TEXT DEFAULT 'bn-en',
    confidence FLOAT DEFAULT 1.0,
    tags TEXT[],
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_fkb_category ON fazle_knowledge_base (category);
CREATE INDEX IF NOT EXISTS idx_fkb_key ON fazle_knowledge_base (key);
CREATE INDEX IF NOT EXISTS idx_fkb_value_trgm ON fazle_knowledge_base USING gin (value gin_trgm_ops);

-- ── 4. Feedback Learning ────────────────────────────────────
CREATE TABLE IF NOT EXISTS fazle_feedback_learning (
    id SERIAL PRIMARY KEY,
    original_query TEXT NOT NULL,
    ai_reply TEXT,
    corrected_reply TEXT,
    rating INT CHECK (rating BETWEEN 1 AND 5),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- SEED DATA — Users
-- ============================================================
INSERT INTO fazle_knowledge_users (id, name, phone, role, access_level) VALUES
('+8801848144841', 'Sajeda Yesmin', '+8801848144841', 'wife', 'full'),
('+8801772274173', 'Arshiya Wafiqah', '+8801772274173', 'daughter', 'full')
ON CONFLICT (phone) DO NOTHING;

-- ============================================================
-- SEED DATA — Access Rules
-- ============================================================
INSERT INTO fazle_access_rules (user_id, data_type, allowed)
SELECT '+8801848144841', 'personal', TRUE
WHERE NOT EXISTS (
    SELECT 1 FROM fazle_access_rules
    WHERE user_id = '+8801848144841' AND data_type = 'personal'
);

INSERT INTO fazle_access_rules (user_id, data_type, allowed)
SELECT '+8801772274173', 'personal', TRUE
WHERE NOT EXISTS (
    SELECT 1 FROM fazle_access_rules
    WHERE user_id = '+8801772274173' AND data_type = 'personal'
);

-- ============================================================
-- SEED DATA — Personal Knowledge
-- ============================================================
INSERT INTO fazle_knowledge_base (category, key, value, language, confidence) VALUES
('personal', 'full_name', 'Azim', 'bn-en', 1.0),
('personal', 'father_name', 'A. K. M. Shah Alam', 'bn-en', 1.0),
('personal', 'mother_name', 'Akter Jahan Alo', 'bn-en', 1.0),
('personal', 'spouse_name', 'Sajeda Yesmin', 'bn-en', 1.0),
('personal', 'date_of_birth', '1980-11-30', 'bn-en', 1.0),
('personal', 'birth_place', 'Khagrachari', 'bn-en', 1.0),
('personal', 'nid_number', '1595708912924', 'bn-en', 1.0),
('personal', 'blood_group', 'AB+', 'bn-en', 1.0),
('personal', 'passport_number', 'A02235098', 'bn-en', 1.0),
('personal', 'passport_expiry', '2031-11-13', 'bn-en', 1.0),
('personal', 'address', 'Faruk Villa, Arakan Housing Society, Chandgaon, Chattogram', 'bn-en', 1.0)
ON CONFLICT DO NOTHING;

-- ============================================================
-- SEED DATA — Business Knowledge
-- ============================================================
INSERT INTO fazle_knowledge_base (category, key, value, language, confidence) VALUES
('business', 'company_name', 'AL-AQSA SECURITY & LOGISTICS SERVICES LTD.', 'bn-en', 1.0),
('business', 'tin', '250686246674', 'bn-en', 1.0),
('business', 'company_address', 'Akborsha, Chattogram', 'bn-en', 1.0),
('business', 'brac_account', '20604039890001', 'bn-en', 1.0),
('business', 'one_bank_account', '06310200007495', 'bn-en', 1.0)
ON CONFLICT DO NOTHING;
