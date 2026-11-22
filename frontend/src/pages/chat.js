// Ultron Chat — the central intelligence interface. Streaming, tools, citations, effects, memory, tasks, context.
import { h, icon, fmt, md, mount, clear } from '../ui/dom.js';
import { Button, IconButton, EmptyState, Skeleton, Menu, toast, confirm, Modal, Input } from '../ui/components/index.js';
import { chatService, events } from '../services/index.js';
import { presence } from '../ui/core/presence.js';
import { appState, bus } from '../store.js';
import { navigate } from '../router.js';
import { CommandBar } from '../ui/commandbar.js';

export default async function chat(root, { params, query }) {
  let convId = params.id || null, conversations = [], messages = [], streaming = false;
  const railList = h('div', { class: 'rl' });
  const rail = h('div', { class: 'rail' }, h('div', { class: 'rh' }, Input({ placeholder: 'Search conversations', icon: 'search', onInput: (v) => renderRail(v) }), IconButton({ icon: 'plus', label: 'New conversation', square: true, onClick: newConversation })), railList);
  const title = h('h2', { class: 'truncate' }, 'Ultron');
  const msgs = h('div', { class: 'msgs', role: 'log', 'aria-live': 'polite' });
  const composerHost = h('div', { class: 'composer' });
  const thread = h('div', { class: 'thread' },
    h('div', { class: 'th' }, h('button', { class: 'iconbtn sm', 'aria-label': 'Conversations', onClick: () => wrap.classList.toggle('show-rail'), style: { display: 'none' }, id: 'railToggle' }, icon('list')), title, h('div', { class: 'spacer' }),
      IconButton({ icon: 'more', label: 'Conversation options', size: 'sm', square: true, onClick: (e) => convMenu(e.currentTarget) })),
    msgs, composerHost);
  const wrap = h('div', { class: 'chat' }, rail, thread);
  mount(root, wrap);
  if (matchMedia('(max-width:960px)').matches) { wrap.querySelector('#railToggle').style.display = ''; }
  mount(composerHost, CommandBar({ onSubmit: send, chips: false, placeholder: 'Message Ultron…', compact: true }));

  await loadRail();
  if (!convId) {
    if (query.ask) await newConversation(query.ask);
    else if (conversations[0] && !query.new) { convId = conversations[0].id; await loadThread(); }
    else renderEmptyThread();
  } else await loadThread();

  /* ---------- rail ---------- */
  async function loadRail() { try { conversations = await chatService.list(); } catch { conversations = []; } renderRail(); }
  function renderRail(filter = '') {
    const f = filter.toLowerCase();
    const items = conversations.filter(c => !f || c.title.toLowerCase().includes(f));
    mount(railList, items.length ? items.map(c => h('div', { class: ['conv', c.id === convId && 'on'], role: 'button', tabindex: 0, onClick: () => { navigate('/chat/' + c.id); wrap.classList.remove('show-rail'); } },
      h('div', { class: 't' }, c.pinned ? icon('pin', 11) : null, ' ', c.title), h('div', { class: 's' }, fmt.relShort(c.updatedAt))))
      : h('p', { class: 'faint', style: { padding: '14px', fontSize: '12.5px' } }, f ? 'No matches.' : 'No conversations yet.'));
  }

  /* ---------- thread ---------- */
  async function loadThread() {
    mount(msgs, Skeleton({ lines: 5 }));
    try {
      const [conv, list] = await Promise.all([chatService.get(convId), chatService.messages(convId)]);
      title.textContent = conv.title; messages = list;
      if (conv.projectId) appState.set({ context: { type: 'project', id: conv.projectId, label: conv.title.split(' ')[0] } });
      mount(msgs, messages.map(renderMessage)); scrollDown();
      renderRail();
      if (query.ask) { const q = query.ask; query.ask = null; history.replaceState(null, '', '#/chat/' + convId); send(q); }
    } catch (e) { console.error('loadThread', e); mount(msgs, EmptyState({ icon: 'chat', title: 'Conversation not found.', body: 'It may have been deleted.', action: { label: 'New conversation', onClick: () => newConversation() } })); }
  }
  function renderEmptyThread() {
    title.textContent = 'Ultron';
    const sugg = ['Plan my day', 'What\'s left on Ultron?', 'Remind me tomorrow at 9 AM to review the roadmap', 'Research local wake-word engines', 'Remember that I prefer local models', 'How much did I work this week?'];
    mount(msgs, h('div', { class: 'empty-thread' }, h('div', { class: 'mini-orb', style: { width: '40px', height: '40px' } }), h('h2', null, 'What are we working on?'), h('p', { class: 'muted' }, 'Ultron remembers what matters and can act on your computer.'), h('div', { class: 'sugg' }, sugg.map(s => h('button', { class: 'chip', onClick: () => send(s) }, s)))));
  }
  async function newConversation(firstMessage) {
    messages = [];
    try {
      const c = await chatService.create({ title: firstMessage ? firstMessage.slice(0, 48) : 'New conversation', projectId: appState.get().context?.type === 'project' ? appState.get().context.id : null });
      conversations.unshift(c); convId = c.id; title.textContent = c.title; history.replaceState(null, '', '#/chat/' + c.id); renderRail();
    } catch {
      // Backend may create the conversation from the first streamed message instead.
      convId = null; title.textContent = firstMessage ? firstMessage.slice(0, 48) : 'Ultron';
    }
    if (firstMessage) { clear(msgs); send(firstMessage); } else { renderEmptyThread(); }
  }
  function convMenu(anchor) {
    if (!convId) return;
    const c = conversations.find(x => x.id === convId);
    Menu(anchor, [
      { label: c?.pinned ? 'Unpin' : 'Pin', icon: 'pin', onClick: async () => { await chatService.update(convId, { pinned: !c.pinned }); await loadRail(); } },
      { label: 'Rename', icon: 'edit', onClick: () => { let v = c.title; Modal({ title: 'Rename conversation', body: Input({ value: c.title, onInput: (x) => v = x, onEnter: async () => { await chatService.update(convId, { title: v }); title.textContent = v; loadRail(); document.querySelector('.modal-bg')?.remove(); } }), actions: [{ label: 'Cancel', variant: 'ghost' }, { label: 'Save', variant: 'primary', onClick: async () => { await chatService.update(convId, { title: v }); title.textContent = v; loadRail(); } }] }); } },
      { label: 'Open project', icon: 'projects', onClick: () => c?.projectId ? navigate('/projects/' + c.projectId) : toast('No project linked', { tone: 'info' }) },
      '-',
      { label: 'Delete conversation', icon: 'trash', danger: true, onClick: async () => { if (await confirm({ title: 'Delete conversation?', message: 'Messages are removed permanently. Memories created from them stay.', confirmLabel: 'Delete', danger: true })) { await chatService.remove(convId); convId = null; await loadRail(); renderEmptyThread(); toast('Conversation deleted'); } } },
    ]);
  }

  /* ---------- messages ---------- */
  function renderMessage(m) {
    const body = h('div', { class: 'body' });
    const el = h('div', { class: ['msg', m.role], 'data-id': m.id }, h('div', { class: 'who' }, m.role === 'user' ? (appState.get().user?.initials || 'AY') : h('div', { class: 'mini-orb', style: { width: '18px', height: '18px', animation: 'none' } })), body);
    fillBody(body, m);
    return el;
  }
  function fillBody(body, m, { live } = {}) {
    clear(body);
    if (m.tools?.length) body.append(ToolsBox(m.tools, live));
    const text = h('div', { class: 'md', html: md(m.text || '') });
    if (live) text.append(h('span', { class: 'typing' }));
    body.append(text);
    if (m.citations?.length) body.append(h('div', { class: 'cites' }, m.citations.map(c => h('span', { title: c.source }, h('b', null, c.n), c.title))));
    if (m.reminderCreated) body.append(h('div', { class: 'effect' }, icon('checkcircle'), h('span', null, 'Reminder created'), h('span', { class: 'k' }, (m.reminderCreated.recurrence ? m.reminderCreated.recurrence + ' · ' : '') + fmt.date(m.reminderCreated.at) + ' · ' + fmt.time(m.reminderCreated.at))));
    if (m.taskCreated) body.append(h('div', { class: 'effect', style: { cursor: 'pointer' }, onClick: () => navigate('/tasks') }, icon('checkcircle'), h('span', null, 'Task created'), h('span', { class: 'k' }, m.taskCreated.title)));
    if (m.memoryCreated) body.append(h('div', { class: 'effect', style: { cursor: 'pointer' }, onClick: () => navigate('/memory') }, icon('memory'), h('span', null, 'Saved to memory'), h('span', { class: 'k truncate', style: { maxWidth: '320px' } }, m.memoryCreated)));
    if (m.researchStarted) body.append(h('div', { class: 'effect', style: { cursor: 'pointer' }, onClick: () => navigate('/research/' + m.researchStarted.id) }, icon('research'), h('span', null, 'Research running'), h('span', { class: 'k' }, 'Open')));
    if (m.automationCreated) body.append(h('div', { class: 'effect', style: { cursor: 'pointer' }, onClick: () => navigate('/automations') }, icon('automations'), h('span', null, 'Automation created'), h('span', { class: 'k' }, m.automationCreated.trigger)));
    if (!live) body.append(h('div', { class: 'meta' }, h('span', { class: 'when' }, fmt.time(m.at)),
      IconButton({ icon: 'copy', label: 'Copy', onClick: () => { navigator.clipboard?.writeText(m.text); toast('Copied'); } }),
      m.role === 'assistant' && IconButton({ icon: 'memory', label: 'Save to memory', onClick: async () => { await chatService.saveToMemory(m.id, m.text); toast('Saved to memory', { action: { label: 'Open', onClick: () => navigate('/memory') } }); } }),
      m.role === 'assistant' && IconButton({ icon: 'tasks', label: 'Create task from message', onClick: async () => { const t = await chatService.createTask(m.id, m.text.replace(/[*`#]/g, '').split('\n')[0], appState.get().context?.id); toast('Task created: ' + t.title, { action: { label: 'Open', onClick: () => navigate('/tasks') } }); } }),
      m.role === 'assistant' && IconButton({ icon: 'refresh', label: 'Regenerate', onClick: () => { const prev = [...messages].reverse().find(x => x.role === 'user'); if (prev) send(prev.text, { regenerate: m.id }); } }),
      m.role === 'user' && IconButton({ icon: 'edit', label: 'Edit and resend', onClick: () => { composerHost.querySelector('textarea').value = m.text; composerHost.querySelector('textarea').focus(); } })));
  }
  function ToolsBox(tools, live) {
    const box = h('div', { class: ['tools-box', live && 'open'] });
    const running = tools.some(t => t.status === 'running');
    const head = h('button', { onClick: () => box.classList.toggle('open'), 'aria-expanded': live ? 'true' : 'false' }, icon('chev'), running ? `Working · ${tools.filter(t => t.status === 'done').length}/${tools.length}` : `${tools.length} step${tools.length === 1 ? '' : 's'} · ${Math.round(tools.reduce((a, t) => a + (t.ms || 0), 0) / 1000 * 10) / 10}s`);
    box.append(head, h('div', { class: 'tl' }, tools.map(t => h('div', { class: 'tool-row' }, h('span', { class: 'dot', 'data-s': t.status === 'done' ? 'ok' : t.status }), h('div', null, t.name, t.detail && h('div', { class: 'd' }, t.detail)), h('span', { class: 'ms' }, t.status === 'done' && t.ms ? (t.ms >= 1000 ? (t.ms / 1000).toFixed(1) + 's' : t.ms + 'ms') : '')))));
    return box;
  }
  function scrollDown() { msgs.scrollTop = msgs.scrollHeight; }

  /* ---------- send (streaming) ---------- */
  async function send(text, { regenerate } = {}) {
    if (streaming || !text) return;
    streaming = true;
    if (!convId) {
      // Best effort: some backends create the conversation from the stream call instead.
      try {
        const c = await chatService.create({ title: text.slice(0, 48), projectId: appState.get().context?.type === 'project' ? appState.get().context.id : null });
        conversations.unshift(c); convId = c.id; history.replaceState(null, '', '#/chat/' + c.id); title.textContent = c.title; renderRail();
      } catch { title.textContent = text.slice(0, 48); }
    }
    if (msgs.querySelector('.empty-thread')) clear(msgs);
    if (regenerate) msgs.querySelector(`[data-id="${regenerate}"]`)?.remove();
    const live = { id: 'live', role: 'assistant', text: '', tools: [] };
    let liveEl = null, liveBody = null;
    const context = appState.get().context ? { projectId: appState.get().context.type === 'project' ? appState.get().context.id : null, documentId: appState.get().context.type === 'document' ? appState.get().context.id : null, label: appState.get().context.label } : null;
    try {
      const result = await chatService.send(convId, text, context, (ev) => {
        if (ev.type === 'user') { if (!regenerate) { messages.push(ev.payload); msgs.append(renderMessage(ev.payload)); } liveEl = renderMessage(live); liveBody = liveEl.querySelector('.body'); fillBody(liveBody, live, { live: true }); msgs.append(liveEl); scrollDown(); }
        else if (ev.type === 'state') { presence.setState(ev.state); if (liveBody && ev.state === 'thinking') mount(liveBody, h('span', { class: 'ai-state' }, h('i'), 'Thinking…')); }
        else if (ev.type === 'tool') { const i = live.tools.findIndex(t => t.name === ev.tool.name); if (i >= 0) live.tools[i] = ev.tool; else live.tools.push(ev.tool); fillBody(liveBody, live, { live: true }); scrollDown(); }
        else if (ev.type === 'token') { live.text += ev.text; const t = liveBody.querySelector('.md'); if (t) { t.innerHTML = md(live.text); t.append(h('span', { class: 'typing' })); } else fillBody(liveBody, live, { live: true }); scrollDown(); }
      });
      const m = result.message; messages.push(m);
      if (liveEl) { liveEl.dataset.id = m.id; fillBody(liveBody, m); } else msgs.append(renderMessage(m));
      if (result.conversation) {
        if (!convId) { convId = result.conversation.id; conversations.unshift(result.conversation); history.replaceState(null, '', '#/chat/' + convId); }
        title.textContent = result.conversation.title;
        const c = conversations.find(x => x.id === convId); if (c) { c.title = result.conversation.title; c.updatedAt = result.conversation.updatedAt; }
        renderRail();
      }
      presence.setState(m.taskCreated || m.reminderCreated || m.memoryCreated ? 'success' : 'idle');
      scrollDown();
    } catch (err) {
      presence.setState('error', 'Couldn\'t reach Ultron');
      if (liveBody) mount(liveBody, h('div', { class: 'error', style: { padding: '12px 14px' } }, h('div', { class: 'ic' }, icon('alert')), h('div', null, h('h3', null, 'Ultron couldn\'t answer'), h('p', { class: 'muted', style: { fontSize: '12.5px' } }, err.message || 'The model did not respond.'), Button({ label: 'Retry', icon: 'refresh', size: 'sm', onClick: () => { liveEl.remove(); send(text); } }))));
      else toast(err.message || 'Ultron could not answer', { tone: 'bad', action: { label: 'Retry', onClick: () => send(text) } });
    } finally { streaming = false; }
  }

  const offAsk = bus.on('ask', (q) => { if (appState.get().route.name === 'chat' && q) send(q); });
  return () => { offAsk(); if (appState.get().route.name !== 'chat') appState.set({ context: null }); };
}
