// Memory — what Ultron knows about you, and why. Stats, categories, search, teach / edit / pin / delete.
import { h, fmt, mount } from '../ui/dom.js';
import { PageHeader, Button, IconButton, Tabs, Badge, Input, Select, Textarea, Field, Metric, RingGauge, EmptyState, load, Modal, confirm, toast } from '../ui/components/index.js';
import { memoryService } from '../services/index.js';
import { presence } from '../ui/core/presence.js';

const CATEGORIES = ['personal', 'preferences', 'projects', 'people', 'work', 'conversations', 'learned'];
const IMPORTANCE = ['high', 'medium', 'low'];
const cap = (s) => s ? s[0].toUpperCase() + s.slice(1) : '';

export default async function memory(root, { query }) {
  /* ---------- state (all declared before any await) ---------- */
  let category = CATEGORIES.includes(query.category) ? query.category : 'all';
  let q = query.q || '';
  let stats = null, listSeq = 0, searchTimer = null, openModal = null;

  /* ---------- scaffolding ---------- */
  const statsHost = h('div', { style: { marginBottom: '18px' } });
  const tabsHost = h('div');
  const listHost = h('div', { class: 'stack' });
  const search = Input({ placeholder: 'Search memories', icon: 'search', value: q,
    onInput: (v) => { q = v; clearTimeout(searchTimer); searchTimer = setTimeout(() => refreshList(), 150); },
    onEnter: () => { clearTimeout(searchTimer); refreshList(); } });

  mount(root,
    PageHeader({ title: 'Memory', subtitle: 'What Ultron knows about you, and why.', actions: [Button({ label: 'Teach Ultron', icon: 'plus', variant: 'primary', onClick: () => openTeach() })] }),
    statsHost, tabsHost,
    h('div', { class: 'row', style: { marginBottom: '14px' } }, h('div', { style: { flex: '1 1 220px', maxWidth: '420px' } }, search)),
    listHost);

  if (query.teach === '1') { history.replaceState(null, '', '#/memory' + (q ? '?q=' + encodeURIComponent(q) : '')); openTeach(); }
  await Promise.all([refreshStats(), refreshList()]);

  return () => { clearTimeout(searchTimer); openModal?.close(); };

  /* ---------- stats + tabs ---------- */
  async function refreshStats(quiet) {
    if (quiet) { try { stats = await memoryService.stats(); mount(statsHost, renderStats(stats)); } catch (e) { console.error(e); } renderTabs(); return; }
    const skeleton = h('div', { class: 'mem-stats', 'aria-busy': 'true' }, h('div', { class: 'skel', style: { width: '96px', height: '96px', borderRadius: '50%' } }), h('div', { class: 'skel', style: { height: '76px' } }), h('div', { class: 'skel', style: { height: '76px' } }), h('div', { class: 'skel', style: { height: '76px' } }));
    try { await load(statsHost, () => memoryService.stats(), (s) => { stats = s; return renderStats(s); }, { skeleton }); } catch { /* ErrorState is shown by load() */ }
    renderTabs();
  }
  function renderStats(s) {
    if (!s || !s.total) return null;                       // nothing to measure yet — the list's empty state speaks instead
    return h('div', { class: 'mem-stats' },
      RingGauge({ value: Math.round(s.recall || 0), label: 'recall', size: 96 }),
      Metric({ label: 'Memories', value: fmt.num(s.total) }),
      Metric({ label: 'Learned today', value: fmt.num(s.learnedToday || 0), delta: s.learnedToday ? 'since midnight' : 'nothing new yet' }),
      Metric({ label: 'Pinned', value: fmt.num(s.pinned || 0), delta: 'always recalled' }));
  }
  function renderTabs() {
    const by = stats?.byCategory || {};
    const all = Object.values(by).reduce((a, n) => a + n, 0);
    const items = [{ key: 'all', label: 'All', count: all || undefined }, ...CATEGORIES.map(c => ({ key: c, label: cap(c), count: by[c] || undefined }))];
    mount(tabsHost, Tabs({ items, active: category, onChange: (k) => { category = k; refreshList(); } }));
  }

  /* ---------- list ---------- */
  async function refreshList({ quiet } = {}) {
    const seq = ++listSeq;
    const fetcher = () => memoryService.list({ category: category === 'all' ? undefined : category, q: q.trim() || undefined });
    if (quiet) { try { const list = await fetcher(); if (seq === listSeq) mount(listHost, renderList(list)); } catch (e) { console.error(e); } return; }
    await load(listHost, fetcher, (list) => seq === listSeq ? renderList(list) : null).catch(() => null);
  }
  function renderList(list) {
    if (!list.length) {
      const filtered = category !== 'all' || q.trim();
      return filtered
        ? EmptyState({ icon: 'search', title: 'Nothing matches.', body: 'Try another word, or a different category.', action: { label: 'Clear filters', variant: 'ghost', onClick: clearFilters } })
        : EmptyState({ icon: 'memory', title: 'No memories yet.', body: 'Give Ultron something worth remembering.', action: { label: 'Teach Ultron', icon: 'plus', onClick: () => openTeach() } });
    }
    return list.map(memCard);
  }
  function clearFilters() { category = 'all'; q = ''; search.querySelector('input').value = ''; renderTabs(); refreshList(); }

  function memCard(m) {
    const conf = Math.round((m.confidence || 0) * 100);
    const pinBtn = IconButton({ icon: 'pin', label: m.pinned ? 'Unpin' : 'Pin', class: m.pinned && 'on', onClick: () => togglePin(m, card, pinBtn) });
    const card = h('div', { class: ['mem-card', m.pinned && 'pinned'], 'data-id': m.id },
      h('div', null,
        h('div', { class: 'txt' }, m.text),
        h('div', { class: 'mt' },
          h('span', null, h('b', null, m.source || 'Unknown source')),
          h('span', { title: new Date(m.createdAt).toLocaleString() }, fmt.relShort(m.createdAt)),
          h('span', { class: 'conf', title: 'Confidence ' + conf + '%' }, conf + '%', h('i', null, h('b', { style: { width: conf + '%' } }))),
          Badge({ label: m.importance || 'medium', tone: m.importance === 'high' ? 'warn' : 'neutral' }),
          m.lastAccessed && h('span', null, 'recalled ' + fmt.relShort(m.lastAccessed)),
          h('span', null, fmt.num(m.accessCount || 0) + (m.accessCount === 1 ? ' recall' : ' recalls')))),
      h('div', { class: 'ops' }, pinBtn,
        IconButton({ icon: 'edit', label: 'Edit memory', onClick: () => openEdit(m) }),
        IconButton({ icon: 'trash', label: 'Delete memory', onClick: () => removeMemory(m, card) })));
    return card;
  }

  /* ---------- mutations ---------- */
  async function togglePin(m, card, btn) {
    const next = !m.pinned;
    paint(next);
    try { await memoryService.update(m.id, { pinned: next }); m.pinned = next; toast(next ? 'Pinned' : 'Unpinned'); refreshStats(true); refreshList({ quiet: true }); }
    catch (e) { paint(!next); toast(e.message || 'Could not update memory', { tone: 'bad' }); }
    function paint(on) { card.classList.toggle('pinned', on); btn.classList.toggle('on', on); btn.setAttribute('aria-label', on ? 'Unpin' : 'Pin'); btn.title = on ? 'Unpin' : 'Pin'; }
  }
  function openEdit(m) {
    let text = m.text;
    const ta = Textarea({ value: m.text, rows: 4, onInput: (v) => text = v, ref: (el) => el.addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); openModal?.el.querySelector('.mf .primary')?.click(); } }) });
    openModal = Modal({ title: 'Edit memory', body: Field({ label: 'Memory', control: ta }), onClose: () => openModal = null,
      actions: [{ label: 'Cancel', variant: 'ghost' }, { label: 'Save', variant: 'primary', onClick: async () => {
        const t = text.trim(); if (!t) { ta.focus(); return false; }
        if (t === m.text) return;
        try { await memoryService.update(m.id, { text: t }); m.text = t; toast('Memory updated'); refreshList({ quiet: true }); }
        catch (e) { toast(e.message || 'Could not save memory', { tone: 'bad' }); return false; }
      } }] });
  }
  async function removeMemory(m, card) {
    if (!await confirm({ title: 'Delete this memory?', message: 'Ultron forgets it permanently. Nothing else is affected.', confirmLabel: 'Delete', danger: true })) return;
    const next = card.nextSibling; card.remove();
    try {
      await memoryService.remove(m.id); toast('Memory deleted'); refreshStats(true);
      if (!listHost.querySelector('.mem-card')) refreshList({ quiet: true });
    } catch (e) { listHost.insertBefore(card, next && next.parentNode === listHost ? next : null); toast(e.message || 'Could not delete memory', { tone: 'bad' }); }
  }
  function openTeach() {
    if (openModal) return;
    let text = '', cat = category !== 'all' ? category : 'personal', imp = 'medium';
    const ta = Textarea({ placeholder: 'Something worth remembering — a preference, a fact, a person, a decision.', rows: 4, onInput: (v) => text = v,
      ref: (el) => el.addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); openModal?.el.querySelector('.mf .primary')?.click(); } }) });
    openModal = Modal({ title: 'Teach Ultron', onClose: () => openModal = null,
      body: [
        Field({ label: 'Memory', control: ta }),
        h('div', { class: 'grid c2' },
          Field({ label: 'Category', control: Select({ options: CATEGORIES.map(c => ({ value: c, label: cap(c) })), value: cat, onChange: (v) => cat = v }) }),
          Field({ label: 'Importance', control: Select({ options: IMPORTANCE.map(c => ({ value: c, label: cap(c) })), value: imp, onChange: (v) => imp = v }) })),
        h('p', { class: 'faint', style: { fontSize: '12px' } }, 'Ctrl+Enter to save.'),
      ],
      actions: [{ label: 'Cancel', variant: 'ghost' }, { label: 'Remember', variant: 'primary', onClick: async () => {
        const t = text.trim(); if (!t) { ta.focus(); return false; }
        try {
          await memoryService.create({ text: t, category: cat, importance: imp });
          toast('Remembered'); presence.setState('success', 'Remembered');
          if (category !== 'all' && category !== cat) category = 'all';
          if (q) { q = ''; search.querySelector('input').value = ''; }
          refreshStats(true); refreshList({ quiet: true });
        } catch (e) { toast(e.message || 'Could not save memory', { tone: 'bad' }); return false; }
      } }] });
  }
}
