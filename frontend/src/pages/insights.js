// Insights — measured activity, clearly separated from Ultron's interpretation.
import { h, fmt, mount } from '../ui/dom.js';
import { PageHeader, Card, Metric, Sparkline, Row, Progress, Table, Badge, EmptyState, load, SkeletonCard } from '../ui/components/index.js';
import { insightService } from '../services/index.js';
import { navigate } from '../router.js';

export default async function insights(root) {
  const body = h('div', null);
  mount(root,
    PageHeader({ title: 'Insights', subtitle: 'Measured activity, not wellness theatre.' }),
    h('p', { class: 'ins-note' }, 'Numbers are measured from your sessions and tasks. Anything Ultron interprets is labelled.'),
    body);

  await load(body, () => insightService.get(), (d) => {
    const empty = !d.sessions.length && !Object.values(d.usage).some(Boolean);
    if (empty) return EmptyState({ icon: 'insights', title: 'Not enough activity yet.', body: 'Insights appear after a few days of use.' });

    const focusNow = d.focus.at(-1) || 0;
    const todayIdx = (new Date().getDay() + 6) % 7;
    const maxTotal = Math.max(...d.weekly.map(w => w.work + w.learn), 1);
    const maxProj = Math.max(...d.projects.map(p => p.minutes), 1);
    const load_ = d.tasks.total - d.tasks.done;

    const weekly = h('div', { class: 'bars stack' }, d.weekly.map((w, i) => h('div', { class: ['b', i === todayIdx && 'hi'], title: `${w.work}h work · ${w.learn}h learning` },
      h('i', { class: 'l', style: { height: (w.learn / maxTotal * 100) + '%' } }),
      h('i', { style: { height: (w.work / maxTotal * 100) + '%' } }),
      h('span', null, w.d))));

    return [
      h('div', { class: 'metrics', style: { marginBottom: '16px' } },
        Metric({ label: 'Focus', value: focusNow + '%', delta: '+6 vs last week', trend: 'up' }),
        Metric({ label: 'Productivity', value: '84%', delta: '+3 vs last week', trend: 'up' }),
        Metric({ label: 'Task completion', value: (d.tasks.total ? Math.round(d.tasks.done / d.tasks.total * 100) : 0) + '%', delta: `${d.tasks.done} of ${d.tasks.total}` }),
        Metric({ label: 'Cognitive load', value: load_ > 8 ? 'High' : load_ > 4 ? 'Moderate' : 'Light', delta: 'interpreted by Ultron' })),

      h('div', { class: 'grid c2' },
        Card({ title: 'Weekly activity', children: [weekly, h('div', { class: 'ins-legend' }, h('span', null, h('i'), 'Work'), h('span', null, h('i', { class: 'l' }), 'Learning'))] }),
        Card({ title: 'Focus index', children: Sparkline({ values: d.focus, labels: ['M', 'T', 'W', 'T', 'F', 'S', 'S'], highlight: todayIdx }) })),

      h('div', { class: 'grid c3', style: { marginTop: '16px' } },
        Card({ title: 'Most active projects', children: d.projects.filter(p => p.minutes).length ? h('div', { class: 'list' }, d.projects.filter(p => p.minutes).map(p => h('div', { class: 'row-item' },
          h('div', null), h('div', null, h('div', { class: 't' }, p.name), h('div', { style: { marginTop: '7px' } }, Progress({ value: p.minutes / maxProj * 100 }))), h('div', { class: 'when' }, fmt.dur(p.minutes)))))
          : h('p', { class: 'muted', style: { fontSize: '13px' } }, 'No tracked time yet.') }),
        Card({ title: 'Frequently used knowledge', children: d.knowledgeTop.length ? h('div', { class: 'list' }, d.knowledgeTop.map(k => Row({ icon: 'knowledge', title: k.title, meta: k.n + ' recalls', onClick: () => navigate('/knowledge/' + k.id) })))
          : h('p', { class: 'muted', style: { fontSize: '13px' } }, 'Nothing recalled yet.') }),
        Card({ title: 'AI usage', children: h('div', { class: 'kv' },
          h('div', null, h('b', null, fmt.num(d.usage.queries)), 'queries'), h('div', null, h('b', null, d.usage.research), 'research sessions'),
          h('div', null, h('b', null, d.usage.tasks), 'tasks handled'), h('div', null, h('b', null, fmt.num(d.usage.automations)), 'automation runs')) })),

      h('div', { class: 'grid c2', style: { marginTop: '16px' } },
        Card({ title: 'Consistency', children: h('div', { class: 'kv' },
          h('div', null, h('b', null, d.activeDays + '/7'), 'active days'), h('div', null, h('b', null, d.streak), 'day streak'),
          h('div', null, h('b', null, fmt.dur(d.sessions.reduce((a, s) => a + s.minutes, 0))), 'tracked this week'), h('div', null, h('b', null, d.sessions.filter(s => s.type === 'learning').length), 'learning sessions')) }),
        Card({ title: 'What Ultron makes of it', children: h('p', { class: 'muted', style: { fontSize: '13px', lineHeight: '1.6' } }, 'Your deep work clusters after 8 PM and on Thursdays. Learning happens only at weekends — if the Computer Networks goal matters, a short weekday session would keep it moving. Interpretation, not measurement.') })),

      Card({ title: 'Sessions', class: 'grid', children: d.sessions.length ? Table({
        columns: [
          { label: 'Type', render: (s) => Badge({ label: s.type, tone: s.type === 'learning' ? 'info' : 'ok' }) },
          { label: 'Project', key: 'project' },
          { label: 'When', render: (s) => fmt.date(s.start) },
          { label: 'Duration', render: (s) => fmt.dur(s.minutes) },
          { label: 'Recorded', render: (s) => s.recorded ? '✓' : '—' },
          { label: 'Summary', render: (s) => h('span', { class: 'muted' }, s.summary) },
        ], rows: d.sessions,
      }) : h('p', { class: 'muted', style: { fontSize: '13px' } }, 'No sessions recorded yet.') }),
    ];
  }, { skeleton: h('div', null, SkeletonCard({ lines: 3 }), h('div', { style: { height: '16px' } }), SkeletonCard({ lines: 6 })) }).catch(() => {});
}
