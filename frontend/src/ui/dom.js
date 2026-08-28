// Tiny DOM layer. No framework: h() builds elements, everything else is plain DOM.
import { ICONS } from './icons.js';

const SVG_NS = 'http://www.w3.org/2000/svg';

/** h(tag, attrs?, ...children) — attrs: class, style, dataset, aria-*, on<Event>, html, ref, any attribute. */
export function h(tag, attrs, ...children) {
  if (attrs instanceof Node || typeof attrs === 'string' || Array.isArray(attrs)) { children.unshift(attrs); attrs = {}; }
  attrs = attrs || {};
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = Array.isArray(v) ? v.filter(Boolean).join(' ') : v;
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else if (k === 'html') el.innerHTML = v;
    else if (k === 'ref') v(el);
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k in el && typeof v !== 'string' && k !== 'value') el[k] = v;
    else el.setAttribute(k, v === true ? '' : v);
    if (k === 'value') el.value = v;
  }
  append(el, children);
  return el;
}

export function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export const frag = (...children) => append(document.createDocumentFragment(), children);
export const clear = (el) => { while (el.firstChild) el.removeChild(el.firstChild); return el; };
export const mount = (el, ...children) => append(clear(el), children);
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/** icon(name, size?) → inline SVG element. Unknown names render an empty circle so layout never breaks. */
export function icon(name, size) {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('class', 'i');
  svg.setAttribute('aria-hidden', 'true');
  if (size) { svg.style.width = size + 'px'; svg.style.height = size + 'px'; }
  svg.innerHTML = ICONS[name] || ICONS.circle;
  return svg;
}

/* ---------- formatting ---------- */
const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });
export const fmt = {
  rel(d) {
    const t = new Date(d).getTime(), now = Date.now(), s = Math.round((t - now) / 1000);
    const abs = Math.abs(s);
    if (abs < 45) return 'just now';
    if (abs < 3600) return rtf.format(Math.round(s / 60), 'minute');
    if (abs < 86400) return rtf.format(Math.round(s / 3600), 'hour');
    if (abs < 86400 * 7) return rtf.format(Math.round(s / 86400), 'day');
    return new Date(d).toLocaleDateString('en', { month: 'short', day: 'numeric' });
  },
  relShort(d) {
    const s = Math.round((Date.now() - new Date(d).getTime()) / 1000), a = Math.abs(s);
    if (a < 60) return 'now';
    if (a < 3600) return Math.round(a / 60) + 'm ago';
    if (a < 86400) return Math.round(a / 3600) + 'h ago';
    if (a < 86400 * 2) return 'Yesterday';
    if (a < 86400 * 7) return Math.round(a / 86400) + 'd ago';
    return new Date(d).toLocaleDateString('en', { month: 'short', day: 'numeric' });
  },
  time(d) { return new Date(d).toLocaleTimeString('en', { hour: 'numeric', minute: '2-digit' }); },
  date(d) { return new Date(d).toLocaleDateString('en', { weekday: 'short', month: 'short', day: 'numeric' }); },
  dateLong(d) { return new Date(d).toLocaleDateString('en', { weekday: 'long', month: 'long', day: 'numeric' }); },
  num(n) { return Number(n).toLocaleString('en'); },
  pct(n) { return Math.round(n) + '%'; },
  dur(min) { const h = Math.floor(min / 60), m = Math.round(min % 60); return h ? `${h}h ${m ? m + 'm' : ''}`.trim() : `${m}m`; },
  bytes(b) { if (b < 1024) return b + ' B'; if (b < 1048576) return (b / 1024).toFixed(0) + ' KB'; return (b / 1048576).toFixed(1) + ' MB'; },
  clock(sec) { return `${String(Math.floor(sec / 60)).padStart(2, '0')}:${String(sec % 60).padStart(2, '0')}`; },
  dayKey(d) { const x = new Date(d); return `${x.getFullYear()}-${x.getMonth()}-${x.getDate()}`; },
};

export const greeting = () => { const hr = new Date().getHours(); return hr < 12 ? 'Good morning' : hr < 17 ? 'Good afternoon' : 'Good evening'; };
export const uid = () => Math.random().toString(36).slice(2, 10);
export const sleep = (ms) => new Promise(r => setTimeout(r, ms));
export const escapeHtml = (s) => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/** Minimal markdown → safe HTML (paragraphs, bold, inline code, fenced code, lists, [n] citations). */
export function md(text) {
  const esc = escapeHtml(text);
  const blocks = esc.split(/```/);
  let out = '';
  blocks.forEach((b, i) => {
    if (i % 2 === 1) { const nl = b.indexOf('\n'); out += `<pre><code>${nl >= 0 ? b.slice(nl + 1) : b}</code></pre>`; return; }
    const paras = b.split(/\n{2,}/).filter(p => p.trim());
    for (const p of paras) {
      const lines = p.split('\n');
      if (lines.every(l => /^\s*[-*] /.test(l))) { out += '<ul>' + lines.map(l => `<li>${inline(l.replace(/^\s*[-*] /, ''))}</li>`).join('') + '</ul>'; }
      else out += `<p>${inline(lines.join('<br>'))}</p>`;
    }
  });
  return out;
  function inline(s) {
    return s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\[(\d+)\]/g, '<span class="cite">$1</span>');
  }
}

/** Click-outside helper: returns a dispose fn. */
export function onClickOutside(el, fn) {
  const handler = (e) => { if (!el.contains(e.target)) fn(e); };
  setTimeout(() => document.addEventListener('pointerdown', handler), 0);
  return () => document.removeEventListener('pointerdown', handler);
}
