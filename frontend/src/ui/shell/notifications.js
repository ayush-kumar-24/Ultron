// Notification centre — a quiet panel, grouped by importance, never a firehose.
import { h, icon, fmt, mount, onClickOutside } from '../dom.js';
import { notificationService, events } from '../../services/index.js';
import { appState } from '../../store.js';
import { navigate } from '../../router.js';
import { EmptyState, Skeleton } from '../components/index.js';

const TYPE_ICON = { reminder: 'clock', task: 'tasks', agent: 'agents', automation: 'automations', system: 'monitor', important: 'alert' };
const TYPE_ROUTE = { reminder: '/tasks', task: '/tasks', agent: '/agents', automation: '/automations', system: '/settings', important: '/activity' };
let panel = null, dispose = null;

export async function openNotifications(anchor) {
  if (panel) { closeNotifications(); return; }
  const listEl = h('div', { class: 'notif-list' }, Skeleton({ lines: 3 }));
  panel = h('div', { class: 'notif-panel', role: 'dialog', 'aria-label': 'Notifications' },
    h('div', { class: 'nh' }, 'Notifications', h('button', { onClick: async () => { await notificationService.readAll(); appState.set({ unread: 0 }); render(await notificationService.list()); } }, 'Mark all read')),
    listEl);
  document.body.append(panel);
  dispose = onClickOutside(panel, (e) => { if (!anchor.contains(e.target)) closeNotifications(); });
  const off = events.on('notification', async () => render(await notificationService.list()));
  panel._off = off;
  render(await notificationService.list());

  function render(list) {
    const filter = 'all';
    const items = list.filter(n => filter === 'all' || n.type === filter).slice(0, 20);
    mount(listEl, items.length ? items.map(n => h('div', { class: ['notif', !n.read && 'unread'], role: 'button', tabindex: 0, onClick: async () => { if (!n.read) { await notificationService.markRead(n.id); appState.set(s => ({ unread: Math.max(0, s.unread - 1) })); } closeNotifications(); navigate(TYPE_ROUTE[n.type] || '/activity'); } },
      h('div', { class: 'ic' }, icon(TYPE_ICON[n.type] || 'bell')),
      h('div', { class: 'truncate' }, h('div', { class: 't truncate' }, n.title), h('div', { class: 'b' }, n.body)),
      h('div', { class: 'w' }, fmt.relShort(n.at))))
      : EmptyState({ icon: 'bell', title: 'All quiet.', body: 'Ultron only interrupts for things that matter.' }));
  }
}
export function closeNotifications() { if (!panel) return; dispose?.(); panel._off?.(); panel.remove(); panel = null; }
