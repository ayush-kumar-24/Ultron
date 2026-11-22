// Profile — who Ultron is working with. Identity, a few preferences, how it talks, what it may interrupt you for.
import { h, mount } from '../ui/dom.js';
import { PageHeader, Card, Button, Input, Select, Field, Toggle, SkeletonCard, load, toast } from '../ui/components/index.js';
import { userService, settingsService } from '../services/index.js';
import { appState } from '../store.js';
import { navigate } from '../router.js';

const TIMEZONES = ['Asia/Kolkata', 'UTC', 'Europe/London', 'America/New_York'];
const LANGUAGES = ['English', 'Hindi'];

const initialsOf = (u) => (u.name || '').trim().split(/\s+/).map(w => w[0]).join('').slice(0, 2).toUpperCase() || u.initials || '?';

export default async function profile(root) {
  const host = h('div');
  mount(root, PageHeader({ title: 'Profile', subtitle: 'Who Ultron is working with.' }), host);
  await load(host,
    async () => { const [me, config] = await Promise.all([userService.me(), settingsService.config()]); return { me, config }; },
    render,
    { skeleton: [h('div', { class: 'profile-h' }, h('div', { class: 'skel', style: { width: '64px', height: '64px', borderRadius: '50%' } }), h('div', { class: 'skel', style: { width: '180px', height: '22px' } })), h('div', { class: 'grid main' }, SkeletonCard({ lines: 5 }), h('div', { class: 'col' }, SkeletonCard(), SkeletonCard()))] },
  ).catch(() => null);
  return () => {};

  function render({ me, config }) {
    const draft = { name: me.name || '', timezone: me.timezone || TIMEZONES[0], language: me.language || LANGUAGES[0] };
    const field = (path) => config.fields.find(f => f.path === path);

    /* ---------- identity ---------- */
    const avatar = h('div', { class: 'avatar', 'aria-hidden': 'true' }, me.initials || initialsOf(me));
    const nameEl = h('h2', { style: { fontSize: '20px' } }, me.name);
    const header = h('div', { class: 'profile-h' }, avatar,
      h('div', { class: 'truncate' }, nameEl, me.role && h('div', { class: 'muted', style: { fontSize: '13px' } }, me.role), me.email && h('div', { class: 'faint', style: { fontSize: '12.5px' } }, me.email)));

    /* ---------- profile card ---------- */
    const saveBtn = Button({ label: 'Save', variant: 'primary', onClick: saveProfile });
    const profileCard = Card({ title: 'Profile', children: h('div', { class: 'stack' },
      Field({ label: 'Name', control: Input({ value: draft.name, placeholder: 'Your name', onInput: (v) => draft.name = v, onEnter: saveProfile }) }),
      h('div', { class: 'grid c2' },
        Field({ label: 'Timezone', control: Select({ options: TIMEZONES, value: draft.timezone, onChange: (v) => draft.timezone = v }) }),
        Field({ label: 'Language', control: Select({ options: LANGUAGES, value: draft.language, onChange: (v) => draft.language = v }) })),
      h('div', { class: 'row', style: { justifyContent: 'flex-end', marginTop: '6px' } }, saveBtn)) });

    async function saveProfile() {
      const name = draft.name.trim();
      if (!name) { toast('A name is needed', { tone: 'warn' }); return; }
      saveBtn.classList.add('loading');
      try {
        const updated = await userService.update({ name, initials: initialsOf({ name }), timezone: draft.timezone, language: draft.language });
        const user = { ...(appState.get().user || {}), ...updated };
        appState.set({ user });
        nameEl.textContent = user.name; avatar.textContent = user.initials || initialsOf(user);
        document.querySelectorAll('button.avatar').forEach(b => { b.textContent = user.initials || initialsOf(user); });   // the shell avatar is static; keep it honest
        toast('Profile saved');
      } catch (e) { toast(e.message || 'Could not save profile', { tone: 'bad' }); }
      finally { saveBtn.classList.remove('loading'); }
    }

    /* ---------- the model, as configured (read from the real settings) ---------- */
    const model = field('ollama.model')?.value, agentModel = field('agent.model')?.value;
    const aiCard = Card({ title: "Ultron's brain", action: { label: 'Change', onClick: () => navigate('/settings/ai') }, children: [
      h('div', { class: 'setting' }, h('div', null, h('div', { class: 'l' }, 'Chat model'), h('div', { class: 'd' }, 'Runs locally through Ollama.')), h('span', { class: 'mono', style: { fontSize: '12px' } }, model || '-')),
      h('div', { class: 'setting' }, h('div', null, h('div', { class: 'l' }, 'Agent model'), h('div', { class: 'd' }, 'Used when Ultron does a job on this PC.')), h('span', { class: 'mono', style: { fontSize: '12px' } }, agentModel || '-')),
    ] });

    /* ---------- notifications: the real switches ---------- */
    const SWITCHES = [
      ['notifications.enabled', 'Pop-up reminders', 'Shown when a reminder is due, even with the window closed.'],
      ['tasks.remind_at_due', "Remind me at a task's time", 'A task with a clock time also gets a reminder.'],
      ['briefing.enabled', 'Daily briefing', "Today's plan once each morning."],
    ];
    const notifCard = Card({ title: 'Notifications', action: { label: 'All settings', onClick: () => navigate('/settings/tasks') }, children:
      SWITCHES.filter(([path]) => field(path)).map(([path, label, d]) => {
        const t = Toggle({ checked: !!field(path).value, label, onChange: async (v) => {
          try { const res = await settingsService.setConfig(path, v); field(path).value = res.value; toast(res.restart ? `${label} ${v ? 'on' : 'off'} - applies after a restart` : `${label} ${v ? 'on' : 'off'}`); }
          catch (e) { t.setAttribute('aria-checked', String(!v)); toast(e.detail || e.message || 'Could not save', { tone: 'bad' }); }
        } });
        return h('div', { class: 'setting' }, h('div', null, h('div', { class: 'l' }, label), h('div', { class: 'd' }, d)), t);
      }) });

    return [header, h('div', { class: 'grid main' }, h('div', { class: 'col' }, profileCard), h('div', { class: 'col' }, aiCard, notifCard))];
  }
}
