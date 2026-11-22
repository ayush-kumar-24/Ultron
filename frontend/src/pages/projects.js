// Projects — workspaces Ultron keeps context for.
import { h, icon, fmt, mount } from '../ui/dom.js';
import { PageHeader, Card, Button, Row, Check, Progress, Metric, Tabs, EmptyState, Modal, Input, Textarea, load, SkeletonCard, toast } from '../ui/components/index.js';
import { projectService, taskService } from '../services/index.js';
import { appState } from '../store.js';
import { navigate } from '../router.js';

export default async function projects(root, { params }) {
  if (params.id) return workspace(root, params.id);

  const list = h('div', null);
  mount(root, PageHeader({ title: 'Projects', subtitle: 'Workspaces Ultron keeps context for.', actions: [Button({ label: 'New project', icon: 'plus', variant: 'primary', onClick: newProject })] }), list);
  await refresh();

  async function refresh() {
    await load(list, () => projectService.list(), (ps) => ps.length
      ? h('div', { class: 'grid c3' }, ps.map(p => h('div', { class: 'proj-card', role: 'button', tabindex: 0, onClick: () => navigate('/projects/' + p.id) },
          h('h4', null, p.name), h('p', null, p.description || 'No description.'),
          Progress({ value: p.progress }),
          h('div', { class: 'pf' }, h('span', null, `${p.openTasks} open task${p.openTasks === 1 ? '' : 's'}`), h('span', null, 'updated ' + fmt.relShort(p.updatedAt))))))
      : EmptyState({ icon: 'projects', title: 'No projects yet.', body: 'Create one to give Ultron context.', action: { label: 'New project', onClick: newProject } }),
      { skeleton: h('div', { class: 'grid c3' }, SkeletonCard(), SkeletonCard(), SkeletonCard()) }).catch(() => {});
  }
  function newProject() {
    let name = '', description = '';
    Modal({ title: 'New project', body: [Input({ placeholder: 'Project name', onInput: (v) => name = v }), Textarea({ placeholder: 'What is this project about?', onInput: (v) => description = v })],
      actions: [{ label: 'Cancel', variant: 'ghost' }, { label: 'Create', variant: 'primary', onClick: async () => { if (!name.trim()) { toast('Give it a name', { tone: 'warn' }); return false; } await projectService.create({ name: name.trim(), description }); toast('Project created'); refresh(); } }] });
  }
}

/* ---------------- workspace ---------------- */
async function workspace(root, id) {
  const head = h('div', null), tabsHost = h('div', null), pane = h('div', null);
  mount(root, head, tabsHost, pane);
  let p = null;
  await load(head, () => projectService.get(id), (data) => {
    p = data;
    appState.set({ context: { type: 'project', id: p.id, label: p.name } });
    const items = [
      { key: 'overview', label: 'Overview' },
      { key: 'tasks', label: 'Tasks', count: p.tasks.length },
      { key: 'conversations', label: 'Conversations', count: p.conversations.length },
      { key: 'files', label: 'Files', count: p.files.length },
      { key: 'research', label: 'Research', count: p.research.length },
      { key: 'memories', label: 'Memories', count: p.memories.length },
      { key: 'goals', label: 'Goals', count: p.goals.length },
      { key: 'activity', label: 'Activity', count: p.activity.length },
    ];
    mount(tabsHost, Tabs({ items, active: 'overview', onChange: renderTab }));
    renderTab('overview');
    return PageHeader({ eyebrow: 'Project', title: p.name, subtitle: p.description, actions: [
      Button({ label: 'Ask Ultron', icon: 'spark', variant: 'primary', onClick: () => navigate('/chat?new=1&ask=' + encodeURIComponent("What's left?")) }),
      Button({ label: 'Back', icon: 'left', variant: 'ghost', onClick: () => navigate('/projects') })] });
  }, { skeleton: SkeletonCard({ lines: 2 }) }).catch(() => {});

  function taskRow(t) {
    return h('div', { class: ['row-item', 'clickable'] },
      Check({ checked: t.status === 'done', label: t.title, onChange: async (v) => { await taskService.update(t.id, { status: v ? 'done' : 'todo' }); toast(v ? 'Task completed' : 'Reopened'); } }),
      h('div', { class: 'truncate' }, h('div', { class: 't' }, t.title), h('div', { class: 's' }, [t.priority, t.due && fmt.relShort(t.due)].filter(Boolean).join(' · '))),
      h('div', { class: 'trail' }, t.estimate ? h('span', { class: 'when' }, fmt.dur(t.estimate)) : null));
  }
  function empty(title, body, action) { return EmptyState({ icon: 'projects', title, body, action }); }

  function renderTab(key) {
    if (!p) return;
    const open = p.tasks.filter(t => t.status !== 'done');
    if (key === 'overview') {
      mount(pane,
        h('div', { class: 'metrics', style: { marginBottom: '16px' } },
          Metric({ label: 'Progress', value: p.progress + '%' }),
          Metric({ label: 'Open tasks', value: open.length }),
          Metric({ label: 'Conversations', value: p.conversations.length }),
          Metric({ label: 'Knowledge', value: p.files.length })),
        h('div', { class: 'grid c2' },
          Card({ title: "What's next", children: open.length ? h('div', { class: 'list' }, open.slice(0, 3).map(taskRow)) : h('p', { class: 'muted', style: { fontSize: '13px' } }, 'Nothing open. Good place to be.') }),
          Card({ title: 'Recent activity', children: p.activity.length ? h('div', { class: 'list' }, p.activity.slice(0, 5).map(a => Row({ icon: 'activity', title: a.body, subtitle: a.title, meta: fmt.relShort(a.at) }))) : h('p', { class: 'muted', style: { fontSize: '13px' } }, 'No activity for this project yet.') })));
    } else if (key === 'tasks') {
      mount(pane, p.tasks.length ? Card({ children: h('div', { class: 'list' }, p.tasks.map(taskRow)) }) : empty('No tasks in this project.', 'Add one and Ultron will keep it in context.', { label: 'Open tasks', onClick: () => navigate('/tasks') }));
    } else if (key === 'conversations') {
      mount(pane, p.conversations.length ? Card({ children: h('div', { class: 'list' }, p.conversations.map(c => Row({ icon: 'chat', title: c.title, meta: fmt.relShort(c.updatedAt), onClick: () => navigate('/chat/' + c.id) }))) }) : empty('No conversations yet.', 'Ask Ultron something about this project.', { label: 'Ask Ultron', onClick: () => navigate('/chat?new=1&ask=' + encodeURIComponent('What should I focus on in ' + p.name + '?')) }));
    } else if (key === 'files') {
      mount(pane, p.files.length ? Card({ children: h('div', { class: 'list' }, p.files.map(k => Row({ icon: k.type === 'link' ? 'link' : k.type === 'image' ? 'image' : k.type === 'code' ? 'code' : k.type === 'note' ? 'note' : 'file', title: k.title, subtitle: k.source, meta: fmt.relShort(k.createdAt), onClick: () => navigate('/knowledge/' + k.id) }))) }) : empty('No files linked.', 'Add documents in Knowledge and tag them with this project.', { label: 'Open knowledge', onClick: () => navigate('/knowledge') }));
    } else if (key === 'research') {
      mount(pane, p.research.length ? Card({ children: h('div', { class: 'list' }, p.research.map(r => Row({ icon: 'research', title: r.query, subtitle: r.status, meta: fmt.relShort(r.createdAt), onClick: () => navigate('/research/' + r.id) }))) }) : empty('No research yet for this project.', 'Ask Ultron to investigate something.', { label: 'Start research', onClick: () => navigate('/research?new=1') }));
    } else if (key === 'memories') {
      mount(pane, p.memories.length ? Card({ children: h('div', { class: 'list' }, p.memories.map(m => Row({ icon: 'memory', title: m.text, subtitle: m.source, meta: fmt.relShort(m.createdAt), onClick: () => navigate('/memory') }))) }) : empty('Nothing remembered yet.', 'Ultron stores what matters as you work.', { label: 'Teach Ultron', onClick: () => navigate('/memory?teach=1') }));
    } else if (key === 'goals') {
      mount(pane, p.goals.length ? h('div', { class: 'stack' }, p.goals.map(g => Card({ title: g.title, children: [h('p', { class: 'muted', style: { fontSize: '13px', marginBottom: '10px' } }, g.objective), Progress({ value: g.progress }), h('div', { class: 'ms', style: { marginTop: '12px' } }, g.milestones.map(m => h('div', { class: [m.done && 'done', m.current && 'cur'] }, h('span', { class: 'ck' }, m.done ? '✓' : ''), m.t)))] }))) : empty('No goals for this project.', 'Give Ultron a direction to plan toward.', { label: 'Open goals', onClick: () => navigate('/goals') }));
    } else {
      mount(pane, p.activity.length ? Card({ children: h('div', { class: 'list' }, p.activity.map(a => Row({ icon: 'activity', title: a.body, subtitle: a.title, meta: fmt.relShort(a.at) }))) }) : empty('No activity yet.', 'Everything Ultron does for this project shows up here.'));
    }
  }
  return () => appState.set({ context: null });
}
