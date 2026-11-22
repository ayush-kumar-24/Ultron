-- Tasks, calendar, notifications, and automation history for the web contract.

ALTER TABLE tasks ADD COLUMN description TEXT NOT NULL DEFAULT '';
ALTER TABLE tasks ADD COLUMN project_id TEXT;
ALTER TABLE tasks ADD COLUMN tags TEXT NOT NULL DEFAULT '[]';
ALTER TABLE tasks ADD COLUMN estimate INTEGER NOT NULL DEFAULT 30;
ALTER TABLE tasks ADD COLUMN recurrence TEXT;
ALTER TABLE tasks ADD COLUMN completed_at TEXT;
-- The UI has three stages while the domain enum only has open/done, so the
-- stage rides alongside it and stays in sync (stage 'done' means status 'done').
ALTER TABLE tasks ADD COLUMN stage TEXT NOT NULL DEFAULT 'todo';

ALTER TABLE automations ADD COLUMN run_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE automations ADD COLUMN failure_count INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS calendar_events (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'meeting',
    project_id TEXT,
    task_id TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_calendar_events_start ON calendar_events (start_at);

CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL DEFAULT 'system',
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    read INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications (created_at DESC);

CREATE TABLE IF NOT EXISTS automation_runs (
    id TEXT PRIMARY KEY,
    automation_id TEXT NOT NULL,
    ran_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'done',
    duration_ms INTEGER NOT NULL DEFAULT 0,
    output TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_automation_runs_job ON automation_runs (automation_id, ran_at DESC);
