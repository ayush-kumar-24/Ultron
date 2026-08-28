// Calendar — day / week / month views over events, with Ultron's context line and quick event creation.
import { h, icon, fmt, mount } from '../ui/dom.js';
import { PageHeader, Button, IconButton, Chip, Badge, Input, Select, Field, EmptyState, load, Modal, Drawer, confirm, toast, Skeleton } from '../ui/components/index.js';
import { calendarService, projectService } from '../services/index.js';
import { navigate } from '../router.js';

const VIEWS = ['day', 'week', 'month'];
const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const TYPES = [{ value: 'meeting', label: 'Meeting' }, { value: 'focus', label: 'Focus block' }, { value: 'deadline', label: 'Deadline' }, { value: 'reminder', label: 'Reminder' }];
const TONE = { meeting: 'info', focus: 'think', deadline: 'bad', reminder: 'warn' };
const DAY_START = 8, ROW_PX = 44, ROWS = 14; // 08:00–22:00 (matches .cal-week .hrs in pages.css)

export default async function calendar(root, { params, query }) {
  const view = VIEWS.includes(params.view) ? params.view : 'week';
  // all page state is declared here, before any await (see docs/PAGES.md)
  let anchor = startOfDay(query.d ? new Date(query.d + 'T00:00') : new Date());
  if (isNaN(anchor)) anchor = startOfDay(new Date());
  let projects = [], eventsCache = [], disposed = false;

  /* ---------- scaffolding ---------- */
  const ctxText = h('span', null, 'Reading your calendar…');
  const ctx = h('div', { class: 'cal-ctx' }, h('div', { class: 'mini-orb', 'aria-hidden': 'true' }), ctxText);
  const label = h('h2', null, rangeLabel());
  const nav = h('div', { class: 'cal-nav' },
    IconButton({ icon: 'chevl', label: 'Previous ' + view, square: true, onClick: () => shift(-1) }),
    IconButton({ icon: 'chev', label: 'Next ' + view, square: true, onClick: () => shift(1) }),
    Button({ label: 'Today', size: 'sm', onClick: () => { anchor = startOfDay(new Date()); refresh(); } }),
    label,
    h('div', { class: 'spacer' }),
    h('div', { class: 'chips', role: 'group', 'aria-label': 'Calendar view' }, VIEWS.map(v => Chip({ label: v[0].toUpperCase() + v.slice(1), active: v === view, onClick: () => switchView(v) }))));
  const grid = h('div', { class: 'cal-grid' });

  mount(root,
    PageHeader({ title: 'Calendar', subtitle: 'Meetings, focus blocks and deadlines — one honest picture of your time.', actions: [
      Button({ label: 'Add event', icon: 'plus', variant: 'primary', onClick: addEvent }),
    ] }),
    ctx, nav, grid);

  loadContext();
  projectService.list().then(ps => { projects = ps; }).catch(() => {});
  await refresh();

  return () => { disposed = true; };

  /* ---------- navigation ---------- */
  function switchView(v) {
    if (v === view) return;
    navigate('/calendar/' + v + (isSameDay(anchor, new Date()) ? '' : '?d=' + dayISO(anchor)));
  }
  function shift(dir) {
    const d = new Date(anchor);
    if (view === 'day') d.setDate(d.getDate() + dir);
    else if (view === 'week') d.setDate(d.getDate() + 7 * dir);
    else d.setMonth(d.getMonth() + dir, 1);
    anchor = startOfDay(d);
    refresh();
  }
  function range() {
    if (view === 'day') return { from: anchor, to: addDays(anchor, 1) };
    if (view === 'week') { const s = startOfWeek(anchor); return { from: s, to: addDays(s, 7) }; }
    const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1), s = startOfWeek(first);
    return { from: s, to: addDays(s, 42) };
  }
  function rangeLabel() {
    if (view === 'day') return fmt.dateLong(anchor);
    if (view === 'month') return anchor.toLocaleDateString('en', { month: 'long', year: 'numeric' });
    const { from, to } = range(); const end = addDays(to, -1);
    const a = from.toLocaleDateString('en', { month: 'short', day: 'numeric' });
    const b = end.toLocaleDateString('en', from.getMonth() === end.getMonth() ? { day: 'numeric' } : { month: 'short', day: 'numeric' });
    return `${a} – ${b}, ${end.getFullYear()}`;
  }

  /* ---------- data ---------- */
  function refresh() {
    label.textContent = rangeLabel();
    history.replaceState(null, '', '#/calendar/' + view + (isSameDay(anchor, new Date()) ? '' : '?d=' + dayISO(anchor)));
    return load(grid, fetchRange, renderGrid, { skeleton: Skeleton({ lines: 8, height: 36 }) }).catch(() => {});
  }
  async function fetchRange() {
    const { from, to } = range();
    const list = await calendarService.events({ from: from.toISOString(), to: to.toISOString() });
    eventsCache = list.slice().sort((a, b) => new Date(a.start) - new Date(b.start));
    return eventsCache;
  }
  async function loadContext() {
    try { const c = await calendarService.context(); if (!disposed) ctxText.textContent = c.text; }
    catch { if (!disposed) ctxText.textContent = 'Ultron could not read your calendar right now.'; }
  }
  function eventsOn(day) { return eventsCache.filter(e => isSameDay(new Date(e.start), day)); }
  function renderGrid(evs) {
    if (view === 'day') return renderDay(evs);
    if (view === 'month') return renderMonth();
    return renderWeek();
  }

  /* ---------- week ---------- */
  function renderWeek() {
    const { from } = range();
    const days = Array.from({ length: 7 }, (_, i) => addDays(from, i));
    return h('div', { class: 'cal-week', role: 'grid', 'aria-label': 'Week of ' + fmt.date(from) },
      h('div', { class: 'hd', 'aria-hidden': 'true' }),
      days.map(d => h('div', { class: ['hd', isSameDay(d, new Date()) && 'today'], role: 'columnheader' }, DOW[(d.getDay() + 6) % 7], h('b', null, d.getDate()))),
      h('div', { class: 'hrs', 'aria-hidden': 'true' }, Array.from({ length: ROWS }, (_, i) => h('span', null, String(DAY_START + i).padStart(2, '0') + ':00'))),
      days.map(d => h('div', { class: 'day', role: 'gridcell', 'aria-label': fmt.date(d) }, eventsOn(d).map(WeekEvent))));
  }
  function WeekEvent(e) {
    const s = new Date(e.start), en = new Date(e.end || e.start);
    const deadline = en.getTime() <= s.getTime();
    const maxPx = ROWS * ROW_PX;
    let top = (s.getHours() - DAY_START) * ROW_PX + s.getMinutes() / 60 * ROW_PX;
    let height = deadline ? 22 : Math.max(22, (en - s) / 3.6e6 * ROW_PX);
    if (top < 0) { height += top; top = 0; }
    height = Math.max(22, Math.min(height, maxPx - top));
    top = Math.min(top, maxPx - 22);
    return h('div', { class: 'cal-ev', 'data-t': e.type, role: 'button', tabindex: 0, style: { top: top + 'px', height: height + 'px' }, title: e.title + ' · ' + timeRange(e),
      onClick: () => openEvent(e), onKeydown: (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); openEvent(e); } } },
      h('b', null, e.title), h('span', null, deadline ? fmt.time(s) : timeRange(e)));
  }

  /* ---------- month ---------- */
  function renderMonth() {
    const { from } = range();
    const cells = Array.from({ length: 42 }, (_, i) => addDays(from, i));
    return h('div', { class: 'cal-month', role: 'grid', 'aria-label': rangeLabel() },
      DOW.map(d => h('div', { class: 'hd', role: 'columnheader' }, d)),
      cells.map(d => {
        const evs = eventsOn(d), extra = evs.length - 3;
        return h('div', { class: ['cell', d.getMonth() !== anchor.getMonth() && 'dim', isSameDay(d, new Date()) && 'today'], role: 'gridcell' },
          h('button', { class: 'n', 'aria-label': 'Open ' + fmt.date(d), onClick: () => openDay(d) }, d.getDate()),
          evs.slice(0, 3).map(e => h('div', { class: 'pill', 'data-t': e.type, role: 'button', tabindex: 0, title: e.title + ' · ' + timeRange(e), onClick: () => openEvent(e), onKeydown: (ev) => { if (ev.key === 'Enter') openEvent(e); } }, fmt.time(e.start) + ' ' + e.title)),
          extra > 0 && h('button', { class: 'faint', style: { fontSize: '10.5px', marginTop: '3px' }, onClick: () => openDay(d) }, `+${extra} more`));
      }));
  }
  function openDay(d) { navigate('/calendar/day' + (isSameDay(d, new Date()) ? '' : '?d=' + dayISO(d))); }

  /* ---------- day ---------- */
  function renderDay(evs) {
    if (!evs.length) return EmptyState({ icon: 'calendar', title: 'Nothing scheduled.', body: 'Connect a calendar or add an event.', action: { label: 'Add event', onClick: addEvent } });
    const busy = evs.reduce((a, e) => a + Math.max(0, new Date(e.end || e.start) - new Date(e.start)) / 3.6e6, 0);
    const free = Math.max(0, 8 - busy);
    const meetings = evs.filter(e => e.type === 'meeting').length;
    return h('div', { class: 'card cal-day' },
      h('div', { class: 'row between', style: { fontSize: '12.5px', color: 'var(--t2)', marginBottom: '10px', flexWrap: 'wrap', gap: '8px' } },
        h('span', null, `${evs.length} event${evs.length === 1 ? '' : 's'} · ${meetings} meeting${meetings === 1 ? '' : 's'}`),
        h('span', { class: 'num' }, `${fmtHours(busy)} busy · about ${fmtHours(free)} free`)),
      h('div', null, evs.map(e => h('div', { class: 'slot', role: 'button', tabindex: 0, onClick: () => openEvent(e), onKeydown: (ev) => { if (ev.key === 'Enter') openEvent(e); }, style: { cursor: 'pointer' } },
        h('div', { class: 't' }, fmt.time(e.start)),
        h('div', { style: { minWidth: 0 } },
          h('div', { class: 'row', style: { gap: '8px', flexWrap: 'wrap' } }, h('span', { style: { fontSize: '13.5px', fontWeight: 500 } }, e.title), Badge({ label: e.type, tone: TONE[e.type] })),
          h('div', { class: 'faint', style: { fontSize: '11.5px', marginTop: '2px' } }, timeRange(e), projectName(e.projectId) ? ' · ' + projectName(e.projectId) : ''))))));
  }

  /* ---------- event detail ---------- */
  function openEvent(e) {
    const pname = projectName(e.projectId);
    const drawer = Drawer({
      title: e.title,
      body: [
        h('div', { class: 'row', style: { gap: '8px' } }, Badge({ label: e.type, tone: TONE[e.type] })),
        h('div', { class: 'kv' },
          h('div', null, h('b', null, fmt.date(e.start)), 'date'),
          h('div', null, h('b', null, timeRange(e)), 'time'),
          pname && h('div', null, h('b', null, pname), 'project'),
          h('div', null, h('b', null, durationText(e)), 'duration')),
        e.taskId && h('div', null, Button({ label: 'Open task', icon: 'tasks', variant: 'ghost', onClick: () => { drawer.close(); navigate('/tasks/today'); } })),
      ],
      actions: [
        { label: 'Delete', variant: 'danger', icon: 'trash', onClick: async () => {
          if (!await confirm({ title: 'Delete event?', message: `“${e.title}” is removed from your calendar.`, confirmLabel: 'Delete', danger: true })) return;
          try { await calendarService.remove(e.id); toast('Event deleted'); drawer.close(); await refresh(); }
          catch (err) { toast(err.message || 'Could not delete the event', { tone: 'bad' }); }
        } },
        { label: 'Close', variant: 'ghost', onClick: () => drawer.close() },
      ],
    });
  }

  /* ---------- add event ---------- */
  function addEvent() {
    const base = new Date(anchor); base.setHours(Math.min(21, Math.max(DAY_START, new Date().getHours() + 1)), 0, 0, 0);
    const draft = { title: '', type: 'meeting', start: toLocalInput(base), end: toLocalInput(new Date(base.getTime() + 3.6e6)) };
    const endField = Input({ type: 'datetime-local', value: draft.end, onInput: (v) => draft.end = v });
    const modal = Modal({
      title: 'Add event',
      body: [
        Field({ label: 'Title', control: Input({ placeholder: 'e.g. Investor call', onInput: (v) => draft.title = v, onEnter: async () => { if (await submit() !== false) modal.close(); } }) }),
        Field({ label: 'Type', control: Select({ options: TYPES, value: draft.type, onChange: (v) => { draft.type = v; endField.style.opacity = v === 'deadline' ? '.5' : ''; } }) }),
        h('div', { class: 'grid c2' },
          Field({ label: 'Start', control: Input({ type: 'datetime-local', value: draft.start, onInput: (v) => { draft.start = v; if (draft.end < v) { draft.end = v; endField.querySelector('input').value = v; } } }) }),
          Field({ label: 'End', control: endField })),
        h('p', { class: 'faint', style: { fontSize: '11.5px' } }, 'Deadlines ignore the end time and show as a single marker.'),
      ],
      actions: [
        { label: 'Cancel', variant: 'ghost' },
        { label: 'Add event', variant: 'primary', onClick: submit },
      ],
    });

    async function submit() {
      const title = draft.title.trim();
      if (!title) { toast('Give the event a title', { tone: 'warn' }); return false; }
      if (!draft.start) { toast('Pick a start time', { tone: 'warn' }); return false; }
      const start = new Date(draft.start), end = draft.type === 'deadline' || !draft.end ? start : new Date(draft.end);
      if (isNaN(start) || isNaN(end)) { toast('That date does not look right', { tone: 'warn' }); return false; }
      if (end < start) { toast('End must be after start', { tone: 'warn' }); return false; }
      try {
        await calendarService.add({ title, type: draft.type, start: start.toISOString(), end: end.toISOString() });
        toast('Event added');
        anchor = startOfDay(start);
        await refresh();
        return true;
      } catch (err) { toast(err.message || 'Could not add the event', { tone: 'bad' }); return false; }
    }
  }

  /* ---------- local helpers ---------- */
  function projectName(id) { return id ? projects.find(p => p.id === id)?.name : null; }
  function timeRange(e) { const s = new Date(e.start), en = new Date(e.end || e.start); return en <= s ? fmt.time(s) : fmt.time(s) + ' – ' + fmt.time(en); }
  function durationText(e) { const m = Math.round((new Date(e.end || e.start) - new Date(e.start)) / 6e4); return m > 0 ? fmt.dur(m) : 'Point in time'; }
}

/* ---------- date helpers ---------- */
function startOfDay(d) { const x = new Date(d); x.setHours(0, 0, 0, 0); return x; }
function startOfWeek(d) { const x = startOfDay(d); x.setDate(x.getDate() - (x.getDay() + 6) % 7); return x; } // Monday
function addDays(d, n) { const x = new Date(d); x.setDate(x.getDate() + n); return x; }
function isSameDay(a, b) { return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate(); }
function dayISO(d) { const p = (n) => String(n).padStart(2, '0'); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`; }
function toLocalInput(d) { const x = new Date(d), p = (n) => String(n).padStart(2, '0'); return `${dayISO(x)}T${p(x.getHours())}:${p(x.getMinutes())}`; }
function fmtHours(hrs) { const m = Math.round(hrs * 60); return m ? fmt.dur(m) : '0m'; }
