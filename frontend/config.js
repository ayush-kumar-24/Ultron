// ULTRON frontend runtime configuration.
// Loaded as a plain script BEFORE the app, so a backend can rewrite/inject it at deploy time
// without rebuilding anything (there is no build step).
//
//   mode: 'live'  → talk to a real backend at apiBaseUrl
//         'mock'  → run the built-in in-memory backend (demo data, no server needed)
//         'auto'  → probe `${apiBaseUrl}${healthPath}`; use live if it answers, otherwise mock
//
// Everything here can also be overridden at runtime from the browser console:
//   localStorage.setItem('ultron.mode', 'live'); location.reload();
window.ULTRON_CONFIG = {
  mode: 'live',

  // Where the backend lives. '' = same origin (recommended when the backend serves this folder).
  // Examples: 'http://127.0.0.1:8000', 'https://api.ultron.local'
  apiBaseUrl: 'http://127.0.0.1:8000',

  // Path prefix for REST + streaming endpoints, appended to apiBaseUrl.
  apiPrefix: '/api',

  // Health probe used by mode:'auto'.
  healthPath: '/system/health',

  // Server-sent events endpoint for realtime (agent status, automations, notifications…).
  // Set to null to disable realtime; the UI degrades gracefully.
  eventsPath: null,

  auth: {
    // 'bearer'  → Authorization: Bearer <token>, token read from localStorage[tokenKey]
    // 'cookie'  → rely on session cookies (sends credentials: 'include')
    // 'none'    → no auth headers (local single-user desktop mode)
    mode: 'none',
    tokenKey: 'ultron.token',
    // Where to send the user when the backend answers 401. null = show an inline notice instead.
    loginUrl: null,
  },

  // Extra headers sent with every request (e.g. a desktop-shell shared secret).
  headers: {},

  // Network behaviour
  requestTimeoutMs: 30000,
  retry: { attempts: 2, backoffMs: 400 },   // GETs only; never retries writes

  // Feature flags the backend can turn off without touching the UI code.
  features: { voice: true, recording: true, mind: true, research: true, agents: true, automations: true },

  // Shown in Settings → About.
  appName: 'ULTRON',
  version: '1.0.0',
};
