// Voice interface: LISTENING → THINKING → SPEAKING with a live waveform and transcript. Cinematic, minimal.
import { h, mount } from '../dom.js';
import { presence } from '../core/presence.js';
import { voiceService } from '../../services/index.js';
import { bus } from '../../store.js';

let el, canvas, stateEl, transcriptEl, dock, raf, level = 0, target = 0, mode = 'idle', resolveFn = null;

function ensure() {
  if (el) return;
  canvas = h('canvas', { width: 1040, height: 128, 'aria-hidden': 'true' });
  stateEl = h('div', { class: 'state' }, 'Listening');
  transcriptEl = h('div', { class: 'transcript dim' }, 'Say something…');
  dock = h('div', { class: 'dock' });
  el = h('div', { class: 'voice', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Voice' },
    h('button', { class: 'close', onClick: () => close(null) }, 'Stop · Esc'),
    dock, canvas, stateEl, transcriptEl,
    h('div', { class: 'row', style: { gap: '8px', marginTop: '6px' } }, h('button', { class: 'btn ghost sm', onClick: () => close(null) }, 'Cancel'), h('button', { class: 'btn sm', id: 'voiceSend', onClick: () => close(transcriptEl.textContent) }, 'Send')));
  document.body.append(el);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && el.classList.contains('on')) close(null); });
}

function draw() {
  const ctx = canvas.getContext('2d'), W = canvas.width, H = canvas.height, t = performance.now() / 1000;
  ctx.clearRect(0, 0, W, H);
  level += (target - level) * .12;
  const bars = 64, gap = 6, bw = (W - gap * (bars - 1)) / bars;
  for (let i = 0; i < bars; i++) {
    const env = Math.sin((i / bars) * Math.PI);
    const n = Math.sin(t * 9 + i * .7) * .5 + Math.sin(t * 5.3 + i * .31) * .3 + Math.sin(t * 13 + i * 1.9) * .2;
    const amp = mode === 'thinking' ? (.12 + .06 * Math.sin(t * 2 + i * .2)) : (.06 + level * env * (.55 + .45 * n));
    const hgt = Math.max(3, amp * H);
    ctx.fillStyle = mode === 'speaking' ? 'rgba(127,215,196,.85)' : mode === 'thinking' ? 'rgba(167,139,250,.7)' : 'rgba(237,239,243,.8)';
    ctx.fillRect(i * (bw + gap), H / 2 - hgt / 2, bw, hgt);
  }
  raf = requestAnimationFrame(draw);
}

function setMode(m, label) { mode = m; stateEl.textContent = label || m; presence.setState(m === 'idle' ? 'idle' : m); target = m === 'listening' ? .7 : m === 'speaking' ? .9 : .2; }

export function openVoice({ prompt } = {}) {
  ensure(); el.classList.add('on'); presence.dock(dock);
  transcriptEl.textContent = 'Say something…'; transcriptEl.classList.add('dim');
  setMode('listening', 'Listening'); cancelAnimationFrame(raf); draw();
  return new Promise(async (resolve) => {
    resolveFn = resolve;
    try {
      const r = await voiceService.transcribe(prompt, (ev) => { if (ev.type === 'partial') { transcriptEl.textContent = ev.text; transcriptEl.classList.remove('dim'); target = .5 + Math.random() * .5; } });
      if (!el.classList.contains('on')) return;
      setMode('thinking', 'Thinking');
      setTimeout(() => { if (el.classList.contains('on')) close(r.transcript); }, 500);
    } catch (e) { close(null); }
  });
}
export function close(transcript) {
  cancelAnimationFrame(raf); el.classList.remove('on'); setMode('idle', ''); presence.dock(null); bus.emit('voice:closed');
  const r = resolveFn; resolveFn = null; r?.(transcript && transcript !== 'Say something…' ? transcript : null);
}
