// Config accessor. Merges window.ULTRON_CONFIG (from /config.js) with localStorage overrides.
const defaults = {
  mode: 'auto', apiBaseUrl: '', apiPrefix: '/api', healthPath: '/system/health', eventsPath: '/events',
  auth: { mode: 'bearer', tokenKey: 'ultron.token', loginUrl: null },
  headers: {}, requestTimeoutMs: 30000, retry: { attempts: 2, backoffMs: 400 },
  features: { voice: true, recording: true, mind: true, research: true, agents: true, automations: true },
  appName: 'ULTRON', version: '1.0.0',
};

const injected = (typeof window !== 'undefined' && window.ULTRON_CONFIG) || {};
export const config = {
  ...defaults, ...injected,
  auth: { ...defaults.auth, ...(injected.auth || {}) },
  retry: { ...defaults.retry, ...(injected.retry || {}) },
  features: { ...defaults.features, ...(injected.features || {}) },
  headers: { ...defaults.headers, ...(injected.headers || {}) },
};

// Runtime override, useful for debugging against a live backend: localStorage.setItem('ultron.mode','live')
const override = (() => { try { return localStorage.getItem('ultron.mode'); } catch { return null; } })();
if (override === 'live' || override === 'mock') config.mode = override;

/** Absolute URL for an API path. */
export const apiUrl = (path) => `${config.apiBaseUrl}${config.apiPrefix}${path}`;

/** Bearer token storage (no-op in cookie/none modes). */
export const auth = {
  get token() { try { return localStorage.getItem(config.auth.tokenKey); } catch { return null; } },
  set token(v) { try { v ? localStorage.setItem(config.auth.tokenKey, v) : localStorage.removeItem(config.auth.tokenKey); } catch {} },
  clear() { this.token = null; },
  headers() {
    const h = { ...config.headers };
    if (config.auth.mode === 'bearer' && this.token) h.Authorization = `Bearer ${this.token}`;
    return h;
  },
  get credentials() { return config.auth.mode === 'cookie' ? 'include' : 'same-origin'; },
};
