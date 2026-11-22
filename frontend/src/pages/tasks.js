// Tasks — natural-language quick add, views (today/upcoming/inbox/completed/projects), detail drawer, and "Plan my day".
import { h, icon, fmt, mount, clear } from '../ui/dom.js';
import { PageHeader, Card, Button, IconButton, Tabs, Badge, Input, Select, Textarea, Field, Check, Progress, EmptyState, load, Drawer, confirm, toast } from '../ui/components/index.js';
import { taskService, projectService } from '../services/index.js';
import { presence } from '../ui/core/presence.js';
import { appState } from '../store.js';
import { navigate } from '../router.js';

const VIEWS = [
  { key: 'today', label: 'Today' },
  { key: 'upcoming', label: 'Upcoming' },
  { key: 'inbox', label: 'Inbox' },
  { key: 'completed', label: 'Completed' },
  { key: 'projects', label: 'Projects' },
  { key: 'plan', label: 'Plan my day' },
];
const EMPTY = {
  today: { icon: 'sun', title: 'Nothing due today.', body: 'Enjoy it, or pull something forward from Upcoming.', action: { label: 'Open Upcoming', variant: 'ghost', onClick: () => navigate('/tasks/upcoming') } },
  inbox: { icon: 'inbox', title: 'Inbox is clear.', body: 'Tell Ultron what needs doing — in plain language.' },
  completed: { icon: 'checkcircle', title: 'Nothing completed yet.' },
  generic: { icon: 'tasks', title: 'No tasks here.' },
};
const PLAN_BLOCKS = [['morning', 'Morning', 'sunrise'], ['afternoon', 'Afternoon', 'sun'], ['evening', 'Evening', 'moon']];
const PRIORITIES = [{ value: 'high', label: 'High' }, { value: 'medium', label: 'Medium' }, { value: 'low', label: 'Low' }];

export default async function tasks(root, { params, query }) {
  const view = VIEWS.some(v => v.key === params.view) ? params.view : 'today';
  // all page state is declared here, before any await (see docs/PAGES.md)
  let projects = [], parseTimer = null, parseSeq = 0, disposed = false;

  /* ---------- scaffolding ---------- */
  const quickInput = h('input', { type: 'text', 'aria-label': 'Add a task in plain language', placeholder: 'Add a task in plain language — e.g. “Remind me every Monday at 9 AM to review the roadmap”', autocomplete: 'off', value: query.text || '', onInput: onQuickInput, onKeydown: onQuickKey });
  const preview = h('div', { class: 'preview', 'aria-live': 'polite' });
  const quickAdd = h('div', { class: 'quickadd' }, icon('spark', 16), quickInput, preview, Button({ label: 'Add', size: 'sm', icon: 'plus', onClick: submitQuick }));
  const tabs = Tabs({ items: VIEWS, active: view, onChange: (k) => { if (k !== view) navigate('/tasks/' + k); } });
  const host = h('div', { class: 'col' });

  mount(root,
    PageHeader({ title: 'Tasks', subtitle: 'Say it in plain language. Ultron sorts it out.', actions: [
      Button({ label: 'Plan my day', icon: 'sunrise', onClick: () => navigate('/tasks/plan') }),
      Button({ label: 'New task', icon: 'plus', variant: 'primary', onClick: focusQuickAdd }),
    ] }),
    tabs,
    view === 'plan' ? null : quickAdd,
    host);

  if (view === 'plan') await loadPlan();
  else await refresh();
  if (query.new === '1' && view !== 'plan') focusQuickAdd();
  if (query.text && view !== 'plan') runParse(query.text);

  return () => { disposed = true; clearTimeout(parseTimer); };

  /* ---------- quick add ---------- */
  function focusQuickAdd() {
    if (view === 'plan') { navigate('/tasks/today?new=1'); return; }
    quickInput.focus(); quickInput.select();
  }
  function onQuickInput(e) {
    const text = e.target.value;
    clearTimeout(parseTimer);
    if (!text.trim()) { clear(preview); parseSeq++; return; }
    parseTimer = setTimeout(() => runParse(text), 200);
  }
  function onQuickKey(e) { if (e.key === 'Enter') { e.preventDefault(); submitQuick(); } else if (e.key === 'Escape') { quickInput.value = ''; clear(preview); } }
  async function runParse(text) {
    const seq = ++parseSeq;
    try {
      const p = await taskService.parse(text);
      if (seq !== parseSeq || disposed) return;
      renderPreview(p);
    } catch { if (seq === parseSeq) clear(preview); }
  }
  function renderPreview(p) {
    const project = projects.find(x => x.id === p.projectId);
    const chips = [];
    if (p.due) chips.push(h('span', { title: 'Due' }, fmt.date(p.due) + ' · ' + fmt.time(p.due)));
    if (p.recurrence) chips.push(h('span', { title: 'Recurrence' }, p.recurrence));
    if (p.priority) chips.push(h('span', { title: 'Priority' }, p.priority + ' priority'));
    if (project) chips.push(h('span', { title: 'Project' }, project.name));
    if (p.reminder) chips.push(h('span', { title: 'Reminder' }, 'reminder'));
    mount(preview, chips);
  }
  async function submitQuick() {
    const text = quickInput.value.trim();
    if (!text) { quickInput.focus(); return; }
    quickInput.disabled = true;
    try {
      const t = await taskService.create({ text });
      quickInput.value = ''; clear(preview); parseSeq++;
      if (t.automationId) toast('Task + automation created', { action: { label: 'Open', onClick: () => navigate('/automations') } });
      else toast('Task created');
      presence.setState('success');
      await refresh();
    } catch (err) {
      toast(err.message || 'Could not create the task', { tone: 'bad' });
    } finally { quickInput.disabled = false; quickInput.focus(); }
  }

  /* ---------- list views ---------- */
  async function fetchView() {
    const [ps, ts] = await Promise.all([projectService.list().catch(() => []), taskService.list(view === 'projects' ? {} : { view })]);
    projects = ps;
    return ts;
  }
  function refresh() { return load(host, fetchView, renderView).catch(() => {}); }
  function renderView(list) {
    if (view === 'projects') return renderProjects(list);
    if (!list.length) return EmptyState(emptyFor(view));
    return Card({ tight: true, children: h('div', { class: 'list' }, list.map(TaskRow)) });
  }
  function emptyFor(v) {
    const e = { ...(EMPTY[v] || EMPTY.generic) };
    if (v === 'inbox') e.action = { label: 'Add a task', variant: 'ghost', onClick: focusQuickAdd };
    return e;
  }
  function projectName(id) { return projects.find(p => p.id === id)?.name; }

  function TaskRow(t) {
    const done = t.status === 'done';
    const overdue = !done && t.due && new Date(t.due).getTime() < Date.now();
    const pname = projectName(t.projectId);
    const row = h('div', { class: ['task', done && 'done'], 'data-id': t.id },
      Check({ checked: done, label: (done ? 'Reopen: ' : 'Complete: ') + t.title, onChange: (v) => toggleDone(t, v, row) }),
      h('div', { style: { minWidth: 0 } },
        h('div', { class: 'tt truncate', role: 'button', tabindex: 0, onClick: () => openDetail(t), onKeydown: (e) => { if (e.key === 'Enter') openDetail(t); } }, t.title),
        h('div', { class: 'tm' },
          h('span', { class: 'pri', 'data-p': t.priority, title: 'Priority' }, h('i'), t.priority),
          t.due && h('span', { class: overdue && 'overdue', title: overdue ? 'Overdue' : 'Due' }, icon('clock', 11), ' ', fmt.date(t.due) + ' · ' + fmt.time(t.due)),
          pname && h('span', { title: 'Project' }, icon('projects', 11), ' ', pname),
          t.estimate ? h('span', { title: 'Estimate' }, fmt.dur(t.estimate)) : null,
          t.recurrence && h('span', { title: 'Repeats' }, icon('repeat', 11), ' ', t.recurrence),
          (t.tags || []).map(tag => h('span', { class: 'faint' }, '#' + tag)))),
      h('div', { class: 'ops' },
        IconButton({ icon: 'edit', label: 'Edit ' + t.title, onClick: () => openDetail(t) }),
        IconButton({ icon: 'trash', label: 'Delete ' + t.title, onClick: () => removeTask(t) })));
    return row;
  }

  async function toggleDone(t, done, row) {
    const prev = t.status;
    t.status = done ? 'done' : 'todo';
    row?.classList.toggle('done', done);
    try {
      await taskService.update(t.id, { status: t.status });
      toast(done ? 'Task completed' : 'Reopened');
      if (done) presence.setState('success');
    } catch (err) {
      t.status = prev; row?.classList.toggle('done', prev === 'done');
      const chk = row?.querySelector('.check'); if (chk) chk.setAttribute('aria-checked', prev === 'done' ? 'true' : 'false');
      toast(err.message || 'Could not update the task', { tone: 'bad' });
    }
  }
  async function removeTask(t) {
    if (!await confirm({ title: 'Delete task?', message: `“${t.title}” is removed permanently.`, confirmLabel: 'Delete', danger: true })) return false;
    try { await taskService.remove(t.id); toast('Task deleted'); await refresh(); return true; }
    catch (err) { toast(err.message || 'Could not delete the task', { tone: 'bad' }); return false; }
  }

  /* ---------- detail drawer ---------- */
  function openDetail(t) {
    const draft = { title: t.title, description: t.description || '', priority: t.priority || 'medium', due: t.due ? toLocalInput(t.due) : '', projectId: t.projectId || '', estimate: t.estimate ?? '', recurrence: t.recurrence || '', tags: (t.tags || []).join(', ') };
    const projectOpts = [{ value: '', label: 'No project' }, ...projects.map(p => ({ value: p.id, label: p.name }))];
    const drawer = Drawer({
      title: t.title,
      body: [
        h('div', { class: 'row', style: { gap: '8px' } }, Badge({ label: t.status.replace('_', ' '), tone: t.status === 'done' ? 'ok' : t.status === 'in_progress' ? 'busy' : undefined }), t.createdAt && h('span', { class: 'faint', style: { fontSize: '11.5px' } }, 'Created ' + fmt.rel(t.createdAt))),
        Field({ label: 'Title', control: Input({ value: draft.title, onInput: (v) => draft.title = v, onEnter: save }) }),
        Field({ label: 'Description', control: Textarea({ value: draft.description, placeholder: 'What does done look like?', onInput: (v) => draft.description = v }) }),
        h('div', { class: 'grid c2' },
          Field({ label: 'Priority', control: Select({ options: PRIORITIES, value: draft.priority, onChange: (v) => draft.priority = v }) }),
          Field({ label: 'Due', control: Input({ type: 'datetime-local', value: draft.due, onInput: (v) => draft.due = v }) })),
        h('div', { class: 'grid c2' },
          Field({ label: 'Project', control: Select({ options: projectOpts, value: draft.projectId, onChange: (v) => draft.projectId = v }) }),
          Field({ label: 'Estimate (minutes)', control: Input({ type: 'number', value: draft.estimate, placeholder: '30', onInput: (v) => draft.estimate = v }) })),
        h('div', { class: 'grid c2' },
          Field({ label: 'Recurrence', control: Input({ value: draft.recurrence, placeholder: 'e.g. Every Monday', onInput: (v) => draft.recurrence = v }) }),
          Field({ label: 'Tags', control: Input({ value: draft.tags, placeholder: 'comma, separated', onInput: (v) => draft.tags = v }) })),
        h('div', null, Button({ label: 'Ask Ultron about this', icon: 'spark', variant: 'ghost', onClick: askUltron })),
      ],
      actions: [
        { label: 'Save', variant: 'primary', onClick: save },
        { label: t.status === 'done' ? 'Reopen' : 'Mark done', icon: 'check', onClick: markDone },
        { label: 'Delete', variant: 'danger', onClick: async () => { if (await removeTask(t)) drawer.close(); } },
      ],
    });

    async function save() {
      const title = draft.title.trim();
      if (!title) { toast('Give the task a title', { tone: 'warn' }); return; }
      const patch = {
        title, description: draft.description.trim(), priority: draft.priority,
        due: draft.due ? new Date(draft.due).toISOString() : null,
        projectId: draft.projectId || null,
        estimate: draft.estimate === '' ? null : Math.max(0, Number(draft.estimate) || 0),
        recurrence: draft.recurrence.trim() || null,
        tags: draft.tags.split(',').map(s => s.trim()).filter(Boolean),
      };
      try { await taskService.update(t.id, patch); toast('Task saved'); drawer.close(); await refresh(); }
      catch (err) { toast(err.message || 'Could not save the task', { tone: 'bad' }); }
    }
    async function markDone() {
      const done = t.status !== 'done';
      try { await taskService.update(t.id, { status: done ? 'done' : 'todo' }); toast(done ? 'Task completed' : 'Reopened'); if (done) presence.setState('success'); drawer.close(); await refresh(); }
      catch (err) { toast(err.message || 'Could not update the task', { tone: 'bad' }); }
    }
    function askUltron() {
      drawer.close();
      appState.set({ context: { type: 'task', id: t.id, label: t.title } });
      navigate('/chat?new=1&ask=' + encodeURIComponent('How should I approach: ' + t.title));
    }
  }

  /* ---------- projects view ---------- */
  function renderProjects(list) {
    const open = list.filter(t => t.status !== 'done');
    if (!projects.length && !open.length) return EmptyState({ icon: 'projects', title: 'No projects yet.', body: 'Create a project to group work, or add tasks and Ultron will file them.', action: { label: 'Open Projects', variant: 'ghost', onClick: () => navigate('/projects') } });
    const cards = projects.map(p => {
      const rows = open.filter(t => t.projectId === p.id);
      return Card({ title: p.name, action: { label: 'Open project', onClick: () => navigate('/projects/' + p.id) }, children: [
        h('div', { class: 'row between', style: { fontSize: '11.5px', color: 'var(--t3)', marginBottom: '8px' } }, h('span', null, `${rows.length} open`), h('span', { class: 'num' }, fmt.pct(p.progress || 0))),
        Progress({ value: p.progress || 0 }),
        h('div', { class: 'list', style: { marginTop: '10px' } }, rows.length ? rows.map(TaskRow) : h('p', { class: 'faint', style: { fontSize: '12.5px', padding: '8px 0' } }, 'Nothing open here.')),
      ] });
    });
    const loose = open.filter(t => !t.projectId || !projects.some(p => p.id === t.projectId));
    if (loose.length) cards.push(Card({ title: 'No project', children: h('div', { class: 'list' }, loose.map(TaskRow)) }));
    return h('div', { class: 'grid c2' }, cards);
  }

  /* ---------- plan my day ---------- */
  async function loadPlan() {
    presence.setState('thinking', 'Planning your day…');
    try { await load(host, () => taskService.planDay(), renderPlan); presence.setState('idle'); }
    catch { presence.setState('error', 'Could not plan the day'); }
  }
  function renderPlan(plan) {
    const conflicts = plan.conflicts || [], postpone = plan.postpone || [];
    return [
      h('div', { class: 'plan-blocks' }, PLAN_BLOCKS.map(([key, label, ic]) => {
        const items = plan[key] || [];
        return h('div', { class: 'card plan-block' }, h('h3', null, icon(ic, 15), label), items.length ? items.map(PlanItem) : h('p', { class: 'faint', style: { fontSize: '12.5px' } }, 'Nothing planned.'));
      })),
      h('div', { class: 'grid c2' },
        Card({ title: 'Can be postponed', children: postpone.length
          ? h('div', { class: 'list' }, postpone.map(p => h('div', { class: 'plan-item' }, h('div', { class: 't' }, p.title), p.why && h('div', { class: 'w' }, p.why))))
          : h('p', { class: 'faint', style: { fontSize: '12.5px' } }, 'Everything fits today.') }),
        Card({ title: 'Conflicts', children: conflicts.length
          ? h('div', { class: 'list' }, conflicts.map(c => h('div', { class: 'plan-item row', style: { gap: '10px' } }, Badge({ label: 'conflict', tone: 'warn' }), h('span', { style: { fontSize: '13px' } }, c))))
          : h('p', { class: 'faint', style: { fontSize: '12.5px' } }, 'No conflicts.') })),
      h('div', { class: 'row between', style: { flexWrap: 'wrap', gap: '10px' } },
        h('span', { class: 'row muted', style: { fontSize: '13px' } }, icon('clock', 15), `${plan.freeHours ?? 0} free hours today`),
        h('div', { class: 'row' },
          Button({ label: 'Re-plan', icon: 'refresh', onClick: loadPlan }),
          Button({ label: 'Accept plan', icon: 'check', variant: 'primary', onClick: () => { toast('Plan applied'); presence.setState('success'); } }))),
    ];
  }
  function PlanItem(it) {
    if (it.kind === 'task') return h('div', { class: 'plan-item' }, h('div', { class: 't' }, h('span', { class: 'k' }, (it.minutes || 0) + 'm'), it.title), it.why && h('div', { class: 'w' }, it.why));
    return h('div', { class: 'plan-item' }, h('div', { class: 't' }, h('span', { class: 'k' }, it.at ? fmt.time(it.at) : ''), it.title), h('div', { class: 'w' }, it.kind));
  }
}

/* ---------- helpers ---------- */
function toLocalInput(d) {
  const x = new Date(d), p = (n) => String(n).padStart(2, '0');
  return `${x.getFullYear()}-${p(x.getMonth() + 1)}-${p(x.getDate())}T${p(x.getHours())}:${p(x.getMinutes())}`;
}
