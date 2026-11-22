// Minimal reactive store. Pages subscribe to slices; the shell subscribes to global state.
export function createStore(initial = {}) {
  let state = { ...initial };
  const subs = new Set();
  return {
    get: () => state,
    set(patch) {
      const next = typeof patch === 'function' ? patch(state) : patch;
      const prev = state;
      state = { ...state, ...next };
      subs.forEach(fn => fn(state, prev));
    },
    subscribe(fn, keys) {
      const wrapped = keys ? (s, p) => { if (keys.some(k => s[k] !== p[k])) fn(s, p); } : fn;
      subs.add(wrapped);
      return () => subs.delete(wrapped);
    },
  };
}

/** Global app state (UI-level only — domain data lives behind services). */
export const appState = createStore({
  route: { path: '/overview', params: {}, query: {} },
  user: null,
  collapsed: false,
  unread: 0,
  agents: [],
  context: null,          // smart context: { type:'project'|'document'|'task', id, label }
  coreState: 'idle',
  focus: null,            // { task, startedAt, paused }
  online: true,
});

/** Tiny event emitter used for app-wide signals (shell ↔ pages). */
export function createEmitter() {
  const map = new Map();
  return {
    on(ev, fn) { if (!map.has(ev)) map.set(ev, new Set()); map.get(ev).add(fn); return () => map.get(ev)?.delete(fn); },
    off(ev, fn) { map.get(ev)?.delete(fn); },
    emit(ev, payload) { map.get(ev)?.forEach(fn => { try { fn(payload); } catch (e) { console.error(e); } }); map.get('*')?.forEach(fn => fn(ev, payload)); },
  };
}
export const bus = createEmitter();
