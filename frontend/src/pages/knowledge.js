// Knowledge — documents, notes and links Ultron can reason over. Add (modal or drag/drop), filter, live processing, detail drawer.
import { h, icon, fmt, mount } from '../ui/dom.js';
import { PageHeader, Button, Chip, Badge, Input, Select, Field, Progress, EmptyState, AiState, load, Modal, confirm, Drawer, toast } from '../ui/components/index.js';
import { knowledgeService, events } from '../services/index.js';
import { appState } from '../store.js';
import { navigate } from '../router.js';

const TYPES = ['pdf', 'doc', 'note', 'link', 'image', 'code'];
const TYPE_ICON = { pdf: 'file', doc: 'file', note: 'note', link: 'link', image: 'image', code: 'code' };
const TYPE_LABEL = { pdf: 'PDF', doc: 'Doc', note: 'Note', link: 'Link', image: 'Image', code: 'Code' };
const EXT_TYPE = { pdf: 'pdf', doc: 'doc', docx: 'doc', odt: 'doc', rtf: 'doc', ppt: 'doc', pptx: 'doc', xls: 'doc', xlsx: 'doc', txt: 'note', md: 'note', markdown: 'note',
  png: 'image', jpg: 'image', jpeg: 'image', gif: 'image', webp: 'image', svg: 'image', bmp: 'image',
  js: 'code', mjs: 'code', ts: 'code', tsx: 'code', jsx: 'code', py: 'code', json: 'code', html: 'code', css: 'code', sh: 'code', ps1: 'code', rs: 'code', go: 'code', java: 'code', c: 'code', cpp: 'code', h: 'code', yml: 'code', yaml: 'code', toml: 'code', sql: 'code',
  url: 'link', webloc: 'link' };

export default async function knowledge(root, { params, query }) {
  /* ---------- state (all declared before any await) ---------- */
  let type = TYPES.includes(query.type) ? query.type : 'all';
  let q = query.q || '';
  let items = [], listSeq = 0, searchTimer = null, drawer = null, drawerId = null, openModal = null, leaving = false;

  /* ---------- scaffolding ---------- */
  const chipsHost = h('div', { class: 'chips' });
  const gridHost = h('div');
  const search = Input({ placeholder: 'Search titles and tags', icon: 'search', value: q,
    onInput: (v) => { q = v; clearTimeout(searchTimer); searchTimer = setTimeout(() => refreshList(), 150); },
    onEnter: () => { clearTimeout(searchTimer); refreshList(); } });
  const dropzone = h('div', { class: 'dropzone', role: 'button', tabindex: 0, 'aria-label': 'Add knowledge: drop files here, or press Enter', style: { marginBottom: '16px' },
    onClick: () => openAdd(),
    onKeydown: (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openAdd(); } },
    onDragenter: (e) => { e.preventDefault(); dropzone.classList.add('over'); },
    onDragover: (e) => { e.preventDefault(); if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'; dropzone.classList.add('over'); },
    onDragleave: (e) => { if (!dropzone.contains(e.relatedTarget)) dropzone.classList.remove('over'); },
    onDrop: onDrop },
    h('div', { class: 'row', style: { justifyContent: 'center' } }, icon('upload', 16), h('span', null, 'Drop files here, or click to add')));

  mount(root,
    PageHeader({ title: 'Knowledge', subtitle: 'Documents, notes, and links Ultron can reason over.', actions: [Button({ label: 'Add knowledge', icon: 'plus', variant: 'primary', onClick: () => openAdd() })] }),
    dropzone,
    h('div', { class: 'row between', style: { flexWrap: 'wrap', gap: '10px', marginBottom: '16px' } }, chipsHost, h('div', { style: { flex: '1 1 220px', maxWidth: '360px' } }, search)),
    gridHost);

  renderChips();
  const offKnowledge = events.on('knowledge', onKnowledgeEvent);
  await refreshList();
  if (params.id) openDetail(params.id);

  return () => { leaving = true; offKnowledge(); clearTimeout(searchTimer); drawer?.close(); openModal?.close(); };

  /* ---------- filters ---------- */
  function renderChips() {
    mount(chipsHost, [{ key: 'all', label: 'All' }, ...TYPES.map(t => ({ key: t, label: TYPE_LABEL[t] }))]
      .map(c => Chip({ label: c.label, active: type === c.key, onClick: () => { if (type === c.key) return; type = c.key; renderChips(); refreshList(); } })));
  }
  function setSearch(v) { q = v; search.querySelector('input').value = v; refreshList(); }

  /* ---------- list ---------- */
  async function refreshList({ quiet } = {}) {
    const seq = ++listSeq;
    const fetcher = async () => { const list = await knowledgeService.list({ type: type === 'all' ? undefined : type, q: q.trim() || undefined }); if (seq === listSeq) items = list; return list; };
    if (quiet) { try { const list = await fetcher(); if (seq === listSeq) mount(gridHost, renderList(list)); } catch (e) { console.error(e); } return; }
    await load(gridHost, fetcher, (list) => seq === listSeq ? renderList(list) : null, { skeleton: h('div', { class: 'k-grid', 'aria-busy': 'true' }, Array.from({ length: 6 }, () => h('div', { class: 'skel', style: { height: '140px', borderRadius: 'var(--r-md)' } }))) }).catch(() => null);
  }
  function renderList(list) {
    if (!list.length) {
      const filtered = type !== 'all' || q.trim();
      return filtered
        ? EmptyState({ icon: 'search', title: 'Nothing matches.', body: 'Try another word, or a different type.', action: { label: 'Clear filters', variant: 'ghost', onClick: () => { type = 'all'; q = ''; search.querySelector('input').value = ''; renderChips(); refreshList(); } } })
        : EmptyState({ icon: 'knowledge', title: 'No knowledge yet.', body: 'Add a document, link, or note to start your library.', action: { label: 'Add knowledge', icon: 'plus', onClick: () => openAdd() } });
    }
    return h('div', { class: 'k-grid' }, list.map(kCard));
  }
  function metaLine(k) {
    return [k.source, k.size ? fmt.bytes(k.size) : null, fmt.relShort(k.createdAt), k.pages ? k.pages + (k.pages === 1 ? ' page' : ' pages') : null].filter(Boolean).join(' · ');
  }
  function kCard(k) {
    return h('div', { class: 'k-card', 'data-id': k.id, role: 'button', tabindex: 0, 'aria-label': k.title, onClick: () => openDetail(k.id), onKeydown: (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openDetail(k.id); } } },
      h('div', { class: 'kt' }, h('div', { class: 'ic' }, icon(TYPE_ICON[k.type] || 'file')), h('h4', null, k.title)),
      h('div', { class: 'ks' }, metaLine(k)),
      k.status === 'processing' ? h('div', { class: 'proc' }, Progress({ value: k.progress || 0 }), h('span', null, `Analysing… ${Math.round(k.progress || 0)}%`)) : null,
      k.tags?.length ? h('div', { class: 'tags' }, k.tags.map(t => h('span', null, t))) : null);
  }
  /** Progress ticks patch the card in place; a status change re-renders it (so the rise animation only plays once). */
  function patchCard(k) {
    const old = gridHost.querySelector(`.k-card[data-id="${k.id}"]`); if (!old) return;
    const proc = old.querySelector('.proc');
    if (k.status === 'processing' && proc) { proc.querySelector('.progress i').style.width = Math.max(0, Math.min(100, k.progress || 0)) + '%'; proc.querySelector('span').textContent = `Analysing… ${Math.round(k.progress || 0)}%`; }
    else old.replaceWith(kCard(k));
  }
  function upsert(k) {
    const i = items.findIndex(x => x.id === k.id);
    const prev = i >= 0 ? items[i] : null;
    if (i >= 0) items[i] = k; else items.unshift(k);
    return prev;
  }
  function current(id) { return items.find(x => x.id === id); }

  function onKnowledgeEvent(k) {
    if (!k || !k.id) return;
    const i = items.findIndex(x => x.id === k.id);
    if (i < 0) return;                                       // not in the current view — it will be there on the next load
    const prev = items[i]; items[i] = k;
    patchCard(k);
    if (drawer && drawerId === k.id && (prev.status !== k.status || prev.summary !== k.summary || k.status === 'processing')) drawer.setBody(detailBody(k));
  }

  /* ---------- add ---------- */
  function onDrop(e) {
    e.preventDefault(); dropzone.classList.remove('over');
    const files = [...(e.dataTransfer?.files || [])];
    if (files.length) { addFiles(files); return; }
    const url = (e.dataTransfer?.getData('text/uri-list') || e.dataTransfer?.getData('text/plain') || '').trim().split('\n')[0];
    if (/^https?:\/\//i.test(url)) { openAdd({ title: url.replace(/^https?:\/\//i, '').replace(/\/$/, ''), type: 'link', source: url }); return; }
    openAdd();
  }
  function inferType(f) {
    const ext = (f.name.split('.').pop() || '').toLowerCase();
    if (EXT_TYPE[ext]) return EXT_TYPE[ext];
    if (f.type.startsWith('image/')) return 'image';
    if (f.type.startsWith('text/')) return 'note';
    return 'doc';
  }
  async function addFiles(files) {
    let added = 0, failed = 0;
    for (const f of files) {
      const t = inferType(f);
      const title = t === 'code' ? f.name : f.name.replace(/\.[^.]+$/, '') || f.name;
      try { await addItem({ title, type: t, source: 'Upload', size: f.size || undefined, tags: [] }); added++; } catch (e) { console.error(e); failed++; }
    }
    if (added) toast(added === 1 ? `Added ${files[0].name}` : `Added ${added} files`, { action: added === 1 && items[0] ? { label: 'Open', onClick: () => openDetail(items[0].id) } : undefined });
    if (failed) toast(`${failed} file${failed === 1 ? '' : 's'} could not be added`, { tone: 'bad' });
  }
  async function addItem(body) {
    const k = await knowledgeService.add(body);
    if ((type !== 'all' && type !== k.type) || q.trim()) { type = 'all'; q = ''; search.querySelector('input').value = ''; renderChips(); await refreshList({ quiet: true }); return k; }
    upsert(k);
    const grid = gridHost.querySelector('.k-grid');
    if (grid) grid.prepend(kCard(k)); else mount(gridHost, renderList(items));
    return k;
  }
  function openAdd(preset = {}) {
    if (openModal) return;
    let title = preset.title || '', t = preset.type || 'doc', source = preset.source || '', tags = '';
    const submit = () => openModal?.el.querySelector('.mf .primary')?.click();
    const titleIn = Input({ placeholder: 'What is it called?', value: title, onInput: (v) => title = v, onEnter: submit });
    openModal = Modal({ title: 'Add knowledge', onClose: () => openModal = null,
      body: [
        Field({ label: 'Title', control: titleIn }),
        h('div', { class: 'grid c2' },
          Field({ label: 'Type', control: Select({ options: TYPES.map(x => ({ value: x, label: TYPE_LABEL[x] })), value: t, onChange: (v) => t = v }) }),
          Field({ label: 'Source', control: Input({ placeholder: 'Upload, folder, or URL', value: source, onInput: (v) => source = v, onEnter: submit }) })),
        Field({ label: 'Tags', control: Input({ placeholder: 'comma, separated', icon: 'tag', onInput: (v) => tags = v, onEnter: submit }) }),
      ],
      actions: [{ label: 'Cancel', variant: 'ghost' }, { label: 'Add', variant: 'primary', onClick: async () => {
        const ttl = title.trim(); if (!ttl) { titleIn.querySelector('input').focus(); return false; }
        try {
          const k = await addItem({ title: ttl, type: t, source: source.trim() || undefined, tags: tags.split(',').map(s => s.trim().toLowerCase()).filter(Boolean) });
          toast('Added to knowledge', { action: { label: 'Open', onClick: () => openDetail(k.id) } });
        } catch (e) { toast(e.message || 'Could not add', { tone: 'bad' }); return false; }
      } }] });
  }

  /* ---------- detail drawer ---------- */
  async function openDetail(id) {
    let k = current(id);
    if (!k) {
      try { k = await knowledgeService.get(id); upsert(k); }
      catch (e) { toast(e.status === 404 ? 'That item is no longer in the library' : (e.message || 'Could not open item'), { tone: 'bad' }); if (location.hash.startsWith('#/knowledge/')) history.replaceState(null, '', '#/knowledge'); return; }
    }
    if (drawer) drawer.close();
    drawerId = id;
    drawer = Drawer({ title: k.title, body: detailBody(k),
      onClose: () => { drawer = null; drawerId = null; if (!leaving && location.hash.startsWith('#/knowledge/')) history.replaceState(null, '', '#/knowledge'); },
      actions: [
        { label: 'Summarize', icon: 'spark', onClick: async (e) => {
          const btn = e.currentTarget; btn.classList.add('loading');
          try { const upd = await knowledgeService.summarize(id); upsert(upd); patchCard(upd); if (drawer && drawerId === id) drawer.setBody(detailBody(upd)); toast('Summary ready'); }
          catch (err) { toast(err.message || 'Could not summarize', { tone: 'bad' }); }
          finally { btn.classList.remove('loading'); }
        } },
        { label: 'Ask Ultron', icon: 'chat', variant: 'primary', onClick: () => {
          const cur = current(id) || k;
          appState.set({ context: { type: 'document', id, label: cur.title } });
          leaving = true; drawer?.close();
          navigate('/chat?new=1&ask=' + encodeURIComponent('Explain this.'));
        } },
        { label: 'Save to memory', icon: 'memory', onClick: async (e) => {
          const btn = e.currentTarget; btn.classList.add('loading');
          try { await knowledgeService.saveToMemory(id); toast('Saved to memory', { action: { label: 'Open', onClick: () => navigate('/memory') } }); }
          catch (err) { toast(err.message || 'Could not save to memory', { tone: 'bad' }); }
          finally { btn.classList.remove('loading'); }
        } },
        { label: 'Create knowledge graph', icon: 'mind', onClick: () => { leaving = true; drawer?.close(); navigate('/mind'); } },
        { label: 'Delete', icon: 'trash', variant: 'danger', onClick: () => removeItem(id) },
      ] });
    if (!location.hash.startsWith('#/knowledge/' + id)) history.replaceState(null, '', '#/knowledge/' + encodeURIComponent(id));
  }
  function detailBody(k) {
    const meta = [k.source, k.size ? fmt.bytes(k.size) : null, k.pages ? k.pages + (k.pages === 1 ? ' page' : ' pages') : null, 'added ' + fmt.relShort(k.createdAt)].filter(Boolean).join(' · ');
    const processing = k.status === 'processing';
    return [
      h('div', { class: 'row' }, Badge({ label: TYPE_LABEL[k.type] || k.type }), processing ? Badge({ label: 'Processing', tone: 'busy' }) : null),
      h('div', { class: 'faint mono', style: { fontSize: '11.5px' } }, meta),
      processing ? h('div', { class: 'stack' }, Progress({ value: k.progress || 0 }), AiState(`Analysing… ${Math.round(k.progress || 0)}%`)) : null,
      h('div', { class: 'report' },
        h('h3', null, 'Summary'),
        k.summary ? h('p', null, k.summary) : (processing ? h('p', { class: 'muted' }, 'The summary appears as soon as analysis finishes.') : AiState('Not analysed yet')),
        k.tags?.length ? [h('h3', null, 'Tags'), h('div', { class: 'chips' }, k.tags.map(t => Chip({ label: t, icon: 'tag', onClick: () => { drawer?.close(); setSearch(t); } })))] : null),
    ];
  }
  async function removeItem(id) {
    const k = current(id);
    const ok = await confirm({ title: k ? `Delete “${k.title}”?` : 'Delete this item?', message: 'It leaves the library and the knowledge graph. Memories made from it stay.', confirmLabel: 'Delete', danger: true });
    if (!ok) return;
    try {
      await knowledgeService.remove(id);
      items = items.filter(x => x.id !== id);
      if (drawer && drawerId === id) drawer.close();
      gridHost.querySelector(`.k-card[data-id="${id}"]`)?.remove();
      if (!items.length) mount(gridHost, renderList(items));
      toast('Removed from knowledge');
    } catch (e) { toast(e.message || 'Could not delete', { tone: 'bad' }); }
  }
}
