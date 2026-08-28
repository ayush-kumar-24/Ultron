// Hash router with lazy page modules. Pages export `default async function (container, ctx) → cleanup?`.
import { appState, bus } from './store.js';
import { clear, h } from './ui/dom.js';

const routes = [];
let cleanup = null, container = null, current = null, navSeq = 0;

export function defineRoutes(list) { for (const r of list) routes.push({ ...r, re: new RegExp('^' + r.path.replace(/:(\w+)\??/g, (m, k) => m.endsWith('?') ? `(?:/(?<${k}>[^/]+))?` : `(?<${k}>[^/]+)`).replace(/\/\(\?:\//g, '(?:/') + '$') }); }

export function parseHash() {
  const raw = (location.hash || '#/overview').slice(1);
  const [path, qs] = raw.split('?');
  return { path: path || '/overview', query: Object.fromEntries(new URLSearchParams(qs || '')) };
}

export function navigate(path, { replace } = {}) {
  const target = '#' + (path.startsWith('/') ? path : '/' + path);
  if (replace) location.replace(target); else location.hash = target;
}

export function currentRoute() { return current; }

export function startRouter(el) {
  container = el;
  addEventListener('hashchange', render);
  if (!location.hash) location.replace('#/overview');
  render();
}

async function render() {
  const { path, query } = parseHash();
  const seq = ++navSeq;
  let match = null, params = {};
  for (const r of routes) { const m = path.match(r.re); if (m) { match = r; params = Object.fromEntries(Object.entries(m.groups || {}).map(([k, v]) => [k, v && decodeURIComponent(v)])); break; } }
  if (!match) { navigate('/overview', { replace: true }); return; }
  if (cleanup) { try { cleanup(); } catch (e) { console.error(e); } cleanup = null; }
  current = { path, params, query, name: match.name };
  appState.set({ route: current });
  bus.emit('route', current);
  document.title = `${match.title ? match.title + ' · ' : ''}ULTRON`;
  container.classList.add('leaving');
  try {
    const mod = await match.load();
    if (seq !== navSeq) return;
    clear(container); container.classList.remove('leaving');
    container.scrollTop = 0; container.parentElement.scrollTop = 0;
    const page = h('div', { class: 'content', 'data-page': match.name });
    container.append(page);
    const out = await mod.default(page, { params, query, navigate, route: current });
    if (typeof out === 'function') cleanup = out;
  } catch (err) {
    console.error(err);
    container.classList.remove('leaving');
    clear(container);
    container.append(h('div', { class: 'content' }, h('div', { class: 'error' }, h('div', { class: 'ic' }, '!'), h('div', null, h('h3', null, 'This page failed to load'), h('p', { class: 'muted' }, err.message)))));
  }
}
