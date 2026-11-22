// Demo database. Seeded once, persisted to localStorage so interactions survive reloads.
// Replace the transport (api.use(fetchTransport)) and none of this is loaded.
const KEY = 'ultron.db.v1';
const now = Date.now();
const ago = (min) => new Date(now - min * 60000).toISOString();
const at = (dayOffset, hour, minute = 0) => { const d = new Date(now); d.setDate(d.getDate() + dayOffset); d.setHours(hour, minute, 0, 0); return d.toISOString(); };
const id = (p, n) => `${p}_${n}`;

export function seed() {
  const db = {
    user: { id: 'u_1', name: 'Ayush', initials: 'AY', email: 'info@goxl.in', timezone: 'Asia/Kolkata', language: 'English', role: 'Founder, GoXL' },

    projects: [
      { id: 'p_ultron', name: 'Ultron', description: 'Personal AI operating system. Offline-first, self-extending.', progress: 42, color: 'think', status: 'active', updatedAt: ago(12), goals: ['g_ultron'], tags: ['ai', 'desktop', 'python'] },
      { id: 'p_goxl', name: 'GoXL', description: 'Ally AI diagnosis agent platform and landing experience.', progress: 67, color: 'info', status: 'active', updatedAt: ago(95), goals: ['g_goxl'], tags: ['product', 'saas'] },
      { id: 'p_research', name: 'AI Research', description: 'Local model benchmarks, agent architectures, memory systems.', progress: 23, color: 'speak', status: 'active', updatedAt: ago(1440), goals: [], tags: ['research'] },
      { id: 'p_personal', name: 'Personal Development', description: 'Learning sessions, reading, and habits.', progress: 10, color: 'ok', status: 'active', updatedAt: ago(4300), goals: [], tags: ['learning'] },
    ],

    goals: [
      { id: 'g_ultron', title: 'Build Ultron', objective: 'Ship a usable personal AI OS that runs on my laptop.', deadline: at(120, 18), progress: 42, projectId: 'p_ultron',
        milestones: [{ t: 'Foundation', done: true }, { t: 'Memory', done: true }, { t: 'Agent system', done: false, current: true }, { t: 'Automation', done: false }, { t: 'Voice', done: false }],
        recommendation: 'Agent runtime is the critical path. Finish the tool interface before the factory — every agent depends on it.' },
      { id: 'g_goxl', title: 'Ally production-ready', objective: 'Backend stable, billing live, diagnosis engine verified.', deadline: at(45, 18), progress: 67, projectId: 'p_goxl',
        milestones: [{ t: 'Auth', done: true }, { t: 'Billing', done: true }, { t: 'Diagnosis engine', done: false, current: true }, { t: 'Load test', done: false }],
        recommendation: 'Two Alembic migrations are unapplied. Resolve the revision mismatch before load testing.' },
      { id: 'g_learn', title: 'Learn Computer Networks', objective: 'Finish the course and build one network tool.', deadline: at(60, 18), progress: 15, projectId: 'p_personal',
        milestones: [{ t: 'Layers and protocols', done: true }, { t: 'TCP deep-dive', done: false, current: true }, { t: 'Build a packet tool', done: false }],
        recommendation: 'You learn best in 40-minute evening sessions. Three this week would keep the streak.' },
    ],

    tasks: [
      { id: 't_1', title: 'Complete backend architecture', description: 'Finalise service boundaries and the tool interface.', priority: 'high', status: 'todo', due: at(0, 18), projectId: 'p_ultron', tags: ['architecture'], estimate: 120, createdAt: ago(3000) },
      { id: 't_2', title: 'Review project roadmap', priority: 'medium', status: 'todo', due: at(0, 11), projectId: 'p_ultron', tags: ['planning'], estimate: 30, createdAt: ago(2000) },
      { id: 't_3', title: 'Research agent architecture', priority: 'high', status: 'in_progress', due: at(1, 17), projectId: 'p_research', tags: ['research'], estimate: 90, createdAt: ago(1800) },
      { id: 't_4', title: 'Prepare weekly plan', priority: 'low', status: 'todo', due: at(2, 9), projectId: null, tags: [], estimate: 20, recurrence: 'weekly', createdAt: ago(1500) },
      { id: 't_5', title: 'Fix Alembic revision mismatch', description: 'alembic_version points at a missing revision; reconcile with Supabase migrations.', priority: 'high', status: 'todo', due: at(1, 12), projectId: 'p_goxl', tags: ['backend', 'db'], estimate: 60, createdAt: ago(900) },
      { id: 't_6', title: 'Write Ally pricing copy', priority: 'medium', status: 'done', due: at(-1, 15), projectId: 'p_goxl', tags: ['copy'], completedAt: ago(180), createdAt: ago(4000) },
      { id: 't_7', title: 'Benchmark Qwen 7B on the laptop', priority: 'medium', status: 'done', due: at(-1, 20), projectId: 'p_research', tags: ['llm'], completedAt: ago(1300), createdAt: ago(5000) },
      { id: 't_8', title: 'Read TCP congestion control chapter', priority: 'low', status: 'todo', due: at(3, 21), projectId: 'p_personal', tags: ['learning'], estimate: 40, createdAt: ago(600) },
      { id: 't_9', title: 'Draft memory retention policy', priority: 'medium', status: 'todo', due: null, projectId: 'p_ultron', tags: ['memory'], estimate: 45, createdAt: ago(400) },
      { id: 't_10', title: 'Reply to investor intro', priority: 'high', status: 'done', due: at(-2, 10), projectId: 'p_goxl', tags: [], completedAt: ago(2900), createdAt: ago(3500) },
      { id: 't_11', title: 'Set up wake-word engine spike', priority: 'medium', status: 'todo', due: at(5, 16), projectId: 'p_ultron', tags: ['voice'], estimate: 90, createdAt: ago(300) },
      { id: 't_12', title: 'Weekly roadmap review', priority: 'medium', status: 'done', due: at(0, 9), projectId: 'p_ultron', tags: ['planning'], completedAt: ago(190), createdAt: ago(10000) },
    ],

    reminders: [
      { id: 'r_1', text: 'Finish the backend architecture', at: at(1, 9), taskId: 't_1', createdAt: ago(60) },
      { id: 'r_2', text: 'Review the weekly roadmap', at: at(7, 9), recurrence: 'Every Monday · 9:00 AM', createdAt: ago(4000) },
    ],

    events: [
      { id: 'e_1', title: 'GoXL standup', start: at(0, 10), end: at(0, 10, 30), type: 'meeting', projectId: 'p_goxl' },
      { id: 'e_2', title: 'Deep work · Ultron agents', start: at(0, 14), end: at(0, 16), type: 'focus', projectId: 'p_ultron' },
      { id: 'e_3', title: 'Investor call', start: at(1, 11), end: at(1, 11, 45), type: 'meeting' },
      { id: 'e_4', title: 'Ally diagnosis review', start: at(1, 15), end: at(1, 16), type: 'meeting', projectId: 'p_goxl' },
      { id: 'e_5', title: 'Design sync', start: at(1, 17), end: at(1, 17, 30), type: 'meeting' },
      { id: 'e_6', title: 'Backend architecture due', start: at(0, 18), end: at(0, 18), type: 'deadline', taskId: 't_1' },
      { id: 'e_7', title: 'Learning · Computer Networks', start: at(2, 20), end: at(2, 21), type: 'focus', projectId: 'p_personal' },
      { id: 'e_8', title: 'Week planning', start: at(3, 9), end: at(3, 9, 30), type: 'reminder' },
      { id: 'e_9', title: 'Alembic fix due', start: at(1, 12), end: at(1, 12), type: 'deadline', taskId: 't_5' },
      { id: 'e_10', title: 'Team retro', start: at(4, 16), end: at(4, 17), type: 'meeting' },
      { id: 'e_11', title: 'Deep work · Memory policy', start: at(-1, 15), end: at(-1, 17), type: 'focus', projectId: 'p_ultron' },
    ],

    memories: [
      { id: 'm_1', text: 'Prefers concise, technical explanations. Skip preambles.', category: 'preferences', source: 'Conversation', confidence: .97, importance: 'high', createdAt: ago(40000), lastAccessed: ago(30), pinned: true, accessCount: 212 },
      { id: 'm_2', text: 'Is building Ultron — a personal AI operating system that runs locally on a Windows laptop.', category: 'projects', source: 'Conversation', confidence: .99, importance: 'high', createdAt: ago(60000), lastAccessed: ago(12), pinned: true, accessCount: 540 },
      { id: 'm_3', text: 'Works on multiple AI systems in parallel: Ultron, Ally (GoXL), and research benchmarks.', category: 'work', source: 'Inferred', confidence: .91, importance: 'medium', createdAt: ago(50000), lastAccessed: ago(200), pinned: false, accessCount: 88 },
      { id: 'm_4', text: 'Prefers local models whenever possible; cloud only when the task needs it.', category: 'preferences', source: 'Explicit ("Remember that…")', confidence: .98, importance: 'high', createdAt: ago(20000), lastAccessed: ago(400), pinned: true, accessCount: 64 },
      { id: 'm_5', text: 'Target hardware: Intel i5-1335U, 16 GB RAM, Iris Xe. Quantized 7B models are the ceiling.', category: 'learned', source: 'Document · Product Vision', confidence: .95, importance: 'medium', createdAt: ago(15000), lastAccessed: ago(1300), pinned: false, accessCount: 31 },
      { id: 'm_6', text: 'Razorpay is the payment provider for Ally billing. GST is 18%.', category: 'projects', source: 'Conversation', confidence: .96, importance: 'medium', createdAt: ago(9000), lastAccessed: ago(2800), pinned: false, accessCount: 19 },
      { id: 'm_7', text: 'Ally backend uses both Supabase migrations and Alembic; the alembic_version is currently out of sync.', category: 'projects', source: 'Research session', confidence: .9, importance: 'high', createdAt: ago(900), lastAccessed: ago(50), pinned: false, accessCount: 7 },
      { id: 'm_8', text: 'Evening deep-work sessions (after 8 PM) are the most productive.', category: 'personal', source: 'Inferred from sessions', confidence: .82, importance: 'medium', createdAt: ago(30000), lastAccessed: ago(700), pinned: false, accessCount: 44 },
      { id: 'm_9', text: 'Last time the Ally backend failed, the fix was restarting Docker and rebuilding the API image.', category: 'learned', source: 'Episodic · Work session', confidence: .88, importance: 'medium', createdAt: ago(12000), lastAccessed: ago(3000), pinned: false, accessCount: 12 },
      { id: 'm_10', text: 'Rahul (co-founder) handles sales; loop him in on anything customer-facing.', category: 'people', source: 'Conversation', confidence: .93, importance: 'high', createdAt: ago(45000), lastAccessed: ago(5000), pinned: false, accessCount: 26 },
      { id: 'm_11', text: 'Wants Ultron to verify outcomes before saying "done".', category: 'preferences', source: 'Document · Product Vision', confidence: .97, importance: 'high', createdAt: ago(14000), lastAccessed: ago(100), pinned: false, accessCount: 73 },
      { id: 'm_12', text: 'Currently learning Computer Networks; prefers 40-minute sessions.', category: 'personal', source: 'Learning session', confidence: .86, importance: 'low', createdAt: ago(7000), lastAccessed: ago(2000), pinned: false, accessCount: 9 },
      { id: 'm_13', text: 'Design taste: premium, minimal, monochrome; dislikes generic AI glow and dashboards.', category: 'preferences', source: 'Conversation · Design review', confidence: .94, importance: 'medium', createdAt: ago(500), lastAccessed: ago(20), pinned: false, accessCount: 15 },
      { id: 'm_14', text: 'Key decision: Ultron UI ships as a dependency-free web layer so it can embed in the PySide6 shell.', category: 'conversations', source: 'Conversation · Architecture', confidence: .92, importance: 'high', createdAt: ago(60), lastAccessed: ago(5), pinned: false, accessCount: 2 },
    ],
    memoryStats: { total: 8421, recall: 94, learnedToday: 12 },

    knowledge: [
      { id: 'k_1', title: 'Agent Architecture Review', type: 'pdf', source: 'Upload', size: 2_340_000, tags: ['agents', 'architecture'], status: 'ready', createdAt: ago(2), summary: 'Compares orchestrator-worker, blackboard, and pipeline topologies. Recommends orchestrator-worker with a shared tool registry for Ultron-scale systems.', pages: 24 },
      { id: 'k_2', title: 'ULTRON Product Vision', type: 'doc', source: 'Docs folder', size: 188_000, tags: ['ultron', 'vision'], status: 'ready', createdAt: ago(30000), summary: 'North-star specification: local-first, offline-capable, self-extending personal AI OS with verify-before-claiming-success as a core principle.', pages: 18 },
      { id: 'k_3', title: 'ULTRON Build Roadmap', type: 'doc', source: 'Docs folder', size: 96_000, tags: ['ultron', 'roadmap'], status: 'ready', createdAt: ago(30000), summary: 'Capability-based roadmap in 22 stages, from foundation stabilisation to the full personal AI OS.', pages: 9 },
      { id: 'k_4', title: 'Local LLM Benchmarks — August', type: 'note', source: 'Note', size: 12_000, tags: ['llm', 'benchmarks'], status: 'ready', createdAt: ago(1500), summary: 'Qwen2.5-7B Q4 averages 11 tok/s on the i5; Llama 3.1 8B Q4 hits 8 tok/s. Both usable for fast-path intent with streaming.' },
      { id: 'k_5', title: 'Whisper.cpp streaming guide', type: 'link', source: 'github.com/ggerganov/whisper.cpp', size: 0, tags: ['voice', 'stt'], status: 'ready', createdAt: ago(9000), summary: 'Streaming transcription with VAD windows; the stream example is the reference for the Ultron voice pipeline.' },
      { id: 'k_6', title: 'Ally Phase 4 Diagnosis Engine Report', type: 'pdf', source: 'Upload', size: 4_100_000, tags: ['goxl', 'ally'], status: 'ready', createdAt: ago(20000), summary: 'Architecture and evaluation of the Ally diagnosis engine; 87% agreement with expert review on the test set.', pages: 41 },
      { id: 'k_7', title: 'Memory system design sketch', type: 'image', source: 'Screenshot', size: 640_000, tags: ['memory'], status: 'ready', createdAt: ago(4000), summary: 'Whiteboard of short-term, long-term, semantic, episodic and workflow memory tiers.' },
      { id: 'k_8', title: 'tool_registry.py', type: 'code', source: 'Ultron repo', size: 8_400, tags: ['ultron', 'tools'], status: 'ready', createdAt: ago(700), summary: 'Unified tool interface: name, schema, permissions, risk level, timeout, verification hook.' },
      { id: 'k_9', title: 'Piper TTS voices', type: 'link', source: 'github.com/rhasspy/piper', size: 0, tags: ['voice', 'tts'], status: 'ready', createdAt: ago(11000), summary: 'Fast local neural TTS; en_US-lessac-medium is the best balance of quality and latency on CPU.' },
      { id: 'k_10', title: 'Competitor notes — personal AI assistants', type: 'note', source: 'Note', size: 22_000, tags: ['research', 'market'], status: 'processing', progress: 62, createdAt: ago(4) },
    ],

    conversations: [
      { id: 'c_1', title: 'Ally backend failing on startup', projectId: 'p_goxl', updatedAt: ago(62), pinned: false },
      { id: 'c_2', title: 'Ultron memory retention', projectId: 'p_ultron', updatedAt: ago(240), pinned: true },
      { id: 'c_3', title: 'Agent architecture options', projectId: 'p_research', updatedAt: ago(1500), pinned: false },
      { id: 'c_4', title: 'Weekly planning', projectId: null, updatedAt: ago(3000), pinned: false },
      { id: 'c_5', title: 'GoXL strategy', projectId: 'p_goxl', updatedAt: ago(60), pinned: false },
    ],
    messages: {
      c_1: [
        { id: 'mg_1', role: 'user', text: 'Open my Ally project and check why the backend is failing.', at: ago(70) },
        { id: 'mg_2', role: 'assistant', text: 'Checked the container logs. The API is failing at startup because `alembic_version` points at revision `9f3c2a` which no longer exists in the migrations folder.\n\nTwo options:\n- **Stamp** the database to the latest real revision (fast, safe if the schema already matches).\n- **Recreate** the missing revision as an empty migration (keeps history honest).\n\nI\'d stamp it — the Supabase migrations already applied the schema [1].', at: ago(68),
          tools: [{ name: 'Read container logs', status: 'done', detail: 'docker logs ally-api --tail 200', ms: 820 }, { name: 'Inspect migrations', status: 'done', detail: 'alembic/versions · 14 files', ms: 310 }, { name: 'Checked memory', status: 'done', detail: 'Recalled: dual migration systems (m_7)', ms: 40 }],
          citations: [{ n: 1, title: 'Ally dual migration systems', source: 'Memory · m_7' }] },
        { id: 'mg_3', role: 'user', text: 'Stamp it, then run the API tests.', at: ago(64) },
        { id: 'mg_4', role: 'assistant', text: 'Stamped to `b81e77` and rebuilt the image. 42 API tests passed, 0 failed. The backend is up and responding on :8000.\n\nSaved to memory: the fix for this failure mode.', at: ago(62),
          tools: [{ name: 'alembic stamp head', status: 'done', ms: 1400 }, { name: 'Rebuild API image', status: 'done', ms: 41000 }, { name: 'Run API tests', status: 'done', detail: '42 passed', ms: 18000 }, { name: 'Verify endpoint', status: 'done', detail: 'GET /health → 200', ms: 120 }],
          memoryCreated: 'Fix for Alembic revision mismatch: stamp head, rebuild image.' },
      ],
      c_2: [
        { id: 'mg_5', role: 'user', text: 'How should Ultron decide which memories to keep?', at: ago(250) },
        { id: 'mg_6', role: 'assistant', text: 'Score each memory on **importance × recency × access frequency**, with explicit user pins as an override.\n\n- Keep everything for 30 days.\n- After that, drop memories below the score threshold unless pinned.\n- Never auto-delete preferences or people.\n\nWant me to draft this as a retention policy task?', at: ago(248) },
        { id: 'mg_7', role: 'user', text: 'Yes, create the task.', at: ago(241) },
        { id: 'mg_8', role: 'assistant', text: 'Created **Draft memory retention policy** in Ultron.', at: ago(240), taskCreated: { id: 't_9', title: 'Draft memory retention policy' } },
      ],
      c_3: [
        { id: 'mg_9', role: 'user', text: 'Compare orchestrator-worker vs blackboard for Ultron agents.', at: ago(1510) },
        { id: 'mg_10', role: 'assistant', text: 'Orchestrator-worker fits Ultron better: one planner that delegates to specialist agents keeps permissions and verification in one place [1]. Blackboard is more flexible but makes "who did this and why" hard to explain — which conflicts with your explainability principle [2].', at: ago(1500), citations: [{ n: 1, title: 'Agent Architecture Review', source: 'Knowledge · k_1' }, { n: 2, title: 'ULTRON Product Vision §4.6', source: 'Knowledge · k_2' }] },
      ],
      c_4: [
        { id: 'mg_11', role: 'user', text: 'Plan my week.', at: ago(3010) },
        { id: 'mg_12', role: 'assistant', text: 'You have 5 meetings and roughly 14 free hours. I blocked two deep-work sessions for Ultron and kept Friday afternoon open. Three tasks are overdue risk — I moved them to Tuesday.', at: ago(3000) },
      ],
      c_5: [
        { id: 'mg_13', role: 'user', text: 'What should GoXL focus on this month?', at: ago(65) },
        { id: 'mg_14', role: 'assistant', text: 'Finish the diagnosis engine verification before any growth work. Billing is live, auth is done — the engine is the only thing standing between you and a production claim you can defend.', at: ago(60) },
      ],
    },

    agents: [
      { id: 'a_core', name: 'Ultron Core', role: 'Orchestrator', status: 'ready', description: 'Understands goals, plans, delegates, verifies and reports.', capabilities: ['planning', 'delegation', 'verification', 'memory'], executions: 1248, lastRun: ago(3), model: 'local · qwen2.5-7b' },
      { id: 'a_memory', name: 'Memory Agent', role: 'Persistent memory', status: 'idle', description: 'Stores, scores, deduplicates and retrieves memories.', capabilities: ['store', 'recall', 'rank', 'lifecycle'], executions: 3102, lastRun: ago(12), model: 'local' },
      { id: 'a_research', name: 'Research Agent', role: 'Deep research', status: 'working', description: 'Searches, reads, compares and synthesises sources.', capabilities: ['web search', 'read', 'compare', 'synthesise'], executions: 86, lastRun: ago(1), model: 'cloud · optional', currentTask: 'Competitor notes — personal AI assistants' },
      { id: 'a_planning', name: 'Planning Agent', role: 'Plans and schedules', status: 'ready', description: 'Turns goals into plans; fits tasks into real calendar time.', capabilities: ['plan', 'schedule', 'prioritise'], executions: 412, lastRun: ago(190), model: 'local' },
      { id: 'a_task', name: 'Task Agent', role: 'Tasks and reminders', status: 'ready', description: 'Creates and updates tasks and reminders from natural language.', capabilities: ['create', 'update', 'remind', 'recurrence'], executions: 920, lastRun: ago(60), model: 'fast path' },
      { id: 'a_knowledge', name: 'Knowledge Agent', role: 'Documents and knowledge', status: 'idle', description: 'Ingests, chunks, embeds and summarises documents.', capabilities: ['ingest', 'summarise', 'embed', 'graph'], executions: 233, lastRun: ago(4), model: 'local · embeddings' },
      { id: 'a_auto', name: 'Automation Agent', role: 'Scheduled workflows', status: 'monitoring', description: 'Runs triggers and scheduled behaviours.', capabilities: ['schedule', 'trigger', 'run', 'retry'], executions: 1560, lastRun: ago(25), model: 'fast path' },
      { id: 'a_system', name: 'System Agent', role: 'Computer actions', status: 'ready', description: 'Permitted desktop, file, terminal and process actions.', capabilities: ['desktop', 'files', 'terminal', 'processes'], executions: 678, lastRun: ago(62), model: 'fast path', permissions: ['READ', 'WRITE', 'EXECUTE'] },
    ],
    executions: [
      { id: 'x_1', agentId: 'a_research', task: 'Competitor notes — personal AI assistants', status: 'running', startedAt: ago(4), steps: ['Search sources', 'Read 6 pages', 'Compare'] },
      { id: 'x_2', agentId: 'a_system', task: 'Rebuild Ally API image', status: 'done', startedAt: ago(63), endedAt: ago(62), ms: 41000 },
      { id: 'x_3', agentId: 'a_system', task: 'Run API tests', status: 'done', startedAt: ago(62), endedAt: ago(62), ms: 18000 },
      { id: 'x_4', agentId: 'a_memory', task: 'Store: Alembic fix', status: 'done', startedAt: ago(62), endedAt: ago(62), ms: 30 },
      { id: 'x_5', agentId: 'a_auto', task: 'Evening summary', status: 'done', startedAt: ago(25), endedAt: ago(25), ms: 2200 },
      { id: 'x_6', agentId: 'a_knowledge', task: 'Analyse: Agent Architecture Review', status: 'done', startedAt: ago(5), endedAt: ago(4), ms: 61000 },
      { id: 'x_7', agentId: 'a_planning', task: 'Plan week', status: 'done', startedAt: ago(3001), endedAt: ago(3000), ms: 4100 },
      { id: 'x_8', agentId: 'a_research', task: 'Local LLM benchmarks', status: 'failed', startedAt: ago(1600), endedAt: ago(1590), ms: 600000, error: 'Timed out fetching 2 of 9 sources' },
    ],

    automations: [
      { id: 'au_1', name: 'Morning schedule summary', trigger: 'Every day · 8:00 AM', action: 'Summarise calendar, deadlines and top 3 tasks', status: 'active', lastRun: at(0, 8), nextRun: at(1, 8), runs: 61, failures: 0 },
      { id: 'au_2', name: 'Evening work summary', trigger: 'Every day · 9:30 PM', action: 'Summarise completed tasks, sessions and what moved', status: 'active', lastRun: ago(25), nextRun: at(1, 21, 30), runs: 60, failures: 1 },
      { id: 'au_3', name: 'Weekly plan', trigger: 'Every Monday · 9:00 AM', action: 'Prepare the week plan from goals and deadlines', status: 'active', lastRun: at(-3, 9), nextRun: at(4, 9), runs: 14, failures: 0 },
      { id: 'au_4', name: 'Important email alert', trigger: 'When an important email arrives', action: 'Notify with a one-line summary', status: 'paused', lastRun: at(-6, 14), nextRun: null, runs: 9, failures: 0, note: 'Gmail disconnected' },
      { id: 'au_5', name: 'Analyse new documents', trigger: 'When a document is added to Knowledge', action: 'Summarise, tag and link to projects', status: 'active', lastRun: ago(4), nextRun: null, runs: 38, failures: 0 },
      { id: 'au_6', name: 'Backup memory', trigger: 'Every Sunday · 2:00 AM', action: 'Snapshot memory and settings locally', status: 'failed', lastRun: at(-1, 2), nextRun: at(6, 2), runs: 12, failures: 1, error: 'Destination drive not mounted' },
    ],
    automationRuns: [
      { id: 'ar_1', automationId: 'au_2', at: ago(25), status: 'done', ms: 2200, output: '3 tasks completed · 2h 17m focused · Ally backend fixed' },
      { id: 'ar_2', automationId: 'au_1', at: at(0, 8), status: 'done', ms: 1900, output: '2 meetings · 1 deadline · top tasks: backend architecture, roadmap review, Alembic fix' },
      { id: 'ar_3', automationId: 'au_5', at: ago(4), status: 'done', ms: 61000, output: 'Agent Architecture Review · summarised, 2 tags, linked to Ultron' },
      { id: 'ar_4', automationId: 'au_6', at: at(-1, 2), status: 'failed', ms: 400, output: 'Destination drive not mounted' },
      { id: 'ar_5', automationId: 'au_2', at: at(-1, 21, 30), status: 'done', ms: 2100, output: '5 tasks completed · 3h 02m focused' },
      { id: 'ar_6', automationId: 'au_3', at: at(-3, 9), status: 'done', ms: 4100, output: 'Week plan prepared: 14 free hours, 2 deep-work blocks' },
    ],

    research: [
      { id: 'rs_1', query: 'Best architecture for a local-first personal AI assistant', status: 'done', createdAt: ago(1500), sources: 9, projectId: 'p_research',
        report: {
          summary: 'An orchestrator-worker topology with a unified tool registry and a local-first LLM router is the strongest fit. It keeps permissions, verification and explainability centralised while letting specialist agents be replaced independently.',
          findings: ['Orchestrator-worker keeps a single point of verification and permission control.', 'A provider-agnostic LLM gateway avoids lock-in and enables local → cloud escalation.', 'Workflow memory (reusing successful multi-step procedures) is the largest quality lever after retrieval.', 'Fast-path intents (open app, start session) should bypass the LLM entirely.'],
          evidence: [{ n: 1, title: 'Agent Architecture Review', detail: 'Compares three topologies; recommends orchestrator-worker for controllable systems.' }, { n: 2, title: 'ULTRON Product Vision §7.2', detail: 'Fast path requirement for deterministic commands.' }, { n: 3, title: 'Local LLM Benchmarks', detail: '7B Q4 models sustain 8–11 tok/s on the target laptop.' }],
          contradictions: ['Blackboard architectures score higher on flexibility in two sources, but lower on auditability — a direct conflict with the explainability principle.'],
          recommendations: ['Build the tool interface before the agent factory.', 'Benchmark local models on real Ultron tasks, not generic suites.', 'Keep the security kernel outside the self-extension boundary.'],
          nextActions: ['Define tool manifest schema', 'Implement LLM router with local-first policy', 'Spike workflow memory on the Ally fix procedure'] } },
      { id: 'rs_2', query: 'Competitor notes — personal AI assistants', status: 'running', createdAt: ago(4), sources: 6, projectId: 'p_research', step: 2 },
      { id: 'rs_3', query: 'Local wake-word engines for Windows', status: 'done', createdAt: ago(9000), sources: 7, projectId: 'p_ultron',
        report: { summary: 'openWakeWord and Porcupine are the two viable options; openWakeWord is fully local and open, Porcupine is more accurate but licensed.', findings: ['openWakeWord runs on CPU at <5% utilisation.', 'Custom wake words require ~1 hour of synthetic training data.'], evidence: [{ n: 1, title: 'openWakeWord README', detail: 'Performance and training notes.' }], contradictions: [], recommendations: ['Start with openWakeWord; keep Porcupine as a fallback.'], nextActions: ['Train "Hey Ultron" model', 'Measure false-accept rate over a day'] } },
    ],

    notifications: [
      { id: 'n_1', type: 'agent', title: 'Research complete', body: 'Best architecture for a local-first personal AI assistant — 9 sources, 4 findings.', at: ago(1500), read: true },
      { id: 'n_2', type: 'reminder', title: 'Reminder · tomorrow 9:00 AM', body: 'Finish the backend architecture', at: ago(60), read: false },
      { id: 'n_3', type: 'automation', title: 'Automation failed', body: 'Backup memory — destination drive not mounted', at: at(-1, 2), read: false },
      { id: 'n_4', type: 'task', title: 'Task completed', body: 'Weekly roadmap review', at: ago(190), read: true },
      { id: 'n_5', type: 'system', title: 'Gmail disconnected', body: 'Important email alerts are paused until you reconnect.', at: at(-6, 14), read: true },
      { id: 'n_6', type: 'important', title: 'Alembic revision mismatch', body: 'Ally backend migrations are out of sync — fix before load testing.', at: ago(900), read: false },
    ],

    activity: [
      { id: 'ac_1', kind: 'agents', title: 'Research started', body: 'Competitor notes — personal AI assistants', at: ago(4) },
      { id: 'ac_2', kind: 'memory', title: 'Memory updated', body: 'Key decision: Ultron UI ships as a dependency-free web layer', at: ago(60) },
      { id: 'ac_3', kind: 'chat', title: 'Conversation', body: 'Ally backend failing on startup — resolved', at: ago(62) },
      { id: 'ac_4', kind: 'system', title: 'Command executed', body: 'alembic stamp head · rebuild image · 42 tests passed', at: ago(62) },
      { id: 'ac_5', kind: 'tasks', title: 'Task completed', body: 'Weekly roadmap review', at: ago(190) },
      { id: 'ac_6', kind: 'automations', title: 'Evening summary generated', body: '3 tasks completed · 2h 17m focused', at: ago(25) },
      { id: 'ac_7', kind: 'memory', title: 'Memory created', body: 'Fix for Alembic revision mismatch', at: ago(62) },
      { id: 'ac_8', kind: 'research', title: 'Document analysed', body: 'Agent Architecture Review · 24 pages', at: ago(4) },
      { id: 'ac_9', kind: 'tasks', title: 'Task completed', body: 'Write Ally pricing copy', at: ago(180) },
      { id: 'ac_10', kind: 'automations', title: 'Morning summary generated', body: '2 meetings · 1 deadline', at: at(0, 8) },
      { id: 'ac_11', kind: 'chat', title: 'Conversation', body: 'GoXL strategy', at: ago(65) },
      { id: 'ac_12', kind: 'automations', title: 'Automation failed', body: 'Backup memory — destination drive not mounted', at: at(-1, 2) },
      { id: 'ac_13', kind: 'tasks', title: 'Task completed', body: 'Benchmark Qwen 7B on the laptop', at: ago(1300) },
      { id: 'ac_14', kind: 'research', title: 'Research complete', body: 'Best architecture for a local-first personal AI assistant', at: ago(1500) },
      { id: 'ac_15', kind: 'system', title: 'Work session ended', body: '2h 17m · Ultron · authentication, Redis integration, API tests', at: ago(1400) },
      { id: 'ac_16', kind: 'memory', title: 'Memory created', body: 'Design taste: premium, minimal, monochrome', at: ago(500) },
      { id: 'ac_17', kind: 'chat', title: 'Conversation', body: 'Weekly planning', at: ago(3000) },
      { id: 'ac_18', kind: 'agents', title: 'Research failed', body: 'Local LLM benchmarks — timed out fetching 2 of 9 sources', at: ago(1590) },
    ],

    sessions: [
      { id: 's_1', type: 'work', project: 'Ultron', start: ago(1540), minutes: 137, recorded: true, summary: 'Authentication, Redis integration, API tests' },
      { id: 's_2', type: 'work', project: 'GoXL', start: ago(3000), minutes: 92, recorded: false, summary: 'Pricing page, checkout flow' },
      { id: 's_3', type: 'learning', project: 'Computer Networks', start: ago(2000), minutes: 41, recorded: false, summary: 'TCP handshake, congestion control' },
      { id: 's_4', type: 'work', project: 'Ultron', start: ago(4400), minutes: 182, recorded: true, summary: 'Memory retention policy, tool registry' },
    ],

    insights: {
      focus: [42, 55, 48, 66, 61, 74, 72],
      weekly: [{ d: 'M', work: 3.2, learn: .5 }, { d: 'T', work: 4.1, learn: 0 }, { d: 'W', work: 2.4, learn: .7 }, { d: 'T', work: 5.0, learn: .7 }, { d: 'F', work: 3.8, learn: 0 }, { d: 'S', work: 1.5, learn: 1.2 }, { d: 'S', work: 2.3, learn: .7 }],
      usage: { queries: 342, research: 14, tasks: 61, automations: 186 },
      knowledgeTop: [{ id: 'k_2', n: 38 }, { id: 'k_1', n: 21 }, { id: 'k_4', n: 17 }, { id: 'k_8', n: 9 }],
    },

    integrations: [
      { id: 'gcal', name: 'Google Calendar', icon: 'calendar', status: 'connected', detail: 'Primary calendar · synced 4m ago' },
      { id: 'gmail', name: 'Gmail', icon: 'mail', status: 'disconnected', detail: 'Token expired 6 days ago', error: true },
      { id: 'gdrive', name: 'Google Drive', icon: 'drive', status: 'connected', detail: '2 folders watched' },
      { id: 'github', name: 'GitHub', icon: 'github', status: 'connected', detail: 'ultron, ally-platform' },
      { id: 'slack', name: 'Slack', icon: 'slack', status: 'available', detail: 'Not connected' },
      { id: 'notion', name: 'Notion', icon: 'notion', status: 'available', detail: 'Not connected' },
      { id: 'browser', name: 'Browser', icon: 'globe', status: 'connected', detail: 'Chrome · local extension' },
      { id: 'local', name: 'Local computer', icon: 'monitor', status: 'connected', detail: 'Desktop, files, terminal · permissions: READ, WRITE, EXECUTE' },
    ],

    settings: {
      general: { theme: 'dark', language: 'English', timezone: 'Asia/Kolkata', dateFormat: 'DD MMM YYYY' },
      ai: { responseStyle: 'concise', model: 'local · qwen2.5-7b', cloudEscalation: true, temperature: 0.3, reasoning: 'balanced', defaultAgent: 'a_core' },
      memory: { enabled: true, automatic: true, review: 'weekly', retentionDays: 365 },
      voice: { voice: 'en_US-lessac-medium', speed: 1.0, wakeWord: true, pushToTalk: 'Alt+Space', interruptions: true },
      notifications: { reminders: true, tasks: true, agents: true, automations: true, quietHours: '23:00–08:00' },
      privacy: { localOnly: true, telemetry: false, recordingDefault: false },
    },
    meta: { seededAt: new Date().toISOString(), version: 1 },
  };
  return db;
}

export function load() {
  try { const raw = localStorage.getItem(KEY); if (raw) { const db = JSON.parse(raw); if (db.meta?.version === 1) return db; } } catch {}
  const db = seed(); save(db); return db;
}
export function save(db) { try { localStorage.setItem(KEY, JSON.stringify(db)); } catch {} }
export function reset() { localStorage.removeItem(KEY); return load(); }
export function wipe(db) {
  // "Delete all data" — empties user-generated collections; the app must stand on its empty states.
  for (const k of ['tasks', 'reminders', 'events', 'memories', 'knowledge', 'conversations', 'executions', 'automations', 'automationRuns', 'research', 'notifications', 'activity', 'sessions', 'goals', 'projects']) db[k] = [];
  db.messages = {}; db.memoryStats = { total: 0, recall: 0, learnedToday: 0 }; db.insights = { focus: [0, 0, 0, 0, 0, 0, 0], weekly: db.insights.weekly.map(w => ({ ...w, work: 0, learn: 0 })), usage: { queries: 0, research: 0, tasks: 0, automations: 0 }, knowledgeTop: [] };
  db.agents.forEach(a => { a.status = a.id === 'a_core' ? 'ready' : 'idle'; a.executions = 0; a.currentTask = null; });
  save(db); return db;
}
