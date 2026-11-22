// Overview — the home. Greeting, the presence, the command bar, and the intelligence dashboard.
import { h, icon, fmt, greeting, mount } from '../ui/dom.js';
import { Card, Row, RingGauge, Sparkline, Metric, Progress, Dot, load, SkeletonCard, EmptyState, toast } from '../ui/components/index.js';
import { overviewService, events } from '../services/index.js';
import { presence } from '../ui/core/presence.js';
import { appState, bus } from '../store.js';
import { navigate } from '../router.js';
import { CommandBar } from '../ui/commandbar.js';

const KIND_ICON = { chat: 'chat', memory: 'memory', research: 'research', tasks: 'check', agents: 'agents', automations: 'automations', system: 'terminal' };

export default async function overview(root, ctx) {
  const user = appState.get().user;
  const dock = h('div', { class: 'dock' });
  const status = h('div', { class: 'status' }, h('i'), 'Your intelligence layer is active.');
  const grid = h('div', { class: 'grid main', style: { marginTop: '16px' } });
  const metrics = h('div', { class: 'metrics', style: { marginTop: '16px' } });

  mount(root,
    h('section', { class: 'hero' },
      h('div', null, h('div', { class: 'eyebrow' }, `${greeting()}, ${user?.name || 'there'}.`), h('h1', null, 'Ready to get things done?'), status),
      h('div', { class: 'identity' }, dock, h('div', { class: 'word wordmark' }, 'Ultron'), h('div', { class: 'tag' }, 'Personal intelligence · Connected context'))),
    CommandBar({ onSubmit: (text) => bus.emit('ask', text), chips: true }),
    grid, metrics);

  presence.dock(dock);
  const offOnline = appState.subscribe((s) => { status.querySelector('i').classList.toggle('off', !s.online); status.lastChild.textContent = s.online ? 'Your intelligence layer is active.' : 'Offline — local intelligence only.'; }, ['online']);

  let agentsEl;
  const agentRow = (a) => h('div', { class: 'agent', 'data-id': a.id }, Dot(a.status), a.name, h('span', { class: 'st' }, a.currentTask && a.status === 'working' ? a.currentTask : a.status));
  const data = await load(grid, () => overviewService.summary(), (d) => renderGrid(d), { skeleton: h('div', { class: 'grid main' }, h('div', { class: 'col' }, SkeletonCard({ lines: 5 }), h('div', { class: 'grid c2' }, SkeletonCard(), SkeletonCard())), h('div', { class: 'col' }, SkeletonCard(), SkeletonCard(), SkeletonCard())) }).catch(() => null);
  if (data) mount(metrics, data.metrics.map(m => Metric({ label: m.l, value: m.v, delta: m.d, trend: m.up ? 'up' : '' })));

  function renderGrid(d) {
    agentsEl = h('div', { class: 'ov-agents' }, d.agents.map(agentRow));
    return [
      h('div', { class: 'col' },
        Card({ title: 'Cognitive activity', action: { label: 'See all', onClick: () => navigate('/activity') }, children: d.activity.length ? h('div', { class: 'list' }, d.activity.map(a => Row({ icon: KIND_ICON[a.kind] || 'circle', title: a.body, subtitle: a.title, meta: fmt.relShort(a.at), onClick: () => navigate('/activity') }))) : EmptyState({ icon: 'activity', title: 'Nothing yet today.', body: 'Ask Ultron something and it shows up here.' }) }),
        h('div', { class: 'grid c2' },
          Card({ title: 'Recent projects', action: { label: 'Open', onClick: () => navigate('/projects') }, class: 'projects', children: d.projects.length ? h('div', { class: 'list' }, d.projects.map(p => h('div', { class: 'row-item clickable', onClick: () => navigate('/projects/' + p.id) }, h('div', null, h('div', { class: 't' }, p.name), h('div', { style: { marginTop: '7px' } }, Progress({ value: p.progress }))), h('div', { class: 'when' }, p.progress + '%')))) : EmptyState({ icon: 'projects', title: 'No projects.', body: 'Create one to give Ultron context.' }) }),
          Card({ title: 'System activity', action: { label: 'Timeline', onClick: () => navigate('/activity') }, class: 'ov-log', children: d.log.length ? h('div', { class: 'list' }, d.log.map(l => h('div', { class: 'row-item' }, h('div', { class: 'when' }, fmt.time(l.at)), h('div', { class: 't' }, l.title)))) : h('p', { class: 'faint', style: { fontSize: '13px' } }, 'Quiet so far.') }))),
      h('div', { class: 'col' },
        Card({ title: 'Memory system', action: { label: 'Browse', onClick: () => navigate('/memory') }, children: d.memory.total ? [RingGauge({ value: d.memory.recall, label: 'recall', big: fmt.num(d.memory.total), sub: 'memories stored' }), h('div', { class: 'kv', style: { marginTop: '14px' } }, h('div', null, h('b', null, d.memory.learnedToday), 'learned today'), h('div', null, h('b', null, d.pinned), 'pinned'))] : EmptyState({ icon: 'memory', title: 'No memories yet.', body: 'Give Ultron something worth remembering.', action: { label: 'Teach Ultron', onClick: () => navigate('/memory?teach=1') } }) }),
        Card({ title: 'Focus index', action: { label: 'This week', onClick: () => navigate('/insights') }, children: Sparkline({ values: d.focus, labels: ['M', 'T', 'W', 'T', 'F', 'S', 'S'], highlight: (new Date().getDay() + 6) % 7 }) }),
        Card({ title: 'Productivity', action: { label: 'Tasks', onClick: () => navigate('/tasks') }, children: h('div', { class: 'kv' }, h('div', null, h('b', null, d.productivity.done), 'completed'), h('div', null, h('b', null, d.productivity.pending), 'pending'), h('div', null, h('b', null, d.productivity.rate + '%'), 'completion rate'), h('div', null, h('b', null, d.productivity.sessions), 'focus sessions')) }),
        Card({ title: 'Active agents', action: { label: 'Manage', onClick: () => navigate('/agents') }, children: agentsEl })),
    ];
  }
  const offAgent = events.on('agent', (a) => { const row = agentsEl?.querySelector(`[data-id="${a.id}"]`); if (row) row.replaceWith(agentRow(a)); });

  return () => { offAgent(); offOnline(); presence.dock(null); };
}
