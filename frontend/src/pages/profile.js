// Profile — who Ultron is working with. Identity, a few preferences, how it talks, what it may interrupt you for.
import { h, mount } from '../ui/dom.js';
import { PageHeader, Card, Button, Input, Select, Field, Toggle, SkeletonCard, load, toast } from '../ui/components/index.js';
import { userService, settingsService } from '../services/index.js';
import { appState } from '../store.js';
import { navigate } from '../router.js';

const TIMEZONES = ['Asia/Kolkata', 'UTC', 'Europe/London', 'America/New_York'];
const LANGUAGES = ['English', 'Hindi'];
const STYLES = [{ value: 'concise', label: 'Concise' }, { value: 'balanced', label: 'Balanced' }, { value: 'detailed', label: 'Detailed' }];
const NOTIFS = [
  { key: 'reminders', label: 'Reminders', d: 'The nudges you asked for, at the time you asked.' },
  { key: 'tasks', label: 'Tasks', d: 'Due soon, overdue, done.' },
  { key: 'agents', label: 'Agents', d: 'When an agent finishes, or needs you.' },
  { key: 'automations', label: 'Automations', d: 'Runs, failures, paused rules.' },
];

const initialsOf = (u) => (u.name || '').trim().split(/\s+/).map(w => w[0]).join('').slice(0, 2).toUpperCase() || u.initials || '?';

export default async function profile(root) {
  const host = h('div');
  mount(root, PageHeader({ title: 'Profile', subtitle: 'Who Ultron is working with.' }), host);
  await load(host,
    async () => { const [me, settings] = await Promise.all([userService.me(), settingsService.get()]); return { me, settings }; },
    render,
    { skeleton: [h('div', { class: 'profile-h' }, h('div', { class: 'skel', style: { width: '64px', height: '64px', borderRadius: '50%' } }), h('div', { class: 'skel', style: { width: '180px', height: '22px' } })), h('div', { class: 'grid main' }, SkeletonCard({ lines: 5 }), h('div', { class: 'col' }, SkeletonCard(), SkeletonCard()))] },
  ).catch(() => null);
  return () => {};

  function render({ me, settings }) {
    const draft = { name: me.name || '', timezone: me.timezone || TIMEZONES[0], language: me.language || LANGUAGES[0] };
    const ai = { ...(settings.ai || {}) }, notifs = { ...(settings.notifications || {}) };

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

    /* ---------- AI behaviour ---------- */
    const cloudToggle = Toggle({ checked: !!ai.cloudEscalation, label: 'Allow cloud escalation', onChange: (v) => saveAi({ cloudEscalation: v }, () => cloudToggle.setAttribute('aria-checked', String(!v))) });
    const aiCard = Card({ title: 'AI behaviour', action: { label: 'All settings', onClick: () => navigate('/settings/ai') }, children: [
      Field({ label: 'Response style', control: Select({ options: STYLES, value: ai.responseStyle || 'balanced', onChange: (v) => saveAi({ responseStyle: v }) }) }),
      h('div', { class: 'setting', style: { marginTop: '6px' } },
        h('div', null, h('div', { class: 'l' }, 'Allow cloud escalation'), h('div', { class: 'd' }, 'Use a cloud model only when the local one isn\'t enough. Off keeps everything on this machine.')),
        cloudToggle),
      ai.model && h('div', { class: 'faint mono', style: { fontSize: '11px', letterSpacing: '.04em' } }, 'Local model · ' + ai.model),
    ] });
    async function saveAi(patch, revert) {
      try { Object.assign(ai, await settingsService.update('ai', patch)); toast('AI behaviour updated'); }
      catch (e) { revert?.(); toast(e.message || 'Could not save', { tone: 'bad' }); }
    }

    /* ---------- notifications ---------- */
    const notifCard = Card({ title: 'Notifications', action: { label: 'All settings', onClick: () => navigate('/settings/notifications') }, children: [
      h('div', null, NOTIFS.map(n => {
        const t = Toggle({ checked: !!notifs[n.key], label: n.label + ' notifications', onChange: async (v) => {
          try { Object.assign(notifs, await settingsService.update('notifications', { [n.key]: v })); toast(`${n.label} ${v ? 'on' : 'off'}`); }
          catch (e) { t.setAttribute('aria-checked', String(!v)); toast(e.message || 'Could not save', { tone: 'bad' }); }
        } });
        return h('div', { class: 'setting' }, h('div', null, h('div', { class: 'l' }, n.label), h('div', { class: 'd' }, n.d)), t);
      })),
      notifs.quietHours && h('div', { class: 'faint mono', style: { fontSize: '11px', letterSpacing: '.04em', marginTop: '6px' } }, 'Quiet hours · ' + notifs.quietHours),
    ] });

    return [header, h('div', { class: 'grid main' }, h('div', { class: 'col' }, profileCard), h('div', { class: 'col' }, aiCard, notifCard))];
  }
}
