# ULTRON backend contract

Everything the frontend needs from a backend. Implement these and set `mode: 'live'` in `config.js`.
Until then the built-in mock (`src/api/mock/`) serves the same shapes, so the UI is fully clickable.

- Base URL: `config.apiBaseUrl + config.apiPrefix` (default `/api`).
- All bodies and responses are JSON. `204` is allowed for deletes.
- Auth: `Authorization: Bearer <token>` (or session cookie — see `config.auth.mode`). A `401` makes the UI clear the token and either redirect to `config.auth.loginUrl` or show "Session expired".
- Errors: any non-2xx with `{ "detail": "human readable" }`. The UI renders `what / why / next` and a Retry button.
- Timestamps: ISO-8601 strings. IDs: opaque strings.

---

## Health

| Method | Path | Returns |
|---|---|---|
| GET | `/system/health` | `{ ok, local, model, latencyMs, memoryCount }` |

Used by `mode:'auto'` to decide live vs mock. Must be cheap and unauthenticated-friendly.

## User

| Method | Path | Body / Returns |
|---|---|---|
| GET | `/me` | `{ id, name, initials, email, timezone, language, role }` |
| PATCH | `/me` | partial user → updated user |

## Overview

| Method | Path | Returns |
|---|---|---|
| GET | `/overview` | `{ activity[], memory:{total,recall,learnedToday}, pinned, focus:number[7], agents[], projects[], productivity:{done,pending,rate,sessions}, log[], metrics:[{l,v,d,up}], dueSoon }` |

## Chat

| Method | Path | Body / Returns |
|---|---|---|
| GET | `/conversations` | `[{ id, title, projectId, updatedAt, pinned }]` |
| POST | `/conversations` | `{ title?, projectId? }` → conversation |
| GET | `/conversations/:id` | conversation |
| PATCH | `/conversations/:id` | `{ title?, pinned? }` → conversation |
| DELETE | `/conversations/:id` | `204` |
| GET | `/conversations/:id/messages` | `[message]` |
| POST | `/messages/:id/memory` | `{ text }` → memory |
| POST | `/messages/:id/task` | `{ title, projectId? }` → task |

**`POST /chat/stream`** — body `{ conversationId, text, context }` where `context` is `{ projectId?, documentId?, label? }` or `null`.
Responds `text/event-stream`-style: newline-delimited `data: {json}` lines.

```
data: {"type":"user","payload":{ …the persisted user message… }}
data: {"type":"state","state":"thinking"}          // thinking | working | speaking — drives the orb
data: {"type":"tool","tool":{"name":"Read container logs","status":"running","detail":"…"}}
data: {"type":"tool","tool":{"name":"Read container logs","status":"done","ms":820}}
data: {"type":"token","text":"Checked "}           // stream the reply word by word
data: {"type":"done","payload":{"message":{…},"conversation":{…}}}
```

`message` fields the UI renders: `id, role('user'|'assistant'), text(markdown subset), at, tools[], citations[{n,title,source}]`, plus optional side-effect markers — `taskCreated`, `reminderCreated`, `memoryCreated`, `researchStarted`, `automationCreated`. Each renders as a small confirmation card under the reply.

## Memory

| Method | Path | Body / Returns |
|---|---|---|
| GET | `/memories?category=&q=` | `[{ id, text, category, source, confidence(0-1), importance, createdAt, lastAccessed, pinned, accessCount }]` |
| GET | `/memory/stats` | `{ total, recall, learnedToday, pinned, byCategory }` |
| POST | `/memories` | `{ text, category, importance }` → memory |
| PATCH | `/memories/:id` | partial → memory |
| DELETE | `/memories/:id` | `204` — must actually delete |

Categories: `personal, preferences, projects, people, work, conversations, learned`.

## Knowledge

| Method | Path | Body / Returns |
|---|---|---|
| GET | `/knowledge?type=&q=` | `[{ id, title, type, source, size, tags[], status('processing'\|'ready'), progress?, summary?, pages?, createdAt }]` |
| GET | `/knowledge/:id` | item |
| POST | `/knowledge` | `{ title, type, source, size, tags[] }` → item (`status:'processing'`) |
| DELETE | `/knowledge/:id` | `204` |
| POST | `/knowledge/:id/summarize` | → item with `summary` |
| POST | `/knowledge/:id/memory` | → memory |

Types: `pdf, doc, note, link, image, code`. Emit `knowledge` events while processing so the card's progress bar moves.

## Tasks & planning

| Method | Path | Body / Returns |
|---|---|---|
| GET | `/tasks?view=&projectId=` | `[task]` — views: `today, upcoming, inbox, completed` |
| POST | `/tasks/parse` | `{ text }` → `{ title, priority, due, recurrence, projectId }` (natural-language preview, no write) |
| POST | `/tasks` | `{ text }` **or** a full task → task |
| PATCH | `/tasks/:id` | partial → task |
| DELETE | `/tasks/:id` | `204` |
| GET | `/plan/day` | `{ morning[], afternoon[], evening[], postpone[], conflicts[], freeHours }` |

`task`: `{ id, title, description, priority('high'\|'medium'\|'low'), status('todo'\|'in_progress'\|'done'), due, projectId, tags[], estimate(min), recurrence, completedAt?, createdAt }`.
A task created with a recurrence should also create the matching automation and return `automationId`.

## Calendar

| Method | Path | Body / Returns |
|---|---|---|
| GET | `/events?from=&to=` | `[{ id, title, start, end, type, projectId, taskId }]` — types: `meeting, focus, deadline, reminder` |
| POST | `/events` | `{ title, start, end, type, projectId? }` → event |
| DELETE | `/events/:id` | `204` |
| GET | `/calendar/context` | `{ text, meetings, freeHours }` — one honest sentence about tomorrow |

## Automations

| Method | Path | Body / Returns |
|---|---|---|
| GET | `/automations` | `[{ id, name, trigger, action, status('active'\|'paused'\|'failed'), lastRun, nextRun, runs, failures, error?, note? }]` |
| POST | `/automations` | `{ text }` or `{ name, trigger, action }` → automation |
| PATCH | `/automations/:id` | `{ status? … }` → automation |
| DELETE | `/automations/:id` | `204` |
| POST | `/automations/:id/run` | → `{ id, automationId, at, status, ms, output }` |
| GET | `/automations/:id/runs` | `[run]` |

## Agents

| Method | Path | Returns |
|---|---|---|
| GET | `/agents` | `[{ id, name, role, status('ready'\|'idle'\|'working'\|'monitoring'), description, capabilities[], executions, lastRun, model, currentTask?, permissions[] }]` |
| GET | `/agents/:id` | agent |
| GET | `/agents/:id/executions` | `[{ id, agentId, task, status, startedAt, endedAt, ms, error? }]` |
| GET | `/executions` | all executions |

**`POST /agents/orchestrate`** — body `{ request }`. Streams the delegation:

```
data: {"type":"step","index":0,"agent":"a_core","label":"Understand goal","status":"running"}
data: {"type":"step","index":0,"agent":"a_core","label":"Understand goal","status":"done"}
…
data: {"type":"done","payload":{"summary":"…","plan":["…"],"verified":true}}
```

## Research

| Method | Path | Body / Returns |
|---|---|---|
| GET | `/research` | `[{ id, query, status('running'\|'done'\|'failed'), createdAt, sources, step, projectId, report? }]` |
| GET | `/research/:id` | session |
| DELETE | `/research/:id` | `204` |
| POST | `/research/:id/tasks` | → `[task]` created from `report.nextActions` |
| POST | `/research/:id/knowledge` | → knowledge item |

**`POST /research/stream`** — body `{ query, projectId }`:

```
data: {"type":"session","session":{…}}
data: {"type":"step","step":1,"label":"Search sources","sources":3}
data: {"type":"report","report":{…}}
data: {"type":"done","payload":{…session with report…}}
```

`report`: `{ summary, findings[], evidence[{n,title,detail}], contradictions[], recommendations[], nextActions[] }`.
Long sessions may return immediately and finish via `research` events instead.

## Projects, goals

| Method | Path | Returns |
|---|---|---|
| GET | `/projects` | `[{ id, name, description, progress, status, updatedAt, tags[], openTasks }]` |
| GET | `/projects/:id` | project **plus** `tasks[], conversations[], files[], research[], memories[], goals[], activity[]` |
| POST | `/projects` | `{ name, description }` → project |
| GET | `/goals` | `[{ id, title, objective, deadline, progress, projectId, project, milestones:[{t,done,current}], recommendation }]` |
| POST | `/goals` | `{ title, objective, deadline, projectId, milestones[] }` → goal |
| PATCH | `/goals/:id` | partial → goal |

## Insights, activity, sessions

| Method | Path | Returns |
|---|---|---|
| GET | `/insights` | `{ focus:number[7], weekly:[{d,work,learn}], usage:{queries,research,tasks,automations}, knowledgeTop:[{id,title,n}], sessions[], projects:[{name,minutes}], tasks:{done,total}, activeDays, streak }` |
| GET | `/activity?kind=` | `[{ id, kind, title, body, at }]` — kinds: `chat, memory, research, tasks, agents, automations, system` |
| GET | `/sessions` | `[{ id, type('work'\|'learning'), project, start, minutes, recorded, summary }]` |

Keep measured numbers separate from interpretation — the UI labels anything interpreted.

## Notifications, integrations, settings, search

| Method | Path | Body / Returns |
|---|---|---|
| GET | `/notifications` | `[{ id, type, title, body, at, read }]` — types: `reminder, task, agent, automation, system, important` |
| PATCH | `/notifications/:id` | `{ read:true }` |
| POST | `/notifications/read-all` | `204` |
| GET | `/integrations` | `[{ id, name, icon, status('connected'\|'disconnected'\|'available'), detail, error? }]` |
| POST | `/integrations/:id/connect` \| `/disconnect` | → integration |
| GET | `/settings` | `{ general, ai, memory, voice, notifications, privacy }` |
| PATCH | `/settings/:section` | partial → section |
| GET | `/search?q=` | `[{ kind, id, title, sub, route }]` — kinds: `conversation, memory, knowledge, task, research, project, person` |

`route` is a frontend hash route (e.g. `/chat/c_1`) — the backend decides where a hit leads.

## Voice

**`POST /voice/transcribe`** — body `{ prompt? }`, streams partial transcripts:

```
data: {"type":"state","state":"listening"}
data: {"type":"partial","text":"Ultron, I need to"}
data: {"type":"done","payload":{"transcript":"Ultron, I need to finish the Ally backend today."}}
```

Real STT should stream from the microphone; the frontend only needs `partial` + `done`.

## System

| Method | Path | Notes |
|---|---|---|
| POST | `/system/reset` | demo/dev only — reseed sample data |
| POST | `/system/wipe` | **must really delete** the user's tasks, memories, knowledge, conversations, research, automations, activity |

## Realtime — `GET /events` (SSE)

```
data: {"type":"agent","payload":{ …agent… }}
data: {"type":"automation","payload":{ …automation… }}
data: {"type":"notification","payload":{ …notification… }}
data: {"type":"knowledge","payload":{ …item with progress/status… }}
data: {"type":"research","payload":{ …session with step/status… }}
data: {"type":"heartbeat","payload":{"at":"…","online":true}}
```

The client reconnects with exponential backoff (1s → 30s) and degrades gracefully if `eventsPath` is `null`.

---

## Implementation order (matches the Build Roadmap)

1. `/system/health`, `/me`, `/settings` — the shell boots.
2. `/chat/stream` + `/conversations*` — the product exists.
3. `/memories*`, `/overview` — Ultron starts feeling personal.
4. `/tasks*`, `/plan/day`, `/events` (calendar) — daily use.
5. `/knowledge*`, `/research/stream` — depth.
6. `/agents*`, `/automations*`, SSE `/events` — autonomy.
7. `/insights`, `/activity`, `/search` — reflection.

Each endpoint the backend does not implement yet can 404 — the page shows its error state with a Retry, and the rest of the app keeps working.
