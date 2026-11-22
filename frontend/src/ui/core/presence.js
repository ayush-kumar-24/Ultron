// THE CORE — ULTRON's presence. The approved V3 orb: one light, many behaviours, smoothed life engine.
// API: presence.el, presence.setState(key, line?), presence.dock(target|null), presence.state, presence.onClick(fn)
import { h } from '../dom.js';
import { appState, bus } from '../../store.js';

export const STATES = {
  idle:      { c: '#8f96a3', line: 'Ready',                 drift: 4,   speed: .16, base: .30, range: .09, breath: .08, ring: .35, glance: true, lean: 1 },
  listening: { c: '#6aa6f8', line: 'Listening…',            drift: 2.5, speed: .5,  base: .45, range: .3,  breath: .35, ring: .7,  voice: true,  lean: 1.5 },
  thinking:  { c: '#a78bfa', line: 'Thinking…',             drift: 12,  speed: .4,  base: .40, range: .13, breath: .3,  ring: .5,  orbit: true,  lean: .3 },
  working:   { c: '#f0a35e', line: 'Working…',              drift: 3,   speed: .45, base: .42, range: .12, breath: .6,  ring: .9,  ringSpd: 80,  lean: .4 },
  speaking:  { c: '#7fd7c4', line: 'Speaking…',             drift: 2.5, speed: .8,  base: .45, range: .35, breath: .45, ring: .55, voice: true,  syll: true, lean: 1 },
  recording: { c: '#f87171', line: 'Recording',             drift: 3,   speed: .2,  base: .32, range: .09, breath: .12, ring: .4,  blink: true,  lean: .8 },
  approval:  { c: '#eac35b', line: 'Needs your permission', drift: 1,   speed: .3,  base: .5,  range: .28, breath: .4,  ring: .8,  hold: true,   lean: 1.8 },
  success:   { c: '#5ec98f', line: 'Done',                  drift: 3,   speed: .15, base: .34, range: .07, breath: .08, ring: .45, bloom: true,  lean: .8 },
  error:     { c: '#e0655f', line: 'Something went wrong',  drift: 1,   speed: .1,  base: .24, range: .04, breath: .04, ring: .25, lean: .2 },
};

export function createPresence() {
  const line = h('span', null, 'Ready');
  const allow = h('button', { 'aria-label': 'Allow' }, '✓'), deny = h('button', { 'aria-label': 'Deny' }, '✕');
  const orb = h('div', { class: 'orb', role: 'button', tabindex: 0, 'aria-label': 'Ultron' }, h('div', { class: 'halo' }), h('div', { class: 'ring' }), h('div', { class: 'light' }), h('div', { class: 'rec-dot' }));
  const el = h('div', { class: 'core', id: 'core', 'data-state': 'idle' }, orb, h('div', { class: 'ctag' }, h('i'), line, h('span', { class: 'acts' }, allow, deny)));

  let S = STATES.idle, state = 'idle', stateT = 0, successTimer = null, clickFn = null, approvalResolve = null;
  const api = {
    el, orb,
    get state() { return state; },
    setState(k, text) {
      if (!STATES[k]) k = 'idle';
      S = STATES[k]; state = k; stateT = 0; clearTimeout(successTimer);
      el.dataset.state = k; el.style.setProperty('--sc', S.c);
      line.textContent = text || S.line;
      el.classList.toggle('open', k !== 'idle');
      appState.set({ coreState: k }); bus.emit('core', { state: k, line: line.textContent });
      if (k === 'success') successTimer = setTimeout(() => { if (state === 'success') api.setState('idle'); }, 3200);
      if (k === 'error') successTimer = setTimeout(() => { if (state === 'error') api.setState('idle'); }, 6000);
    },
    setLine(text) { line.textContent = text; },
    /** Ask the user for permission through the presence itself. Resolves true/false. */
    approve(question) { return new Promise(res => { approvalResolve = res; api.setState('approval', question); }); },
    dock(target, cls = 'hero') {
      const t = target || document.body;
      if (el.parentElement !== t) t.appendChild(el);
      el.classList.toggle('hero', t !== document.body);
    },
    onClick(fn) { clickFn = fn; },
  };
  allow.onclick = (e) => { e.stopPropagation(); approvalResolve?.(true); approvalResolve = null; api.setState('working'); };
  deny.onclick = (e) => { e.stopPropagation(); approvalResolve?.(false); approvalResolve = null; api.setState('idle'); };
  orb.onclick = () => clickFn?.(state);
  orb.onkeydown = (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); clickFn?.(state); } };

  /* ---- life engine (smoothed) ---- */
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let t = 0, last = performance.now(), mx = 0, my = 0, leanX = 0, leanY = 0, glanceX = 0, glanceY = 0, gX = 0, gY = 0, nextGlance = 3, env = 0, envTgt = 0, nextBurst = 0, rot = 0;
  const out = { lx: 0, ly: 0, li: .3, ls: 1, ro: .35, blink: 0 };
  const lp = (c, tg, k, dt) => c + (tg - c) * Math.min(1, k * dt);
  const n1 = (x) => Math.sin(x) * .55 + Math.sin(x * 1.73 + 1.3) * .3 + Math.sin(x * 2.61 + 4.1) * .15;
  document.addEventListener('mousemove', (e) => { const r = orb.getBoundingClientRect(); const dx = e.clientX - (r.left + r.width / 2), dy = e.clientY - (r.top + r.height / 2); const d = Math.max(60, Math.hypot(dx, dy)); const near = Math.max(0, 1 - d / 520); mx = dx / d * near; my = dy / d * near; }, { passive: true });
  let visible = true; document.addEventListener('visibilitychange', () => { visible = !document.hidden; if (visible) { last = performance.now(); requestAnimationFrame(frame); } });
  function frame(now) {
    if (!visible) return;
    const dt = Math.min(.05, (now - last) / 1000); last = now; t += dt; stateT += dt;
    leanX = lp(leanX, mx * 6 * (S.lean || 1), 2.2, dt); leanY = lp(leanY, my * 6 * (S.lean || 1), 2.2, dt);
    if (S.glance) { nextGlance -= dt; if (nextGlance <= 0) { gX = (Math.random() * 2 - 1) * 8; gY = (Math.random() * 2 - 1) * 6; nextGlance = 4 + Math.random() * 5; setTimeout(() => { gX = 0; gY = 0; }, 800 + Math.random() * 600); } } else { gX = 0; gY = 0; }
    glanceX = lp(glanceX, gX, 3, dt); glanceY = lp(glanceY, gY, 3, dt);
    if (S.voice) { nextBurst -= dt; if (nextBurst <= 0) { envTgt = Math.random() < (S.syll ? .7 : .55) ? .35 + Math.random() * .5 : .04; nextBurst = (S.syll ? .18 : .3) + Math.random() * (S.syll ? .3 : .7); } env = lp(env, envTgt, envTgt > env ? 6 : 3, dt); } else env = lp(env, 0, 3, dt);
    let lx, ly; if (S.orbit) { const a = t * (1.1 + n1(t * .5) * .3); lx = Math.cos(a) * 14; ly = Math.sin(a) * 11; } else { lx = n1(t * S.speed) * S.drift; ly = n1(t * S.speed + 7.7) * S.drift; }
    lx += leanX + glanceX; ly += leanY + glanceY;
    let li = S.base + n1(t * S.breath * 5) * S.range * .5 + Math.sin(t * S.breath * 2.2) * S.range * .5 + env * .4;
    if (S.hold) li = S.base + Math.sin(t * 2.4) * .2;
    if (S.bloom) li = Math.max(li, .9 * Math.exp(-stateT * 1.1));
    li = Math.max(.06, Math.min(1, li));
    const ls = 1 + n1(t * S.breath * 3.5 + 2) * .04 + env * .07;
    rot += dt * (S.ringSpd || (16 + n1(t * .3) * 5));
    const blink = S.blink ? (.4 + .6 * Math.max(0, Math.sin(t * 2.2))) : 0;
    const oy = Math.sin(t * .6) * 1.4 + Math.sin(t * .23 + 2) * .7;
    out.lx = lp(out.lx, lx, 6, dt); out.ly = lp(out.ly, ly, 6, dt); out.li = lp(out.li, li, 5, dt); out.ls = lp(out.ls, ls, 5, dt); out.ro = lp(out.ro, S.ring + env * .15, 4, dt); out.blink = lp(out.blink, blink, 8, dt);
    const st = el.style;
    st.setProperty('--lx', out.lx.toFixed(2)); st.setProperty('--ly', out.ly.toFixed(2)); st.setProperty('--li', out.li.toFixed(3)); st.setProperty('--ls', out.ls.toFixed(3)); st.setProperty('--ro', out.ro.toFixed(3)); st.setProperty('--rot', (rot % 360).toFixed(1)); st.setProperty('--oy', oy.toFixed(2) + 'px'); st.setProperty('--blink', out.blink.toFixed(2));
    requestAnimationFrame(frame);
  }
  if (!reduced) requestAnimationFrame(frame); else el.style.setProperty('--li', '.35');
  api.setState('idle');
  return api;
}

/** Singleton used by the shell and pages. */
export const presence = createPresence();

/** Convenience: run a scripted turn through the presence (thinking → working → speaking → idle). */
export async function runTurn(steps = [['thinking', 900], ['working', 1200], ['speaking', 2200]]) {
  for (const [k, ms, text] of steps) { presence.setState(k, text); await new Promise(r => setTimeout(r, ms)); }
  presence.setState('idle');
}
