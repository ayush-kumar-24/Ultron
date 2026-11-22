# Writing an ULTRON page

Every page is one ES module in `src/pages/<name>.js`. No framework, no build step, no dependencies.

```js
// src/pages/example.js
import { h, icon, fmt, md, mount, clear, $ } from '../ui/dom.js';
import { PageHeader, Card, Button, IconButton, Chip, Tabs, Badge, Dot, Input, Select, Textarea, Field, Toggle, Check, Row, Progress,
         Metric, Sparkline, RingGauge, Bars, EmptyState, ErrorState, Skeleton, SkeletonCard, AiState, load, Modal, confirm, Drawer, Menu, toast, Table } from '../ui/components/index.js';
import { taskService /* etc */, events } from '../services/index.js';
import { presence } from '../ui/core/presence.js';
import { appState, bus } from '../store.js';
import { navigate } from '../router.js';

export default async function example(root, { params, query, navigate }) {
  // 1. build static scaffolding synchronously with h()
  // 2. await data through `load(container, fetcher, render)` (gives skeleton + error state + retry for free)
  // 3. subscribe to `events` if the page shows live data; return a cleanup function that unsubscribes
  return () => { /* cleanup */ };
}
```

## Rules (these caused real bugs)
- **Never declare `const fn = () => {}` after an `await` and call it from code that ran before.** Module-level `await` + TDZ = "Cannot access X before initialization". Use `function fn() {}` declarations for helpers inside the page, or declare all consts at the top before any `await`.
- Pages import **services**, never `api` or the mock.
- Do not use `innerHTML` with user/content strings; use `h()` children (auto-escaped) or `md()` for assistant text.
- Every list view needs: skeleton while loading (via `load()`), an `EmptyState` when empty (copy from the spec: inviting, no apology), an `ErrorState` on failure (`load()` does this).
- Mutations: optimistic where cheap; always `toast()` the outcome in plain words ("Task created", "Memory deleted").
- Keyboard: Enter submits single-line inputs; Escape closes overlays (Modal/Drawer handle this).
- Style only with classes in `src/styles/*.css`. Page-specific classes live in `pages.css` under a section comment. Tokens: `var(--t1|--t2|--t3|--line|--line2|--accent|--ok|--warn|--busy|--info|--bad|--think)`.
- Colour is signal, never decoration. Monochrome first.
- Responsive: grids use `.grid.c2/.c3/.c4/.main/.side` which collapse under 960px. Don't write fixed widths.
- Smart context: when a page represents a project/document, set `appState.set({ context: { type: 'project'|'document', id, label } })` on enter and clear it in cleanup (`appState.set({ context: null })`).

## The presence
`presence.setState('idle'|'listening'|'thinking'|'working'|'speaking'|'recording'|'approval'|'success'|'error', optionalLine)`.
`presence.dock(containerEl)` moves the orb into a page (Overview hero, Focus Mode); `presence.dock(null)` returns it to the corner. Always `dock(null)` in cleanup.
`await presence.approve('Push to origin/main?')` → resolves true/false via the orb's ✓/✕.

## Services (all return Promises; see `src/services/index.js`)
userService, overviewService, chatService, memoryService, knowledgeService, taskService, calendarService, automationService, agentService, researchService, projectService, goalService, insightService, activityService, sessionService, notificationService, integrationService, settingsService, searchService, voiceService, systemService.
Streaming ones take an `onEvent` callback: `chatService.send`, `researchService.start`, `agentService.orchestrate`, `voiceService.transcribe`.

## Real-time
`events.on('agent'|'automation'|'notification'|'knowledge'|'research'|'heartbeat', fn)` returns an unsubscribe function — call it in cleanup.

## Routes
`/overview /chat/:id? /mind /memory /knowledge/:id? /tasks/:view? /calendar/:view? /automations/:id? /agents/:id? /research/:id? /projects/:id? /goals /insights /activity /focus /settings/:section? /profile /search`
Query strings arrive in `query` (e.g. `/tasks?new=1&text=…`, `/memory?teach=1&q=…`, `/research?new=1&q=…`, `/automations?new=1`).
