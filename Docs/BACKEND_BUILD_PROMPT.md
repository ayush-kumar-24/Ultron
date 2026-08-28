# ULTRON — backend build brief

Give this to Cursor as the task. It is written to be accurate about what already exists,
so the agent extends the project instead of reinventing it.

---

## The task

Build the HTTP API layer for Ultron so the existing web frontend runs on real data instead of demo data.

The frontend is **finished** and lives in `frontend/`. It is a dependency-free ES-module SPA with 18 pages.
It already knows how to talk to a backend — streaming, realtime events, auth, retries, error states.
**Do not modify the frontend** except `frontend/config.js`.

The Python app in `maira/` is **finished for what it covers** — brain, memory, planner, automation, desktop
control, knowledge, voice, vision — but it is a PySide6 desktop app with **no HTTP surface at all**.
No FastAPI, no uvicorn, no routes.

**Your job is the layer between them, plus the domain services that do not exist yet.**

---

## Read these first, in this order

1. `frontend/docs/API.md` — **the contract.** Every endpoint, payload shape, stream format and SSE event.
   This is the specification. Do not invent endpoints; implement these.
2. `Docs/ULTRON_Product_Vision.docx` — the principles (local-first, offline-capable, verify before
   claiming success, explainable actions, user control).
3. `Docs/ULTRON_Build_Roadmap.docx` — the capability order.
4. `maira/app/bootstrap.py` and `maira/app/container.py` — how services are wired today.
5. `maira/core/interfaces/` — the existing ports. Follow this pattern exactly.

---

## Architecture conventions — follow these exactly

The codebase has a consistent style. Match it; do not introduce a second one.

- **Indentation is 2 spaces.** Not 4. Every file.
- `from __future__ import annotations` at the top of every module.
- A one-line module docstring explaining purpose.
- **Ports** (abstract interfaces) live in `maira/core/interfaces/<name>.py` as `ABC` classes with
  `@abstractmethod` and a docstring per method.
- **Adapters** (concrete tech) live in `maira/infrastructure/<tech>/`. Optional dependencies are
  lazy-loaded behind an `_ensure()` function and expose `is_available() -> tuple[bool, str]`, so a
  missing package is never fatal at import time. See `maira/infrastructure/screen/mss_capture.py`.
- **Services** live in `maira/modules/<name>/service.py` and implement the port.
- Wire everything in `maira/app/bootstrap.py` via `container.register_instance(...)`.
- Settings: add a frozen dataclass in `maira/app/settings.py`, parse it from `config/default.yaml`.
- Logging is `loguru` (`from loguru import logger`).
- Domain entities live in `maira/core/domain/entities/`.

Example of the expected shape:

```python
"""Screen port - capture what is on the display and read it as text."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Screen(ABC):
  @abstractmethod
  def is_available(self) -> tuple[bool, str]:
    """Whether Ultron can look at the screen, plus reason."""
```

---

## How to run the API

Add `fastapi` and `uvicorn[standard]` to a new `api` extra in `pyproject.toml`.

Run **uvicorn in a daemon thread inside the existing Qt process**, sharing the same DI container.
This is safe and already supported:

- `maira/infrastructure/persistence/sqlite/connection.py` uses `check_same_thread=False` with an
  `RLock`, so the SQLite layer is thread-safe.
- `maira/core/bus/event_bus.py` is lock-guarded, so the API thread can subscribe and publish freely.

Do **not** spawn a second process or a second container — the API must operate on the same live
services the desktop UI uses, so a task created in the browser appears in the orb immediately.

Also add a headless entry point (e.g. `python -m maira --headless` or `maira/api/__main__.py`) that
boots the container and serves the API **without** Qt, for running the backend alone.

Structure:

```
maira/api/
  __init__.py
  server.py          # app factory, thread runner, lifespan
  deps.py            # resolve services from the container
  schemas.py         # pydantic request/response models mirroring frontend/docs/API.md
  routes/
    system.py        # /system/health, /system/reset, /system/wipe
    user.py          # /me
    settings.py      # /settings
    chat.py          # /conversations, /chat/stream
    memory.py        # /memories, /memory/stats
    tasks.py         # /tasks, /tasks/parse, /plan/day
    calendar.py      # /events, /calendar/context
    knowledge.py     # /knowledge
    automations.py   # /automations
    screen.py        # /screen/read
    events.py        # /events  (SSE bridge from EventBus)
    ...
```

---

## What already exists — wrap it, do not rewrite it

Resolve these from the container (`container.resolve("brain")` etc.) and expose them over HTTP:

| Endpoint group | Existing service | Notes |
|---|---|---|
| `/chat/stream`, `/conversations` | `brain` + `conversation_repository` | `BrainService` already streams tokens and publishes `brain.token` / `brain.complete` on the bus. Bridge that to the `data: {json}` line format in the contract. |
| `/memories`, `/memory/stats` | `memory` + `memory_repository` | |
| `/tasks`, `/plan/day` | `planner` + `task_repository` | `PlannerService` covers tasks and notes. |
| `/automations` | `automation` + `automation_repository` | `AutomationService` + `AutomationRunner` already exist. |
| `/knowledge` | `knowledge_base` | |
| `/settings`, `/me` | `settings` | |
| `/screen/read` | `vision` | New. `VisionService.read_screen()` returns a `ScreenReading`. **Not yet in the contract — add it to `frontend/docs/API.md`.** |
| `/system/health` | — | Cheap, unauthenticated-friendly. The frontend probes this to decide live vs demo. |

Existing domain entities: `Message`, `Conversation`, `Task`, `Note`, `MemoryEntry`, `AutomationJob`.
Existing repositories: `ConversationRepository`, `TaskRepository`, `NoteRepository`, `MemoryRepository`,
`AutomationRepository`.

---

## What does not exist yet — build these

The frontend has complete UI for all of these, and currently falls back to demo data. Each needs a
domain service, persistence (new migration), and routes. Follow the same port/adapter/service pattern.

- **Agents** — `/agents`, `/agents/:id/executions`, `POST /agents/orchestrate` (streams delegation steps).
  Roadmap stages 6-7: agent runtime with identity, tools, permissions, logs, verification.
- **Research** — `/research`, `POST /research/stream` (6-step plan, then a report with summary, findings,
  evidence, **contradictions**, recommendations, next actions).
- **Projects** — `/projects`, `/projects/:id` (returns the project plus its tasks, conversations, files,
  research, memories, goals, activity).
- **Goals** — `/goals` with milestones and progress.
- **Insights + Sessions** — `/insights`, `/sessions`. Keep measured numbers and interpretation separate;
  the UI labels anything interpreted.
- **Activity** — `/activity?kind=` — a chronological log of everything Ultron did.
- **Notifications** — `/notifications`, `/notifications/read-all`.
- **Integrations** — `/integrations`, connect/disconnect.
- **Search** — `/search?q=` across conversations, memories, knowledge, tasks, research, projects, people.
- **Realtime** — `GET /events` (SSE) emitting `agent`, `automation`, `notification`, `knowledge`,
  `research`, `heartbeat`. Bridge from the existing `EventBus`.

---

## Build order

Ship in phases. After each phase the app must run and be usable.

**Phase 1 — the app goes live.** `/system/health`, `/me`, `/settings`, `/conversations`, `/chat/stream`,
`/memories`. Set `frontend/config.js` to `mode: 'live'`, `auth.mode: 'none'`.
*Done when:* you can hold a real conversation in the browser, it streams, and memories persist.

**Phase 2 — daily use.** `/tasks`, `/tasks/parse`, `/plan/day`, `/events` (calendar),
`/calendar/context`, `/knowledge`, `/automations`, `/screen/read`.

**Phase 3 — realtime.** SSE `/events` bridged from `EventBus`, so agent status and automation runs
update live without a refresh.

**Phase 4 — new domains.** Activity, notifications, search, projects, goals.

**Phase 5 — the hard ones.** Agents + orchestration, research, insights, integrations.

---

## Rules

- **Every endpoint you have not built must 404 with `{"detail": "..."}`.** The frontend renders a proper
  error state with Retry and keeps working. Never return HTML from `/api/*` — the frontend treats a
  non-JSON 200 as "no backend" and silently falls back to demo data.
- **Local-first.** No cloud service may be required. Everything must work offline.
- **Deleting means deleting.** `/system/wipe` must really remove the user's data, not archive it.
- **Verify before claiming success.** Do not return `ok: true` because a command ran — check the outcome.
- Errors: non-2xx with `{"detail": "human readable"}`. No stack traces to the client.
- Do not break the desktop app. `python -m maira` must still work exactly as before.

---

## Testing

- `pytest`, tests in `tests/unit/`, plain functions (no classes), 2-space indent, docstring at the top
  of the file. See `tests/unit/test_vision_service.py` for the fake-adapter style.
- Use FastAPI's `TestClient` for route tests. Fake the services; do not hit a real LLM or a real screen.
- Every new endpoint needs at least: a success case, a not-found/invalid case, and a service-failure case.
- Run the suite before declaring done.

**Note:** 4 tests fail today, before you start. They are pre-existing and unrelated:
- `test_brain_service.py::test_brain_service_includes_system_prompt_and_limits_history` asserts
  `"You are Maira"` but the prompt now says `"You are Ultron"` (a rename that missed this test).
- Three migration tests assert version 3 while `004_automations.sql` is committed.

Fix them if you like, but do not let them mask new failures.

---

## Definition of done

1. `python -m maira` starts the desktop app **and** serves the API.
2. A headless mode serves the API without Qt.
3. `frontend/config.js` set to `mode: 'live'` and the app runs on real data with no demo banner.
4. Chat streams token by token from the real model.
5. Tasks, memories and automations created in the browser appear in the desktop app, and vice versa.
6. Unimplemented endpoints 404 cleanly and the UI degrades without breaking.
7. `frontend/docs/API.md` updated for anything you added (starting with `/screen/read`).
8. Tests pass.
