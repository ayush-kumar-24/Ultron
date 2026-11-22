# ULTRON — frontend

The complete web frontend for Ultron: a personal AI operating layer. Dark, cinematic, calm.

Built as a **dependency-free ES-module SPA** — no framework, no bundler, no `node_modules`, no build step. It runs from any static file server, embeds cleanly in a PySide6 `QWebEngineView`, and pairs with a backend by changing one config file.

---

## Run it

```bash
python serve.py
```

Open **http://127.0.0.1:5173**. With no backend running it boots against a built-in demo backend, so every screen is fully clickable immediately.

Against your backend:

```bash
python serve.py --api http://127.0.0.1:8000
```

`--api` proxies `/api/*` to your server, so the browser sees one origin and you need no CORS setup while developing. Any static server works too (`python -m http.server`, nginx, or your backend serving this folder) — then point `config.js` at the API instead.

---

## Pairing with a backend

Everything lives in **`config.js`** — a plain script the backend can rewrite at deploy time.

```js
window.ULTRON_CONFIG = {
  mode: 'auto',                 // 'auto' | 'live' | 'mock'
  apiBaseUrl: '',               // '' = same origin
  apiPrefix: '/api',
  healthPath: '/system/health',
  eventsPath: '/events',        // SSE; null disables realtime
  auth: { mode: 'bearer', tokenKey: 'ultron.token', loginUrl: null },
  ...
};
```

- **`auto`** (default) probes `GET /api/system/health`. If it answers JSON, the app uses the real backend; otherwise it falls back to the demo backend so the UI is never dead. The chosen mode is on `<html data-backend>`, and a one-off toast says which one is running.
- **`live`** always uses the real backend. **`mock`** always uses the demo one.
- Runtime override without editing files: `localStorage.setItem('ultron.mode','live')`.

**The contract your backend implements is [`docs/API.md`](docs/API.md)** — every endpoint, payload shape, stream format and SSE event, with a suggested implementation order. Endpoints you have not built yet can 404: that page shows its error state with a Retry, and the rest of the app keeps working.

Auth: bearer token from `localStorage['ultron.token']`, or session cookies (`auth.mode: 'cookie'`). A `401` clears the token and redirects to `auth.loginUrl`, or shows "Session expired" if that is null.

---

## What is in here

```
index.html                 shell document; loads fonts, styles, config.js, then src/main.js
config.js                  runtime configuration (backend URL, auth, feature flags)
serve.py                   zero-dependency dev server, with optional --api proxy
manifest.webmanifest       installable-app metadata
favicon.svg
src/
  main.js                  boot: transport -> shell -> presence -> router -> realtime; shortcuts
  config.js                config accessor + auth token store
  router.js                hash router, lazy page modules, transitions, per-page cleanup
  store.js                 reactive store (appState) + event bus
  api/
    client.js              the one seam: REST + streaming + SSE, retries, timeouts, 401 handling,
                           and initTransport() which picks live vs demo
    errors.js              ApiError
    mock/db.js             demo data, persisted to localStorage (reset / wipe supported)
    mock/handlers.js       the whole /api surface in memory: routes, streaming, simulated events
  services/index.js        domain services. Pages import ONLY these, never the client
  ui/
    dom.js                 h() element builder, icon(), fmt, md()
    icons.js               stroke icon set
    components/index.js    Card, Button, Tabs, Modal, Drawer, Menu, toast, EmptyState, ErrorState,
                           Skeleton, Table, Sparkline, RingGauge, Bars, load(), ...
    commandbar.js          "What are you thinking about?" - text, voice, attachments, action chips
    core/presence.js       THE CORE: Ultron's orb, its life engine, states, docking, approvals
    shell/                 sidebar + topbar + bottom nav, command palette, notifications, voice
  pages/                   one module per route (contract: docs/PAGES.md)
  styles/                  tokens -> base -> shell -> components -> core -> pages
docs/API.md                backend contract
docs/PAGES.md              how to write or change a page
```

## Pages

`/overview` `/chat/:id?` `/mind` `/memory` `/knowledge/:id?` `/tasks/:view?` `/calendar/:view?`
`/automations/:id?` `/agents/:id?` `/research/:id?` `/projects/:id?` `/goals` `/insights` `/activity`
`/focus` `/settings/:section?` `/profile` `/search`

Every page has loading, empty and error states, and is responsive down to 375px (the sidebar becomes a bottom tab bar).

## Keyboard

`Ctrl/Cmd K` command palette - `/` palette - `Alt+Space` talk to Ultron - `Esc` close -
`g` then `o c m t k a r i s` to jump to a section.

## Design

Tokens live in `src/styles/tokens.css`. Monochrome first - colour is a signal (presence state, agent state, priority), never decoration. The wordmark is Syncopate; **the mark is the presence itself**: a mini orb in the sidebar, and the living orb docked into the Overview hero, Focus Mode and the voice overlay, otherwise resting in the corner.

The orb's motion is a smoothed "life engine" (`src/ui/core/presence.js`): breathing, drift, cursor-lean and occasional glances, all low-pass filtered so nothing twitches. Nine states - idle, listening, thinking, working, speaking, recording, approval, success, error.

## Embedding in the PySide6 shell

```python
view = QWebEngineView()
view.load(QUrl("http://127.0.0.1:8000/"))   # backend serves this folder
```

Set `config.js` to `mode: 'live'`, `apiBaseUrl: ''`, and `auth.mode: 'none'` for a local single-user desktop build.
