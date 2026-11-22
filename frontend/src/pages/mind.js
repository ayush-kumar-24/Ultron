// Mind — the interactive knowledge graph. Canvas force layout; zoom, pan, search, filter, expand/collapse, node details.
import { h, icon, mount, fmt } from '../ui/dom.js';
import { Input, IconButton, Chip, Button, toast } from '../ui/components/index.js';
import { projectService, memoryService, knowledgeService, taskService, goalService } from '../services/index.js';
import { navigate } from '../router.js';
import { appState } from '../store.js';

const KINDS = {
  root: { c: '#EDEFF3', r: 22 }, group: { c: '#9CC4FF', r: 12 }, project: { c: '#A78BFA', r: 9 }, person: { c: '#7FD7C4', r: 7 },
  knowledge: { c: '#F0A35E', r: 7 }, goal: { c: '#5EC98F', r: 7 }, task: { c: '#8B93A1', r: 5 }, memory: { c: '#EAC35B', r: 6 }, concept: { c: '#6AA6F8', r: 6 },
};

export default async function mind(root) {
  const canvas = h('canvas');
  const detail = h('div', { class: 'detail', style: { display: 'none' } });
  const search = Input({ placeholder: 'Search the graph…', icon: 'search', onInput: (v) => { query = v.toLowerCase(); draw(); } });
  const filters = h('div', { class: 'chips' });
  const wrap = h('div', { class: 'mind' }, canvas,
    h('div', { class: 'hud' }, search, filters, h('div', { class: 'spacer' }), Button({ label: 'Expand all', size: 'sm', variant: 'ghost', onClick: () => { nodes.forEach(n => n.collapsed = false); rebuild(); } }), Button({ label: 'Collapse', size: 'sm', variant: 'ghost', onClick: () => { nodes.filter(n => n.kind === 'group').forEach(n => n.collapsed = true); rebuild(); } })),
    detail,
    h('div', { class: 'legend' }, Object.entries(KINDS).filter(([k]) => k !== 'root').map(([k, v]) => h('span', { style: { '--c': v.c } }, k))),
    h('div', { class: 'zoom' }, IconButton({ icon: 'zoomin', label: 'Zoom in', square: true, onClick: () => zoomBy(1.25) }), IconButton({ icon: 'zoomout', label: 'Zoom out', square: true, onClick: () => zoomBy(.8) }), IconButton({ icon: 'focus', label: 'Reset view', square: true, onClick: () => { tx = 0; ty = 0; scale = 1; draw(); } })));
  mount(root, h('div', { class: 'page-h' }, h('div', null, h('h1', null, 'Mind'), h('p', null, 'Everything Ultron knows, as a map. Drag to pan, scroll to zoom, click a node to open it.'))), wrap);

  /* ---------- data → graph ---------- */
  let nodes = [], edges = [], visible = [], vEdges = [], query = '', hidden = new Set();
  const [projects, memories, knowledge, tasks, goals] = await Promise.all([projectService.list(), memoryService.list({}), knowledgeService.list({}), taskService.list({}), goalService.list()]).catch(() => [[], [], [], [], []]);
  const add = (id, kind, label, data, parent) => { const n = { id, kind, label, data, parent, x: (Math.random() - .5) * 300, y: (Math.random() - .5) * 300, vx: 0, vy: 0, collapsed: false }; nodes.push(n); if (parent) edges.push([parent, id]); return n; };
  add('root', 'root', 'ULTRON', { desc: 'Your personal intelligence layer. Everything below is connected through it.' });
  const groups = [['user', 'You'], ['projects', 'Projects'], ['people', 'People'], ['knowledge', 'Knowledge'], ['goals', 'Goals'], ['tasks', 'Tasks'], ['memories', 'Memories'], ['concepts', 'Concepts']];
  groups.forEach(([id, label]) => add('g_' + id, 'group', label, { desc: `${label} Ultron is tracking.` }, 'root'));
  add('me', 'person', appState.get().user?.name || 'Ayush', { desc: 'Founder, GoXL. Builds Ultron. Prefers concise technical answers and local models.' }, 'g_user');
  projects.forEach(p => add(p.id, 'project', p.name, { desc: p.description, route: '/projects/' + p.id, progress: p.progress }, 'g_projects'));
  memories.filter(m => m.category === 'people').forEach(m => add(m.id, 'person', m.text.split(' ')[0].replace(/[^A-Za-z]/g, ''), { desc: m.text, route: '/memory?category=people' }, 'g_people'));
  knowledge.slice(0, 8).forEach(k => add(k.id, 'knowledge', k.title, { desc: k.summary || 'Not analysed yet.', route: '/knowledge/' + k.id }, 'g_knowledge'));
  goals.forEach(g => add(g.id, 'goal', g.title, { desc: g.objective, route: '/goals', progress: g.progress }, g.projectId && nodes.some(n => n.id === g.projectId) ? g.projectId : 'g_goals'));
  tasks.filter(t => t.status !== 'done').slice(0, 9).forEach(t => add(t.id, 'task', t.title, { desc: `${t.priority} priority${t.due ? ' · due ' + fmt.date(t.due) : ''}`, route: '/tasks' }, t.projectId && nodes.some(n => n.id === t.projectId) ? t.projectId : 'g_tasks'));
  memories.filter(m => m.category !== 'people').slice(0, 8).forEach(m => add(m.id, 'memory', m.text.slice(0, 28) + (m.text.length > 28 ? '…' : ''), { desc: m.text, route: '/memory' }, 'g_memories'));
  ['Local-first', 'Verification', 'Agent orchestration', 'Workflow memory', 'Fast path'].forEach((c, i) => add('c_' + i, 'concept', c, { desc: 'A principle from the Ultron Product Vision.', route: '/knowledge' }, 'g_concepts'));
  // cross-links: goals ↔ concepts, knowledge ↔ projects
  if (nodes.some(n => n.id === 'g_ultron')) edges.push(['g_ultron', 'c_2'], ['g_ultron', 'c_1']);
  if (nodes.some(n => n.id === 'p_ultron') && nodes.some(n => n.id === 'k_2')) edges.push(['p_ultron', 'k_2'], ['p_ultron', 'k_3']);
  if (nodes.some(n => n.id === 'p_goxl') && nodes.some(n => n.id === 'k_6')) edges.push(['p_goxl', 'k_6']);
  nodes.filter(n => n.kind === 'group' && ['g_tasks', 'g_memories', 'g_concepts'].includes(n.id)).forEach(n => n.collapsed = true);

  mount(filters, Object.keys(KINDS).filter(k => !['root', 'group', 'person'].includes(k)).map(k => { const ch = Chip({ label: k, active: true, onClick: () => { if (hidden.has(k)) hidden.delete(k); else hidden.add(k); ch.classList.toggle('on', !hidden.has(k)); rebuild(); } }); return ch; }));

  function rebuild() {
    const byId = Object.fromEntries(nodes.map(n => [n.id, n]));
    const isVisible = (n) => { if (hidden.has(n.kind)) return false; let p = n.parent; while (p) { const pn = byId[p]; if (!pn || pn.collapsed) return false; p = pn.parent; } return true; };
    visible = nodes.filter(isVisible);
    const vis = new Set(visible.map(n => n.id));
    vEdges = edges.filter(([a, b]) => vis.has(a) && vis.has(b)).map(([a, b]) => [byId[a], byId[b]]);
    alpha = 1;
  }

  /* ---------- physics ---------- */
  let alpha = 1, W = 0, H = 0, dpr = devicePixelRatio || 1, tx = 0, ty = 0, scale = 1, hover = null, selected = null, dragging = null, panning = null, raf = 0;
  function step() {
    if (alpha < .003) return;
    alpha *= .985;
    const k = alpha;
    for (const n of visible) {
      n.vx += (0 - n.x) * .0015 * (n.kind === 'root' ? 10 : 1) * k; n.vy += (0 - n.y) * .0015 * (n.kind === 'root' ? 10 : 1) * k;
      for (const m of visible) { if (m === n) continue; let dx = n.x - m.x, dy = n.y - m.y; let d2 = dx * dx + dy * dy + 0.01; const d = Math.sqrt(d2); const rep = Math.min(40, 2600 / d2) * k; n.vx += dx / d * rep; n.vy += dy / d * rep; }
    }
    for (const [a, b] of vEdges) { const dx = b.x - a.x, dy = b.y - a.y, d = Math.sqrt(dx * dx + dy * dy) + .01; const target = a.kind === 'root' ? 150 : b.kind === 'group' ? 110 : 70; const f = (d - target) * .02 * k; a.vx += dx / d * f; a.vy += dy / d * f; b.vx -= dx / d * f; b.vy -= dy / d * f; }
    for (const n of visible) { if (n === dragging) { n.vx = n.vy = 0; continue; } n.vx *= .82; n.vy *= .82; n.x += n.vx; n.y += n.vy; }
    const rootN = visible.find(n => n.kind === 'root'); if (rootN && rootN !== dragging) { rootN.x *= .9; rootN.y *= .9; }
  }

  /* ---------- drawing ---------- */
  const ctx = canvas.getContext('2d');
  function resize() { const r = wrap.getBoundingClientRect(); W = r.width; H = r.height; canvas.width = W * dpr; canvas.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0); draw(); }
  const toScreen = (n) => [W / 2 + (n.x + tx) * scale, H / 2 + (n.y + ty) * scale];
  function draw() {
    ctx.clearRect(0, 0, W, H);
    ctx.lineWidth = 1;
    for (const [a, b] of vEdges) { const [ax, ay] = toScreen(a), [bx, by] = toScreen(b); const hi = selected && (a === selected || b === selected); ctx.strokeStyle = hi ? 'rgba(237,239,243,.55)' : 'rgba(255,255,255,.09)'; ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke(); }
    for (const n of visible) {
      const [x, y] = toScreen(n), K = KINDS[n.kind], r = K.r * Math.max(.7, Math.min(1.3, scale));
      const match = query && n.label.toLowerCase().includes(query);
      const dim = query && !match;
      ctx.globalAlpha = dim ? .25 : 1;
      if (n === hover || n === selected || match) { ctx.beginPath(); ctx.arc(x, y, r + 8, 0, Math.PI * 2); ctx.fillStyle = K.c + '22'; ctx.fill(); }
      if (n.kind === 'root') { const g = ctx.createRadialGradient(x, y, 2, x, y, r + 14); g.addColorStop(0, 'rgba(237,239,243,.9)'); g.addColorStop(.5, 'rgba(180,190,205,.25)'); g.addColorStop(1, 'rgba(0,0,0,0)'); ctx.beginPath(); ctx.arc(x, y, r + 14, 0, Math.PI * 2); ctx.fillStyle = g; ctx.fill(); }
      ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fillStyle = n.kind === 'root' ? '#0b0e14' : '#0b0e14'; ctx.fill(); ctx.strokeStyle = K.c; ctx.lineWidth = n.kind === 'group' ? 1.5 : 1; ctx.stroke();
      ctx.beginPath(); ctx.arc(x, y, Math.max(1.5, r * .38), 0, Math.PI * 2); ctx.fillStyle = K.c; ctx.fill();
      if (n.kind === 'group' && n.collapsed) { ctx.fillStyle = K.c; ctx.font = '10px Geist Mono, monospace'; ctx.textAlign = 'center'; ctx.fillText('+', x, y - r - 4); }
      const showLabel = n.kind === 'root' || n.kind === 'group' || n.kind === 'project' || scale > .9 || n === hover || n === selected || match;
      if (showLabel) { ctx.fillStyle = n.kind === 'root' ? '#EDEFF3' : n.kind === 'group' ? '#EDEFF3' : '#8B93A1'; ctx.font = (n.kind === 'root' ? '700 11px Syncopate, sans-serif' : n.kind === 'group' ? '500 12px Inter, sans-serif' : '11px Inter, sans-serif'); ctx.textAlign = 'center'; ctx.textBaseline = 'top'; ctx.fillText(n.kind === 'root' ? 'ULTRON' : n.label.length > 26 ? n.label.slice(0, 25) + '…' : n.label, x, y + r + 5); }
      ctx.globalAlpha = 1;
    }
  }
  function loop() { step(); draw(); raf = requestAnimationFrame(loop); }

  /* ---------- interaction ---------- */
  const pick = (e) => { const r = canvas.getBoundingClientRect(); const px = e.clientX - r.left, py = e.clientY - r.top; let best = null, bd = 1e9; for (const n of visible) { const [x, y] = toScreen(n); const d = Math.hypot(px - x, py - y); if (d < KINDS[n.kind].r + 10 && d < bd) { bd = d; best = n; } } return best; };
  canvas.addEventListener('pointerdown', (e) => { const n = pick(e); if (n) { dragging = n; canvas.setPointerCapture(e.pointerId); } else { panning = { x: e.clientX, y: e.clientY, tx, ty }; canvas.classList.add('drag'); } });
  canvas.addEventListener('pointermove', (e) => { if (dragging) { const r = canvas.getBoundingClientRect(); dragging.x = (e.clientX - r.left - W / 2) / scale - tx; dragging.y = (e.clientY - r.top - H / 2) / scale - ty; alpha = Math.max(alpha, .3); } else if (panning) { tx = panning.tx + (e.clientX - panning.x) / scale; ty = panning.ty + (e.clientY - panning.y) / scale; } else { const n = pick(e); if (n !== hover) { hover = n; canvas.style.cursor = n ? 'pointer' : 'grab'; } } });
  canvas.addEventListener('pointerup', (e) => { if (dragging) { const moved = Math.hypot(dragging.vx, dragging.vy); select(dragging); dragging = null; } panning = null; canvas.classList.remove('drag'); });
  canvas.addEventListener('dblclick', (e) => { const n = pick(e); if (n && n.kind === 'group') { n.collapsed = !n.collapsed; rebuild(); } });
  canvas.addEventListener('wheel', (e) => { e.preventDefault(); zoomBy(e.deltaY < 0 ? 1.12 : .89); }, { passive: false });
  function zoomBy(f) { scale = Math.max(.35, Math.min(3, scale * f)); draw(); }
  function select(n) {
    selected = n;
    if (!n) { detail.style.display = 'none'; return; }
    const children = visible.filter(c => c.parent === n.id);
    mount(detail, h('div', { class: 'k' }, n.kind), h('h4', null, n.kind === 'root' ? 'ULTRON' : n.label), h('p', null, n.data?.desc || ''),
      n.data?.progress !== undefined && h('div', { style: { marginTop: '8px' } }, h('div', { class: 'progress' }, h('i', { style: { width: n.data.progress + '%' } }))),
      children.length ? h('div', { class: 'links' }, children.slice(0, 10).map(c => h('span', { onClick: () => { select(c); tx = -c.x; ty = -c.y; } }, c.label))) : null,
      h('div', { class: 'row', style: { marginTop: '12px', gap: '6px' } },
        n.data?.route && Button({ label: 'Open', size: 'sm', variant: 'primary', onClick: () => navigate(n.data.route) }),
        n.kind === 'group' && Button({ label: n.collapsed ? 'Expand' : 'Collapse', size: 'sm', onClick: () => { n.collapsed = !n.collapsed; rebuild(); select(n); } }),
        Button({ label: 'Ask Ultron', size: 'sm', variant: 'ghost', onClick: () => navigate('/chat?new=1&ask=' + encodeURIComponent(`Tell me about ${n.label}`)) }),
        IconButton({ icon: 'x', label: 'Close', size: 'sm', onClick: () => select(null) })));
    detail.style.display = '';
  }

  rebuild(); resize(); loop();
  const ro = new ResizeObserver(resize); ro.observe(wrap);
  return () => { cancelAnimationFrame(raf); ro.disconnect(); };
}
