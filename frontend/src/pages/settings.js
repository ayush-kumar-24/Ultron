// Settings — an assistant first, a platform second. Every control saves immediately.
import { h, icon, mount } from '../ui/dom.js';
import { PageHeader, Card, Button, Badge, Select, Input, Toggle, Kbd, toast, confirm, load, SkeletonCard, EmptyState } from '../ui/components/index.js';
import { settingsService, integrationService, agentService, systemService } from '../services/index.js';
import { presence } from '../ui/core/presence.js';
import { navigate } from '../router.js';

const SECTIONS = [['general', 'General', 'sliders'], ['ai', 'AI', 'spark'], ['memory', 'Memory', 'memory'], ['voice', 'Voice', 'mic'], ['notifications', 'Notifications', 'bell'], ['privacy', 'Privacy', 'shield'], ['integrations', 'Integrations', 'globe']];
const DESC = {
  general: 'How Ultron looks and formats things.', ai: 'How Ultron thinks and which model answers.',
  memory: 'What Ultron keeps, and for how long.', voice: 'How Ultron listens and speaks.',
  notifications: 'Ultron only interrupts for these.', privacy: 'Your data stays on this device by default.', integrations: 'What Ultron is allowed to reach.',
};

export default async function settings(root, { params }) {
  const section = SECTIONS.some(s => s[0] === params.section) ? params.section : 'general';
  const pane = h('div', null);
  const nav = h('div', { class: 'snav' }, SECTIONS.map(([key, label, ic]) => h('button', { 'aria-current': key === section ? 'true' : 'false', onClick: () => navigate('/settings/' + key) }, icon(ic), label)));
  mount(root, PageHeader({ title: 'Settings', subtitle: 'Ultron is an assistant first — most of this you will never need.' }), h('div', { class: 'settings' }, nav, pane));

  let s = null, agents = [];
  await load(pane, async () => { [s, agents] = await Promise.all([settingsService.get(), agentService.list().catch(() => [])]); return s; }, () => render(section), { skeleton: SkeletonCard({ lines: 6 }) }).catch(() => {});

  function save(sec, patch) { settingsService.update(sec, patch).then(() => toast('Saved')).catch(() => toast('Could not save', { tone: 'bad' })); Object.assign(s[sec], patch); }
  function setting(label, desc, control) { return h('div', { class: 'setting' }, h('div', null, h('div', { class: 'l' }, label), desc && h('div', { class: 'd' }, desc)), control); }
  function head(key) { return [h('h2', { style: { fontSize: '17px' } }, SECTIONS.find(x => x[0] === key)[1]), h('p', { class: 'muted', style: { fontSize: '13px', marginTop: '2px', marginBottom: '10px' } }, DESC[key])]; }

  function render(key) {
    if (key === 'general') return Card({ children: [...head(key),
      setting('Theme', "Dark is Ultron's native theme.", Select({ options: ['dark', 'system'], value: s.general.theme, onChange: (v) => save('general', { theme: v }) })),
      setting('Language', null, Select({ options: ['English', 'Hindi'], value: s.general.language, onChange: (v) => save('general', { language: v }) })),
      setting('Timezone', null, Select({ options: ['Asia/Kolkata', 'UTC', 'Europe/London', 'America/New_York'], value: s.general.timezone, onChange: (v) => save('general', { timezone: v }) })),
      setting('Date format', null, Select({ options: ['DD MMM YYYY', 'MM/DD/YYYY', 'YYYY-MM-DD'], value: s.general.dateFormat, onChange: (v) => save('general', { dateFormat: v }) }))] });

    if (key === 'ai') {
      const tempOut = h('span', { class: 'num', style: { minWidth: '28px', textAlign: 'right' } }, String(s.ai.temperature));
      return Card({ children: [...head(key),
        setting('Response style', 'Concise is the Ultron default.', Select({ options: ['concise', 'balanced', 'detailed'], value: s.ai.responseStyle, onChange: (v) => save('ai', { responseStyle: v }) })),
        setting('Model', 'Local first. Cloud only when it helps.', Select({ options: ['local · qwen2.5-7b', 'local · llama3.1-8b', 'cloud · optional'], value: s.ai.model, onChange: (v) => save('ai', { model: v }) })),
        setting('Cloud escalation', 'Allow harder tasks to reach an optional cloud model.', Toggle({ checked: s.ai.cloudEscalation, label: 'Cloud escalation', onChange: (v) => save('ai', { cloudEscalation: v }) })),
        setting('Temperature', 'Lower is more deterministic.', h('div', { class: 'row' }, h('input', { type: 'range', min: '0', max: '1', step: '0.1', value: String(s.ai.temperature), style: { width: '160px' }, onInput: (e) => { tempOut.textContent = e.target.value; }, onChange: (e) => save('ai', { temperature: +e.target.value }) }), tempOut)),
        setting('Reasoning', null, Select({ options: ['fast', 'balanced', 'deep'], value: s.ai.reasoning, onChange: (v) => save('ai', { reasoning: v }) })),
        setting('Default agent', null, Select({ options: agents.map(a => ({ value: a.id, label: a.name })), value: s.ai.defaultAgent, onChange: (v) => save('ai', { defaultAgent: v }) }))] });
    }

    if (key === 'memory') return Card({ children: [...head(key),
      setting('Memory', 'Ultron without memory is just a chatbot.', Toggle({ checked: s.memory.enabled, label: 'Memory enabled', onChange: (v) => save('memory', { enabled: v }) })),
      setting('Automatic memory', 'Let Ultron decide what is worth keeping.', Toggle({ checked: s.memory.automatic, label: 'Automatic memory', onChange: (v) => save('memory', { automatic: v }) })),
      setting('Review', 'How often Ultron asks you to confirm what it learned.', Select({ options: ['weekly', 'monthly', 'never'], value: s.memory.review, onChange: (v) => save('memory', { review: v }) })),
      setting('Retention', 'Days before unpinned, unused memories fade.', Input({ type: 'number', value: String(s.memory.retentionDays), onInput: (v) => save('memory', { retentionDays: +v }) })),
      h('div', { style: { marginTop: '14px' } }, Button({ label: 'Review memories', icon: 'memory', onClick: () => navigate('/memory') }))] });

    if (key === 'voice') {
      const speedOut = h('span', { class: 'num', style: { minWidth: '32px', textAlign: 'right' } }, s.voice.speed + '×');
      return Card({ children: [...head(key),
        setting('Voice', null, Select({ options: ['en_US-lessac-medium', 'en_GB-alan-medium'], value: s.voice.voice, onChange: (v) => save('voice', { voice: v }) })),
        setting('Speed', null, h('div', { class: 'row' }, h('input', { type: 'range', min: '0.5', max: '1.5', step: '0.1', value: String(s.voice.speed), style: { width: '160px' }, onInput: (e) => { speedOut.textContent = e.target.value + '×'; }, onChange: (e) => save('voice', { speed: +e.target.value }) }), speedOut)),
        setting('Wake word', 'Say “Hey Ultron” to start talking.', Toggle({ checked: s.voice.wakeWord, label: 'Wake word', onChange: (v) => save('voice', { wakeWord: v }) })),
        setting('Push to talk', 'Hold to talk from anywhere.', Kbd(s.voice.pushToTalk)),
        setting('Interruptions', 'Talking over Ultron stops it speaking.', Toggle({ checked: s.voice.interruptions, label: 'Interruptions', onChange: (v) => save('voice', { interruptions: v }) })),
        h('div', { style: { marginTop: '14px' } }, Button({ label: 'Test voice', icon: 'volume', onClick: () => { presence.setState('speaking', 'Testing voice'); setTimeout(() => presence.setState('idle'), 2200); } }))] });
    }

    if (key === 'notifications') return Card({ children: [...head(key),
      setting('Reminders', null, Toggle({ checked: s.notifications.reminders, label: 'Reminders', onChange: (v) => save('notifications', { reminders: v }) })),
      setting('Tasks', null, Toggle({ checked: s.notifications.tasks, label: 'Tasks', onChange: (v) => save('notifications', { tasks: v }) })),
      setting('Agent activity', 'Only when an agent finishes or fails.', Toggle({ checked: s.notifications.agents, label: 'Agents', onChange: (v) => save('notifications', { agents: v }) })),
      setting('Automations', null, Toggle({ checked: s.notifications.automations, label: 'Automations', onChange: (v) => save('notifications', { automations: v }) })),
      setting('Quiet hours', 'Nothing interrupts during these hours.', Input({ value: s.notifications.quietHours, onInput: (v) => save('notifications', { quietHours: v }) }))] });

    if (key === 'privacy') return [
      Card({ children: [...head(key),
        setting('Local-only mode', 'Never send personal data off this device.', Toggle({ checked: s.privacy.localOnly, label: 'Local only', onChange: (v) => save('privacy', { localOnly: v }) })),
        setting('Telemetry', 'Off. Ultron does not phone home.', Toggle({ checked: s.privacy.telemetry, label: 'Telemetry', onChange: (v) => save('privacy', { telemetry: v }) })),
        setting('Recording', 'Screen recording stays off until you ask for it.', Toggle({ checked: s.privacy.recordingDefault, label: 'Recording default', onChange: (v) => save('privacy', { recordingDefault: v }) }))] }),
      h('div', { class: 'danger-zone' },
        h('div', { class: 'l', style: { fontWeight: '500', marginBottom: '4px' } }, 'Data controls'),
        h('p', { class: 'muted', style: { fontSize: '12.5px', marginBottom: '12px' } }, 'Deleting removes the data from this device. It cannot be undone.'),
        h('div', { class: 'row', style: { flexWrap: 'wrap' } },
          Button({ label: 'Export my data', icon: 'download', onClick: exportData }),
          Button({ label: 'Reset demo data', icon: 'refresh', onClick: async () => { if (await confirm({ title: 'Reset demo data?', message: 'Restores the sample projects, tasks and memories Ultron shipped with.', confirmLabel: 'Reset' })) { await systemService.resetDemo(); toast('Demo data reset'); setTimeout(() => location.reload(), 400); } } }),
          Button({ label: 'Delete all data', icon: 'trash', variant: 'danger', onClick: async () => { if (await confirm({ title: 'Delete all data?', message: 'This removes tasks, memories, knowledge, conversations, research, automations and activity from this device. Ultron will start empty.', confirmLabel: 'Delete everything', danger: true })) { await systemService.wipe(); toast('All data deleted'); setTimeout(() => { location.hash = '#/overview'; location.reload(); }, 400); } } })))];

    if (key === 'integrations') {
      const grid = h('div', { class: 'grid c2' });
      load(grid, () => integrationService.list(), (list) => list.length ? list.map(i => intCard(i, grid)) : EmptyState({ icon: 'globe', title: 'No integrations.', body: 'Connect a service to widen what Ultron can reach.' }), { skeleton: h('div', { class: 'grid c2' }, SkeletonCard({ lines: 2 }), SkeletonCard({ lines: 2 })) }).catch(() => {});
      return [...head(key), grid];
    }
  }

  function intCard(i, grid) {
    const btn = Button({ label: i.status === 'connected' ? 'Disconnect' : i.error ? 'Reconnect' : 'Connect', size: 'sm', variant: i.status === 'connected' ? '' : 'primary', onClick: async () => {
      btn.classList.add('loading');
      try {
        const next = i.status === 'connected' ? await integrationService.disconnect(i.id) : await integrationService.connect(i.id);
        toast(next.status === 'connected' ? `${i.name} connected` : `${i.name} disconnected`);
        const fresh = await integrationService.list();
        mount(grid, fresh.map(x => intCard(x, grid)));
      } catch { toast('Could not reach ' + i.name, { tone: 'bad' }); btn.classList.remove('loading'); }
    } });
    return h('div', { class: ['int-card', i.error && 'err'] },
      h('div', { class: 'ic' }, icon(i.icon)),
      h('div', { class: 'truncate' }, h('h4', null, i.name), h('div', { class: 'd' }, i.detail)),
      h('div', { class: 'row', style: { gap: '8px' } }, Badge({ label: i.status, tone: i.status === 'connected' ? 'ok' : i.status === 'disconnected' ? 'bad' : undefined }), btn));
  }

  function exportData() {
    const blob = new Blob([JSON.stringify({ exportedAt: new Date().toISOString(), settings: s }, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = h('a', { href: url, download: 'ultron-data.json' });
    document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast('Exported');
  }
}
