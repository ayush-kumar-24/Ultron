// API client — the single seam between the UI and a backend.
// Pages → services → this client → transport. Nothing above this file knows where data comes from.
import { createEmitter } from '../store.js';
import { config, apiUrl, auth } from '../config.js';
import { ApiError } from './errors.js';
export { ApiError };

const emitter = createEmitter();
let transport = null;
let stopEvents = null;

/* ---------------- live transport (real backend) ---------------- */
const jsonHeaders = () => ({ 'content-type': 'application/json', accept: 'application/json', ...auth.headers() });
const httpMessage = (s) => ({ 400: 'Bad request', 403: 'Not allowed', 404: 'Not found', 409: 'Conflict', 422: 'Could not process that', 429: 'Too many requests', 500: 'Ultron hit an internal error', 502: 'Backend unavailable', 503: 'Backend unavailable' }[s] || `Request failed (${s})`);

async function doFetch(method, path, body, { timeoutMs = config.requestTimeoutMs } = {}) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const res = await fetch(apiUrl(path), { method, headers: jsonHeaders(), credentials: auth.credentials, body: body === undefined ? undefined : JSON.stringify(body), signal: ctl.signal });
    if (res.status === 401) { emitter.emit('unauthorized', { path }); throw new ApiError(401, 'Not signed in', 'The backend rejected the session.'); }
    if (!res.ok) {
      let detail = '';
      try { const j = await res.json(); detail = j.detail || j.message || j.error || JSON.stringify(j); } catch { detail = await res.text().catch(() => ''); }
      throw new ApiError(res.status, httpMessage(res.status), detail);
    }
    if (res.status === 204) return null;
    const ct = res.headers.get('content-type') || '';
    return ct.includes('json') ? res.json() : res.text();
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err.name === 'AbortError') throw new ApiError(0, 'Request timed out', `No response in ${Math.round(timeoutMs / 1000)}s.`);
    throw new ApiError(0, 'Cannot reach Ultron', err.message || 'The backend is not responding.');
  } finally { clearTimeout(timer); }
}

export const fetchTransport = {
  async request(method, path, body) {
    const retries = method === 'GET' ? config.retry.attempts : 0;
    let lastErr;
    for (let i = 0; i <= retries; i++) {
      try { return await doFetch(method, path, body); }
      catch (err) {
        lastErr = err;
        if (err.status && err.status !== 0 && err.status < 500) break;      // client errors are not retried
        if (i < retries) await new Promise(r => setTimeout(r, config.retry.backoffMs * (i + 1)));
      }
    }
    throw lastErr;
  },

  /** POST that streams `data: {json}` lines. Resolves with the payload of the final {type:'done'} event. */
  async stream(path, body, onChunk) {
    const res = await fetch(apiUrl(path), { method: 'POST', headers: jsonHeaders(), credentials: auth.credentials, body: JSON.stringify(body) });
    if (res.status === 401) { emitter.emit('unauthorized', { path }); throw new ApiError(401, 'Not signed in'); }
    if (!res.ok || !res.body) throw new ApiError(res.status || 0, httpMessage(res.status || 0), await res.text().catch(() => ''));
    const reader = res.body.getReader(), dec = new TextDecoder();
    let buf = '', result = null;
    for (;;) {
      const { value, done } = await reader.read(); if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split('\n'); buf = lines.pop();
      for (const line of lines) {
        const l = line.trim(); if (!l || l.startsWith(':')) continue;
        const payload = l.startsWith('data:') ? l.slice(5).trim() : l;
        if (!payload || payload === '[DONE]') continue;
        let ev; try { ev = JSON.parse(payload); } catch { continue; }
        if (ev.type === 'done') result = ev.payload ?? ev.result ?? null;
        else if (ev.type === 'error') throw new ApiError(ev.status || 500, ev.message || 'Stream failed', ev.detail);
        else onChunk(ev);
      }
    }
    return result;
  },

  /** Server-sent events with auto-reconnect. Emits {type, payload} onto the app bus. */
  events(emit) {
    if (!config.eventsPath) return null;
    let es = null, closed = false, backoff = 1000;
    const open = () => {
      if (closed) return;
      try { es = new EventSource(apiUrl(config.eventsPath), { withCredentials: config.auth.mode === 'cookie' }); } catch { return; }
      es.onopen = () => { backoff = 1000; emit('heartbeat', { at: new Date().toISOString(), online: true }); };
      es.onmessage = (m) => { try { const ev = JSON.parse(m.data); emit(ev.type, ev.payload); } catch {} };
      es.onerror = () => { es?.close(); emit('heartbeat', { at: new Date().toISOString(), online: false }); if (!closed) { setTimeout(open, backoff); backoff = Math.min(30000, backoff * 2); } };
    };
    open();
    return () => { closed = true; es?.close(); };
  },
};

/* ---------------- public client ---------------- */
export const api = {
  /** Swap the transport. Called by boot(); can be called again at runtime. */
  use(t) { transport = t; if (stopEvents) { stopEvents(); stopEvents = null; } },
  get transport() { return transport; },
  get isMock() { return transport?.isMock === true; },

  get: (path, params) => transport.request('GET', withQuery(path, params)),
  post: (path, body) => transport.request('POST', path, body ?? {}),
  patch: (path, body) => transport.request('PATCH', path, body ?? {}),
  put: (path, body) => transport.request('PUT', path, body ?? {}),
  delete: (path) => transport.request('DELETE', path),
  stream: (path, body, onChunk) => transport.stream(path, body, onChunk),

  /** Realtime bus: 'agent' | 'automation' | 'notification' | 'knowledge' | 'research' | 'heartbeat' | 'unauthorized'. */
  events: emitter,
  start() { if (!stopEvents && transport?.events) stopEvents = transport.events(emitter.emit) || null; },
  stop() { stopEvents?.(); stopEvents = null; },
};

function withQuery(path, params) {
  if (!params) return path;
  const q = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '').map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('&');
  return q ? `${path}?${q}` : path;
}

/**
 * Choose a transport per config.mode. 'auto' probes the backend health endpoint and
 * falls back to the built-in mock so the UI is never dead.
 * Returns { mode:'live'|'mock', reason }.
 */
export async function initTransport() {
  const useMock = async (reason) => { const { mockTransport } = await import('./mock/handlers.js'); api.use(mockTransport); return { mode: 'mock', reason }; };
  if (config.mode === 'mock') return useMock('configured');
  if (config.mode === 'live') { api.use(fetchTransport); return { mode: 'live', reason: 'configured' }; }
  try {
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), 2500);
    const res = await fetch(apiUrl(config.healthPath), { headers: { accept: 'application/json', ...auth.headers() }, credentials: auth.credentials, signal: ctl.signal });
    clearTimeout(t);
    if (!res.ok) return useMock(`backend answered ${res.status}`);
    // A static host may answer 200 with the SPA shell; only JSON counts as a real backend.
    if (!(res.headers.get('content-type') || '').includes('json')) return useMock('endpoint did not return JSON');
    api.use(fetchTransport);
    return { mode: 'live', reason: 'health check passed' };
  } catch { return useMock('no backend detected'); }
}
