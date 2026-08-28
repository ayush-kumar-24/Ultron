// The command bar — "What are you thinking about?" Shared by Overview and Chat.
// Text, voice, attachments (files/images/documents), action chips. Enter sends, Shift+Enter newlines.
import { h, icon, mount } from './dom.js';
import { bus, appState } from '../store.js';
import { navigate } from '../router.js';

const CHIPS = [
  { label: 'Ask Ultron', icon: 'spark', run: (bar) => bar.focus() },
  { label: 'Deep research', icon: 'research', run: (bar) => navigate('/research?new=1' + (bar.value() ? '&q=' + encodeURIComponent(bar.value()) : '')) },
  { label: 'Generate ideas', icon: 'bulb', run: (bar) => bar.prefill('Generate ideas for ') },
  { label: 'Solve problem', icon: 'zap', run: (bar) => bar.prefill('Help me solve: ') },
  { label: 'Plan my day', icon: 'sunrise', run: () => navigate('/tasks/plan') },
  { label: 'Search memory', icon: 'memory', run: (bar) => navigate('/memory' + (bar.value() ? '?q=' + encodeURIComponent(bar.value()) : '')) },
  { label: 'Create task', icon: 'tasks', run: (bar) => navigate('/tasks?new=1' + (bar.value() ? '&text=' + encodeURIComponent(bar.value()) : '')) },
];

export function CommandBar({ onSubmit, chips = true, placeholder = 'What are you thinking about?', compact, context }) {
  let attachments = [];
  const ta = h('textarea', { placeholder, rows: 1, 'aria-label': placeholder });
  const attachEl = h('div', { class: 'attach', style: { display: 'none' } });
  const fileInput = h('input', { type: 'file', multiple: true, style: { display: 'none' }, accept: 'image/*,.pdf,.doc,.docx,.md,.txt,.csv,.json,.py,.js,.ts' });
  const ctxChip = context ? h('span', { class: 'ctxchip' }, h('i'), 'Context · ' + context.label) : null;

  const bar = {
    el: null,
    focus: () => ta.focus(),
    value: () => ta.value.trim(),
    prefill: (t) => { ta.value = t; ta.focus(); autosize(); },
    clear: () => { ta.value = ''; attachments = []; renderAttach(); autosize(); },
  };
  const autosize = () => { ta.style.height = 'auto'; ta.style.height = Math.min(160, ta.scrollHeight) + 'px'; };
  const submit = () => { const v = ta.value.trim(); if (!v && !attachments.length) { ta.focus(); return; } onSubmit(v || `Look at ${attachments.map(a => a.name).join(', ')}`, { attachments: attachments.slice(), context: context || appState.get().context }); bar.clear(); };
  const renderAttach = () => { attachEl.style.display = attachments.length ? '' : 'none'; mount(attachEl, attachments.map((a, i) => h('span', null, icon(a.type?.startsWith('image') ? 'image' : 'file', 12), a.name, h('button', { 'aria-label': 'Remove', onClick: () => { attachments.splice(i, 1); renderAttach(); } }, icon('x', 11))))); };
  fileInput.onchange = () => { attachments.push(...[...fileInput.files].map(f => ({ name: f.name, type: f.type, size: f.size }))); fileInput.value = ''; renderAttach(); };
  ta.addEventListener('input', autosize);
  ta.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } });
  ta.addEventListener('paste', (e) => { const files = [...(e.clipboardData?.files || [])]; if (files.length) { attachments.push(...files.map(f => ({ name: f.name || 'pasted image', type: f.type, size: f.size }))); renderAttach(); } });

  bar.el = h('section', { class: 'command', 'aria-label': 'Ask Ultron', onDragover: (e) => { e.preventDefault(); bar.el.style.borderColor = 'var(--accent)'; }, onDragleave: () => bar.el.style.borderColor = '', onDrop: (e) => { e.preventDefault(); bar.el.style.borderColor = ''; attachments.push(...[...e.dataTransfer.files].map(f => ({ name: f.name, type: f.type, size: f.size }))); renderAttach(); } },
    ctxChip, ta, attachEl,
    h('div', { class: 'row' },
      chips ? CHIPS.map(c => h('button', { class: 'chip', onClick: () => c.run(bar) }, icon(c.icon), c.label)) : null,
      h('div', { class: 'tools' },
        h('button', { class: 'iconbtn', 'aria-label': 'Attach files, images or documents', title: 'Attach', onClick: () => fileInput.click() }, icon('clip')),
        h('button', { class: 'iconbtn', 'aria-label': 'Talk to Ultron', title: 'Voice (Alt+Space)', onClick: () => bus.emit('voice') }, icon('mic')),
        h('button', { class: 'send', 'aria-label': 'Send', onClick: submit }, icon('up')))),
    fileInput);
  if (compact) bar.el.classList.add('compact');
  return bar.el;
}
