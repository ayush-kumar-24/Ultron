// Research — the deep research workspace. Plan → live progress → sourced report.
import { h, icon, fmt, mount, clear } from '../ui/dom.js';
import { PageHeader, Card, Button, IconButton, Badge, Row, Select, Textarea, EmptyState, ErrorState, Skeleton, SkeletonCard, load, toast, confirm } from '../ui/components/index.js';
import { researchService, projectService, events } from '../services/index.js';
import { presence } from '../ui/core/presence.js';
import { navigate } from '../router.js';

const STEPS = ['Understand problem', 'Search sources', 'Compare information', 'Analyse', 'Synthesise', 'Generate report'];

export default async function research(root, { params, query }) {
  let sessions = [], projects = [], offEvent = null;
  const main = h('div', { class: 'col', style: { minWidth: '0' } });
  const sideList = h('div', { class: 'list' });
  const side = Card({ title: 'Sessions', children: sideList });
  mount(root, h('div', { class: 'grid side' }, main, h('div', { class: 'col' }, side)));

  try { [sessions, projects] = await Promise.all([researchService.list(), projectService.list()]); } catch { sessions = []; projects = []; }
  renderSide();

  if (params.id) await openSession(params.id); else renderStart();

  function renderSide() {
    mount(sideList, sessions.length ? sessions.map(s => Row({
      icon: 'research', title: s.query, subtitle: `${s.sources || 0} sources · ${fmt.relShort(s.createdAt)}`,
      trailing: Badge({ label: s.status, tone: s.status === 'done' ? 'ok' : s.status === 'failed' ? 'bad' : 'busy' }),
      onClick: () => navigate('/research/' + s.id), class: s.id === params.id ? 'clickable' : 'clickable',
    })) : h('p', { class: 'faint', style: { fontSize: '12.5px' } }, 'No sessions yet.'));
  }

  /* ---------- start a session ---------- */
  function renderStart() {
    let q = query.q || '', projectId = '';
    const ta = Textarea({ placeholder: 'Research…  e.g. “Best local wake-word engine for Windows”', value: q, onInput: (v) => q = v });
    const btn = Button({ label: 'Start research', icon: 'research', variant: 'primary', onClick: () => start(q, projectId, btn) });
    mount(main,
      PageHeader({ title: 'Research', subtitle: 'Deep, sourced, and honest about contradictions.' }),
      Card({ children: [ta, h('div', { class: 'row', style: { marginTop: '12px' } },
        Select({ options: [{ value: '', label: 'No project' }, ...projects.map(p => ({ value: p.id, label: p.name }))], value: '', onChange: (v) => projectId = v }),
        h('div', { class: 'spacer' }), btn)] }),
      sessions.length ? null : EmptyState({ icon: 'research', title: 'No research yet.', body: 'Ask Ultron to investigate something.' }));
    if (query.new === '1' || query.q) setTimeout(() => ta.focus(), 30);
  }

  async function start(q, projectId, btn) {
    if (!q.trim()) { toast('Type what you want researched', { tone: 'warn' }); return; }
    btn?.classList.add('loading');
    const stepsEl = h('div', { class: 'plan-steps' }, STEPS.map((s, i) => stepRow(s, i, i === 0 ? 'running' : '')));
    const head = PageHeader({ eyebrow: 'Researching', title: q, subtitle: 'Ultron is planning, searching, comparing and synthesising.' });
    mount(main, head, Card({ title: 'Research plan', children: stepsEl }));
    presence.setState('working', 'Researching…');
    let sessionId = null;
    try {
      const done = await researchService.start(q.trim(), projectId || null, (ev) => {
        if (ev.type === 'session') { sessionId = ev.session.id; sessions.unshift(ev.session); renderSide(); }
        if (ev.type === 'step') { mount(stepsEl, STEPS.map((s, i) => stepRow(s, i, i < ev.step ? 'done' : i === ev.step ? 'running' : '', i === ev.step ? ev.sources : null))); presence.setState('working', ev.label); }
      });
      presence.setState('success', 'Research complete');
      sessions = await researchService.list(); renderSide();
      if (done?.id) { history.replaceState(null, '', '#/research/' + done.id); params.id = done.id; mount(main, renderReport(done, true)); }
      else { const fresh = (await researchService.list())[0]; if (fresh) mount(main, renderReport(fresh, true)); }
    } catch (err) {
      presence.setState('error');
      mount(main, head, ErrorState({ title: 'Research failed', what: err.message || 'The session stopped before finishing.', why: 'A source did not respond in time.', next: 'Retry — Ultron keeps the sources it already read.', onRetry: () => start(q, projectId) }));
    } finally { btn?.classList.remove('loading'); }
  }

  function stepRow(label, i, state, sources) {
    return h('div', { class: ['step', state] },
      h('div', { class: 'n' }, state === 'done' ? icon('check') : String(i + 1)),
      h('div', { class: 't' }, label),
      h('div', { class: 's' }, sources ? sources + ' sources' : state === 'running' ? 'working…' : ''));
  }

  /* ---------- open an existing session ---------- */
  async function openSession(id) {
    await load(main, () => researchService.get(id), (s) => {
      if (s.status === 'running') { watch(s); return renderRunning(s); }
      if (s.status === 'failed') return [PageHeader({ eyebrow: 'Research', title: s.query }), ErrorState({ title: 'Research failed', what: s.error || 'The session did not finish.', why: 'Some sources could not be read.', next: 'Retry the same question.', onRetry: () => start(s.query, s.projectId) })];
      return renderReport(s, true);
    }, { skeleton: h('div', null, SkeletonCard({ lines: 2 }), h('div', { style: { height: '16px' } }), SkeletonCard({ lines: 8 })) }).catch(() => {});
  }
  function renderRunning(s) {
    const stepsEl = h('div', { class: 'plan-steps' }, STEPS.map((x, i) => stepRow(x, i, i < (s.step || 0) ? 'done' : i === (s.step || 0) ? 'running' : '', i === s.step ? s.sources : null)));
    main._steps = stepsEl;
    return [PageHeader({ eyebrow: 'Researching', title: s.query, subtitle: 'Live — you can leave this page; Ultron keeps going.' }), Card({ title: 'Research plan', children: stepsEl })];
  }
  function watch(s) {
    offEvent?.();
    offEvent = events.on('research', async (r) => {
      if (r.id !== s.id) return;
      if (r.status === 'done') { offEvent(); offEvent = null; sessions = await researchService.list(); renderSide(); mount(main, renderReport(r, true)); presence.setState('success', 'Research complete'); }
      else if (main._steps) mount(main._steps, STEPS.map((x, i) => stepRow(x, i, i < r.step ? 'done' : i === r.step ? 'running' : '', i === r.step ? r.sources : null)));
    });
  }

  function renderReport(s, withHeader) {
    const rp = s.report || {};
    const body = h('div', { class: 'report' },
      h('h3', null, 'Executive summary'), h('p', null, rp.summary || '—'),
      h('h3', null, 'Key findings'), h('ul', null, (rp.findings || []).map(f => h('li', null, f))),
      h('h3', null, 'Evidence'), (rp.evidence || []).map(e => h('div', { class: 'ev' }, h('b', null, '[' + e.n + ']'), h('div', null, h('div', null, e.title), h('div', { class: 'd' }, e.detail)))),
      h('h3', null, 'Contradictions'), (rp.contradictions || []).length ? (rp.contradictions).map(c => h('p', { class: 'warn' }, c)) : h('p', { class: 'muted' }, 'No contradictions found.'),
      h('h3', null, 'Recommendations'), h('ul', null, (rp.recommendations || []).map(r => h('li', null, r))),
      h('h3', null, 'Next actions'), h('ul', null, (rp.nextActions || []).map(a => h('li', null, a))),
      h('div', { class: 'acts' },
        Button({ label: 'Save research', icon: 'save', onClick: () => toast('Research saved') }),
        Button({ label: 'Export', icon: 'download', onClick: () => exportMd(s) }),
        Button({ label: 'Ask follow-up', icon: 'chat', onClick: () => navigate('/chat?new=1&ask=' + encodeURIComponent('Follow-up on research: ' + s.query)) }),
        Button({ label: 'Create tasks', icon: 'tasks', onClick: async (e) => { const made = await researchService.createTasks(s.id); toast(`${made.length} tasks created`, { action: { label: 'Open', onClick: () => navigate('/tasks') } }); } }),
        Button({ label: 'Save to knowledge', icon: 'knowledge', onClick: async () => { await researchService.saveToKnowledge(s.id); toast('Saved to knowledge', { action: { label: 'Open', onClick: () => navigate('/knowledge') } }); } }),
        Button({ label: 'Delete', icon: 'trash', variant: 'danger', onClick: async () => { if (await confirm({ title: 'Delete research?', message: 'The report and its sources are removed. Tasks and knowledge you saved stay.', confirmLabel: 'Delete', danger: true })) { await researchService.remove(s.id); toast('Research deleted'); navigate('/research'); } } })));
    const out = [Card({ children: body })];
    if (withHeader) out.unshift(PageHeader({ eyebrow: `Research · ${s.sources} sources`, title: s.query, subtitle: fmt.date(s.createdAt), actions: [Button({ label: 'New research', icon: 'plus', onClick: () => navigate('/research?new=1') })] }));
    return out;
  }

  function exportMd(s) {
    const rp = s.report || {};
    const md = [`# ${s.query}`, '', `_${s.sources} sources · ${fmt.date(s.createdAt)}_`, '', '## Executive summary', rp.summary || '', '', '## Key findings', ...(rp.findings || []).map(f => '- ' + f), '', '## Evidence', ...(rp.evidence || []).map(e => `${e.n}. **${e.title}** — ${e.detail}`), '', '## Contradictions', ...((rp.contradictions || []).length ? rp.contradictions.map(c => '- ' + c) : ['None found.']), '', '## Recommendations', ...(rp.recommendations || []).map(r => '- ' + r), '', '## Next actions', ...(rp.nextActions || []).map(a => '- [ ] ' + a), ''].join('\n');
    const url = URL.createObjectURL(new Blob([md], { type: 'text/markdown' }));
    const a = h('a', { href: url, download: s.query.slice(0, 40).replace(/[^\w ]+/g, '') + '.md' });
    document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast('Exported as Markdown');
  }

  return () => { offEvent?.(); };
}
