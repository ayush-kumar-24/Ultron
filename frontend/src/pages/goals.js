// Goals — objectives with milestones, progress, and Ultron's recommendation for the next move.
import { h, icon, fmt, mount } from '../ui/dom.js';
import { PageHeader, Button, Input, Select, Textarea, Field, Progress, EmptyState, load, Modal, toast, SkeletonCard } from '../ui/components/index.js';
import { goalService, projectService } from '../services/index.js';
import { presence } from '../ui/core/presence.js';
import { navigate } from '../router.js';

const DEFAULT_REC = 'Set the first milestone small enough to finish this week.';

export default async function goals(root) {
  // all page state is declared here, before any await (see docs/PAGES.md)
  let projects = [];
  const host = h('div', { class: 'col' });

  mount(root,
    PageHeader({ title: 'Goals', subtitle: 'Objectives with milestones, kept honest by Ultron.', actions: [
      Button({ label: 'New goal', icon: 'plus', variant: 'primary', onClick: newGoal }),
    ] }),
    host);

  await refresh();
  return () => {};

  /* ---------- data ---------- */
  function refresh() { return load(host, fetchAll, renderGoals, { skeleton: h('div', { class: 'col' }, SkeletonCard({ lines: 5 }), SkeletonCard({ lines: 5 })) }).catch(() => {}); }
  async function fetchAll() {
    const [gs, ps] = await Promise.all([goalService.list(), projectService.list().catch(() => [])]);
    projects = ps;
    return gs;
  }
  function renderGoals(gs) {
    if (!gs.length) return EmptyState({ icon: 'goals', title: 'No goals yet.', body: 'Give Ultron a direction to plan toward.', action: { label: 'New goal', icon: 'plus', onClick: newGoal } });
    return gs.map(GoalCard);
  }
  function projectName(g) { return g.project || projects.find(p => p.id === g.projectId)?.name; }

  /* ---------- card ---------- */
  function GoalCard(g) {
    const ms = g.milestones || [];
    const done = ms.filter(m => m.done).length;
    const pname = projectName(g);
    const overdue = g.deadline && new Date(g.deadline) < new Date() && (g.progress || 0) < 100;
    return h('div', { class: 'goal', 'data-id': g.id },
      h('div', { style: { minWidth: 0 } },
        h('h3', null, g.title),
        g.objective && h('div', { class: 'obj' }, g.objective),
        h('div', { class: 'gm' },
          g.deadline && h('span', { style: overdue ? { color: 'var(--bad)' } : null }, icon('flag', 11), ' ', (overdue ? 'Was due ' : 'Due ') + fmt.date(g.deadline)),
          pname && h('span', null, icon('projects', 11), ' ', pname),
          h('span', null, fmt.pct(g.progress || 0) + ' complete'),
          ms.length ? h('span', null, `${done}/${ms.length} milestones`) : null),
        h('div', { style: { marginTop: '10px' } }, Progress({ value: g.progress || 0, tone: (g.progress || 0) >= 100 ? 'ok' : '' })),
        ms.length ? h('div', { class: 'ms', role: 'list', 'aria-label': 'Milestones' }, ms.map((m, i) => Milestone(g, m, i))) : h('p', { class: 'faint', style: { fontSize: '12.5px', marginTop: '12px' } }, 'No milestones yet — ask Ultron to break this down.')),
      h('div', { class: 'col', style: { gap: '12px' } },
        h('div', { class: 'rec' }, h('b', null, 'Ultron recommends'), g.recommendation || DEFAULT_REC),
        h('div', null, Button({ label: 'Discuss with Ultron', icon: 'chat', variant: 'ghost', onClick: () => navigate('/chat?new=1&ask=' + encodeURIComponent('Help me make progress on ' + g.title)) }))));
  }
  function Milestone(g, m, i) {
    const interactive = !m.done;
    // the owning .goal card is resolved from the event target: the card element does not exist yet while its children are built
    return h('div', { class: [m.done && 'done', !m.done && m.current && 'cur'], role: interactive ? 'button' : 'listitem', tabindex: interactive ? 0 : null,
      'aria-label': interactive ? 'Mark milestone done: ' + m.t : m.t + ' (done)', title: interactive ? 'Mark done' : null, style: interactive ? { cursor: 'pointer' } : null,
      onClick: interactive ? (e) => completeMilestone(g, i, e.currentTarget.closest('.goal')) : null,
      onKeydown: interactive ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); completeMilestone(g, i, e.currentTarget.closest('.goal')); } } : null },
      h('span', { class: 'ck', 'aria-hidden': 'true' }, m.done ? '✓' : ''), m.t);
  }

  /* ---------- mutations ---------- */
  async function completeMilestone(g, i, card) {
    const milestones = (g.milestones || []).map(m => ({ ...m, current: false }));
    if (!milestones[i] || milestones[i].done) return;
    milestones[i].done = true;
    const next = milestones.find(m => !m.done); if (next) next.current = true;
    const progress = Math.round(milestones.filter(m => m.done).length / milestones.length * 100);
    try {
      const updated = await goalService.update(g.id, { milestones, progress });
      const merged = { ...g, ...updated, milestones, progress, project: g.project };
      if (card) card.replaceWith(GoalCard(merged)); else await refresh();
      toast(progress >= 100 ? 'Goal complete' : 'Milestone completed');
      presence.setState('success');
    } catch (err) { toast(err.message || 'Could not update the goal', { tone: 'bad' }); }
  }

  function newGoal() {
    const draft = { title: '', objective: '', deadline: '', projectId: '', milestones: '' };
    const projectOpts = [{ value: '', label: 'No project' }, ...projects.map(p => ({ value: p.id, label: p.name }))];
    const modal = Modal({
      title: 'New goal',
      body: [
        Field({ label: 'Title', control: Input({ placeholder: 'e.g. Ship Ultron v1', onInput: (v) => draft.title = v, onEnter: async () => { if (await submit() !== false) modal.close(); } }) }),
        Field({ label: 'Objective', control: Textarea({ placeholder: 'What does success look like?', rows: 2, onInput: (v) => draft.objective = v }) }),
        h('div', { class: 'grid c2' },
          Field({ label: 'Deadline', control: Input({ type: 'date', onInput: (v) => draft.deadline = v }) }),
          Field({ label: 'Project', control: Select({ options: projectOpts, value: '', onChange: (v) => draft.projectId = v }) })),
        Field({ label: 'Milestones (one per line)', control: Textarea({ placeholder: 'Foundation\nFirst working version\nLaunch', rows: 4, onInput: (v) => draft.milestones = v }) }),
      ],
      actions: [
        { label: 'Cancel', variant: 'ghost' },
        { label: 'Create goal', variant: 'primary', onClick: submit },
      ],
    });

    async function submit() {
      const title = draft.title.trim();
      if (!title) { toast('Give the goal a title', { tone: 'warn' }); return false; }
      const body = {
        title, objective: draft.objective.trim(),
        deadline: draft.deadline ? new Date(draft.deadline + 'T18:00').toISOString() : null,
        projectId: draft.projectId || null,
        milestones: draft.milestones.split('\n').map(s => s.trim()).filter(Boolean),
      };
      try { await goalService.create(body); toast('Goal created'); presence.setState('success'); await refresh(); return true; }
      catch (err) { toast(err.message || 'Could not create the goal', { tone: 'bad' }); return false; }
    }
  }
}
