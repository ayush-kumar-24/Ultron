// Activity — everything Ultron did, in order.
import { h, icon, fmt, mount } from '../ui/dom.js';
import { PageHeader, Chip, EmptyState, load, Skeleton } from '../ui/components/index.js';
import { activityService } from '../services/index.js';

const KINDS = [['all', 'All'], ['chat', 'Chat'], ['memory', 'Memory'], ['research', 'Research'], ['tasks', 'Tasks'], ['agents', 'Agents'], ['automations', 'Automations'], ['system', 'System']];
const KIND_ICON = { chat: 'chat', memory: 'memory', research: 'research', tasks: 'check', agents: 'agents', automations: 'automations', system: 'terminal' };

export default async function activity(root, { query }) {
  let kind = query.kind || 'all';
  const chips = h('div', { class: 'chips', style: { marginBottom: '8px' } });
  const list = h('div', null);
  mount(root, PageHeader({ title: 'Activity', subtitle: 'Everything Ultron did, in order.' }), chips, list);

  function renderChips() {
    mount(chips, KINDS.map(([k, label]) => Chip({ label, active: k === kind, onClick: () => { kind = k; renderChips(); refresh(); } })));
  }
  function dayLabel(d) {
    const day = new Date(d); day.setHours(0, 0, 0, 0);
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const diff = Math.round((today - day) / 86400000);
    return diff === 0 ? 'Today' : diff === 1 ? 'Yesterday' : fmt.dateLong(d);
  }
  async function refresh() {
    await load(list, () => activityService.list({ kind }), (items) => {
      if (!items.length) return EmptyState({ icon: 'activity', title: kind === 'all' ? 'No activity yet.' : 'Nothing in this category yet.', body: kind === 'all' ? 'Everything Ultron does will be logged here.' : 'Try another filter.' });
      const groups = [];
      let last = null;
      for (const a of items) {
        const key = fmt.dayKey(a.at);
        if (key !== last) { groups.push(h('div', { class: 'day-h' }, dayLabel(a.at))); last = key; }
        groups.push(h('div', { class: 'act' },
          h('div', { class: 'w' }, fmt.time(a.at)),
          h('div', { class: 'ic' }, icon(KIND_ICON[a.kind] || 'circle')),
          h('div', { class: 'truncate' }, h('div', { class: 't' }, a.title), h('div', { class: 's' }, a.body))));
      }
      return groups;
    }, { skeleton: Skeleton({ lines: 8 }) }).catch(() => {});
  }
  renderChips();
  await refresh();
}
