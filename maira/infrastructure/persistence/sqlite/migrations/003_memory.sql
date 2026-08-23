-- Structured memory store (milestone 4)

CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memories_category_updated
    ON memories(category, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_memories_updated
    ON memories(updated_at DESC);
