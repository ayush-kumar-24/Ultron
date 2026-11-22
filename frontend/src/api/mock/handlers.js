// Mock transport: implements the /api/* surface in-memory with realistic latency, streaming and events.
// This file is the only place that knows it is fake. Swap `api.use(fetchTransport)` and it is never imported at runtime.
import { load, save, reset, wipe } from './db.js';
import { ApiError } from '../errors.js';

let db = load();
const uid = (p) => p + '_' + Math.random().toString(36).slice(2, 8);
const nowIso = () => new Date().toISOString();
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const latency = () => 120 + Math.random() * 280;
const persist = () => save(db);
const clone = (x) => JSON.parse(JSON.stringify(x));

/* ---------------- helpers ---------------- */
function log(kind, title, body) {
  const last = db.activity[0];
  // don't stack identical entries (e.g. a demo reload replaying the same event)
  if (last && last.kind === kind && last.title === title && last.body === body && Date.now() - new Date(last.at).getTime() < 120000) return;
  db.activity.unshift({ id: uid('ac'), kind, title, body, at: nowIso() }); db.activity = db.activity.slice(0, 400);
}
function notify(type, title, body) { const n = { id: uid('n'), type, title, body, at: nowIso(), read: false }; db.notifications.unshift(n); emitEvent('notification', n); return n; }
function setAgent(id, status, currentTask) { const a = db.agents.find(a => a.id === id); if (!a) return; a.status = status; a.currentTask = currentTask || null; a.lastRun = nowIso(); if (status === 'working') a.executions++; emitEvent('agent', clone(a)); }
function addMemory(text, category = 'learned', source = 'Conversation', importance = 'medium') {
  const m = { id: uid('m'), text, category, source, confidence: .9, importance, createdAt: nowIso(), lastAccessed: nowIso(), pinned: false, accessCount: 1 };
  db.memories.unshift(m); db.memoryStats.total++; db.memoryStats.learnedToday++; log('memory', 'Memory created', text); return m;
}
function parseTask(text) {
  const t = text.trim();
  const lower = t.toLowerCase();
  const out = { title: t, priority: 'medium', due: null, recurrence: null, projectId: null, reminder: null };
  const rec = lower.match(/every (day|morning|evening|monday|tuesday|wednesday|thursday|friday|saturday|sunday|week)/);
  if (rec) out.recurrence = rec[0].replace(/^every /, 'Every ').replace(/\b\w/g, c => c.toUpperCase());
  const time = lower.match(/\b(?:at )?(\d{1,2})(?::(\d{2}))?\s?(am|pm)\b/);
  const d = new Date();
  if (/tomorrow/.test(lower)) d.setDate(d.getDate() + 1);
  else if (/next week/.test(lower)) d.setDate(d.getDate() + 7);
  const dayMatch = lower.match(/\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b/);
  if (dayMatch) { const days = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']; const target = days.indexOf(dayMatch[1]); let diff = (target - d.getDay() + 7) % 7; if (diff === 0) diff = 7; d.setDate(d.getDate() + diff); }
  if (time) { let h = +time[1]; if (time[3] === 'pm' && h < 12) h += 12; if (time[3] === 'am' && h === 12) h = 0; d.setHours(h, +(time[2] || 0), 0, 0); }
  else if (/tomorrow|next week|monday|tuesday|wednesday|thursday|friday|saturday|sunday|today|tonight/.test(lower)) d.setHours(/tonight|evening/.test(lower) ? 20 : 9, 0, 0, 0);
  if (time || dayMatch || /tomorrow|next week|today|tonight/.test(lower)) out.due = d.toISOString();
  if (/urgent|asap|important|high priority/.test(lower)) out.priority = 'high';
  if (/low priority|whenever|someday/.test(lower)) out.priority = 'low';
  for (const p of db.projects) if (lower.includes(p.name.toLowerCase())) out.projectId = p.id;
  let title = t.replace(/^(remind me( to)?|create (a )?task( to)?|add (a )?task( to)?|todo:?)\s*/i, '');
  title = title.replace(/\b(every (day|morning|evening|monday|tuesday|wednesday|thursday|friday|saturday|sunday|week)|tomorrow|next week|tonight|today)\b/gi, '').replace(/\b(at )?\d{1,2}(:\d{2})?\s?(am|pm)\b/gi, '').replace(/\s{2,}/g, ' ').replace(/^\s*(to|,)\s*/i, '').trim();
  out.title = title ? title[0].toUpperCase() + title.slice(1) : t;
  if (/^remind me/i.test(t)) out.reminder = true;
  return out;
}

/* ---------------- the demo "brain" (rules, not an LLM) ---------------- */
function planReply(text, context) {
  const q = text.toLowerCase();
  const tools = [], effects = {};
  let reply, state = 'speaking';
  const recall = db.memories.slice(0, 40).find(m => q.split(' ').some(w => w.length > 4 && m.text.toLowerCase().includes(w)));

  if (/^remind me/i.test(text)) {
    const p = parseTask(text);
    const r = { id: uid('r'), text: p.title, at: p.due || new Date(Date.now() + 3600e3).toISOString(), recurrence: p.recurrence, createdAt: nowIso() };
    db.reminders.unshift(r);
    if (p.recurrence) { const au = { id: uid('au'), name: p.title, trigger: `${p.recurrence}${p.due ? ' · ' + new Date(p.due).toLocaleTimeString('en', { hour: 'numeric', minute: '2-digit' }) : ''}`, action: `Remind: ${p.title}`, status: 'active', lastRun: null, nextRun: r.at, runs: 0, failures: 0 }; db.automations.unshift(au); effects.automationCreated = au; }
    tools.push({ name: 'Task Agent · create reminder', status: 'done', ms: 40 });
    effects.reminderCreated = r;
    reply = p.recurrence ? `I'll remind you ${p.recurrence.toLowerCase()}${p.due ? ' at ' + new Date(p.due).toLocaleTimeString('en', { hour: 'numeric', minute: '2-digit' }) : ''}.` : `I'll remind you${p.due ? ' ' + whenText(p.due) : ' in an hour'}.`;
    log('tasks', 'Reminder created', p.title);
  } else if (/^(create|add) (a )?task|^todo/i.test(text)) {
    const p = parseTask(text);
    const t = { id: uid('t'), title: p.title, priority: p.priority, status: 'todo', due: p.due, projectId: p.projectId || context?.projectId || null, tags: [], estimate: 30, recurrence: p.recurrence, createdAt: nowIso() };
    db.tasks.unshift(t); effects.taskCreated = t; tools.push({ name: 'Task Agent · create task', status: 'done', ms: 35 });
    reply = `Created **${t.title}**${t.due ? ' · due ' + whenText(t.due) : ''}${t.projectId ? ' in ' + db.projects.find(p => p.id === t.projectId)?.name : ''}.`;
    log('tasks', 'Task created', t.title);
  } else if (/^remember( that)?/i.test(text)) {
    const m = addMemory(text.replace(/^remember( that)?\s*/i, ''), 'preferences', 'Explicit ("Remember that…")', 'high');
    effects.memoryCreated = m.text; tools.push({ name: 'Memory Agent · store', status: 'done', ms: 28 });
    reply = 'Remembered.';
  } else if (/plan (my )?(day|today|tomorrow)/.test(q)) {
    tools.push({ name: 'Read calendar', status: 'done', detail: `${db.events.length} events`, ms: 180 }, { name: 'Read tasks', status: 'done', detail: `${db.tasks.filter(t => t.status !== 'done').length} open`, ms: 90 }, { name: 'Planning Agent · schedule', status: 'done', ms: 2100 });
    const open = db.tasks.filter(t => t.status !== 'done').slice(0, 3).map(t => `- **${t.title}**${t.estimate ? ' · ' + t.estimate + 'm' : ''}`).join('\n');
    reply = `Here's the shape of the day:\n\n- 10:00 GoXL standup\n- 14:00–16:00 deep work on Ultron agents\n- 18:00 backend architecture due\n\nTop three:\n${open}\n\nI kept the evening free — you work best after 8 PM, but you've already done two long sessions this week.`;
    effects.plan = true;
  } else if (/what('s| is) left|remaining|what do i have/.test(q) && context?.projectId) {
    const p = db.projects.find(p => p.id === context.projectId);
    const open = db.tasks.filter(t => t.projectId === p.id && t.status !== 'done');
    tools.push({ name: 'Context · ' + p.name, status: 'done', ms: 10 }, { name: 'Read tasks', status: 'done', detail: `${open.length} open`, ms: 80 });
    reply = `In **${p.name}**, ${open.length} task${open.length === 1 ? '' : 's'} remain:\n\n${open.map(t => `- ${t.title}${t.due ? ' · ' + whenText(t.due) : ''}`).join('\n')}\n\n${p.progress}% of the project is done.`;
  } else if (/explain (this|it)|summari[sz]e (this|it)|what is this/.test(q) && context?.documentId) {
    const k = db.knowledge.find(k => k.id === context.documentId);
    tools.push({ name: 'Context · ' + k.title, status: 'done', ms: 10 }, { name: 'Knowledge Agent · read', status: 'done', detail: k.pages ? k.pages + ' pages' : '', ms: 900 });
    reply = `**${k.title}** — ${k.summary || 'No summary yet.'}`;
  } else if (/^research |deep research|investigate/.test(q)) {
    const query = text.replace(/^(deep )?research (on |about )?|^investigate /i, '');
    const rs = { id: uid('rs'), query, status: 'running', createdAt: nowIso(), sources: 0, step: 0, projectId: context?.projectId || null };
    db.research.unshift(rs); effects.researchStarted = rs; setAgent('a_research', 'working', query);
    tools.push({ name: 'Research Agent · start', status: 'running', ms: 0 });
    reply = `Started a deep research session on **${query}**. I'll plan, search, compare and synthesise — you can follow it in Research.`;
    log('research', 'Research started', query);
  } else if (/^open |^launch |^start (a )?(work|learning) session|^stop (the )?session|^start recording|^stop recording/.test(q)) {
    tools.push({ name: 'Fast path · intent', status: 'done', detail: 'no LLM', ms: 6 }, { name: 'System Agent', status: 'done', ms: 140 });
    if (/session/.test(q) && /start/.test(q)) { reply = `${/learning/.test(q) ? 'Learning' : 'Work'} session started.${/record/.test(q) ? ' Recording is on.' : ' Want me to start recording?'}`; effects.session = 'started'; }
    else if (/stop/.test(q) && /session/.test(q)) { reply = 'Session complete — 2 hours 17 minutes. You completed authentication, fixed Redis integration, and ran the API tests.'; effects.session = 'ended'; }
    else if (/recording/.test(q)) { reply = /start/.test(q) ? 'Recording is on. Segmented, local only.' : 'Recording stopped and saved locally.'; effects.recording = /start/.test(q); }
    else reply = `Opening ${text.replace(/^(open|launch)\s+/i, '')}.`;
  } else if (/how much did i work|what did i do|what have i learned|this (week|month)/.test(q)) {
    const mins = db.sessions.reduce((a, s) => a + s.minutes, 0);
    tools.push({ name: 'Read sessions', status: 'done', detail: db.sessions.length + ' sessions', ms: 70 });
    reply = `Measured: **${Math.floor(mins / 60)}h ${mins % 60}m** across ${db.sessions.length} sessions — ${db.sessions.filter(s => s.type === 'work').length} work, ${db.sessions.filter(s => s.type === 'learning').length} learning.\n\nInterpretation: Ultron took most of it; the Alembic fix and the memory retention policy were the biggest moves.`;
  } else if (/ally|backend|goxl/.test(q)) {
    tools.push({ name: 'Checked memory', status: 'done', detail: 'Recalled 3 memories', ms: 35 });
    reply = 'The Ally backend is up — the Alembic revision was stamped to `b81e77` and 42 API tests passed [1]. The open risk is still the diagnosis engine verification; billing and auth are done.\n\nWant me to create a task for the load test?';
    effects.citations = [{ n: 1, title: 'Ally backend failing on startup', source: 'Conversation · c_1' }];
  } else if (/ultron|agent|memory|voice/.test(q)) {
    tools.push({ name: 'Checked memory', status: 'done', detail: 'Recalled 2 memories', ms: 30 }, { name: 'Read knowledge', status: 'done', detail: 'Product Vision, Roadmap', ms: 240 });
    reply = 'Current state of Ultron: foundation and memory are done, the agent runtime is the critical path [1]. Next three moves — define the tool manifest, finish the LLM router with the local-first policy, then the agent factory.\n\nI can break any of those into tasks.';
    effects.citations = [{ n: 1, title: 'Build Ultron', source: 'Goal · g_ultron' }];
  } else if (/hello|hi\b|hey/.test(q)) {
    reply = `Hi Ayush. ${db.tasks.filter(t => t.status !== 'done' && t.due && new Date(t.due) < new Date(Date.now() + 86400e3)).length} things are due within a day. What are we working on?`;
  } else {
    tools.push({ name: 'Checked memory', status: 'done', detail: recall ? 'Recalled 1 memory' : 'Nothing relevant', ms: 30 });
    reply = recall ? `From what I remember — ${recall.text}\n\nHow do you want to take this forward?` : `I don't have enough context on that yet. I can research it, check your knowledge library, or just think it through with you — which?`;
  }
  return { reply, tools, effects, state };
}
function whenText(iso) { const d = new Date(iso), today = new Date(); const diff = Math.round((d.setHours(0, 0, 0, 0) - today.setHours(0, 0, 0, 0)) / 86400e3); const t = new Date(iso).toLocaleTimeString('en', { hour: 'numeric', minute: '2-digit' }); return (diff === 0 ? 'today' : diff === 1 ? 'tomorrow' : new Date(iso).toLocaleDateString('en', { weekday: 'long' })) + ' · ' + t; }

/* ---------------- routes ---------------- */
const routes = [];
const on = (method, pattern, fn) => routes.push({ method, re: new RegExp('^' + pattern.replace(/:(\w+)/g, '(?<$1>[^/?]+)') + '$'), fn });

on('GET', '/me', () => db.user);

on('GET', '/overview', () => {
  const done = db.tasks.filter(t => t.status === 'done'), open = db.tasks.filter(t => t.status !== 'done');
  return {
    activity: db.activity.slice(0, 5), memory: db.memoryStats, pinned: db.memories.filter(m => m.pinned).length,
    focus: db.insights.focus, agents: db.agents.slice(0, 5), projects: db.projects.slice(0, 3),
    productivity: { done: done.length, pending: open.length, rate: db.tasks.length ? Math.round(done.length / db.tasks.length * 100) : 0, sessions: db.sessions.length },
    log: db.activity.slice(0, 4),
    metrics: [{ l: 'Focus', v: db.insights.focus.at(-1) + '%', d: '+6 vs last week', up: true }, { l: 'Productivity', v: '84%', d: '+3 vs last week', up: true }, { l: 'Task completion', v: (db.tasks.length ? Math.round(done.length / db.tasks.length * 100) : 0) + '%', d: `${done.length} of ${db.tasks.length}` }, { l: 'Cognitive load', v: open.length > 8 ? 'High' : open.length > 4 ? 'Moderate' : 'Light', d: `${db.projects.filter(p => p.status === 'active').length} active projects` }],
    dueSoon: open.filter(t => t.due && new Date(t.due) < new Date(Date.now() + 86400e3)).length,
  };
});

on('GET', '/conversations', () => db.conversations.slice().sort((a, b) => (b.pinned - a.pinned) || (b.updatedAt > a.updatedAt ? 1 : -1)));
on('POST', '/conversations', (_, body) => { const c = { id: uid('c'), title: body?.title || 'New conversation', projectId: body?.projectId || null, updatedAt: nowIso(), pinned: false }; db.conversations.unshift(c); db.messages[c.id] = []; persist(); return c; });
on('PATCH', '/conversations/:id', (p, body) => { const c = db.conversations.find(c => c.id === p.id); if (!c) throw new ApiError(404, 'Conversation not found'); Object.assign(c, body); persist(); return c; });
on('DELETE', '/conversations/:id', (p) => { db.conversations = db.conversations.filter(c => c.id !== p.id); delete db.messages[p.id]; persist(); return null; });
on('GET', '/conversations/:id/messages', (p) => { if (!db.messages[p.id]) throw new ApiError(404, 'Conversation not found'); return db.messages[p.id]; });
on('GET', '/conversations/:id', (p) => { const c = db.conversations.find(c => c.id === p.id); if (!c) throw new ApiError(404, 'Conversation not found'); return c; });
on('POST', '/messages/:id/memory', (p, body) => { const m = addMemory(body.text.slice(0, 180), 'conversations', 'Saved from chat'); persist(); return m; });
on('POST', '/messages/:id/task', (p, body) => { const t = { id: uid('t'), title: body.title.slice(0, 80), priority: 'medium', status: 'todo', due: null, projectId: body.projectId || null, tags: [], estimate: 30, createdAt: nowIso() }; db.tasks.unshift(t); log('tasks', 'Task created', t.title); persist(); return t; });

on('GET', '/memories', (_, __, q) => {
  let list = db.memories.slice();
  if (q.category && q.category !== 'all') list = list.filter(m => m.category === q.category);
  if (q.q) { const s = q.q.toLowerCase(); list = list.filter(m => m.text.toLowerCase().includes(s) || m.source.toLowerCase().includes(s)); }
  return list.sort((a, b) => (b.pinned - a.pinned) || (b.createdAt > a.createdAt ? 1 : -1));
});
on('GET', '/memory/stats', () => ({ ...db.memoryStats, pinned: db.memories.filter(m => m.pinned).length, byCategory: db.memories.reduce((a, m) => (a[m.category] = (a[m.category] || 0) + 1, a), {}) }));
on('POST', '/memories', (_, body) => { const m = addMemory(body.text, body.category || 'personal', 'Teach Ultron', body.importance || 'medium'); persist(); return m; });
on('PATCH', '/memories/:id', (p, body) => { const m = db.memories.find(m => m.id === p.id); if (!m) throw new ApiError(404, 'Memory not found'); Object.assign(m, body); persist(); return m; });
on('DELETE', '/memories/:id', (p) => { const before = db.memories.length; db.memories = db.memories.filter(m => m.id !== p.id); if (db.memories.length < before) db.memoryStats.total--; log('memory', 'Memory deleted', 'Removed permanently'); persist(); return null; });

on('GET', '/knowledge', (_, __, q) => { let list = db.knowledge.slice(); if (q.type && q.type !== 'all') list = list.filter(k => k.type === q.type); if (q.q) { const s = q.q.toLowerCase(); list = list.filter(k => k.title.toLowerCase().includes(s) || k.tags.join(' ').includes(s)); } return list; });
on('GET', '/knowledge/:id', (p) => { const k = db.knowledge.find(k => k.id === p.id); if (!k) throw new ApiError(404, 'Item not found'); return k; });
on('POST', '/knowledge', (_, body) => { const k = { id: uid('k'), title: body.title, type: body.type || 'doc', source: body.source || 'Upload', size: body.size || Math.round(200000 + Math.random() * 3e6), tags: body.tags || [], status: 'processing', progress: 0, createdAt: nowIso() }; db.knowledge.unshift(k); setAgent('a_knowledge', 'working', k.title); log('research', 'Document added', k.title); persist(); return k; });
on('DELETE', '/knowledge/:id', (p) => { db.knowledge = db.knowledge.filter(k => k.id !== p.id); persist(); return null; });
on('POST', '/knowledge/:id/summarize', async (p) => { const k = db.knowledge.find(k => k.id === p.id); if (!k) throw new ApiError(404, 'Item not found'); await sleep(1400); k.summary = k.summary || `Key points from ${k.title}: covers the core concepts, the trade-offs that matter for Ultron, and three concrete next steps.`; persist(); return k; });
on('POST', '/knowledge/:id/memory', (p) => { const k = db.knowledge.find(k => k.id === p.id); const m = addMemory(`${k.title}: ${k.summary || 'saved to memory'}`.slice(0, 200), 'learned', 'Knowledge · ' + k.title); persist(); return m; });

on('GET', '/tasks', (_, __, q) => {
  let list = db.tasks.slice();
  const today = new Date(); today.setHours(23, 59, 59, 999);
  if (q.view === 'today') list = list.filter(t => t.status !== 'done' && t.due && new Date(t.due) <= today);
  else if (q.view === 'upcoming') list = list.filter(t => t.status !== 'done' && t.due && new Date(t.due) > today);
  else if (q.view === 'inbox') list = list.filter(t => t.status !== 'done' && !t.due);
  else if (q.view === 'completed') list = list.filter(t => t.status === 'done');
  if (q.projectId) list = list.filter(t => t.projectId === q.projectId);
  return list.sort((a, b) => (a.status === 'done') - (b.status === 'done') || ((a.due || '9') > (b.due || '9') ? 1 : -1));
});
on('POST', '/tasks/parse', (_, body) => parseTask(body.text));
on('POST', '/tasks', (_, body) => {
  const p = body.text ? parseTask(body.text) : body;
  const t = { id: uid('t'), title: p.title, description: body.description || '', priority: p.priority || 'medium', status: 'todo', due: p.due || null, projectId: p.projectId || body.projectId || null, tags: body.tags || [], estimate: body.estimate || 30, recurrence: p.recurrence || null, createdAt: nowIso() };
  db.tasks.unshift(t); log('tasks', 'Task created', t.title);
  if (t.recurrence) { const au = { id: uid('au'), name: t.title, trigger: t.recurrence + (t.due ? ' · ' + new Date(t.due).toLocaleTimeString('en', { hour: 'numeric', minute: '2-digit' }) : ''), action: 'Create task: ' + t.title, status: 'active', lastRun: null, nextRun: t.due, runs: 0, failures: 0 }; db.automations.unshift(au); t.automationId = au.id; }
  persist(); return t;
});
on('PATCH', '/tasks/:id', (p, body) => { const t = db.tasks.find(t => t.id === p.id); if (!t) throw new ApiError(404, 'Task not found'); const wasDone = t.status === 'done'; Object.assign(t, body); if (t.status === 'done' && !wasDone) { t.completedAt = nowIso(); log('tasks', 'Task completed', t.title); } persist(); return t; });
on('DELETE', '/tasks/:id', (p) => { db.tasks = db.tasks.filter(t => t.id !== p.id); persist(); return null; });
on('GET', '/plan/day', () => {
  const open = db.tasks.filter(t => t.status !== 'done');
  const byPri = { high: 0, medium: 1, low: 2 };
  const sorted = open.slice().sort((a, b) => byPri[a.priority] - byPri[b.priority] || ((a.due || '9') > (b.due || '9') ? 1 : -1));
  const todayEvents = db.events.filter(e => new Date(e.start).toDateString() === new Date().toDateString());
  return {
    morning: [{ kind: 'task', title: sorted[0]?.title || 'Review priorities', minutes: sorted[0]?.estimate || 30, why: 'Highest priority, due soonest' }, ...todayEvents.filter(e => new Date(e.start).getHours() < 12).map(e => ({ kind: e.type, title: e.title, at: e.start }))],
    afternoon: [...todayEvents.filter(e => { const h = new Date(e.start).getHours(); return h >= 12 && h < 17; }).map(e => ({ kind: e.type, title: e.title, at: e.start })), { kind: 'task', title: sorted[1]?.title || 'Deep work', minutes: sorted[1]?.estimate || 60, why: 'Fits the free block after the standup' }],
    evening: [{ kind: 'task', title: sorted[2]?.title || 'Light admin', minutes: sorted[2]?.estimate || 30, why: 'You work best after 8 PM — but keep it short tonight' }, ...todayEvents.filter(e => new Date(e.start).getHours() >= 17).map(e => ({ kind: e.type, title: e.title, at: e.start }))],
    postpone: sorted.slice(3, 5).map(t => ({ title: t.title, why: 'No free block left today' })),
    conflicts: todayEvents.length > 3 ? ['Three meetings overlap the afternoon focus block'] : [],
    freeHours: Math.max(0, 8 - todayEvents.reduce((a, e) => a + (new Date(e.end) - new Date(e.start)) / 3.6e6, 0)).toFixed(1),
  };
});

on('GET', '/events', (_, __, q) => { let list = db.events.slice(); if (q.from) list = list.filter(e => e.start >= q.from); if (q.to) list = list.filter(e => e.start <= q.to); return list.sort((a, b) => a.start > b.start ? 1 : -1); });
on('POST', '/events', (_, body) => { const e = { id: uid('e'), title: body.title, start: body.start, end: body.end || body.start, type: body.type || 'meeting', projectId: body.projectId || null }; db.events.push(e); log('tasks', 'Event added', e.title); persist(); return e; });
on('DELETE', '/events/:id', (p) => { db.events = db.events.filter(e => e.id !== p.id); persist(); return null; });
on('GET', '/calendar/context', () => {
  const tomorrow = new Date(); tomorrow.setDate(tomorrow.getDate() + 1);
  const evs = db.events.filter(e => new Date(e.start).toDateString() === tomorrow.toDateString() && e.type === 'meeting');
  const busy = evs.reduce((a, e) => a + (new Date(e.end) - new Date(e.start)) / 3.6e6, 0);
  return { text: `You have ${evs.length} meeting${evs.length === 1 ? '' : 's'} tomorrow and about ${Math.max(0, Math.round(8 - busy))} free hours.`, meetings: evs.length, freeHours: Math.max(0, Math.round(8 - busy)) };
});

on('GET', '/automations', () => db.automations);
on('GET', '/automations/:id/runs', (p) => db.automationRuns.filter(r => r.automationId === p.id));
on('POST', '/automations', (_, body) => { const p = parseTask(body.text || body.name || ''); const au = { id: uid('au'), name: body.name || p.title, trigger: body.trigger || p.recurrence || 'Manual', action: body.action || 'Ask Ultron: ' + (body.text || p.title), status: 'active', lastRun: null, nextRun: p.due || null, runs: 0, failures: 0 }; db.automations.unshift(au); log('automations', 'Automation created', au.name); persist(); return au; });
on('PATCH', '/automations/:id', (p, body) => { const a = db.automations.find(a => a.id === p.id); if (!a) throw new ApiError(404, 'Automation not found'); Object.assign(a, body); persist(); return a; });
on('DELETE', '/automations/:id', (p) => { db.automations = db.automations.filter(a => a.id !== p.id); persist(); return null; });
on('POST', '/automations/:id/run', async (p) => {
  const a = db.automations.find(a => a.id === p.id); if (!a) throw new ApiError(404, 'Automation not found');
  setAgent('a_auto', 'working', a.name); await sleep(1500);
  const fail = a.id === 'au_6';
  const run = { id: uid('ar'), automationId: a.id, at: nowIso(), status: fail ? 'failed' : 'done', ms: fail ? 400 : 1800, output: fail ? 'Destination drive not mounted' : `${a.action} · completed` };
  db.automationRuns.unshift(run); a.lastRun = run.at; a.runs++; if (fail) { a.failures++; a.status = 'failed'; a.error = run.output; } else if (a.status === 'failed') { a.status = 'active'; a.error = null; }
  setAgent('a_auto', 'monitoring'); log('automations', fail ? 'Automation failed' : 'Automation ran', a.name); emitEvent('automation', clone(a)); persist(); return run;
});

on('GET', '/agents', () => db.agents);
on('GET', '/agents/:id', (p) => { const a = db.agents.find(a => a.id === p.id); if (!a) throw new ApiError(404, 'Agent not found'); return a; });
on('GET', '/agents/:id/executions', (p) => db.executions.filter(x => x.agentId === p.id));
on('GET', '/executions', () => db.executions);

on('GET', '/research', () => db.research);
on('GET', '/research/:id', (p) => { const r = db.research.find(r => r.id === p.id); if (!r) throw new ApiError(404, 'Research not found'); return r; });
on('DELETE', '/research/:id', (p) => { db.research = db.research.filter(r => r.id !== p.id); persist(); return null; });
on('POST', '/research/:id/tasks', (p) => { const r = db.research.find(r => r.id === p.id); const made = (r.report?.nextActions || []).map(a => { const t = { id: uid('t'), title: a, priority: 'medium', status: 'todo', due: null, projectId: r.projectId, tags: ['research'], estimate: 45, createdAt: nowIso() }; db.tasks.unshift(t); return t; }); log('tasks', 'Tasks created from research', `${made.length} tasks`); persist(); return made; });
on('POST', '/research/:id/knowledge', (p) => { const r = db.research.find(r => r.id === p.id); const k = { id: uid('k'), title: 'Research · ' + r.query, type: 'note', source: 'Research', size: 24000, tags: ['research'], status: 'ready', createdAt: nowIso(), summary: r.report?.summary }; db.knowledge.unshift(k); persist(); return k; });

on('GET', '/projects', () => db.projects.map(p => ({ ...p, openTasks: db.tasks.filter(t => t.projectId === p.id && t.status !== 'done').length })));
on('GET', '/projects/:id', (p) => {
  const pr = db.projects.find(x => x.id === p.id); if (!pr) throw new ApiError(404, 'Project not found');
  return { ...pr, tasks: db.tasks.filter(t => t.projectId === pr.id), conversations: db.conversations.filter(c => c.projectId === pr.id), files: db.knowledge.filter(k => k.tags.some(t => pr.name.toLowerCase().includes(t) || t === pr.id)), research: db.research.filter(r => r.projectId === pr.id), memories: db.memories.filter(m => m.text.toLowerCase().includes(pr.name.toLowerCase())), goals: db.goals.filter(g => g.projectId === pr.id), activity: db.activity.filter(a => (a.body || '').toLowerCase().includes(pr.name.toLowerCase())).slice(0, 10) };
});
on('POST', '/projects', (_, body) => { const p = { id: uid('p'), name: body.name, description: body.description || '', progress: 0, color: 'info', status: 'active', updatedAt: nowIso(), goals: [], tags: [] }; db.projects.unshift(p); persist(); return p; });

on('GET', '/goals', () => db.goals.map(g => ({ ...g, project: db.projects.find(p => p.id === g.projectId)?.name })));
on('PATCH', '/goals/:id', (p, body) => { const g = db.goals.find(g => g.id === p.id); if (!g) throw new ApiError(404, 'Goal not found'); Object.assign(g, body); persist(); return g; });
on('POST', '/goals', (_, body) => { const g = { id: uid('g'), title: body.title, objective: body.objective || '', deadline: body.deadline || null, progress: 0, projectId: body.projectId || null, milestones: (body.milestones || []).map((t, i) => ({ t, done: false, current: i === 0 })), recommendation: 'Set the first milestone small enough to finish this week.' }; db.goals.unshift(g); persist(); return g; });

on('GET', '/insights', () => ({ ...db.insights, sessions: db.sessions, projects: db.projects.map(p => ({ name: p.name, minutes: db.sessions.filter(s => s.project === p.name).reduce((a, s) => a + s.minutes, 0) })).sort((a, b) => b.minutes - a.minutes), knowledgeTop: db.insights.knowledgeTop.map(k => ({ ...k, title: db.knowledge.find(x => x.id === k.id)?.title })).filter(k => k.title), tasks: { done: db.tasks.filter(t => t.status === 'done').length, total: db.tasks.length }, activeDays: 6, streak: 4 }));
on('GET', '/activity', (_, __, q) => { let list = db.activity.slice(); if (q.kind && q.kind !== 'all') list = list.filter(a => a.kind === q.kind); return list; });
on('GET', '/sessions', () => db.sessions);

on('GET', '/notifications', () => db.notifications);
on('PATCH', '/notifications/:id', (p, body) => { const n = db.notifications.find(n => n.id === p.id); if (n) Object.assign(n, body); persist(); return n; });
on('POST', '/notifications/read-all', () => { db.notifications.forEach(n => n.read = true); persist(); return null; });

on('GET', '/integrations', () => db.integrations);
on('POST', '/integrations/:id/connect', async (p) => { const i = db.integrations.find(i => i.id === p.id); await sleep(900); i.status = 'connected'; i.error = false; i.detail = 'Connected just now'; if (i.id === 'gmail') { const au = db.automations.find(a => a.id === 'au_4'); if (au) { au.status = 'active'; au.note = null; } } log('system', 'Integration connected', i.name); persist(); return i; });
on('POST', '/integrations/:id/disconnect', (p) => { const i = db.integrations.find(i => i.id === p.id); i.status = 'available'; i.detail = 'Not connected'; persist(); return i; });

on('GET', '/settings', () => db.settings);
on('PATCH', '/settings/:section', (p, body) => { db.settings[p.section] = { ...db.settings[p.section], ...body }; persist(); return db.settings[p.section]; });
on('PATCH', '/me', (_, body) => { Object.assign(db.user, body); persist(); return db.user; });

on('GET', '/search', (_, __, q) => {
  const s = (q.q || '').toLowerCase().trim(); if (!s) return [];
  const hit = (str) => (str || '').toLowerCase().includes(s);
  const out = [];
  db.conversations.filter(c => hit(c.title)).forEach(c => out.push({ kind: 'conversation', id: c.id, title: c.title, sub: 'Conversation', route: '/chat/' + c.id }));
  db.memories.filter(m => hit(m.text)).forEach(m => out.push({ kind: 'memory', id: m.id, title: m.text, sub: 'Memory · ' + m.category, route: '/memory?q=' + encodeURIComponent(s) }));
  db.knowledge.filter(k => hit(k.title) || k.tags.some(hit)).forEach(k => out.push({ kind: 'knowledge', id: k.id, title: k.title, sub: 'Knowledge · ' + k.type, route: '/knowledge/' + k.id }));
  db.tasks.filter(t => hit(t.title)).forEach(t => out.push({ kind: 'task', id: t.id, title: t.title, sub: 'Task · ' + t.status.replace('_', ' '), route: '/tasks' }));
  db.research.filter(r => hit(r.query)).forEach(r => out.push({ kind: 'research', id: r.id, title: r.query, sub: 'Research', route: '/research/' + r.id }));
  db.projects.filter(p => hit(p.name) || hit(p.description)).forEach(p => out.push({ kind: 'project', id: p.id, title: p.name, sub: 'Project', route: '/projects/' + p.id }));
  db.memories.filter(m => m.category === 'people' && hit(m.text)).forEach(m => out.push({ kind: 'person', id: m.id, title: m.text.split(' ')[0], sub: 'Person', route: '/memory?category=people' }));
  return out.slice(0, 30);
});

on('POST', '/system/reset', () => { db = reset(); return null; });
on('POST', '/system/wipe', () => { db = wipe(db); return null; });
on('GET', '/system/health', () => ({ ok: true, local: true, model: db.settings.ai.model, latencyMs: 12, memoryCount: db.memoryStats.total }));

/* ---------------- streaming endpoints ---------------- */
async function streamChat(body, onChunk) {
  const { conversationId, text, context } = body;
  let conv = db.conversations.find(c => c.id === conversationId);
  if (!conv) { conv = { id: conversationId || uid('c'), title: text.slice(0, 48), projectId: context?.projectId || null, updatedAt: nowIso(), pinned: false }; db.conversations.unshift(conv); db.messages[conv.id] = []; }
  const userMsg = { id: uid('mg'), role: 'user', text, at: nowIso() };
  db.messages[conv.id].push(userMsg);
  if (db.messages[conv.id].length === 1) conv.title = text.slice(0, 48);
  onChunk({ type: 'user', payload: userMsg });
  onChunk({ type: 'state', state: 'thinking' }); await sleep(500 + Math.random() * 500);
  const plan = planReply(text, context);
  if (plan.tools.length) { onChunk({ type: 'state', state: 'working' }); for (const t of plan.tools) { onChunk({ type: 'tool', tool: { ...t, status: 'running' } }); await sleep(Math.min(900, 120 + (t.ms || 200) / 40)); onChunk({ type: 'tool', tool: t }); } }
  onChunk({ type: 'state', state: 'speaking' });
  const words = plan.reply.split(/(\s+)/);
  let acc = '';
  for (const w of words) { acc += w; onChunk({ type: 'token', text: w }); if (w.trim()) await sleep(18 + Math.random() * 40); }
  const msg = { id: uid('mg'), role: 'assistant', text: plan.reply, at: nowIso(), tools: plan.tools.map(t => ({ ...t, status: t.status === 'running' ? 'done' : t.status })), ...plan.effects };
  if (plan.effects.citations) msg.citations = plan.effects.citations;
  db.messages[conv.id].push(msg); conv.updatedAt = nowIso(); db.insights.usage.queries++;
  log('chat', 'Conversation', conv.title);
  if (plan.effects.researchStarted) runResearch(plan.effects.researchStarted.id);
  persist();
  return { message: msg, conversation: conv };
}

async function streamResearch(body, onChunk) {
  const rs = { id: uid('rs'), query: body.query, status: 'running', createdAt: nowIso(), sources: 0, step: 0, projectId: body.projectId || null };
  db.research.unshift(rs); persist();
  onChunk({ type: 'session', session: clone(rs) });
  await runResearch(rs.id, onChunk);
  return db.research.find(r => r.id === rs.id);
}
const RESEARCH_STEPS = ['Understand problem', 'Search sources', 'Compare information', 'Analyse', 'Synthesise', 'Generate report'];
async function runResearch(id, onChunk = () => {}) {
  const rs = db.research.find(r => r.id === id); if (!rs) return;
  setAgent('a_research', 'working', rs.query); log('research', 'Research started', rs.query);
  for (let i = 0; i < RESEARCH_STEPS.length; i++) {
    rs.step = i; rs.sources = Math.min(9, i * 2 + (i > 0 ? 1 : 0)); emitEvent('research', clone(rs)); onChunk({ type: 'step', step: i, label: RESEARCH_STEPS[i], sources: rs.sources });
    await sleep(900 + Math.random() * 900);
  }
  rs.status = 'done'; rs.step = RESEARCH_STEPS.length;
  rs.report = { summary: `${rs.query} — the evidence points to one dominant approach with two credible alternatives. The recommended path optimises for local-first operation and explainability, consistent with Ultron's principles.`, findings: ['The leading approach is already proven at Ultron\'s scale.', 'Two sources disagree on cost; the difference is explained by hardware assumptions.', 'A hybrid approach is viable if latency targets are relaxed by ~20%.', 'Most failures in the field come from skipping verification, not from model quality.'], evidence: [{ n: 1, title: 'Primary source', detail: 'Direct benchmark on comparable hardware.' }, { n: 2, title: 'Secondary analysis', detail: 'Comparative review of three approaches.' }, { n: 3, title: 'ULTRON Product Vision', detail: 'Constraints: local-first, verify before claiming success.' }], contradictions: ['Source 2 claims cloud escalation is always cheaper; source 1 shows the opposite for short prompts.'], recommendations: ['Adopt the leading approach for v1.', 'Keep the hybrid option behind a setting.', 'Add a verification step before reporting success.'], nextActions: ['Prototype the leading approach', 'Write the verification checklist', 'Re-run the benchmark on the target laptop'] };
  setAgent('a_research', 'idle'); db.insights.usage.research++; log('research', 'Research complete', rs.query);
  notify('agent', 'Research complete', `${rs.query} — ${rs.sources} sources, ${rs.report.findings.length} findings.`);
  emitEvent('research', clone(rs)); onChunk({ type: 'report', report: rs.report }); persist();
}

async function streamOrchestrate(body, onChunk) {
  const flow = [
    { agent: 'a_core', label: 'Understand goal', ms: 700 }, { agent: 'a_research', label: 'Research architectures', ms: 1800 },
    { agent: 'a_knowledge', label: 'Read Product Vision + Roadmap', ms: 1200 }, { agent: 'a_planning', label: 'Draft development plan', ms: 1500 }, { agent: 'a_core', label: 'Verify and report', ms: 800 },
  ];
  for (let i = 0; i < flow.length; i++) { const s = flow[i]; setAgent(s.agent, 'working', s.label); onChunk({ type: 'step', index: i, ...s, status: 'running' }); await sleep(s.ms); setAgent(s.agent, s.agent === 'a_core' ? 'ready' : 'idle'); onChunk({ type: 'step', index: i, ...s, status: 'done' }); }
  const result = { summary: 'Recommended: orchestrator-worker with a unified tool registry and local-first LLM router.', plan: ['Define tool manifest schema (2d)', 'Implement LLM gateway + router (4d)', 'Agent runtime with permissions and logs (5d)', 'Verification agent + rollback (3d)', 'Agent factory MVP (6d)'], verified: true };
  db.executions.unshift({ id: uid('x'), agentId: 'a_core', task: body.request, status: 'done', startedAt: nowIso(), endedAt: nowIso(), ms: 6000 });
  log('agents', 'Orchestration complete', body.request); persist();
  return result;
}

async function streamVoice(body, onChunk) {
  const phrases = body.prompt ? [body.prompt] : ['Ultron, ', 'I need to finish ', 'the Ally backend today.'];
  onChunk({ type: 'state', state: 'listening' });
  let acc = '';
  for (const p of phrases) { for (const w of p.split(/(\s+)/)) { acc += w; onChunk({ type: 'partial', text: acc }); if (w.trim()) await sleep(90 + Math.random() * 140); } }
  await sleep(400);
  return { transcript: acc.trim() };
}

/* ---------------- events (simulated SSE) ---------------- */
let emitEvent = () => {};
function startEvents(emit) {
  emitEvent = (type, payload) => emit(type, payload);
  const timers = [];
  // knowledge processing progress
  timers.push(setInterval(() => {
    let changed = false;
    for (const k of db.knowledge) if (k.status === 'processing') { k.progress = Math.min(100, (k.progress || 0) + 6 + Math.random() * 10); changed = true; if (k.progress >= 100) { k.status = 'ready'; k.summary = k.summary || `Summary: ${k.title} — key ideas extracted, 3 tags suggested, linked to the closest project.`; k.tags = k.tags.length ? k.tags : ['auto']; setAgent('a_knowledge', 'idle'); notify('agent', 'Document analysed', k.title); log('research', 'Document analysed', k.title); } emit('knowledge', clone(k)); }
    if (changed) persist();
  }, 1600));
  // the research session seeded as running finishes itself
  setTimeout(() => { const r = db.research.find(r => r.status === 'running' && r.id === 'rs_2'); if (r) runResearch(r.id); }, 9000);
  // ambient agent activity
  timers.push(setInterval(() => {
    const idle = db.agents.filter(a => a.status === 'idle' || a.status === 'ready');
    const a = idle[Math.floor(Math.random() * idle.length)]; if (!a || Math.random() < .4) return;
    const tasks = { a_memory: 'Consolidating memories', a_planning: 'Re-checking tomorrow', a_task: 'Reminder sweep', a_knowledge: 'Refreshing embeddings', a_system: 'Health check', a_core: 'Idle review', a_auto: 'Schedule check', a_research: 'Source refresh' };
    const prev = a.status; setAgent(a.id, 'working', tasks[a.id]);
    setTimeout(() => setAgent(a.id, prev === 'ready' ? 'ready' : 'idle'), 2500 + Math.random() * 4000);
  }, 14000));
  // an occasional useful notification (never spam)
  timers.push(setTimeout(() => notify('reminder', 'Deep work starts in 15 minutes', 'Ultron agents · 14:00–16:00'), 40000));
  timers.push(setInterval(() => emit('heartbeat', { at: nowIso(), online: true }), 30000));
  return () => { timers.forEach(clearInterval); timers.forEach(clearTimeout); emitEvent = () => {}; };
}

/* ---------------- transport ---------------- */
export const mockTransport = {
  isMock: true,
  async request(method, fullPath, body) {
    await sleep(latency());
    const [path, qs] = fullPath.split('?');
    const query = Object.fromEntries(new URLSearchParams(qs || ''));
    for (const r of routes) {
      if (r.method !== method) continue;
      const m = path.match(r.re); if (!m) continue;
      const out = await r.fn(m.groups || {}, body || {}, query);
      if (!['GET'].includes(method)) persist();
      return out === undefined ? null : clone(out);
    }
    throw new ApiError(404, `No route ${method} ${path}`);
  },
  async stream(path, body, onChunk) {
    await sleep(latency() / 2);
    if (path === '/chat/stream') return streamChat(body, onChunk);
    if (path === '/research/stream') return streamResearch(body, onChunk);
    if (path === '/agents/orchestrate') return streamOrchestrate(body, onChunk);
    if (path === '/voice/transcribe') return streamVoice(body, onChunk);
    throw new ApiError(404, `No stream ${path}`);
  },
  events: startEvents,
};
