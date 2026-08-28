-- Columns the web API contract needs that the original schemas omitted.

ALTER TABLE conversations ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0;
ALTER TABLE conversations ADD COLUMN project_id TEXT;

ALTER TABLE memories ADD COLUMN source TEXT NOT NULL DEFAULT '';
ALTER TABLE memories ADD COLUMN confidence REAL NOT NULL DEFAULT 0.9;
ALTER TABLE memories ADD COLUMN importance TEXT NOT NULL DEFAULT 'medium';
ALTER TABLE memories ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0;
ALTER TABLE memories ADD COLUMN last_accessed TEXT;
ALTER TABLE memories ADD COLUMN access_count INTEGER NOT NULL DEFAULT 0;
