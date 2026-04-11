-- ============================================================
-- Knowledge Fact Versioning Migration — 004
-- Adds single-source-of-truth versioning to fazle_owner_knowledge.
-- Each fact has a fact_id, version, is_active flag.
-- Only ONE active version per fact_id at any time.
-- Idempotent: safe to run multiple times.
-- ============================================================

-- ── New columns ────────────────────────────────────────────
ALTER TABLE fazle_owner_knowledge ADD COLUMN IF NOT EXISTS fact_id   VARCHAR(300);
ALTER TABLE fazle_owner_knowledge ADD COLUMN IF NOT EXISTS version   INT NOT NULL DEFAULT 1;
ALTER TABLE fazle_owner_knowledge ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE fazle_owner_knowledge ADD COLUMN IF NOT EXISTS supersedes UUID;

-- ── Backfill: old rows get fact_id = category:key, version 1, active ──
UPDATE fazle_owner_knowledge
SET    fact_id = category || ':' || key
WHERE  fact_id IS NULL;

-- Make fact_id NOT NULL after backfill
ALTER TABLE fazle_owner_knowledge ALTER COLUMN fact_id SET NOT NULL;

-- ── Indexes ────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_knowledge_fact_id
    ON fazle_owner_knowledge(fact_id);

CREATE INDEX IF NOT EXISTS idx_knowledge_active
    ON fazle_owner_knowledge(is_active);

CREATE INDEX IF NOT EXISTS idx_knowledge_fact_active
    ON fazle_owner_knowledge(fact_id, is_active);

-- ── Drop old UNIQUE and upsert that assumed one row per (category, key) ──
-- We keep the old constraint initially; the new versioned_upsert
-- handles deactivation + new row insertion. We relax the unique
-- constraint to allow multiple rows per (category, key) for history.
-- NOTE: wrapped in DO block so it's safe if constraint already dropped.
DO $$ BEGIN
    ALTER TABLE fazle_owner_knowledge DROP CONSTRAINT IF EXISTS fazle_owner_knowledge_category_key_key;
EXCEPTION WHEN undefined_object THEN NULL;
END $$;

-- Unique: only ONE active row per fact_id
CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_fact_active
    ON fazle_owner_knowledge(fact_id) WHERE is_active = TRUE;

-- ── New versioned upsert function ──────────────────────────
CREATE OR REPLACE FUNCTION upsert_owner_knowledge(
    p_category  VARCHAR,
    p_subcategory VARCHAR,
    p_key       VARCHAR,
    p_value     TEXT,
    p_language  VARCHAR DEFAULT 'en',
    p_confidence REAL   DEFAULT 1.0,
    p_source    VARCHAR DEFAULT 'owner_chat',
    p_metadata  JSONB  DEFAULT '{}'
) RETURNS TABLE(result_id UUID, result_action VARCHAR) AS $$
DECLARE
    v_fact_id    VARCHAR;
    v_old_id     UUID;
    v_old_value  TEXT;
    v_old_ver    INT;
    v_new_id     UUID;
BEGIN
    v_fact_id := p_category || ':' || p_key;

    -- Find current active fact
    SELECT id, value, version
    INTO   v_old_id, v_old_value, v_old_ver
    FROM   fazle_owner_knowledge
    WHERE  fact_id = v_fact_id AND is_active = TRUE
    LIMIT  1;

    -- Conflict safety: skip if value unchanged
    IF v_old_id IS NOT NULL AND v_old_value = p_value THEN
        result_id     := v_old_id;
        result_action := 'skipped_duplicate';
        RETURN NEXT;
        RETURN;
    END IF;

    -- Deactivate old version
    IF v_old_id IS NOT NULL THEN
        UPDATE fazle_owner_knowledge
        SET    is_active = FALSE, updated_at = NOW()
        WHERE  id = v_old_id;
    END IF;

    -- Insert new active version
    INSERT INTO fazle_owner_knowledge
        (category, subcategory, key, value, language, confidence, source, metadata,
         fact_id, version, is_active, supersedes)
    VALUES
        (p_category, p_subcategory, p_key, p_value, p_language, p_confidence, p_source, p_metadata,
         v_fact_id,
         COALESCE(v_old_ver, 0) + 1,
         TRUE,
         v_old_id)
    RETURNING id INTO v_new_id;

    result_id     := v_new_id;
    result_action := CASE WHEN v_old_id IS NOT NULL THEN 'updated' ELSE 'created' END;
    RETURN NEXT;
    RETURN;
END;
$$ LANGUAGE plpgsql;
