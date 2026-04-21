-- ============================================================
-- Migration 021 — WhatsApp Candidate Funnel (Sprint-3)
-- Tables: wbom_candidates, wbom_candidate_conversations,
--         wbom_recruitment_reminders
-- ============================================================

-- ── 1. Candidates table ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS wbom_candidates (
    candidate_id        BIGSERIAL PRIMARY KEY,
    phone               VARCHAR(20)  NOT NULL,
    full_name           VARCHAR(100),
    age                 INT,
    area                VARCHAR(100),
    job_preference      VARCHAR(50),   -- Escort|Seal-man|Security Guard|Supervisor|Labor
    experience_years    INT,
    available_join_date DATE,

    -- Funnel state
    funnel_stage        VARCHAR(30) NOT NULL DEFAULT 'new',
    -- new → collecting → scored → assigned → contacted → interviewed → hired|rejected|dropped
    collection_step     VARCHAR(30)  DEFAULT 'name',   -- next question waiting

    -- Scoring
    score               INT         NOT NULL DEFAULT 0,
    score_bucket        VARCHAR(10) NOT NULL DEFAULT 'cold',  -- hot|warm|cold

    -- Recruiter
    assigned_recruiter  VARCHAR(80),
    assigned_at         TIMESTAMPTZ,

    -- Contact tracking
    last_contact_at     TIMESTAMPTZ,
    next_follow_up_at   TIMESTAMPTZ,

    -- Source
    source              VARCHAR(30) DEFAULT 'whatsapp',
    source_message      TEXT,

    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_candidate_stage CHECK (
        funnel_stage IN ('new','collecting','scored','assigned',
                         'contacted','interviewed','hired','rejected','dropped')
    ),
    CONSTRAINT chk_candidate_score CHECK (score BETWEEN 0 AND 100),
    CONSTRAINT chk_score_bucket    CHECK (score_bucket IN ('hot','warm','cold'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_candidates_phone
    ON wbom_candidates (phone);
CREATE INDEX IF NOT EXISTS idx_candidates_stage
    ON wbom_candidates (funnel_stage);
CREATE INDEX IF NOT EXISTS idx_candidates_recruiter
    ON wbom_candidates (assigned_recruiter);
CREATE INDEX IF NOT EXISTS idx_candidates_bucket
    ON wbom_candidates (score_bucket);
CREATE INDEX IF NOT EXISTS idx_candidates_follow_up
    ON wbom_candidates (next_follow_up_at)
    WHERE next_follow_up_at IS NOT NULL;


-- ── 2. Conversation log ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS wbom_candidate_conversations (
    conv_id         BIGSERIAL PRIMARY KEY,
    candidate_id    BIGINT      NOT NULL
                    REFERENCES wbom_candidates(candidate_id) ON DELETE CASCADE,
    step            VARCHAR(30) NOT NULL,   -- which intake step this message answers
    direction       VARCHAR(10) NOT NULL DEFAULT 'inbound',  -- inbound|outbound
    message_text    TEXT        NOT NULL,
    collected_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conv_candidate
    ON wbom_candidate_conversations (candidate_id);


-- ── 3. Recruitment reminders ─────────────────────────────────
CREATE TABLE IF NOT EXISTS wbom_recruitment_reminders (
    reminder_id     BIGSERIAL PRIMARY KEY,
    candidate_id    BIGINT      NOT NULL
                    REFERENCES wbom_candidates(candidate_id) ON DELETE CASCADE,
    due_at          TIMESTAMPTZ NOT NULL,
    reason          VARCHAR(100) NOT NULL,  -- no_response_48h|follow_up|interview_tomorrow
    status          VARCHAR(20)  NOT NULL DEFAULT 'pending',  -- pending|sent|dismissed
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_reminder_status CHECK (status IN ('pending','sent','dismissed'))
);

CREATE INDEX IF NOT EXISTS idx_reminders_due
    ON wbom_recruitment_reminders (due_at)
    WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_reminders_candidate
    ON wbom_recruitment_reminders (candidate_id);
