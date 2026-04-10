-- ============================================================
-- Phase 1B: Knowledge Governance Tables
-- Versioned canonical facts, corrections & phrasing rules
-- ============================================================

-- Canonical business facts (versioned, auditable)
CREATE TABLE IF NOT EXISTS fazle_knowledge_governance (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category        TEXT NOT NULL,          -- 'company','training','duty','office','salary','identity','policy'
    fact_key        TEXT NOT NULL,          -- e.g. 'training_duration', 'corporate_office_address'
    fact_value      TEXT NOT NULL,          -- authoritative answer
    language        TEXT NOT NULL DEFAULT 'bn',  -- 'bn','en','bn-en'
    version         INTEGER NOT NULL DEFAULT 1,
    status          TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active','deprecated','prohibited')),
    created_by      TEXT NOT NULL DEFAULT 'system',  -- 'owner','system','admin'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deprecated_at   TIMESTAMPTZ,
    deprecation_reason TEXT,
    UNIQUE (category, fact_key, version)
);

CREATE INDEX IF NOT EXISTS idx_kg_category ON fazle_knowledge_governance(category);
CREATE INDEX IF NOT EXISTS idx_kg_status   ON fazle_knowledge_governance(status);

-- Correction audit trail
CREATE TABLE IF NOT EXISTS fazle_knowledge_corrections (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    governance_id   UUID NOT NULL REFERENCES fazle_knowledge_governance(id),
    old_value       TEXT NOT NULL,
    new_value       TEXT NOT NULL,
    reason          TEXT,
    corrected_by    TEXT NOT NULL DEFAULT 'owner',
    corrected_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_kc_gov_id ON fazle_knowledge_corrections(governance_id);

-- Preferred / prohibited phrasing rules
CREATE TABLE IF NOT EXISTS fazle_knowledge_phrasing (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic               TEXT NOT NULL,          -- e.g. 'training_pay', 'company_name'
    preferred_phrasing  TEXT NOT NULL,          -- what AI should say
    prohibited_phrasing TEXT,                   -- what AI must NOT say
    language            TEXT NOT NULL DEFAULT 'bn',
    status              TEXT NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active','deprecated')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_kp_topic ON fazle_knowledge_phrasing(topic);

-- ─── Seed canonical facts ──────────────────────────────────
INSERT INTO fazle_knowledge_governance (category, fact_key, fact_value, language, created_by) VALUES
    -- Company
    ('company', 'mother_company', 'আল-আকসা সিকিউরিটি অ্যান্ড লজিস্টিকস সার্ভিসেস লিমিটেড (Al-Aqsa Security & Logistics Services Ltd)', 'bn-en', 'system'),
    ('company', 'sister_concern_1', 'আল-আকসা সিকিউরিটি সার্ভিস অ্যান্ড ট্রেডিং সেন্টার (Al-Aqsa Security Service & Trading Centre)', 'bn-en', 'system'),
    ('company', 'sister_concern_2', 'আল-আকসা সার্ভেইল্যান্স ফোর্স (Al-Aqsa Surveillance Force)', 'bn-en', 'system'),
    ('company', 'established', '2014', 'en', 'system'),
    -- Offices
    ('office', 'corporate_office', 'শাহ আলম মার্কেট, পিসি রোড, নিমতলা, বন্দর – ৪১০০, চট্টগ্রাম', 'bn', 'system'),
    ('office', 'recruitment_training', 'ভিক্টোরিয়া গেইট, একে খান মোড়, পাহাড়তলী, চট্টগ্রাম', 'bn', 'system'),
    ('office', 'zonal_office', 'ইস্পাহানি কন্টেইনার ডিপো গেইট ১, খোকনের বিল্ডিং, একে খান মোড়, পাহাড়তলী, চট্টগ্রাম', 'bn', 'system'),
    -- Training
    ('training', 'training_duration', '৪৫–৯০ দিন (45–90 days)', 'bn-en', 'system'),
    ('training', 'training_pay', '১২,০০০–১৫,০০০ টাকা/মাস', 'bn', 'system'),
    -- Duty
    ('duty', 'shift_hours', '৮ ঘণ্টা শিফট (8 hours per shift)', 'bn-en', 'system'),
    ('duty', 'shift_system', 'দিনে ৩ শিফট ৩ জনে (3 shifts, 3 persons per day)', 'bn-en', 'system'),
    -- Identity
    ('identity', 'owner_name', 'Azim', 'en', 'system'),
    ('identity', 'owner_contact', '01958 122300', 'en', 'system'),
    ('identity', 'owner_website', 'al-aqsasecurity.com', 'en', 'system'),
    -- Salary
    ('salary', 'probation_salary', '১২,০০০–১৮,০০০ টাকা/মাস', 'bn', 'system'),
    ('salary', 'post_probation', 'কাজের দক্ষতার উপর নির্ভরশীল, বৃদ্ধি হবে', 'bn', 'system')
ON CONFLICT (category, fact_key, version) DO NOTHING;

-- ─── Seed phrasing rules ───────────────────────────────────
INSERT INTO fazle_knowledge_phrasing (topic, preferred_phrasing, prohibited_phrasing, language) VALUES
    ('owner_name', 'Azim', 'Md. Muradul Alam Azim, Shah Mohammad Fazle Azim, Fazle Azim', 'en'),
    ('company_name', 'আল-আকসা সিকিউরিটি অ্যান্ড লজিস্টিকস সার্ভিসেস লিমিটেড', 'আল-আকসা সিকিউরিটি সার্ভিস (as the main company name)', 'bn'),
    ('training_duration', '৪৫–৯০ দিন', '১৫ দিন, ৪৫ দিন (alone)', 'bn'),
    ('training_pay', '১২,০০০–১৫,০০০ টাকা', '১০,০০০ টাকা, ১০,০০০–১৫,০০০ টাকা', 'bn'),
    ('duty_hours', '৮ ঘণ্টা শিফটে', '৬–৮ ঘণ্টা, ১২ ঘণ্টা, ২৪ ঘণ্টা', 'bn'),
    ('owner_phone', 'SOCIAL_OWNER_PHONE env var (never hardcode)', '+8801880446111 (hardcoded)', 'en')
ON CONFLICT DO NOTHING;
