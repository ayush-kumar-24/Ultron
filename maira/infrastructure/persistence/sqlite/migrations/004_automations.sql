-- Scheduled automations: one-shot or recurring jobs Maira runs at a set time.

CREATE TABLE IF NOT EXISTS automations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    instruction TEXT NOT NULL,
    action_type TEXT NOT NULL DEFAULT 'agent',
    action_payload TEXT NOT NULL DEFAULT '{}',
    run_at TEXT NOT NULL,
    recurrence TEXT NOT NULL DEFAULT 'none',
    enabled INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'pending',
    last_run_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_automations_due
  ON automations (enabled, status, run_at);
