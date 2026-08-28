// ULTRON — boot. Shell → presence → router → realtime.
import { appState, bus } from './store.js';
import { defineRoutes, startRouter, navigate, parseHash } from './router.js';
import { buildShell } from './ui/shell/shell.js';
import { openPalette, closePalette, isPaletteOpen } from './ui/shell/palette.js';
import { openVoice } from './ui/shell/voice.js';
import { presence } from './ui/core/presence.js';
import { userService, events, api } from './services/index.js';
import { initTransport } from './api/client.js';
import { config, auth } from './config.js';
import { toast } from './ui/components/index.js';

defineRoutes([
  { name: 'overview', path: '/overview', title: 'Overview', load: () => import('./pages/overview.js') },
  { name: 'chat', path: '/chat/:id?', title: 'Chat', load: () => import('./pages/chat.js') },
  { name: 'mind', path: '/mind', title: 'Mind', load: () => import('./pages/mind.js') },
  { name: 'memory', path: '/memory', title: 'Memory', load: () => import('./pages/memory.js') },
  { name: 'knowledge', path: '/knowledge/:id?', title: 'Knowledge', load: () => import('./pages/knowledge.js') },
  { name: 'tasks', path: '/tasks/:view?', title: 'Tasks', load: () => import('./pages/tasks.js') },
  { name: 'calendar', path: '/calendar/:view?', title: 'Calendar', load: () => import('./pages/calendar.js') },
  { name: 'automations', path: '/automations/:id?', title: 'Automations', load: () => import('./pages/automations.js') },
  { name: 'agents', path: '/agents/:id?', title: 'Agents', load: () => import('./pages/agents.js') },
  { name: 'research', path: '/research/:id?', title: 'Research', load: () => import('./pages/research.js') },
  { name: 'projects', path: '/projects/:id?', title: 'Projects', load: () => import('./pages/projects.js') },
  { name: 'goals', path: '/goals', title: 'Goals', load: () => import('./pages/goals.js') },
  { name: 'insights', path: '/insights', title: 'Insights', load: () => import('./pages/insights.js') },
  { name: 'activity', path: '/activity', title: 'Activity', load: () => import('./pages/activity.js') },
  { name: 'focus', path: '/focus', title: 'Focus', load: () => import('./pages/focus.js') },
  { name: 'settings', path: '/settings/:section?', title: 'Settings', load: () => import('./pages/settings.js') },
  { name: 'profile', path: '/profile', title: 'Profile', load: () => import('./pages/profile.js') },
  { name: 'search', path: '/search', title: 'Search', load: () => import('./pages/search.js') },
]);

async function boot() {
  const root = document.getElementById('root');

  /* pick the backend: live if one answers, otherwise the built-in demo backend */
  const { mode, reason } = await initTransport();
  appState.set({ backend: { mode, reason } });
  document.documentElement.dataset.backend = mode;

  let user = null;
  try { user = await userService.me(); } catch (err) { if (err?.status === 401 && config.auth.loginUrl) { location.href = config.auth.loginUrl; return; } }
  appState.set({ user });
  const { view } = buildShell(root, user);
  document.body.append(presence.el);

  /* the presence is the voice entry point */
  presence.onClick((state) => {
    if (state === 'idle' || state === 'success' || state === 'error') bus.emit('voice');
    else if (state === 'speaking' || state === 'listening') presence.setState('idle');   // interruption
  });

  /* global "ask" → chat, carrying smart context */
  bus.on('ask', (q) => { if (appState.get().route.name === 'chat' && q) return; /* chat page handles it in place */ if (!q) { navigate('/chat'); return; } navigate('/chat?new=1&ask=' + encodeURIComponent(q)); });
  bus.on('voice', async () => { const t = await openVoice(); if (t) bus.emit('ask', t); });

  /* keyboard */
  document.addEventListener('keydown', (e) => {
    const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName) || document.activeElement?.isContentEditable;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); isPaletteOpen() ? closePalette() : openPalette(); return; }
    if (e.key === 'Escape' && isPaletteOpen()) { closePalette(); return; }
    if (typing) return;
    if (e.altKey && e.code === 'Space') { e.preventDefault(); bus.emit('voice'); }
    if (e.key === '/') { e.preventDefault(); openPalette(); }
    if (e.key === 'g') { const next = (ev) => { const map = { o: '/overview', c: '/chat', m: '/memory', t: '/tasks', k: '/knowledge', a: '/agents', r: '/research', i: '/insights', s: '/settings' }; if (map[ev.key]) navigate(map[ev.key]); document.removeEventListener('keydown', next); }; document.addEventListener('keydown', next, { once: true }); }
  });

  /* realtime → store + presence */
  api.start();
  events.on('unauthorized', () => { auth.clear(); if (config.auth.loginUrl) location.href = config.auth.loginUrl; else toast('Session expired — sign in again.', { tone: 'bad' }); });
  events.on('agent', (a) => appState.set(s => ({ agents: s.agents.some(x => x.id === a.id) ? s.agents.map(x => x.id === a.id ? a : x) : [...s.agents, a] })));
  events.on('notification', (n) => { if (n.type === 'important' || n.type === 'reminder') toast(n.title, { tone: 'info', action: { label: 'Open', onClick: () => navigate('/activity') } }); });
  events.on('heartbeat', (hb) => appState.set({ online: hb.online }));
  addEventListener('online', () => appState.set({ online: true })); addEventListener('offline', () => { appState.set({ online: false }); toast('Offline — local features keep working.', { tone: 'warn' }); });

  startRouter(view);
  document.getElementById('boot')?.remove();
  if (mode === 'mock') toast('Demo data — no backend connected.', { tone: 'info', duration: 4200, action: { label: 'Why?', onClick: () => toast(`Ultron looked for a backend and found none (${reason}). Set mode:'live' in config.js once yours is running.`, { tone: 'info', duration: 7000 }) } });
}
boot();
