-- telephony_events: idempotency + audit table for inbound Twilio webhooks
-- Run: psql -U postgres -f schema.sql

CREATE TABLE IF NOT EXISTS telephony_events (
    id              BIGSERIAL PRIMARY KEY,
    call_sid        VARCHAR(64) NOT NULL UNIQUE,
    workflow_id     INTEGER NOT NULL,
    from_number     VARCHAR(32),
    to_number       VARCHAR(32),
    call_status     VARCHAR(32),
    direction       VARCHAR(16) DEFAULT 'inbound',
    status          VARCHAR(24) NOT NULL DEFAULT 'received'
                        CHECK (status IN ('received', 'processing', 'completed', 'failed', 'permanently_failed')),
    payload         JSONB NOT NULL DEFAULT '{}',
    error_message   TEXT,
    locked_at       TIMESTAMPTZ,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    request_id      VARCHAR(36),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_telephony_events_call_sid ON telephony_events (call_sid);
CREATE INDEX IF NOT EXISTS idx_telephony_events_workflow_id ON telephony_events (workflow_id);
CREATE INDEX IF NOT EXISTS idx_telephony_events_status ON telephony_events (status);
CREATE INDEX IF NOT EXISTS idx_telephony_events_created_at ON telephony_events (created_at);
CREATE INDEX IF NOT EXISTS idx_telephony_events_locked_at ON telephony_events (locked_at) WHERE locked_at IS NOT NULL;

-- Auto-update updated_at on row change
CREATE OR REPLACE FUNCTION update_telephony_events_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_telephony_events_updated_at ON telephony_events;
CREATE TRIGGER trg_telephony_events_updated_at
    BEFORE UPDATE ON telephony_events
    FOR EACH ROW
    EXECUTE FUNCTION update_telephony_events_updated_at();

-- Migration: add columns if upgrading from v1
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'telephony_events' AND column_name = 'locked_at') THEN
        ALTER TABLE telephony_events ADD COLUMN locked_at TIMESTAMPTZ;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'telephony_events' AND column_name = 'retry_count') THEN
        ALTER TABLE telephony_events ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'telephony_events' AND column_name = 'request_id') THEN
        ALTER TABLE telephony_events ADD COLUMN request_id VARCHAR(36);
    END IF;
    -- Widen status CHECK if upgrading
    BEGIN
        ALTER TABLE telephony_events DROP CONSTRAINT IF EXISTS telephony_events_status_check;
        ALTER TABLE telephony_events ADD CONSTRAINT telephony_events_status_check
            CHECK (status IN ('received', 'processing', 'completed', 'failed', 'permanently_failed'));
    EXCEPTION WHEN OTHERS THEN NULL;
    END;
END $$;
