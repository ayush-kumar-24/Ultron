// Global command palette (Ctrl/Cmd+K): commands + live search across every entity.
import { h, icon, mount } from '../dom.js';
import { navigate } from '../../router.js';
import { searchService } from '../../services/index.js';
import { bus } from '../../store.js';

const COMMANDS = [
  { label: 'Ask Ultron', icon: 'spark', k: 'Enter', run: (q) => bus.emit('ask', q) },
  { label: 'New task', icon: 'tasks', run: () => navigate('/tasks?new=1') },
  { label: 'Search memory', icon: 'memory', run: (q) => navigate('/memory' + (q ? '?q=' + encodeURIComponent(q) : '')) },
  { label: 'Start research', icon: 'research', run: (q) => navigate('/research' + (q ? '?q=' + encodeURIComponent(q) : '?new=1')) },
  { label: 'Plan my day', icon: 'sunrise', run: () => navigate('/tasks/plan') },
  { label: 'Open knowledge', icon: 'knowledge', run: () => navigate('/knowledge') },
  { label: 'Start focus mode', icon: 'focus', run: () => navigate('/focus') },
  { label: 'Create automation', icon: 'automations', run: () => navigate('/automations?new=1') },
  { label: 'Open agents', icon: 'agents', run: () => navigate('/agents') },
  { label: 'Open chat', icon: 'chat', run: () => navigate('/chat') },
  { label: 'Open mind map', icon: 'mind', run: () => navigate('/mind') },
  { label: 'Open calendar', icon: 'calendar', run: () => navigate('/calendar') },
  { label: 'Open projects', icon: 'projects', run: () => navigate('/projects') },
  { label: 'Open goals', icon: 'goals', run: () => navigate('/goals') },
  { label: 'Open insights', icon: 'insights', run: () => navigate('/insights') },
  { label: 'Open activity', icon: 'activity', run: () => navigate('/activity') },
  { label: 'Open settings', icon: 'settings', run: () => navigate('/settings') },
  { label: 'Talk to Ultron', icon: 'mic', run: () => bus.emit('voice') },
];
const KIND_ICON = { conversation: 'chat', memory: 'memory', knowledge: 'knowledge', task: 'tasks', research: 'research', project: 'projects', person: 'user' };

let overlay, input, list, idx = 0, items = [], debounce = null;

function ensure() {
  if (overlay) return;
  input = h('input', { placeholder: 'Ask Ultron or jump anywhere…', autocomplete: 'off', 'aria-label': 'Command palette' });
  list = h('ul', { role: 'listbox' });
  overlay = h('div', { class: 'overlay', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Command palette', onClick: (e) => { if (e.target === overlay) closePalette(); } },
    h('div', { class: 'palette' }, h('div', { class: 'in' }, icon('search'), input), list, h('div', { class: 'foot' }, h('span', null, '↑↓ navigate'), h('span', null, '↵ run'), h('span', null, 'esc close'))));
  document.body.append(overlay);
  input.addEventListener('input', () => { clearTimeout(debounce); debounce = setTimeout(filter, 80); });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); idx = Math.min(items.length - 1, idx + 1); paint(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); idx = Math.max(0, idx - 1); paint(); }
    else if (e.key === 'Enter') { e.preventDefault(); run(); }
  });
  list.addEventListener('click', (e) => { const li = e.target.closest('li[data-i]'); if (li) { idx = +li.dataset.i; run(); } });
}

async function filter() {
  const q = input.value.trim(), ql = q.toLowerCase();
  const cmds = COMMANDS.filter(c => !q || c.label.toLowerCase().includes(ql)).map(c => ({ kind: 'command', label: c.label, icon: c.icon, k: c.k, run: () => c.run(q) }));
  let results = [];
  if (q.length >= 2) { try { results = (await searchService.query(q)).map(r => ({ kind: r.kind, label: r.title, sub: r.sub, icon: KIND_ICON[r.kind] || 'circle', run: () => navigate(r.route) })); } catch {} }
  items = [...cmds, ...results];
  if (q && !items.length) items = [{ kind: 'ask', label: `Ask Ultron: "${q}"`, icon: 'spark', run: () => bus.emit('ask', q) }];
  else if (q && !cmds.some(c => c.label === 'Ask Ultron')) items.unshift({ kind: 'ask', label: `Ask Ultron: "${q}"`, icon: 'spark', run: () => bus.emit('ask', q) });
  idx = 0; paint();
}
function paint() {
  const groups = [];
  const byKind = {};
  for (const it of items) (byKind[it.kind] = byKind[it.kind] || []).push(it);
  let i = 0;
  const labelFor = { ask: null, command: 'Commands', conversation: 'Conversations', memory: 'Memories', knowledge: 'Knowledge', task: 'Tasks', research: 'Research', project: 'Projects', person: 'People' };
  for (const [kind, arr] of Object.entries(byKind)) {
    if (labelFor[kind] && Object.keys(byKind).length > 1) groups.push(h('li', { class: 'group', role: 'presentation' }, labelFor[kind]));
    for (const it of arr) { const me = i++; groups.push(h('li', { role: 'option', 'data-i': me, 'aria-selected': me === idx ? 'true' : 'false' }, icon(it.icon), h('span', { class: 'truncate' }, it.label), it.sub && h('span', { class: 'sub' }, it.sub), it.k && h('span', { class: 'k' }, it.k))); }
  }
  mount(list, groups.length ? groups : h('li', { class: 'none' }, 'Nothing yet.'));
  list.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest' });
}
function run() { const it = items[idx]; if (!it) return; closePalette(); it.run(); }

export function openPalette(prefill = '') { ensure(); overlay.classList.add('on'); input.value = prefill; filter(); setTimeout(() => input.focus(), 10); }
export function closePalette() { overlay?.classList.remove('on'); }
export function isPaletteOpen() { return overlay?.classList.contains('on'); }
