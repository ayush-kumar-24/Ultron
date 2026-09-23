-- Older builds saved plural / capitalised memory categories ("conversations",
-- "Projects"). Normalise them to the MemoryCategory values, and anything unknown
-- becomes "note" so no row can break loading.

UPDATE memories SET category = lower(trim(category));

UPDATE memories
SET category = substr(category, 1, length(category) - 1)
WHERE category IN ('preferences', 'conversations', 'tasks', 'notes', 'ideas', 'projects');

UPDATE memories
SET category = 'note'
WHERE category NOT IN ('preference', 'conversation', 'task', 'note', 'idea', 'project');
