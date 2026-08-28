// Application shell: sidebar, topbar, bottom nav, smart-context chip.
import { h, icon, $, mount } from '../dom.js';
import { appState, bus } from '../../store.js';
import { navigate } from '../../router.js';
import { notificationService, events } from '../../services/index.js';
import { openPalette } from './palette.js';
import { openNotifications } from './notifications.js';

export const NAV = [
  ['overview', 'Overview', '/overview'], ['chat', 'Ultron Chat', '/chat'], ['mind', 'Mind', '/mind'], ['memory', 'Memory', '/memory'], ['knowledge', 'Knowledge', '/knowledge'],
  ['tasks', 'Tasks', '/tasks'], ['calendar', 'Calendar', '/calendar'], ['automations', 'Automations', '/automations'], ['agents', 'Agents', '/agents'], ['research', 'Research', '/research'],
  ['projects', 'Projects', '/projects'], ['goals', 'Goals', '/goals'], ['insights', 'Insights', '/insights'], ['activity', 'Activity', '/activity'],
];
export const NAV_BOTTOM = [['focus', 'Focus Mode', '/focus'], ['settings', 'Settings', '/settings'], ['profile', 'Profile', '/profile']];

const navBtn = ([key, label, path]) => h('button', { class: 'nav-item', 'data-nav': key, onClick: () => navigate(path) }, icon(key), h('span', { class: 'label' }, label));

export function buildShell(root, user) {
  const sidebar = h('aside', { class: 'sidebar', 'aria-label': 'Primary' },
    h('div', { class: 'brand', onClick: () => navigate('/overview'), role: 'link', tabindex: 0 }, h('div', { class: 'mini-orb', 'aria-hidden': 'true' }), h('div', null, h('span', { class: 'word wordmark' }, 'Ultron'), h('span', { class: 'sub' }, 'Personal intelligence'))),
    h('nav', { class: 'nav', 'aria-label': 'Sections' }, NAV.map(navBtn)),
    h('div', { class: 'sidebar-bottom' }, NAV_BOTTOM.map(navBtn)),
    h('button', { class: 'collapse', 'aria-label': 'Collapse sidebar', onClick: () => { userCollapsed = !userCollapsed; applyCollapse(); } }, icon('chevsl')));

  const ctx = h('button', { class: 'ctx', title: 'Ultron is using this as context. Click to clear.', onClick: () => appState.set({ context: null }) }, h('i'), h('span', null, ''), icon('x', 12));
  const bell = h('button', { class: 'iconbtn', 'aria-label': 'Notifications', onClick: (e) => openNotifications(e.currentTarget) }, icon('bell'), h('span', { class: 'badge', style: { display: 'none' } }));
  const topbar = h('header', { class: 'topbar' },
    h('button', { class: 'search', id: 'searchBtn', 'aria-label': 'Search (Ctrl+K)', onClick: () => openPalette() }, icon('search'), h('span', null, 'Search memory, tasks, knowledge…'), h('kbd', null, 'Ctrl K')),
    h('div', { class: 'grow' }), ctx, bell,
    h('button', { class: 'avatar', 'aria-label': 'Profile', onClick: () => navigate('/profile') }, user?.initials || 'AY'));

  const main = h('main', { class: 'main', id: 'main' }, topbar, h('div', { id: 'view' }));
  const bottomnav = h('nav', { class: 'bottomnav', 'aria-label': 'Sections' },
    [['overview', 'Overview', '/overview'], ['chat', 'Chat', '/chat'], ['tasks', 'Tasks', '/tasks'], ['memory', 'Memory', '/memory']].map(([k, l, p]) => h('button', { 'data-nav': k, onClick: () => navigate(p) }, icon(k), l)),
    h('button', { onClick: () => openPalette() }, icon('more'), 'More'));
  const app = h('div', { class: 'app', id: 'app', 'data-collapsed': 'false' }, sidebar, main, bottomnav);
  mount(root, app);

  /* active nav + context chip + unread badge */
  bus.on('route', (r) => { const key = r.name === 'projects' ? 'projects' : r.name; document.querySelectorAll('[data-nav]').forEach(b => { if (b.dataset.nav === key) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current'); }); });
  appState.subscribe((s) => { if (s.context) { ctx.querySelector('span').textContent = 'Context · ' + s.context.label; ctx.classList.add('on'); } else ctx.classList.remove('on'); }, ['context']);
  appState.subscribe((s) => { bell.querySelector('.badge').style.display = s.unread > 0 ? '' : 'none'; }, ['unread']);
  notificationService.list().then(list => appState.set({ unread: list.filter(n => !n.read).length })).catch(() => {});
  events.on('notification', () => appState.set(s => ({ unread: s.unread + 1 })));

  /* collapse */
  let userCollapsed = false;
  const mq = matchMedia('(max-width:1180px)');
  const applyCollapse = () => { app.dataset.collapsed = (userCollapsed || mq.matches) ? 'true' : 'false'; appState.set({ collapsed: app.dataset.collapsed === 'true' }); };
  mq.addEventListener('change', applyCollapse); applyCollapse();

  return { app, view: $('#view', app), main };
}
