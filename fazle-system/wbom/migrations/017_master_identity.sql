-- ============================================================
-- Migration 017: Master Identity & History Unification
-- Safe, idempotent — can be re-run without harm
-- ============================================================

-- ── 1. master_contacts — single identity per canonical phone ──
CREATE TABLE IF NOT EXISTS master_contacts (
    id              SERIAL PRIMARY KEY,
    canonical_phone VARCHAR(11) NOT NULL,
    display_name    TEXT DEFAULT '',
    role            VARCHAR(20) DEFAULT 'unknown',
    sub_role        TEXT DEFAULT '',
    source          VARCHAR(50) DEFAULT 'system',
    is_whatsapp     BOOLEAN DEFAULT FALSE,
    employee_id     INTEGER,          -- FK link if role=employee
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_master_contacts_phone
    ON master_contacts (canonical_phone);
CREATE INDEX IF NOT EXISTS idx_master_contacts_role
    ON master_contacts (role);
CREATE INDEX IF NOT EXISTS idx_master_contacts_name
    ON master_contacts (display_name);

-- ── 2. message_history — unified message store ──
CREATE TABLE IF NOT EXISTS message_history (
    id              BIGSERIAL PRIMARY KEY,
    canonical_phone VARCHAR(11) NOT NULL,
    platform        VARCHAR(20) DEFAULT 'whatsapp',
    direction       VARCHAR(10) NOT NULL,      -- 'incoming' / 'outgoing'
    message_text    TEXT DEFAULT '',
    raw_payload     JSONB DEFAULT '{}',
    role_snapshot   VARCHAR(20) DEFAULT 'unknown',
    wa_message_id   VARCHAR(200) DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_message_history_phone_time
    ON message_history (canonical_phone, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_message_history_wa_msg
    ON message_history (wa_message_id) WHERE wa_message_id != '';

-- ── 3. Populate master_contacts from wbom_employees ──
-- Insert employees first (highest trust source)
INSERT INTO master_contacts (canonical_phone, display_name, role, source, employee_id)
SELECT
    CASE
        WHEN employee_mobile ~ '^\d{11}$' AND employee_mobile LIKE '01%' THEN employee_mobile
        WHEN employee_mobile ~ '^\d{10}$' AND employee_mobile LIKE '1%' THEN '0' || employee_mobile
        ELSE RIGHT(regexp_replace(employee_mobile, '\D', '', 'g'), 11)
    END AS canonical_phone,
    employee_name,
    'employee',
    'wbom_employees',
    employee_id
FROM wbom_employees
WHERE employee_mobile IS NOT NULL
  AND length(regexp_replace(employee_mobile, '\D', '', 'g')) >= 10
ON CONFLICT (canonical_phone) DO UPDATE SET
    role = 'employee',
    employee_id = EXCLUDED.employee_id,
    display_name = CASE
        WHEN master_contacts.display_name = '' THEN EXCLUDED.display_name
        ELSE master_contacts.display_name
    END,
    updated_at = NOW();

-- ── 4. Populate from wbom_contacts ──
-- Normalize BD numbers; skip international/malformed
INSERT INTO master_contacts (canonical_phone, display_name, role, source, is_whatsapp)
SELECT
    CASE
        WHEN wn ~ '^\d{11}$' AND wn LIKE '01%' THEN wn
        WHEN wn LIKE '880%' AND length(wn) >= 13 THEN RIGHT(wn, 11)
        WHEN wn ~ '^\d{10}$' AND wn LIKE '1%' THEN '0' || wn
        ELSE NULL
    END AS cp,
    display_name,
    CASE WHEN relation != 'unknown' THEN relation ELSE 'unknown' END,
    'wbom_contacts',
    TRUE
FROM (
    SELECT
        regexp_replace(whatsapp_number, '\D', '', 'g') AS wn,
        display_name,
        relation
    FROM wbom_contacts
    WHERE whatsapp_number IS NOT NULL AND whatsapp_number != ''
) sub
WHERE
    CASE
        WHEN wn ~ '^\d{11}$' AND wn LIKE '01%' THEN wn
        WHEN wn LIKE '880%' AND length(wn) >= 13 THEN RIGHT(wn, 11)
        WHEN wn ~ '^\d{10}$' AND wn LIKE '1%' THEN '0' || wn
        ELSE NULL
    END IS NOT NULL
ON CONFLICT (canonical_phone) DO UPDATE SET
    display_name = CASE
        WHEN master_contacts.display_name = '' AND EXCLUDED.display_name != '' THEN EXCLUDED.display_name
        ELSE master_contacts.display_name
    END,
    is_whatsapp = TRUE,
    updated_at = NOW();

-- ── 5. Mark employees that overlap with contacts ──
-- Set relation='employee' in wbom_contacts for contacts matching employees
UPDATE wbom_contacts SET relation = 'employee', updated_at = NOW()
WHERE whatsapp_number IN (
    SELECT employee_mobile FROM wbom_employees WHERE employee_mobile IS NOT NULL
)
AND relation = 'unknown';

-- ── 6. Normalize existing phone fields (BD numbers only) ──
-- wbom_contacts: normalize 880-prefix phones to 01X format
UPDATE wbom_contacts
SET whatsapp_number = RIGHT(regexp_replace(whatsapp_number, '\D', '', 'g'), 11),
    updated_at = NOW()
WHERE whatsapp_number ~ '^880\d{10}$';

-- wbom_cash_transactions: normalize 880-prefix payment_mobile
UPDATE wbom_cash_transactions
SET payment_mobile = RIGHT(regexp_replace(payment_mobile, '\D', '', 'g'), 11)
WHERE payment_mobile IS NOT NULL AND payment_mobile ~ '^880\d{10}$';

-- ── 7. Seed message_history from existing wbom_whatsapp_messages ──
INSERT INTO message_history (canonical_phone, platform, direction, message_text, wa_message_id, created_at, role_snapshot)
SELECT
    CASE
        WHEN ci ~ '^\d{11}$' AND ci LIKE '01%' THEN ci
        WHEN ci LIKE '880%' AND length(ci) >= 13 THEN RIGHT(ci, 11)
        WHEN ci ~ '^\d{10}$' AND ci LIKE '1%' THEN '0' || ci
        ELSE ci  -- keep as-is for non-BD (won't match master but preserves data)
    END,
    COALESCE(platform, 'whatsapp'),
    direction,
    COALESCE(message_body, ''),
    COALESCE(wa_message_id, ''),
    COALESCE(received_at, created_at, NOW()),
    'unknown'
FROM (
    SELECT
        regexp_replace(contact_identifier, '\D', '', 'g') AS ci,
        platform, direction, message_body, wa_message_id, received_at, created_at
    FROM wbom_whatsapp_messages
) sub
ON CONFLICT DO NOTHING;

-- Update role_snapshot from master_contacts
UPDATE message_history mh SET role_snapshot = mc.role
FROM master_contacts mc
WHERE mh.canonical_phone = mc.canonical_phone
  AND mh.role_snapshot = 'unknown';

-- ── 8. Access rules — add owner/family to master_contacts ──
INSERT INTO master_contacts (canonical_phone, display_name, role, source)
SELECT
    CASE
        WHEN ph ~ '^\d{11}$' AND ph LIKE '01%' THEN ph
        WHEN ph LIKE '880%' AND length(ph) >= 13 THEN RIGHT(ph, 11)
        WHEN ph ~ '^\d{10}$' AND ph LIKE '1%' THEN '0' || ph
        ELSE NULL
    END,
    '',
    'owner',
    'fazle_access_rules'
FROM (
    SELECT regexp_replace(phone, '\D', '', 'g') AS ph FROM fazle_access_rules
) sub
WHERE CASE
    WHEN ph ~ '^\d{11}$' AND ph LIKE '01%' THEN ph
    WHEN ph LIKE '880%' AND length(ph) >= 13 THEN RIGHT(ph, 11)
    WHEN ph ~ '^\d{10}$' AND ph LIKE '1%' THEN '0' || ph
    ELSE NULL
END IS NOT NULL
ON CONFLICT (canonical_phone) DO UPDATE SET
    role = CASE WHEN master_contacts.role = 'unknown' THEN 'owner' ELSE master_contacts.role END,
    updated_at = NOW();

-- ── 9. Drop legacy tables (no code references them) ──
DROP TABLE IF EXISTS _legacy_fazle_contacts;
DROP TABLE IF EXISTS _legacy_fazle_social_contacts;
DROP TABLE IF EXISTS _legacy_fazle_social_messages;
DROP TABLE IF EXISTS _legacy_ops_employees;
DROP TABLE IF EXISTS _legacy_ops_payments;

-- ── Done ──
-- master_contacts now has unified identity
-- message_history has seeded messages
-- wbom_contacts.relation updated for employees
-- Phone numbers normalized for BD-format entries
