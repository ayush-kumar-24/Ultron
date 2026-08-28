// Component library. Every factory returns a DOM element. Styles live in components.css.
import { h, icon, clear, mount, onClickOutside, fmt } from '../dom.js';

/* ---------- page scaffolding ---------- */
export const PageHeader = ({ eyebrow, title, subtitle, actions = [] }) =>
  h('div', { class: 'page-h' },
    h('div', null, eyebrow && h('div', { class: 'eyebrow' }, eyebrow), h('h1', null, title), subtitle && h('p', null, subtitle)),
    actions.length ? h('div', { class: 'actions' }, actions) : null);

export const Card = ({ title, action, children, class: cls, onClick, tight }) =>
  h('div', { class: ['card', cls, onClick && 'clickable', tight && 'tight'], onClick },
    title && h('div', { class: 'card-h' }, h('h3', null, title), action && h('button', { class: 'act', onClick: (e) => { e.stopPropagation(); action.onClick(e); } }, action.label)),
    children);

/* ---------- controls ---------- */
export const Button = ({ label, icon: ic, variant = '', size = '', onClick, disabled, title, type = 'button', class: cls }) =>
  h('button', { class: ['btn', variant, size, cls], onClick, disabled, title, type }, ic && icon(ic), label);

export const IconButton = ({ icon: ic, label, onClick, badge, size = '', square, class: cls }) =>
  h('button', { class: ['iconbtn', size, square && 'sq', cls], 'aria-label': label, title: label, onClick }, icon(ic), badge && h('span', { class: 'badge' }));

export const Chip = ({ label, icon: ic, active, onClick, count }) =>
  h('button', { class: ['chip', active && 'on'], onClick, 'aria-pressed': active ? 'true' : 'false' }, ic && icon(ic), label, count !== undefined && h('span', { class: 'n' }, count));

export function Tabs({ items, active, onChange }) {
  const el = h('div', { class: 'tabs', role: 'tablist' });
  const render = (cur) => mount(el, items.map(it => h('button', { class: 'tab', role: 'tab', 'aria-selected': it.key === cur ? 'true' : 'false', onClick: () => { render(it.key); onChange(it.key); } }, it.label, it.count !== undefined && h('span', { class: 'n' }, it.count))));
  render(active); el.set = render; return el;
}

export const Badge = ({ label, tone }) => h('span', { class: 'badge', 'data-tone': tone }, label);
export const Dot = (state) => h('span', { class: 'dot', 'data-s': state });

export const Input = ({ placeholder, value = '', onInput, onEnter, icon: ic, type = 'text', class: cls, ref }) =>
  h('label', { class: ['input', cls] }, ic && icon(ic), h('input', { type, placeholder, value, ref, onInput: (e) => onInput?.(e.target.value, e), onKeydown: (e) => { if (e.key === 'Enter' && onEnter) onEnter(e.target.value, e); } }));

export const Select = ({ options, value, onChange, class: cls }) =>
  h('label', { class: ['input', cls] }, h('select', { onChange: (e) => onChange(e.target.value) }, options.map(o => h('option', { value: o.value ?? o, selected: (o.value ?? o) === value }, o.label ?? o))), icon('chevd'));

export const Textarea = ({ placeholder, value = '', onInput, rows = 3, ref }) =>
  h('textarea', { class: 'ta', placeholder, rows, ref, onInput: (e) => onInput?.(e.target.value) }, value);

export const Field = ({ label, control }) => h('div', { class: 'field' }, h('label', null, label), control);

export const Toggle = ({ checked, onChange, label }) => {
  const t = h('button', { class: 'toggle', role: 'switch', 'aria-checked': checked ? 'true' : 'false', 'aria-label': label, onClick: () => { const v = t.getAttribute('aria-checked') !== 'true'; t.setAttribute('aria-checked', v); onChange?.(v); } });
  return t;
};
export const Check = ({ checked, onChange, label }) => {
  const c = h('button', { class: 'check', role: 'checkbox', 'aria-checked': checked ? 'true' : 'false', 'aria-label': label, onClick: (e) => { e.stopPropagation(); const v = c.getAttribute('aria-checked') !== 'true'; c.setAttribute('aria-checked', v); onChange?.(v); } }, icon('check'));
  return c;
};
export const Kbd = (t) => h('kbd', { class: 'kbd' }, t);

/* ---------- lists ---------- */
export const Row = ({ icon: ic, title, subtitle, meta, trailing, onClick, class: cls }) =>
  h('div', { class: ['row-item', onClick && 'clickable', cls], onClick, role: onClick && 'button', tabindex: onClick && 0, onKeydown: onClick && ((e) => { if (e.key === 'Enter') onClick(e); }) },
    ic !== undefined && (typeof ic === 'string' ? h('div', { class: 'ic' }, icon(ic)) : ic),
    h('div', { class: 'truncate' }, h('div', { class: 't' }, title), subtitle && h('div', { class: 's' }, subtitle)),
    h('div', { class: 'trail' }, meta && h('span', { class: 'when' }, meta), trailing));

export const Progress = ({ value, tone }) => h('div', { class: ['progress', tone] }, h('i', { style: { width: Math.max(0, Math.min(100, value)) + '%' } }));

/* ---------- metrics + charts ---------- */
export const Metric = ({ label, value, delta, trend }) =>
  h('div', { class: 'metric' }, h('div', { class: 'l' }, label), h('div', { class: 'v' }, value), delta && h('div', { class: ['d', trend] }, delta));

export function Sparkline({ values, labels, highlight, height = 84 }) {
  const w = 300, pad = 6, min = Math.min(...values) - 8, max = Math.max(...values) + 4;
  const x = (i) => pad + i * (w - pad * 2) / (values.length - 1), y = (v) => height - pad - (v - min) / (max - min || 1) * (height - pad * 2);
  let d = `M${x(0)} ${y(values[0])}`;
  for (let i = 1; i < values.length; i++) { const x0 = x(i - 1), x1 = x(i), y0 = y(values[i - 1]), y1 = y(values[i]), c = (x0 + x1) / 2; d += ` C${c} ${y0} ${c} ${y1} ${x1} ${y1}`; }
  const last = values.length - 1, gid = 'g' + Math.random().toString(36).slice(2, 7);
  const svg = h('div', { html: `<svg class="spark" viewBox="0 0 ${w} ${height}" preserveAspectRatio="none" aria-label="trend"><defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".14"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient></defs><path d="${d} L${x(last)} ${height} L${x(0)} ${height} Z" fill="url(#${gid})"/><path d="${d}" fill="none" stroke="var(--t1)" stroke-width="1.6" vector-effect="non-scaling-stroke"/><circle cx="${x(last)}" cy="${y(values[last])}" r="3.2" fill="var(--t1)" style="filter:drop-shadow(0 0 5px #fff)"/></svg>` });
  if (labels) svg.append(h('div', { class: 'axis' }, labels.map((l, i) => i === highlight ? h('b', null, l) : h('span', null, l))));
  return svg;
}

export function RingGauge({ value, label, size = 110, big, sub }) {
  const r = 46, C = 2 * Math.PI * r, dash = C * Math.max(0, Math.min(100, value)) / 100;
  const svg = h('div', { html: `<svg viewBox="0 0 110 110" width="${size}" height="${size}" aria-label="${label} ${value}%"><circle cx="55" cy="55" r="${r}" fill="none" stroke="rgba(255,255,255,.08)" stroke-width="5"/><circle cx="55" cy="55" r="${r}" fill="none" stroke="var(--t1)" stroke-width="5" stroke-linecap="round" stroke-dasharray="${dash.toFixed(1)} ${C.toFixed(1)}" transform="rotate(-90 55 55)" style="filter:drop-shadow(0 0 6px rgba(255,255,255,.35));transition:stroke-dasharray .8s var(--ease-out)"/><text x="55" y="52" text-anchor="middle" fill="var(--t1)" font-family="Inter,sans-serif" font-size="20" font-weight="600">${value}%</text><text x="55" y="68" text-anchor="middle" fill="var(--t3)" font-family="Inter,sans-serif" font-size="9">${label}</text></svg>` });
  if (!big) return svg.firstElementChild;
  return h('div', { class: 'gauge' }, svg.firstElementChild, h('div', null, h('div', { class: 'big num' }, big), h('div', { class: 'lbl' }, sub)));
}

export const Bars = ({ values, labels, highlight, max }) => {
  const m = max || Math.max(...values, 1);
  const el = h('div', { class: 'bars' }, values.map((v, i) => h('div', { class: ['b', i === highlight && 'hi'], title: String(v) }, h('i', { style: { height: '2px' } }), h('span', null, labels?.[i] ?? ''))));
  requestAnimationFrame(() => el.querySelectorAll('i').forEach((b, i) => b.style.height = (values[i] / m * 100) + '%'));
  return el;
};

/* ---------- states ---------- */
export const EmptyState = ({ icon: ic = 'circle', title, body, action }) =>
  h('div', { class: 'empty' }, icon(ic, 40) && h('div', { class: 'mark' }, icon(ic, 40)), h('h2', null, title), body && h('p', null, body), action && Button({ ...action, variant: action.variant || 'primary' }));

export const ErrorState = ({ title = 'Something went wrong', what, why, next, onRetry, retryLabel = 'Retry' }) =>
  h('div', { class: 'error', role: 'alert' }, h('div', { class: 'ic' }, icon('alert')),
    h('div', null, h('h3', null, title),
      h('dl', null, what && [h('dt', null, 'What'), h('dd', null, what)], why && [h('dt', null, 'Why'), h('dd', null, why)], next && [h('dt', null, 'Next'), h('dd', null, next)]),
      onRetry && Button({ label: retryLabel, icon: 'refresh', onClick: onRetry })));

export const Skeleton = ({ lines = 3, height = 14, width } = {}) =>
  h('div', { class: 'skel-lines', 'aria-busy': 'true' }, Array.from({ length: lines }, (_, i) => h('div', { class: 'skel', style: { height: height + 'px', width: width || (i === lines - 1 ? '60%' : '100%') } })));
export const SkeletonCard = ({ lines = 4 } = {}) => h('div', { class: 'card' }, h('div', { class: 'skel', style: { height: '14px', width: '40%', marginBottom: '14px' } }), Skeleton({ lines }));
export const AiState = (label) => h('span', { class: 'ai-state' }, h('i'), label);

/** load(container, promise, render) — shows a skeleton, then the rendered result; shows an ErrorState with retry on failure. */
export async function load(container, fetcher, render, { skeleton, retry = true } = {}) {
  mount(container, skeleton || SkeletonCard());
  try { const data = await fetcher(); clear(container); const out = render(data); if (out) mount(container, out); return data; }
  catch (err) { console.error(err); mount(container, ErrorState({ title: err.message || 'Request failed', what: err.detail || 'The request did not complete.', why: err.status ? 'Status ' + err.status : 'The service did not respond.', next: 'Try again. If it keeps failing, check the integration in Settings.', onRetry: retry ? () => load(container, fetcher, render, { skeleton, retry }) : null })); throw err; }
}

/* ---------- overlays ---------- */
export function Modal({ title, body, actions = [], onClose, wide }) {
  const close = () => { bg.remove(); document.removeEventListener('keydown', esc); onClose?.(); };
  const esc = (e) => { if (e.key === 'Escape') close(); };
  const bg = h('div', { class: 'modal-bg', onClick: (e) => { if (e.target === bg) close(); } },
    h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', 'aria-label': title, style: wide ? { width: 'min(720px,100%)' } : null },
      h('div', { class: 'mh' }, h('h3', null, title), IconButton({ icon: 'x', label: 'Close', size: 'sm', onClick: close })),
      h('div', { class: 'mb' }, body),
      actions.length ? h('div', { class: 'mf' }, actions.map(a => Button({ ...a, onClick: async (e) => { const r = await a.onClick?.(e, close); if (r !== false && !a.keepOpen) close(); } }))) : null));
  document.body.append(bg); document.addEventListener('keydown', esc);
  setTimeout(() => bg.querySelector('input,textarea,select,button.primary')?.focus(), 30);
  return { close, el: bg };
}

export const confirm = ({ title, message, confirmLabel = 'Confirm', danger }) => new Promise(resolve => {
  Modal({ title, body: h('p', { class: 'muted' }, message), onClose: () => resolve(false), actions: [{ label: 'Cancel', variant: 'ghost', onClick: () => resolve(false) }, { label: confirmLabel, variant: danger ? 'danger' : 'primary', onClick: () => resolve(true) }] });
});

export function Drawer({ title, body, actions = [], onClose }) {
  const close = () => { bg.remove(); el.remove(); document.removeEventListener('keydown', esc); onClose?.(); };
  const esc = (e) => { if (e.key === 'Escape') close(); };
  const bg = h('div', { class: 'drawer-bg', onClick: close });
  const el = h('aside', { class: 'drawer', role: 'dialog', 'aria-label': title },
    h('div', { class: 'dh' }, h('h3', { class: 'truncate' }, title), IconButton({ icon: 'x', label: 'Close', size: 'sm', onClick: close })),
    h('div', { class: 'db' }, body),
    actions.length ? h('div', { class: 'df' }, actions.map(a => Button(a))) : null);
  document.body.append(bg, el); document.addEventListener('keydown', esc);
  return { close, el, setBody: (b) => mount(el.querySelector('.db'), b) };
}

export function Menu(anchor, items) {
  const r = anchor.getBoundingClientRect();
  const m = h('div', { class: 'menu', role: 'menu' }, items.map(it => it === '-' ? h('hr', { style: { border: 0, borderTop: '1px solid var(--line)', margin: '4px 0' } }) : h('button', { class: it.danger && 'danger', role: 'menuitem', onClick: () => { dispose(); m.remove(); it.onClick?.(); } }, it.icon && icon(it.icon), it.label)));
  document.body.append(m);
  const w = m.offsetWidth, hgt = m.offsetHeight;
  m.style.left = Math.min(r.right - w, innerWidth - w - 8) + 'px';
  m.style.top = (r.bottom + hgt + 8 > innerHeight ? r.top - hgt - 6 : r.bottom + 6) + 'px';
  const dispose = onClickOutside(m, () => { dispose(); m.remove(); });
  return m;
}

/* ---------- toast ---------- */
let toastHost;
export function toast(message, { tone = 'ok', action, duration = 2600 } = {}) {
  if (!toastHost) { toastHost = h('div', { class: 'toasts', 'aria-live': 'polite' }); document.body.append(toastHost); }
  const t = h('div', { class: 'toast', 'data-tone': tone }, h('i'), h('span', null, message), action && h('button', { onClick: () => { action.onClick(); dismiss(); } }, action.label));
  toastHost.append(t);
  const dismiss = () => { t.classList.add('out'); setTimeout(() => t.remove(), 260); };
  setTimeout(dismiss, duration);
  return dismiss;
}

/* ---------- table ---------- */
export const Table = ({ columns, rows, onRow }) =>
  h('div', { class: 'table-wrap' }, h('table', { class: 'table' },
    h('thead', null, h('tr', null, columns.map(c => h('th', { style: c.width ? { width: c.width } : null }, c.label)))),
    h('tbody', null, rows.map(r => h('tr', { class: onRow && 'clickable', onClick: onRow && (() => onRow(r)) }, columns.map(c => h('td', null, c.render ? c.render(r) : r[c.key])))))));

export const timeAgo = fmt.relShort;
