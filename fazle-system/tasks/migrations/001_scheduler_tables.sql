-- ============================================================
-- Fazle Task Engine — Scheduler Tables Migration
-- Idempotent: safe to run multiple times
-- ============================================================

-- Task storage table
CREATE TABLE IF NOT EXISTS fazle_tasks (
    id VARCHAR(36) PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    description TEXT DEFAULT '',
    task_type VARCHAR(50) NOT NULL DEFAULT 'reminder',
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    scheduled_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload JSONB DEFAULT '{}'::jsonb
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_fazle_tasks_status ON fazle_tasks (status);
CREATE INDEX IF NOT EXISTS idx_fazle_tasks_type ON fazle_tasks (task_type);
CREATE INDEX IF NOT EXISTS idx_fazle_tasks_created ON fazle_tasks (created_at DESC);

-- APScheduler's SQLAlchemyJobStore creates its own table (apscheduler_jobs)
-- automatically on first use. No manual creation needed.
