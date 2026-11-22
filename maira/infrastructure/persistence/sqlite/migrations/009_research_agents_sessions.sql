-- Research sessions, agent execution history, and focus/work sessions for the web UI.

CREATE TABLE IF NOT EXISTS research_sessions (
    id TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    step INTEGER NOT NULL DEFAULT 0,
    sources INTEGER NOT NULL DEFAULT 0,
    project_id TEXT,
    report TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_research_created ON research_sessions (created_at DESC);

CREATE TABLE IF NOT EXISTS agent_executions (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    task TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    started_at TEXT NOT NULL,
    ended_at TEXT,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_agent_executions_agent ON agent_executions (agent_id, started_at DESC);

CREATE TABLE IF NOT EXISTS work_sessions (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL DEFAULT 'work',
    project TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL,
    minutes INTEGER NOT NULL DEFAULT 0,
    recorded INTEGER NOT NULL DEFAULT 0,
    summary TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_work_sessions_started ON work_sessions (started_at DESC);
