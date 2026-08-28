// Agents — the multi-agent workspace. Orchestration visualiser, live agent grid, per-agent drawer (executions, logs, config).
import { h, icon, fmt, mount, clear } from '../ui/dom.js';
import { PageHeader, Card, Button, Badge, Dot, Input, Select, Field, Toggle, Tabs, Row, EmptyState, ErrorState, Skeleton, SkeletonCard, load, Drawer, toast } from '../ui/components/index.js';
import { agentService, events } from '../services/index.js';
import { presence } from '../ui/core/presence.js';

const TONE = { working: 'busy', ready: 'ok', idle: 'neutral', monitoring: 'info' };
const DEFAULT_REQUEST = 'Research the best architecture for my AI assistant and create a development plan.';
const NODES = [
  { name: 'Ultron Core', lbl: 'orchestrate' },
  { name: 'Research Agent', lbl: 'research' },
  { name: 'Knowledge Agent', lbl: 'knowledge' },
  { name: 'Planning Agent', lbl: 'plan' },
  { name: 'Ultron Core', lbl: 'verify' },
];
const MODELS = ['local · qwen2.5-7b', 'cloud · optional', 'fast path'];

export default async function agents(root, { params }) {
  let list = [], running = false, request = DEFAULT_REQUEST, drawer = null, drawerId = null, alive = true;

  /* ---------- orchestration visualiser ---------- */
  const viz = h('div', { class: 'viz', html: orchSvg() });
  const nodes = [...viz.querySelectorAll('g.node')], edges = [...viz.querySelectorAll('path.edge')], lbls = [...viz.querySelectorAll('text[data-lbl]')];
  const log = h('div', { class: 'logs', role: 'log', 'aria-live': 'polite' });
  const result = h('div', { class: 'res' });
  const runBtn = Button({ label: 'Run', icon: 'play', variant: 'primary', onClick: () => runOrchestration() });
  const orch = h('div', { class: 'orch' },
    h('div', { class: 'ask' }, Input({ placeholder: 'Ask for something complex…', value: request, icon: 'spark', onInput: (v) => request = v, onEnter: () => runOrchestration() }), runBtn),
    viz, log, result);

  /* ---------- grid ---------- */
  const grid = h('div', { class: 'grid c3' });

  mount(root,
    PageHeader({ title: 'Agents', subtitle: 'Specialists Ultron delegates to — with permissions, logs, and verification.', actions: [Button({ label: 'Run orchestration demo', icon: 'agents', onClick: () => { orch.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); runOrchestration(); } })] }),
    orch,
    h('div', { class: 'sec-h' }, 'Specialists'),
    grid);

  await load(grid, () => agentService.list(), (data) => { list = data; renderGrid(); }, { skeleton: h('div', { class: 'grid c3' }, SkeletonCard(), SkeletonCard(), SkeletonCard()) }).catch(() => null);
  if (params.id) openAgent(params.id);

  const offAgent = events.on('agent', (a) => {
    if (!alive) return;
    const i = list.findIndex(x => x.id === a.id);
    if (i >= 0) list[i] = a; else list.push(a);
    const el = grid.querySelector(`[data-id="${a.id}"]`);
    if (el) el.replaceWith(agentCard(a)); else renderGrid();
    if (drawer && drawerId === a.id) { const head = drawer.el.querySelector('[data-head]'); if (head) head.replaceWith(drawerHead(a)); }
  });

  return () => { alive = false; offAgent(); if (drawer) drawer.close(); };

  /* ---------- render ---------- */
  function renderGrid() {
    if (!list.length) { mount(grid, EmptyState({ icon: 'agents', title: 'Ultron Core is standing by.', body: 'Specialist agents appear here as work is delegated.' })); grid.classList.remove('c3'); return; }
    grid.classList.add('c3');
    mount(grid, list.map(agentCard));
  }
  function agentCard(a) {
    return h('div', { class: 'agent-card', 'data-id': a.id, role: 'button', tabindex: 0, 'aria-label': a.name + ' — open details', onClick: () => openAgent(a.id), onKeydown: (e) => { if (e.key === 'Enter' && e.target === e.currentTarget) openAgent(a.id); } },
      h('div', { class: 'ah' }, Dot(a.status), h('h4', { class: 'truncate' }, a.name), Badge({ label: a.status, tone: TONE[a.status] || 'neutral' })),
      h('div', { class: 'role' }, a.role),
      h('p', { class: 'muted', style: { fontSize: '13px' } }, a.description),
      h('div', { class: 'caps' }, (a.capabilities || []).map(c => h('span', null, c))),
      a.currentTask && a.status === 'working' && h('div', { class: 'cur' }, icon('activity', 14), h('span', { class: 'truncate' }, a.currentTask)),
      h('div', { class: 'af' }, h('span', null, `${fmt.num(a.executions || 0)} runs`), h('span', null, 'last ' + (a.lastRun ? fmt.relShort(a.lastRun) : 'never'))));
  }
  function agentName(id) { return list.find(a => a.id === id)?.name || id; }
  function dur(v) { if (v == null) return ''; if (v < 1000) return v + 'ms'; if (v < 60000) return (v / 1000).toFixed(1) + 's'; return Math.round(v / 60000) + 'm'; }
  function clock(d) { return new Date(d || Date.now()).toLocaleTimeString('en', { hour12: false }); }
  function logLine(at, who, msg) { return h('div', { class: 'log-line' }, h('span', { class: 'w' }, clock(at)), h('span', null, who), h('span', { class: 'm' }, msg)); }

  /* ---------- orchestration ---------- */
  async function runOrchestration() {
    if (running) return;
    const req = (request || '').trim() || DEFAULT_REQUEST;
    running = true; runBtn.classList.add('loading');
    nodes.forEach(n => n.classList.remove('running', 'done'));
    edges.forEach(e => e.classList.remove('live', 'done'));
    lbls.forEach((l, i) => l.textContent = NODES[i].lbl.toUpperCase());
    clear(log); clear(result);
    presence.setState('thinking', 'Understanding the request');
    try {
      const res = await agentService.orchestrate(req, (ev) => {
        if (ev.type !== 'step' || !alive) return;
        const n = nodes[ev.index], e = edges[ev.index - 1], l = lbls[ev.index];
        if (ev.status === 'running') {
          n?.classList.add('running'); n?.classList.remove('done');
          e?.classList.add('live'); e?.classList.remove('done');
          if (l) l.textContent = short(ev.label);
          presence.setState('working', ev.label);
          log.append(logLine(null, agentName(ev.agent), ev.label));
        } else {
          n?.classList.remove('running'); n?.classList.add('done');
          e?.classList.remove('live'); e?.classList.add('done');
          log.append(logLine(null, agentName(ev.agent), ev.label + ' · done'));
        }
        log.scrollTop = log.scrollHeight;
      });
      if (!alive) return;
      mount(result, Card({ title: 'Result', children: [
        h('div', { class: 'row', style: { marginBottom: '10px' } }, res.verified ? Badge({ label: 'Verified', tone: 'ok' }) : Badge({ label: 'Unverified', tone: 'warn' }), h('span', { class: 'faint', style: { fontSize: '12px' } }, res.verified ? 'Ultron Core checked the output before reporting.' : 'Output was not verified.')),
        h('p', null, res.summary),
        (res.plan || []).length ? [h('div', { class: 'sec-h', style: { margin: '14px 0 8px' } }, 'Development plan'), h('ol', null, res.plan.map(p => h('li', null, p)))] : null,
      ] }));
      presence.setState('success', 'Orchestration complete');
      toast('Orchestration complete');
    } catch (err) {
      if (!alive) return;
      presence.setState('error', 'Orchestration failed');
      nodes.forEach(n => n.classList.remove('running')); edges.forEach(e => e.classList.remove('live'));
      mount(result, ErrorState({ title: 'Orchestration failed', what: err.message || 'The agents did not finish.', why: err.status ? 'Status ' + err.status : 'An agent stopped responding.', next: 'Run it again. If it keeps failing, check the agent logs.', onRetry: () => runOrchestration() }));
    } finally { running = false; runBtn.classList.remove('loading'); }
  }
  function short(s) { return s.length > 22 ? s.slice(0, 21) + '…' : s; }

  /* ---------- drawer ---------- */
  function drawerHead(a) {
    return h('div', { 'data-head': '', class: 'stack' },
      h('div', { class: 'row' }, Dot(a.status), h('span', { class: 'muted' }, a.role), h('div', { class: 'spacer' }), Badge({ label: a.status, tone: TONE[a.status] || 'neutral' })),
      a.currentTask && a.status === 'working' && h('div', { class: 'agent-cur' }, icon('activity', 14), h('span', { class: 'truncate' }, a.currentTask)),
      h('p', { class: 'muted', style: { fontSize: '13px' } }, a.description),
      h('div', { class: 'kv' }, h('div', null, h('b', null, a.model || '—'), 'model'), h('div', null, h('b', null, fmt.num(a.executions || 0)), 'executions'), h('div', null, h('b', null, a.lastRun ? fmt.relShort(a.lastRun) : 'never'), 'last run'), h('div', null, h('b', null, a.permissions?.length ? 'scoped' : 'none'), 'permissions')),
      a.permissions?.length ? Field({ label: 'Permissions', control: h('div', { class: 'chips' }, a.permissions.map(p => Badge({ label: p, tone: p === 'EXECUTE' ? 'warn' : p === 'WRITE' ? 'info' : undefined }))) }) : null,
      (a.capabilities || []).length ? Field({ label: 'Capabilities', control: h('div', { class: 'cap-list' }, a.capabilities.map(c => h('span', null, c))) }) : null);
  }
  async function openAgent(id) {
    let a = list.find(x => x.id === id);
    if (!a) { try { a = await agentService.get(id); } catch { toast('Agent not found', { tone: 'bad' }); return; } }
    if (drawer) drawer.close();
    drawerId = a.id;
    history.replaceState(null, '', '#/agents/' + a.id);
    const panel = h('div');
    const tabs = Tabs({ items: [{ key: 'exec', label: 'Recent executions' }, { key: 'logs', label: 'Logs' }, { key: 'config', label: 'Configuration' }], active: 'exec', onChange: show });
    drawer = Drawer({ title: a.name, body: [drawerHead(a), h('div', null, tabs, panel)], onClose: () => { drawer = null; drawerId = null; if (alive) history.replaceState(null, '', '#/agents'); } });
    show('exec');

    function show(key) {
      if (key === 'exec') load(panel, () => agentService.executions(a.id), (xs) => xs.length ? h('div', { class: 'list' }, xs.map(execRow)) : h('p', { class: 'faint', style: { fontSize: '12.5px' } }, 'No executions yet.'), { skeleton: Skeleton({ lines: 4 }) }).catch(() => null);
      else if (key === 'logs') load(panel, () => agentService.executions(a.id), (xs) => { const lines = logsFrom(xs); return lines.length ? h('div', { class: 'logs' }, lines) : h('p', { class: 'faint', style: { fontSize: '12.5px' } }, 'No log entries yet.'); }, { skeleton: Skeleton({ lines: 5 }) }).catch(() => null);
      else mount(panel, configPanel(a));
    }
  }
  function execRow(x) {
    return Row({ icon: h('div', { class: 'ic' }, Dot(x.status)), title: x.task,
      subtitle: x.status === 'failed' && x.error ? x.error : x.status === 'running' ? (x.steps?.length ? x.steps.join(' → ') : 'Running…') : x.status,
      meta: fmt.relShort(x.startedAt), trailing: x.ms != null && h('span', { class: 'when' }, dur(x.ms)) });
  }
  function logsFrom(xs) {
    const lines = [];
    for (const x of xs) {
      if (x.status === 'done') lines.push(logLine(x.endedAt || x.startedAt, 'DONE', `${x.task} · ${dur(x.ms)}`));
      else if (x.status === 'failed') lines.push(logLine(x.endedAt || x.startedAt, 'FAIL', `${x.task} · ${x.error || 'failed'}`));
      else (x.steps || []).slice().reverse().forEach(s => lines.push(logLine(x.startedAt, 'STEP', s)));
      lines.push(logLine(x.startedAt, 'START', x.task));
    }
    return lines;
  }
  function configPanel(a) {
    return h('div', { class: 'stack' },
      h('div', { class: 'row between' }, h('div', null, h('div', { style: { fontSize: '13.5px' } }, 'Enabled'), h('div', { class: 'faint', style: { fontSize: '12px' } }, 'Ultron Core can delegate work to this agent.')), Toggle({ checked: true, label: 'Enabled', onChange: (on) => toast(on ? 'Agent enabled' : 'Agent disabled') })),
      Field({ label: 'Model', control: Select({ options: MODELS.includes(a.model) ? MODELS : [a.model || 'local', ...MODELS], value: a.model || 'local', onChange: () => toast('Saved') }) }),
      h('p', { class: 'faint', style: { fontSize: '12px' } }, 'Local models run on this machine. Cloud escalation only happens when you allow it.'));
  }
}

/* Inline SVG for the orchestration flow — static, author-controlled strings only. */
function orchSvg() {
  const W = 150, H = 56, Y = 52, xs = [10, 192.5, 375, 557.5, 740], ym = Y + H / 2;
  let s = `<svg viewBox="0 0 900 160" role="img" aria-label="Orchestration flow: Ultron Core delegates to the Research, Knowledge and Planning agents, then verifies the result.">`;
  for (let i = 0; i < xs.length - 1; i++) {
    const x1 = xs[i] + W, x2 = xs[i + 1] - 2;
    s += `<path class="edge" data-i="${i}" d="M${x1} ${ym} L${x2} ${ym} M${x2 - 7} ${ym - 5} L${x2} ${ym} L${x2 - 7} ${ym + 5}"/>`;
  }
  NODES.forEach((n, i) => {
    const x = xs[i], cx = x + W / 2;
    s += `<g class="node" data-i="${i}"><text class="lbl" x="${cx}" y="${Y - 14}" text-anchor="middle">0${i + 1}</text><rect x="${x}" y="${Y}" width="${W}" height="${H}" rx="10"/><text x="${cx}" y="${Y + 24}" text-anchor="middle">${n.name}</text><text class="lbl" data-lbl="" x="${cx}" y="${Y + 42}" text-anchor="middle">${n.lbl.toUpperCase()}</text></g>`;
  });
  return s + '</svg>';
}
