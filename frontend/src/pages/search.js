// Search — one box over everything Ultron knows: conversations, memories, knowledge, tasks, research, projects, people.
import { h, mount } from '../ui/dom.js';
import { PageHeader, Card, Input, Row, EmptyState, Skeleton, load } from '../ui/components/index.js';
import { searchService } from '../services/index.js';
import { bus } from '../store.js';
import { navigate } from '../router.js';

const KIND_ICON = { conversation: 'chat', memory: 'memory', knowledge: 'knowledge', task: 'tasks', research: 'research', project: 'projects', person: 'user' };
const KIND_LABEL = { conversation: 'Conversations', memory: 'Memories', knowledge: 'Knowledge', task: 'Tasks', research: 'Research', project: 'Projects', person: 'People' };
const ORDER = Object.keys(KIND_ICON);

export default async function search(root, { query }) {
  /* ---------- state (all declared before any await) ---------- */
  let q = query.q || '', seq = 0, timer = null, inputEl = null;

  /* ---------- scaffolding ---------- */
  const results = h('div', { class: 'sr' });
  const input = Input({ placeholder: 'Search everything…', icon: 'search', value: q, ref: (el) => inputEl = el,
    onInput: (v) => { q = v; clearTimeout(timer); timer = setTimeout(run, 200); },
    onEnter: () => { clearTimeout(timer); run(); } });
  mount(root,
    PageHeader({ title: 'Search', subtitle: 'Everything Ultron knows, in one place.' }),
    h('div', { style: { marginBottom: '18px', maxWidth: '640px' } }, input),
    results);

  setTimeout(() => inputEl?.focus(), 30);
  await run();
  return () => clearTimeout(timer);

  /* ---------- query ---------- */
  async function run() {
    const s = q.trim(), mine = ++seq;
    history.replaceState(null, '', '#/search' + (s ? '?q=' + encodeURIComponent(s) : ''));
    if (!s) { mount(results, EmptyState({ icon: 'search', title: 'Search everything.', body: 'Conversations, memories, documents, tasks, research, people.' })); return; }
    await load(results, () => searchService.query(s), (list) => mine === seq ? render(list, s) : null, { skeleton: h('div', { class: 'card' }, Skeleton({ lines: 4 })) }).catch(() => null);
  }
  function render(list, s) {
    if (!list.length) return EmptyState({ icon: 'search', title: `Nothing found for “${s}”.`, body: 'Ultron can still think it through with you.', action: { label: 'Ask Ultron instead', icon: 'spark', onClick: () => bus.emit('ask', s) } });
    const groups = new Map();
    for (const r of list) { if (!groups.has(r.kind)) groups.set(r.kind, []); groups.get(r.kind).push(r); }
    const kinds = [...ORDER.filter(k => groups.has(k)), ...[...groups.keys()].filter(k => !ORDER.includes(k))];
    return [
      h('p', { class: 'faint', style: { fontSize: '12px', margin: '0 4px 6px' } }, `${list.length} result${list.length === 1 ? '' : 's'} for “${s}”`),
      kinds.map(kind => Card({ title: `${KIND_LABEL[kind] || kind} · ${groups.get(kind).length}`, tight: true,
        children: h('div', { class: 'list' }, groups.get(kind).map(r => Row({ icon: KIND_ICON[kind] || 'circle', title: r.title, subtitle: r.sub, onClick: () => navigate(r.route) }))) })),
    ];
  }
}
