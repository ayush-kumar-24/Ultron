// Focus Mode — everything disappears except the task, the timer, and Ultron.
import { h, fmt, mount } from '../ui/dom.js';
import { Button, toast } from '../ui/components/index.js';
import { taskService } from '../services/index.js';
import { presence } from '../ui/core/presence.js';
import { appState, bus } from '../store.js';
import { navigate } from '../router.js';

export default async function focus(root, { query }) {
  const prev = appState.get().focus;
  let task = prev?.task || query.task || null, startedAt = prev?.startedAt || Date.now(), paused = prev?.paused || false, pausedAt = prev?.pausedAt || null, elapsedBefore = prev?.elapsedBefore || 0;
  const dock = h('div', { class: 'dock' });
  const title = h('h2', null, task || 'Pick something to focus on');
  const time = h('div', { class: 'time num', 'aria-live': 'off' }, '00:00');
  const pauseBtn = Button({ label: paused ? 'Resume' : 'Pause', icon: paused ? 'play' : 'pause', onClick: togglePause });
  const pick = h('div', { class: 'pick' });
  const el = h('div', { class: 'focus-page', role: 'dialog', 'aria-label': 'Focus mode' },
    h('div', { class: 'ambient' }),
    h('button', { class: 'exit', onClick: exit }, 'Exit focus · Esc'),
    dock, h('div', { class: 'k' }, 'Focus mode'), title, time,
    h('div', { class: 'acts' }, pauseBtn, Button({ label: 'Ask Ultron', icon: 'spark', onClick: () => bus.emit('voice') }), Button({ label: 'Done', icon: 'check', variant: 'primary', onClick: finish })),
    pick);
  mount(root, el);
  presence.dock(dock);

  if (!task) {
    try {
      const open = (await taskService.list({ view: 'today' })).concat(await taskService.list({ view: 'upcoming' })).slice(0, 6);
      mount(pick, h('div', { class: 'muted', style: { width: '100%', fontSize: '13px', marginBottom: '4px' } }, 'Or choose a task:'), open.map(t => h('button', { class: 'chip', onClick: () => { task = t.id; title.textContent = t.title; el.dataset.taskId = t.id; pick.replaceChildren(); startedAt = Date.now(); elapsedBefore = 0; persist(); } }, t.title)));
    } catch {}
    title.textContent = 'Deep work';
  }

  function elapsed() { return elapsedBefore + (paused ? (pausedAt - startedAt) : (Date.now() - startedAt)); }
  function tick() { time.textContent = fmt.clock(Math.floor(elapsed() / 1000)); }
  function persist() { appState.set({ focus: { task: title.textContent, taskId: el.dataset.taskId, startedAt, paused, pausedAt, elapsedBefore } }); }
  function togglePause() {
    if (!paused) { paused = true; pausedAt = Date.now(); pauseBtn.replaceWith(pauseBtn = Button({ label: 'Resume', icon: 'play', onClick: togglePause })); presence.setState('idle'); }
    else { elapsedBefore += pausedAt - startedAt; startedAt = Date.now(); paused = false; pausedAt = null; pauseBtn.replaceWith(pauseBtn = Button({ label: 'Pause', icon: 'pause', onClick: togglePause })); presence.setState('working', 'Focusing'); }
    persist();
  }
  async function finish() {
    const mins = Math.round(elapsed() / 60000);
    if (el.dataset.taskId) { try { await taskService.update(el.dataset.taskId, { status: 'done' }); } catch {} }
    appState.set({ focus: null });
    presence.setState('success', `Session complete — ${fmt.dur(Math.max(1, mins))}`);
    toast(`Focus session complete · ${fmt.dur(Math.max(1, mins))}`, { action: { label: 'Insights', onClick: () => navigate('/insights') } });
    navigate('/overview');
  }
  function exit() { persist(); navigate('/overview'); toast('Focus paused in the background', { tone: 'info', action: { label: 'Resume', onClick: () => navigate('/focus') } }); }
  const onKey = (e) => { if (e.key === 'Escape') exit(); };
  document.addEventListener('keydown', onKey);

  presence.setState(paused ? 'idle' : 'working', 'Focusing');
  tick(); const timer = setInterval(tick, 1000);
  persist();
  return () => { clearInterval(timer); document.removeEventListener('keydown', onKey); presence.dock(null); if (presence.state === 'working') presence.setState('idle'); };
}
