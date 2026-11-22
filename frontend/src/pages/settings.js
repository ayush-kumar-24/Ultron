// Settings — the real ones. Same list, same file (data/config.yaml) and same rules as the
// desktop app's Settings screen, so a change here is a change everywhere.
import { h, icon, mount } from '../ui/dom.js';
import { PageHeader, Card, Button, Badge, Select, Toggle, toast, confirm, load, SkeletonCard, EmptyState } from '../ui/components/index.js';
import {
  settingsService, integrationService, systemService, taskService, memoryService, chatService, knowledgeService,
  automationService, researchService, projectService, goalService, sessionService, calendarService,
} from '../services/index.js';
import { navigate } from '../router.js';

const ICONS = { general: 'sliders', voice: 'volume', listening: 'mic', ai: 'spark', briefing: 'sunrise', tasks: 'tasks', control: 'monitor', agent: 'agents', skills: 'layers', developer: 'terminal' };
const DESC = {
  general: 'Your name, and how Ultron runs in the background.',
  voice: 'How Ultron sounds when it speaks.',
  listening: 'How Ultron hears you.',
  ai: 'Which local model answers, and how much it remembers.',
  briefing: 'The daily plan Ultron shows you each morning.',
  tasks: 'Reminders, notifications and unfinished tasks.',
  control: 'What Ultron may do on this computer.',
  agent: 'The agent that does jobs for you - files, apps, email.',
  skills: 'Skills installed from GitHub.',
  developer: 'Diagnostics. Leave these alone unless something is wrong.',
  integrations: 'What Ultron can reach right now.',
  privacy: 'Everything stays on this computer. Export or delete it here.',
};

export default async function settings(root, { params }) {
  const pane = h('div', null);
  const nav = h('div', { class: 'snav' });
  const banner = h('div', { class: 'restart-note', style: { display: 'none' } });
  mount(root,
    PageHeader({ title: 'Settings', subtitle: 'The same settings as the desktop app. Changes save as you make them.' }),
    banner,
    h('div', { class: 'settings' }, nav, pane));

  let data = null;
  await load(pane, () => settingsService.config(), (d) => { data = d; draw(); }, { skeleton: SkeletonCard({ lines: 6 }) }).catch(() => {});

  function sections() {
    return [...data.categories.map(c => [c.id, c.label]), ['integrations', 'Integrations'], ['privacy', 'Privacy & data']];
  }
  function current() {
    const all = sections().map(s => s[0]);
    return all.includes(params.section) ? params.section : all[0];
  }
  function draw() {
    const key = current();
    mount(nav, sections().map(([id, label]) => h('button', { 'aria-current': id === key ? 'true' : 'false', onClick: () => navigate('/settings/' + id) }, icon(ICONS[id] || (id === 'integrations' ? 'globe' : 'shield')), label)));
    showBanner();
    mount(pane, render(key));
  }
  function showBanner() {
    const pending = data?.restartPending || [];
    banner.style.display = pending.length ? '' : 'none';
    mount(banner, icon('refresh'), h('span', null, `${pending.length} change${pending.length === 1 ? '' : 's'} will apply the next time Ultron starts.`));
  }
  function head(key, label) {
    return [h('h2', { style: { fontSize: '17px' } }, label), h('p', { class: 'muted', style: { fontSize: '13px', marginTop: '2px', marginBottom: '10px' } }, DESC[key] || '')];
  }
  function valueOf(path) { return data.fields.find(f => f.path === path)?.value; }
  function visible(f) { return !f.visibleWhen || f.visibleWhen.values.includes(valueOf(f.visibleWhen.path)); }

  async function save(f, value) {
    try {
      const res = await settingsService.setConfig(f.path, value);
      f.value = res.value;
      data.restartPending = res.restartPending;
      toast(res.restart ? `Saved - applies after a restart` : 'Saved');
      showBanner();
      // A choice may reveal or hide other fields (e.g. the voice engine's own options).
      if (data.fields.some(x => x.visibleWhen?.path === f.path)) mount(pane, render(current()));
    } catch (err) {
      toast(err.detail || err.message || 'Could not save', { tone: 'bad' });
      mount(pane, render(current()));
    }
  }

  function control(f) {
    if (f.readOnly) return h('span', { class: 'faint', style: { fontSize: '12.5px', maxWidth: '240px' }, title: f.value || '' }, f.value ? String(f.value) : 'Choose it in the desktop app');
    if (f.kind === 'bool') return Toggle({ checked: !!f.value, label: f.label, onChange: (v) => save(f, v) });
    if (f.kind === 'choice' && !f.editable) {
      const opts = f.options.slice();
      if (f.value != null && !opts.some(o => String(o.value) === String(f.value))) opts.unshift({ value: f.value, label: String(f.value) });
      return Select({ options: opts, value: f.value, onChange: (v) => save(f, v) });
    }
    const type = f.kind === 'int' || f.kind === 'float' ? 'number' : f.kind === 'time' ? 'time' : 'text';
    const listId = f.kind === 'choice' ? 'opts-' + f.path.replace(/\W/g, '-') : null;
    const input = h('input', {
      type, value: f.value ?? '', list: listId,
      min: type === 'number' ? String(f.min) : null, max: type === 'number' ? String(f.max) : null,
      step: type === 'number' ? String(f.kind === 'int' ? Math.max(1, f.step) : f.step) : null,
      'aria-label': f.label,
      onChange: (e) => { if (String(e.target.value) !== String(f.value ?? '')) save(f, type === 'number' ? Number(e.target.value) : e.target.value); },
      onKeydown: (e) => { if (e.key === 'Enter') e.target.blur(); },
    });
    return h('label', { class: 'input', style: { minWidth: type === 'number' ? '110px' : '220px' } }, input,
      listId ? h('datalist', { id: listId }, f.options.map(o => h('option', { value: o.value }, o.label))) : null);
  }

  function row(f) {
    return h('div', { class: 'setting' },
      h('div', null,
        h('div', { class: 'l' }, f.label, f.restart ? h('span', { class: 'faint', style: { fontSize: '11px', marginLeft: '8px' }, title: 'Applies after Ultron restarts' }, 'restart') : null),
        f.help ? h('div', { class: 'd' }, f.help) : null),
      control(f));
  }

  function render(key) {
    if (key === 'integrations') {
      const grid = h('div', { class: 'grid c2' });
      load(grid, () => integrationService.list(), (list) => list.length ? list.map(i => intCard(i, grid)) : EmptyState({ icon: 'globe', title: 'Nothing to show.', body: 'Ultron could not read its own services.' }), { skeleton: h('div', { class: 'grid c2' }, SkeletonCard({ lines: 2 }), SkeletonCard({ lines: 2 })) }).catch(() => {});
      return [...head(key, 'Integrations'), grid];
    }
    if (key === 'privacy') return privacy();
    const label = data.categories.find(c => c.id === key)?.label || key;
    const fields = data.fields.filter(f => f.category === key && visible(f));
    return Card({ children: [...head(key, label), fields.length ? fields.map(row) : h('p', { class: 'muted' }, 'Nothing to change here.')] });
  }

  function privacy() {
    const demo = document.documentElement.dataset.backend === 'mock';
    return [
      Card({ children: [...head('privacy', 'Privacy & data'),
        h('div', { class: 'setting' }, h('div', null, h('div', { class: 'l' }, 'Where your data lives'), h('div', { class: 'd' }, 'Conversations, tasks, memories and documents are stored in a database on this computer. Nothing is sent anywhere unless you connect a service that sends it.')), Badge({ label: 'on this device', tone: 'ok' })),
        h('div', { class: 'setting' }, h('div', null, h('div', { class: 'l' }, 'Settings file'), h('div', { class: 'd' }, data.file || 'data/config.yaml')), h('span', null)),
      ] }),
      h('div', { class: 'danger-zone' },
        h('div', { class: 'l', style: { fontWeight: '500', marginBottom: '4px' } }, 'Your data'),
        h('p', { class: 'muted', style: { fontSize: '12.5px', marginBottom: '12px' } }, 'Export downloads everything as one file. Deleting removes it from this computer for good.'),
        h('div', { class: 'row', style: { flexWrap: 'wrap' } },
          Button({ label: 'Export my data', icon: 'download', onClick: (e) => exportData(e.currentTarget) }),
          demo ? Button({ label: 'Reset demo data', icon: 'refresh', onClick: async () => { if (await confirm({ title: 'Reset demo data?', message: 'Restores the sample projects, tasks and memories.', confirmLabel: 'Reset' })) { await systemService.resetDemo(); toast('Demo data reset'); setTimeout(() => location.reload(), 400); } } }) : null,
          Button({ label: 'Delete all data', icon: 'trash', variant: 'danger', onClick: async () => {
            if (!await confirm({ title: 'Delete all your data?', message: 'This permanently removes every conversation, task, memory, document, research report, automation and session from this computer. Your settings stay. This cannot be undone.', confirmLabel: 'Delete everything', danger: true })) return;
            try { await systemService.wipe(); toast('All data deleted'); setTimeout(() => { location.hash = '#/overview'; location.reload(); }, 500); }
            catch (err) { toast(err.detail || err.message || 'Could not delete everything', { tone: 'bad' }); }
          } }))),
    ];
  }

  function intCard(i, grid) {
    const action = i.toggle === false
      ? null
      : Button({ label: i.status === 'connected' ? 'Turn off' : 'Turn on', size: 'sm', variant: i.status === 'connected' ? '' : 'primary', onClick: async () => {
        action.classList.add('loading');
        try {
          const next = i.status === 'connected' ? await integrationService.disconnect(i.id) : await integrationService.connect(i.id);
          toast(next.status === 'connected' ? `${i.name} is on` : `${i.name} is off`);
        } catch (err) {
          toast(err.detail || err.message || `Could not change ${i.name}`, { tone: 'bad' });
        }
        mount(grid, (await integrationService.list()).map(x => intCard(x, grid)));
      } });
    return h('div', { class: ['int-card', i.error && 'err'] },
      h('div', { class: 'ic' }, icon(i.icon)),
      h('div', { class: 'truncate' }, h('h4', null, i.name), h('div', { class: 'd', title: i.detail }, i.detail)),
      h('div', { class: 'row', style: { gap: '8px' } }, Badge({ label: i.status === 'available' ? 'off' : i.status, tone: i.status === 'connected' ? 'ok' : i.status === 'disconnected' ? 'bad' : undefined }), action));
  }

  async function exportData(btn) {
    btn.classList.add('loading');
    try {
      const safe = (p) => p.catch(() => []);
      const [tasks, memories, conversations, knowledge, automations, research, projects, goals, sessions, events] = await Promise.all([
        safe(taskService.list({})), safe(memoryService.list({})), safe(chatService.list()), safe(knowledgeService.list({})),
        safe(automationService.list()), safe(researchService.list()), safe(projectService.list()), safe(goalService.list()),
        safe(sessionService.list()), safe(calendarService.events({})),
      ]);
      for (const c of conversations) c.messages = await chatService.messages(c.id).catch(() => []);
      const dump = { exportedAt: new Date().toISOString(), app: 'Ultron', tasks, memories, conversations, knowledge, automations, research, projects, goals, sessions, events };
      const url = URL.createObjectURL(new Blob([JSON.stringify(dump, null, 2)], { type: 'application/json' }));
      const a = h('a', { href: url, download: `ultron-export-${new Date().toISOString().slice(0, 10)}.json` });
      document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast(`Exported ${tasks.length} tasks, ${memories.length} memories, ${conversations.length} conversations`);
    } catch (err) {
      toast(err.message || 'Export failed', { tone: 'bad' });
    } finally { btn.classList.remove('loading'); }
  }
}
