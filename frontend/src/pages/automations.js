// Automations — recurring intelligence. Plain-language creation, status ops, run-now, execution history.
import { h, fmt, mount } from '../ui/dom.js';
import { PageHeader, Button, IconButton, Chip, Badge, Dot, Input, Textarea, Field, Toggle, EmptyState, Skeleton, SkeletonCard, load, Modal, confirm, Drawer, Menu, toast } from '../ui/components/index.js';
import { automationService, events } from '../services/index.js';
import { presence } from '../ui/core/presence.js';

const TONE = { active: 'ok', paused: 'warn', failed: 'bad' };
const FILTERS = [['all', 'All'], ['active', 'Active'], ['paused', 'Paused'], ['failed', 'Failed']];

export default async function automations(root, { params, query }) {
  let items = [], filter = 'all', drawer = null, drawerId = null, alive = true;
  const chips = h('div', { class: 'chips', style: { marginBottom: '16px' } });
  const list = h('div', { class: 'stack' });

  mount(root,
    PageHeader({ title: 'Automations', subtitle: 'Recurring intelligence, on your schedule.', actions: [Button({ label: 'Create automation', icon: 'plus', variant: 'primary', onClick: openCreate })] }),
    chips, list);

  await refresh();
  if (query.new === '1') openCreate();
  else if (params.id) openDrawer(params.id);

  const offAuto = events.on('automation', (a) => {
    if (!alive) return;
    const i = items.findIndex(x => x.id === a.id);
    if (i >= 0) items[i] = a; else items.unshift(a);
    const el = list.querySelector(`[data-id="${a.id}"]`);
    if (el) { if (matches(a)) el.replaceWith(card(a)); else el.remove(); }
    else if (matches(a)) renderList();
    if (!list.querySelector('.auto-card')) renderList();
    renderChips();
    if (drawer && drawerId === a.id) drawer.setBody(drawerBody(a));
  });

  return () => { alive = false; offAuto(); if (drawer) drawer.close(); };

  /* ---------- data ---------- */
  async function refresh(silent) {
    if (!silent) {
      await load(list, () => automationService.list(), (data) => { items = data; renderChips(); renderList(); }, { skeleton: h('div', { class: 'stack' }, SkeletonCard({ lines: 3 }), SkeletonCard({ lines: 3 }), SkeletonCard({ lines: 3 })) }).catch(() => null);
      return;
    }
    try { items = await automationService.list(); if (!alive) return; renderChips(); renderList(); if (drawer && drawerId) { const a = items.find(x => x.id === drawerId); if (a) drawer.setBody(drawerBody(a)); } }
    catch (err) { toast(err.message || 'Could not refresh automations', { tone: 'bad' }); }
  }
  function matches(a) { return filter === 'all' || a.status === filter; }
  function counts() { return items.reduce((c, a) => { c.all++; c[a.status] = (c[a.status] || 0) + 1; return c; }, { all: 0, active: 0, paused: 0, failed: 0 }); }
  function ms(v) { if (v == null) return ''; return v >= 1000 ? (v / 1000).toFixed(1) + 's' : v + 'ms'; }

  /* ---------- render ---------- */
  function renderChips() {
    const c = counts();
    mount(chips, FILTERS.map(([key, label]) => Chip({ label, count: c[key], active: filter === key, onClick: () => { filter = key; renderChips(); renderList(); } })));
  }
  function renderList() {
    if (!items.length) { mount(list, EmptyState({ icon: 'automations', title: 'No automations running.', body: 'Create your first intelligent workflow.', action: { label: 'Create automation', icon: 'plus', onClick: openCreate } })); return; }
    const shown = items.filter(matches);
    mount(list, shown.length ? shown.map(card) : EmptyState({ icon: 'filter', title: 'Nothing here.', body: `No ${filter} automations right now.` }));
  }
  function card(a) {
    const ops = h('div', { class: 'ops', onClick: (e) => e.stopPropagation() },
      Badge({ label: a.status, tone: TONE[a.status] || 'neutral' }),
      h('div', { class: 'row' },
        Toggle({ checked: a.status === 'active', label: (a.status === 'active' ? 'Pause ' : 'Activate ') + a.name, onChange: (on) => setStatus(a, on ? 'active' : 'paused') }),
        Button({ label: 'Run now', icon: 'play', size: 'sm', onClick: (e) => runNow(a, e.currentTarget) }),
        IconButton({ icon: 'more', label: 'More options for ' + a.name, size: 'sm', square: true, onClick: (e) => Menu(e.currentTarget, [
          { label: 'Open history', icon: 'clock', onClick: () => openDrawer(a.id) },
          { label: a.status === 'active' ? 'Pause' : 'Activate', icon: a.status === 'active' ? 'pause' : 'play', onClick: () => setStatus(a, a.status === 'active' ? 'paused' : 'active') },
          '-',
          { label: 'Delete', icon: 'trash', danger: true, onClick: () => remove(a) },
        ]) })));
    return h('div', { class: ['auto-card', a.status === 'failed' && 'failed'], 'data-id': a.id, role: 'button', tabindex: 0, 'aria-label': a.name + ' — open details',
      onClick: () => openDrawer(a.id), onKeydown: (e) => { if (e.key === 'Enter' && e.target === e.currentTarget) openDrawer(a.id); } },
      h('div', { style: { minWidth: 0 } },
        h('h4', null, Dot(a.status), h('span', { class: 'truncate' }, a.name)),
        h('div', { class: 'rule' }, h('b', null, 'Trigger'), h('span', null, a.trigger), h('b', null, 'Action'), h('span', null, a.action)),
        h('div', { class: 'runs' }, h('span', null, `${fmt.num(a.runs || 0)} runs`), h('span', null, `${fmt.num(a.failures || 0)} failures`), h('span', null, 'last ' + (a.lastRun ? fmt.relShort(a.lastRun) : 'never')), h('span', null, 'next ' + (a.nextRun ? fmt.date(a.nextRun) : '—'))),
        (a.error || a.note) && h('div', { class: 'err' }, a.error || a.note)),
      ops);
  }
  function runRow(r) {
    return h('div', { class: 'run-row' }, Dot(r.status), h('span', { class: 'faint num', title: fmt.date(r.at) + ' · ' + fmt.time(r.at) }, fmt.time(r.at)), h('span', { class: 'o', title: r.output }, r.output), h('span', { class: 'faint num' }, ms(r.ms)));
  }

  /* ---------- mutations ---------- */
  async function setStatus(a, status) {
    try { await automationService.update(a.id, { status }); toast(status === 'active' ? 'Automation activated' : 'Automation paused'); }
    catch (err) { toast(err.message || 'Could not update automation', { tone: 'bad' }); }
    if (alive) await refresh(true);
  }
  async function runNow(a, btn) {
    btn?.classList.add('loading');
    presence.setState('working', a.name);
    try {
      const run = await automationService.run(a.id);
      if (run.status === 'failed') { presence.setState('error', run.output || 'Run failed'); toast(`${a.name} failed: ${run.output}`, { tone: 'bad', action: { label: 'History', onClick: () => openDrawer(a.id) } }); }
      else { presence.setState('success', `${a.name} · done`); toast(`${a.name} ran · ${ms(run.ms)}`); }
    } catch (err) { presence.setState('error', 'Run failed'); toast(err.message || 'Run failed', { tone: 'bad' }); }
    finally { btn?.classList.remove('loading'); }
    if (alive) await refresh(true);
  }
  async function remove(a) {
    if (!await confirm({ title: 'Delete automation?', message: `“${a.name}” stops running and its history is removed.`, confirmLabel: 'Delete', danger: true })) return;
    try { await automationService.remove(a.id); toast('Automation deleted'); if (drawer) drawer.close(); await refresh(true); }
    catch (err) { toast(err.message || 'Could not delete automation', { tone: 'bad' }); }
  }

  /* ---------- create ---------- */
  function openCreate() {
    let text = '', name = '';
    const ta = Textarea({ placeholder: 'Describe it in plain language — e.g. “Every morning summarise my schedule”', rows: 3, onInput: (v) => text = v, ref: (el) => el.addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); submit(); } }) });
    const m = Modal({ title: 'Create automation', body: [
      Field({ label: 'What should happen, and when?', control: ta }),
      Field({ label: 'Name (optional)', control: Input({ placeholder: 'e.g. Morning briefing', onInput: (v) => name = v, onEnter: () => submit() }) }),
      h('p', { class: 'faint', style: { fontSize: '12px' } }, 'Ultron works out the trigger and the action from your description.'),
    ], actions: [{ label: 'Cancel', variant: 'ghost' }, { label: 'Create', variant: 'primary', onClick: () => create() }] });
    async function submit() { if (await create() !== false) m.close(); }
    async function create() {
      if (!text.trim()) { toast('Describe the automation first', { tone: 'warn' }); ta.focus(); return false; }
      try { await automationService.create({ text: text.trim(), name: name.trim() || undefined }); toast('Automation created'); filter = 'all'; await refresh(true); }
      catch (err) { toast(err.message || 'Could not create automation', { tone: 'bad' }); return false; }
    }
  }

  /* ---------- drawer ---------- */
  function drawerBody(a) {
    const hist = h('div', { class: 'list' });
    load(hist, () => automationService.runs(a.id), (runs) => runs.length ? runs.map(runRow) : h('p', { class: 'faint', style: { fontSize: '12.5px' } }, 'No runs yet. Run it now to see output here.'), { skeleton: Skeleton({ lines: 3 }) }).catch(() => null);
    return [
      h('div', { class: 'row' }, Dot(a.status), Badge({ label: a.status, tone: TONE[a.status] || 'neutral' }), (a.error || a.note) && h('span', { class: 'muted truncate', style: { fontSize: '12.5px' } }, a.error || a.note)),
      Field({ label: 'Trigger', control: h('p', null, a.trigger) }),
      Field({ label: 'Action', control: h('p', null, a.action) }),
      h('div', { class: 'kv' },
        h('div', null, h('b', null, fmt.num(a.runs || 0)), 'runs'),
        h('div', null, h('b', null, fmt.num(a.failures || 0)), 'failures'),
        h('div', null, h('b', null, a.lastRun ? fmt.relShort(a.lastRun) : 'never'), 'last run'),
        h('div', null, h('b', null, a.nextRun ? fmt.date(a.nextRun) : '—'), 'next run')),
      h('div', null, h('h4', { style: { fontSize: '13px', marginBottom: '6px' } }, 'Execution history'), hist),
    ];
  }
  function openDrawer(id) {
    const a = items.find(x => x.id === id);
    if (!a) { toast('Automation not found', { tone: 'bad' }); return; }
    if (drawer) drawer.close();
    drawerId = a.id;
    history.replaceState(null, '', '#/automations/' + a.id);
    drawer = Drawer({ title: a.name, body: drawerBody(a), onClose: () => { drawer = null; drawerId = null; if (alive) history.replaceState(null, '', '#/automations'); }, actions: [
      { label: 'Run now', icon: 'play', variant: 'primary', onClick: (e) => runNow(a, e.currentTarget) },
      { label: a.status === 'active' ? 'Pause' : 'Activate', icon: a.status === 'active' ? 'pause' : 'play', onClick: () => setStatus(a, a.status === 'active' ? 'paused' : 'active').then(() => { if (drawer) drawer.close(); }) },
      { label: 'Delete', icon: 'trash', variant: 'danger', onClick: () => remove(a) },
    ] });
  }
}
