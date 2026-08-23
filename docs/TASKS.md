# Maira — Development Tasks

Granular task breakdown derived from [DEVELOPMENT_ROADMAP.md](./DEVELOPMENT_ROADMAP.md).

## Conventions

| Rule | Detail |
|---|---|
| **Task size** | Each task is designed to complete in **under 2 hours**. |
| **Checkboxes** | `- [ ]` = not started. Check off as you finish. |
| **Task ID** | `M{n}-T{nn}` — milestone number + sequence within milestone. |
| **Depends on** | Must be complete before starting this task. Never skip. |
| **Files** | Primary files touched. |

## Milestone Dependency Order

```
M0 → M1 → M2 ─────────────────────────────→ M6 → M7 → M8 ─┐
  ├→ M3 ─────────────────────────────────────────────→ M13 ─┤
  ├→ M4 → M5 ──────────→ M6 ──→ M10 → M12 ────────────────┤
  ├→ M9 ───────────────→ M10 ─────────────────────────────┤
  └→ M14 ──────────────────────────────────────────────────┤
                                                            └→ M15
M5 → M11 (parallel after M5; before M15)
```

---

## Milestone 0: App Shell & Runtime Bootstrap

> **Goal:** Launch a stable PySide6 app with logging, config, and navigable shell.  
> **Milestone depends on:** —  
> **Blocks:** M1, M2, M3, M4, M9, M14, M15

- [ ] **M0-T01** — Add runtime dependencies to `pyproject.toml`  
  - **Files:** `pyproject.toml`  
  - **Depends on:** —  
  - Add `PySide6`, `PyYAML`, `loguru`. Pin minimum versions. Verify `pip install -e .` succeeds.

- [ ] **M0-T02** — Implement `paths.py` (data dir, config paths, logs dir)  
  - **Files:** `maira/shared/utils/paths.py`  
  - **Depends on:** M0-T01  
  - Resolve project root, `data/`, `data/logs/`, user config override path. Create dirs if missing.

- [ ] **M0-T03** — Implement `yaml_loader.py`  
  - **Files:** `maira/infrastructure/config/yaml_loader.py`  
  - **Depends on:** M0-T01  
  - Load YAML file, return dict. Handle missing file gracefully.

- [ ] **M0-T04** — Implement `settings.py` (typed settings dataclass)  
  - **Files:** `maira/app/settings.py`, `config/default.yaml`  
  - **Depends on:** M0-T02, M0-T03  
  - Load default config, merge user override from data dir. Expose `Settings` object.

- [ ] **M0-T05** — Unit tests for paths  
  - **Files:** `tests/unit/test_paths.py`  
  - **Depends on:** M0-T02  
  - Test dir creation, path resolution on Windows.

- [ ] **M0-T06** — Unit tests for settings  
  - **Files:** `tests/unit/test_settings.py`  
  - **Depends on:** M0-T04  
  - Test default load, merge override, missing keys.

- [ ] **M0-T07** — Implement `loguru_setup.py`  
  - **Files:** `maira/infrastructure/logging/loguru_setup.py`, `config/logging.yaml`  
  - **Depends on:** M0-T02, M0-T03  
  - Console sink + rotating file sink under `data/logs/`.

- [ ] **M0-T08** — Implement minimal `event_bus.py`  
  - **Files:** `maira/core/bus/event_bus.py`  
  - **Depends on:** M0-T01  
  - `subscribe(topic, handler)`, `publish(topic, payload)`, `unsubscribe`.

- [ ] **M0-T09** — Implement `container.py` (DI registry)  
  - **Files:** `maira/app/container.py`  
  - **Depends on:** M0-T04, M0-T08  
  - Register and resolve `Settings`, `EventBus`. Singleton pattern.

- [ ] **M0-T10** — Implement `lifecycle.py` (shutdown hooks)  
  - **Files:** `maira/app/lifecycle.py`  
  - **Depends on:** M0-T09  
  - `on_shutdown(callback)` list; `run_shutdown()` calls all in reverse order.

- [ ] **M0-T11** — Implement `dark.py` theme QSS  
  - **Files:** `maira/ui/themes/dark.py`  
  - **Depends on:** M0-T01  
  - Return QSS string: window, sidebar, buttons, inputs.

- [ ] **M0-T12** — Implement `application.py` (QApplication factory)  
  - **Files:** `maira/ui/application.py`  
  - **Depends on:** M0-T11  
  - Create `QApplication`, apply theme, set app name and icon placeholder.

- [ ] **M0-T13** — Implement `window.py` (main shell + sidebar nav)  
  - **Files:** `maira/ui/main_window/window.py`  
  - **Depends on:** M0-T12  
  - Sidebar: Chat, Planner, Memory, Voice, Settings. Stacked content area (empty placeholders).

- [ ] **M0-T14** — Implement `bootstrap.py`  
  - **Files:** `maira/app/bootstrap.py`  
  - **Depends on:** M0-T07, M0-T09, M0-T10, M0-T13  
  - Ordered init: logging → settings → container → main window.

- [ ] **M0-T15** — Wire `__main__.py` entry point  
  - **Files:** `maira/__main__.py`  
  - **Depends on:** M0-T14  
  - `main()` calls bootstrap, shows window, runs `app.exec()`, triggers shutdown.

- [ ] **M0-T16** — Manual smoke test (M0 exit criteria)  
  - **Files:** —  
  - **Depends on:** M0-T15, M0-T05, M0-T06  
  - Verify: launches < 5 s, `data/` created, logs written, clean exit.

---

## Milestone 1: Offline Chat with Streaming

> **Goal:** Real-time conversation with local Ollama; streamed tokens in UI.  
> **Milestone depends on:** M0  
> **Blocks:** M2, M6, M7, M14

- [ ] **M1-T01** — Define `LLMProvider` port (ABC)  
  - **Files:** `maira/core/interfaces/llm.py`  
  - **Depends on:** M0-T08  
  - Methods: `is_available()`, `list_models()`, `chat_stream(messages) -> Iterator[str]`.

- [ ] **M1-T02** — Define `Brain` port (ABC)  
  - **Files:** `maira/core/interfaces/brain.py`  
  - **Depends on:** M1-T01  
  - Methods: `send_message(text) -> None`, `get_history() -> list`.

- [ ] **M1-T03** — Define `Message` entity and `MessageRole` value object  
  - **Files:** `maira/core/domain/entities/__init__.py`, `maira/core/domain/value_objects/__init__.py`  
  - **Depends on:** M0-T01  
  - Dataclasses: `Message(role, content, timestamp)`, enum `MessageRole`.

- [ ] **M1-T04** — Add Ollama section to `config/default.yaml`  
  - **Files:** `config/default.yaml`, `maira/app/settings.py`  
  - **Depends on:** M0-T04  
  - Keys: `host`, `model`, `timeout_seconds`.

- [ ] **M1-T05** — Implement Ollama client: health check + list models  
  - **Files:** `maira/infrastructure/llm/ollama/client.py`  
  - **Depends on:** M1-T01, M1-T04  
  - `GET /api/tags`, connection error handling.

- [ ] **M1-T06** — Implement Ollama client: chat streaming  
  - **Files:** `maira/infrastructure/llm/ollama/client.py`  
  - **Depends on:** M1-T05  
  - `POST /api/chat` with `stream: true`; yield content deltas.

- [ ] **M1-T07** — Unit tests for Ollama client (mocked HTTP)  
  - **Files:** `tests/unit/test_ollama_client.py`  
  - **Depends on:** M1-T06  
  - Mock unreachable host, mock stream JSON lines.

- [ ] **M1-T08** — Implement in-memory conversation session  
  - **Files:** `maira/modules/brain/conversation/__init__.py`  
  - **Depends on:** M1-T03  
  - Append user/assistant messages; `get_messages()` for LLM payload.

- [ ] **M1-T09** — Implement streaming token publisher  
  - **Files:** `maira/modules/brain/streaming/__init__.py`  
  - **Depends on:** M0-T08, M1-T06  
  - Publish `brain.token` and `brain.complete` events on bus.

- [ ] **M1-T10** — Implement `BrainService.send_message()`  
  - **Files:** `maira/modules/brain/service.py`  
  - **Depends on:** M1-T02, M1-T08, M1-T09  
  - Append user msg → call LLM stream → append assistant msg → publish events.

- [ ] **M1-T11** — Register Brain + Ollama in container  
  - **Files:** `maira/app/container.py`, `maira/app/bootstrap.py`  
  - **Depends on:** M1-T10, M0-T14  
  - Wire `OllamaClient` → `BrainService`.

- [ ] **M1-T12** — Implement `async_bridge.py` (worker thread runner)  
  - **Files:** `maira/shared/utils/async_bridge.py`  
  - **Depends on:** M0-T12  
  - `run_in_thread(fn, on_result, on_error)` using `QThread` or `QRunnable`.

- [ ] **M1-T13** — Implement `StreamingLabel` widget  
  - **Files:** `maira/ui/widgets/streaming_label.py`  
  - **Depends on:** M0-T13  
  - `append_token(str)`, `clear()`, `set_complete()`.

- [ ] **M1-T14** — Build chat view layout (history + input)  
  - **Files:** `maira/ui/views/chat/__init__.py`  
  - **Depends on:** M1-T13  
  - Scrollable message area, `QLineEdit` or `QTextEdit` input, Send button.

- [ ] **M1-T15** — Implement `chat_controller.py`  
  - **Files:** `maira/ui/controllers/chat_controller.py`  
  - **Depends on:** M1-T10, M1-T12, M1-T14  
  - Send on Enter; run `BrainService` off UI thread; subscribe to token events.

- [ ] **M1-T16** — Wire chat view into main window stack  
  - **Files:** `maira/ui/main_window/window.py`, `maira/app/bootstrap.py`  
  - **Depends on:** M1-T15  
  - Chat is default visible view; nav switches to chat.

- [ ] **M1-T17** — Ollama offline error UI state  
  - **Files:** `maira/ui/views/chat/__init__.py`, `maira/ui/controllers/chat_controller.py`  
  - **Depends on:** M1-T15  
  - Friendly banner when `is_available()` is false; no stack trace.

- [ ] **M1-T18** — Implement `setup_models.py` Ollama check  
  - **Files:** `scripts/setup_models.py`  
  - **Depends on:** M1-T05  
  - CLI: verify Ollama reachable, print model list.

- [ ] **M1-T19** — Integration test: brain streaming  
  - **Files:** `tests/integration/test_brain_streaming.py`  
  - **Depends on:** M1-T10  
  - Skip if Ollama not running; assert non-empty stream.

- [ ] **M1-T20** — Manual E2E smoke test (M1 exit criteria)  
  - **Files:** —  
  - **Depends on:** M1-T16, M1-T17, M1-T19  
  - Type message → streamed response; UI responsive; offline error shown.

---

## Milestone 2: Conversation Persistence

> **Goal:** Conversations survive restarts; resume or start new.  
> **Milestone depends on:** M1  
> **Blocks:** M6

- [ ] **M2-T01** — Define `Storage` port (ABC)  
  - **Files:** `maira/core/interfaces/storage.py`  
  - **Depends on:** M0-T08  
  - Methods: `execute`, `fetchone`, `fetchall`, transaction context.

- [ ] **M2-T02** — Define `Conversation` and `Message` DB entities  
  - **Files:** `maira/core/domain/entities/__init__.py`  
  - **Depends on:** M1-T03  
  - Add `id`, `title`, `created_at` to conversation model.

- [ ] **M2-T03** — Write `001_conversations.sql` migration  
  - **Files:** `maira/infrastructure/persistence/sqlite/migrations/001_conversations.sql`  
  - **Depends on:** M2-T02  
  - Tables: `conversations`, `messages`, `schema_version`.

- [ ] **M2-T04** — Implement migration runner  
  - **Files:** `maira/infrastructure/persistence/sqlite/migrations/__init__.py`  
  - **Depends on:** M2-T03  
  - Apply pending `.sql` files idempotently; track version.

- [ ] **M2-T05** — Implement SQLite connection manager  
  - **Files:** `maira/infrastructure/persistence/sqlite/connection.py`  
  - **Depends on:** M2-T01, M0-T02  
  - Open DB at `data/maira.db`; WAL mode; connection per thread.

- [ ] **M2-T06** — Implement conversation repository (CRUD)  
  - **Files:** `maira/infrastructure/persistence/sqlite/repositories/__init__.py`  
  - **Depends on:** M2-T05, M2-T04  
  - `create_conversation`, `add_message`, `get_messages`, `list_conversations`.

- [ ] **M2-T07** — Unit tests for conversation repository  
  - **Files:** `tests/unit/test_conversation_repository.py`  
  - **Depends on:** M2-T06  
  - In-memory SQLite; create, read, list.

- [ ] **M2-T08** — Register SQLite in container + run migrations on bootstrap  
  - **Files:** `maira/app/container.py`, `maira/app/bootstrap.py`  
  - **Depends on:** M2-T06, M0-T14  
  - Migration runs before Brain loads.

- [ ] **M2-T09** — Update conversation session to persist messages  
  - **Files:** `maira/modules/brain/conversation/__init__.py`  
  - **Depends on:** M2-T06, M1-T08  
  - Save user + assistant messages after each turn.

- [ ] **M2-T10** — Load last conversation on startup  
  - **Files:** `maira/modules/brain/service.py`  
  - **Depends on:** M2-T09  
  - Bootstrap: fetch most recent conversation; hydrate session.

- [ ] **M2-T11** — Add "New chat" action to chat view  
  - **Files:** `maira/ui/views/chat/__init__.py`, `maira/ui/controllers/chat_controller.py`  
  - **Depends on:** M2-T10  
  - Button creates new conversation; clears UI; old convo stays in DB.

- [ ] **M2-T12** — Display conversation title/timestamp in chat header  
  - **Files:** `maira/ui/views/chat/__init__.py`  
  - **Depends on:** M2-T11  
  - Show active conversation metadata.

- [ ] **M2-T13** — Implement `scripts/migrate_db.py`  
  - **Files:** `scripts/migrate_db.py`  
  - **Depends on:** M2-T04  
  - CLI entry: apply migrations, print current version.

- [ ] **M2-T14** — Integration test: conversation persistence  
  - **Files:** `tests/integration/test_conversation_persistence.py`  
  - **Depends on:** M2-T10  
  - Save messages → reopen session → messages present.

- [ ] **M2-T15** — Manual E2E smoke test (M2 exit criteria)  
  - **Files:** —  
  - **Depends on:** M2-T11, M2-T13, M2-T14  
  - Restart app → history visible; New chat works.

---

## Milestone 3: Todos & Notes

> **Goal:** CRUD todos and notes without AI.  
> **Milestone depends on:** M0  
> **Blocks:** M13

- [ ] **M3-T01** — Define `Planner` port (ABC)  
  - **Files:** `maira/core/interfaces/planner.py`  
  - **Depends on:** M0-T08  
  - Todo and note CRUD method signatures.

- [ ] **M3-T02** — Define `Task`, `Note` entities + `TaskStatus`, `Priority` enums  
  - **Files:** `maira/core/domain/entities/__init__.py`, `maira/core/domain/value_objects/__init__.py`  
  - **Depends on:** M0-T01  
  - Dataclasses with id, title, dates, status, priority.

- [ ] **M3-T03** — Write `002_planner.sql` migration  
  - **Files:** `maira/infrastructure/persistence/sqlite/migrations/002_planner.sql`  
  - **Depends on:** M2-T04  
  - Tables: `tasks`, `notes`.

- [ ] **M3-T04** — Implement task repository  
  - **Files:** `maira/infrastructure/persistence/sqlite/repositories/__init__.py`  
  - **Depends on:** M3-T03, M2-T05  
  - CRUD for tasks.

- [ ] **M3-T05** — Implement note repository  
  - **Files:** `maira/infrastructure/persistence/sqlite/repositories/__init__.py`  
  - **Depends on:** M3-T03, M2-T05  
  - CRUD for notes.

- [ ] **M3-T06** — Implement todo submodule  
  - **Files:** `maira/modules/planner/todos/__init__.py`  
  - **Depends on:** M3-T04, M3-T02  
  - Business logic wrapping repository.

- [ ] **M3-T07** — Implement notes submodule  
  - **Files:** `maira/modules/planner/notes/__init__.py`  
  - **Depends on:** M3-T05, M3-T02  
  - Business logic wrapping repository.

- [ ] **M3-T08** — Implement `PlannerService` facade  
  - **Files:** `maira/modules/planner/service.py`  
  - **Depends on:** M3-T01, M3-T06, M3-T07  
  - Unified API for UI and future Brain tools.

- [ ] **M3-T09** — Register PlannerService in container  
  - **Files:** `maira/app/container.py`, `maira/app/bootstrap.py`  
  - **Depends on:** M3-T08, M2-T08  
  - Available at app startup.

- [ ] **M3-T10** — Build planner view: todos list UI  
  - **Files:** `maira/ui/views/planner/__init__.py`  
  - **Depends on:** M0-T13  
  - QListWidget or table: title, checkbox, priority, due date.

- [ ] **M3-T11** — Build planner view: notes panel UI  
  - **Files:** `maira/ui/views/planner/__init__.py`  
  - **Depends on:** M3-T10  
  - Split/tab: notes list + editor.

- [ ] **M3-T12** — Implement `planner_controller.py`  
  - **Files:** `maira/ui/controllers/planner_controller.py`  
  - **Depends on:** M3-T08, M3-T11  
  - Wire add/complete/delete/edit to service.

- [ ] **M3-T13** — Wire planner view into main window nav  
  - **Files:** `maira/ui/main_window/window.py`  
  - **Depends on:** M3-T12  
  - Sidebar Planner switches to planner view.

- [ ] **M3-T14** — Unit tests for planner service  
  - **Files:** `tests/unit/test_planner_service.py`  
  - **Depends on:** M3-T08  
  - CRUD todos and notes with in-memory DB.

- [ ] **M3-T15** — Manual E2E smoke test (M3 exit criteria)  
  - **Files:** —  
  - **Depends on:** M3-T13, M3-T14  
  - 5 todos lifecycle; note edit persists across restart.

---

## Milestone 4: Structured Memory Store

> **Goal:** Categorized memory entries browsable in UI.  
> **Milestone depends on:** M0  
> **Blocks:** M5, M6

- [ ] **M4-T01** — Define `Memory` port (ABC)  
  - **Files:** `maira/core/interfaces/memory.py`  
  - **Depends on:** M0-T08  
  - `store`, `get`, `list`, `delete`, `search_keyword`.

- [ ] **M4-T02** — Define `MemoryEntry` entity + `MemoryCategory` enum  
  - **Files:** `maira/core/domain/entities/__init__.py`, `maira/core/domain/value_objects/__init__.py`  
  - **Depends on:** M0-T01  
  - Categories: preference, conversation, task, note, idea, project.

- [ ] **M4-T03** — Write `003_memory.sql` migration  
  - **Files:** `maira/infrastructure/persistence/sqlite/migrations/003_memory.sql`  
  - **Depends on:** M2-T04  
  - Table: `memories` with category, title, body, timestamps.

- [ ] **M4-T04** — Implement memory repository  
  - **Files:** `maira/infrastructure/persistence/sqlite/repositories/__init__.py`  
  - **Depends on:** M4-T03, M2-T05  
  - CRUD + filter by category + keyword search on title/body.

- [ ] **M4-T05** — Implement memory store submodule  
  - **Files:** `maira/modules/memory/store/__init__.py`  
  - **Depends on:** M4-T04, M4-T02  
  - Validation and mapping to entities.

- [ ] **M4-T06** — Implement `MemoryService` facade  
  - **Files:** `maira/modules/memory/service.py`  
  - **Depends on:** M4-T01, M4-T05  
  - Public API for UI and Brain.

- [ ] **M4-T07** — Register MemoryService in container  
  - **Files:** `maira/app/container.py`, `maira/app/bootstrap.py`  
  - **Depends on:** M4-T06, M2-T08  
  - Available at startup.

- [ ] **M4-T08** — Build memory browse view (list + detail)  
  - **Files:** `maira/ui/views/memory/__init__.py`  
  - **Depends on:** M0-T13  
  - List with category badge; detail/edit panel.

- [ ] **M4-T09** — Add category filter and keyword search to memory view  
  - **Files:** `maira/ui/views/memory/__init__.py`  
  - **Depends on:** M4-T08  
  - Dropdown filter; search box calls `search_keyword`.

- [ ] **M4-T10** — Wire memory view to MemoryService  
  - **Files:** `maira/ui/views/memory/__init__.py`, `maira/ui/main_window/window.py`  
  - **Depends on:** M4-T07, M4-T09  
  - CRUD from UI; nav item works.

- [ ] **M4-T11** — Add "Save to memory" action on planner notes (optional)  
  - **Files:** `maira/ui/views/planner/__init__.py`, `maira/ui/controllers/planner_controller.py`  
  - **Depends on:** M4-T06, M3-T12  
  - Copy note title/body into new memory entry.

- [ ] **M4-T12** — Unit tests for memory store  
  - **Files:** `tests/unit/test_memory_store.py`  
  - **Depends on:** M4-T06  
  - CRUD, category filter, keyword search.

- [ ] **M4-T13** — Manual E2E smoke test (M4 exit criteria)  
  - **Files:** —  
  - **Depends on:** M4-T10, M4-T12  
  - Add preference; filter works; persists across restart.

---

## Milestone 5: Semantic Memory Retrieval

> **Goal:** Search memories by meaning via ChromaDB + embeddings.  
> **Milestone depends on:** M4  
> **Blocks:** M6, M11

- [ ] **M5-T01** — Define `VectorStore` port (ABC)  
  - **Files:** `maira/core/interfaces/vector_store.py`  
  - **Depends on:** M0-T08  
  - `upsert`, `delete`, `query(text, k) -> list[id, score]`.

- [ ] **M5-T02** — Define `EmbeddingEncoder` port (ABC)  
  - **Files:** `maira/core/interfaces/embeddings.py`  
  - **Depends on:** M0-T08  
  - `encode(text) -> vector`, `encode_batch`.

- [ ] **M5-T03** — Add embedding + chroma config to `default.yaml`  
  - **Files:** `config/default.yaml`, `maira/app/settings.py`  
  - **Depends on:** M0-T04  
  - Keys: `embedding_model`, `chroma_path`.

- [ ] **M5-T04** — Implement ChromaDB client wrapper  
  - **Files:** `maira/infrastructure/vector/chromadb/client.py`  
  - **Depends on:** M5-T01, M5-T03  
  - Persistent client at `data/chroma/`.

- [ ] **M5-T05** — Implement ChromaDB collections manager  
  - **Files:** `maira/infrastructure/vector/chromadb/collections.py`  
  - **Depends on:** M5-T04  
  - `memories` collection get/create.

- [ ] **M5-T06** — Implement Sentence Transformers encoder  
  - **Files:** `maira/infrastructure/embeddings/sentence_transformers/encoder.py`  
  - **Depends on:** M5-T02, M5-T03  
  - Lazy model load; encode single and batch.

- [ ] **M5-T07** — Register vector store + encoder in container  
  - **Files:** `maira/app/container.py`, `maira/app/bootstrap.py`  
  - **Depends on:** M5-T05, M5-T06  
  - Inject into MemoryService.

- [ ] **M5-T08** — Implement memory retrieval submodule  
  - **Files:** `maira/modules/memory/retrieval/__init__.py`  
  - **Depends on:** M5-T05, M5-T06  
  - `recall(query, k)` → list of MemoryEntry.

- [ ] **M5-T09** — Hook MemoryService: upsert on create/update  
  - **Files:** `maira/modules/memory/service.py`  
  - **Depends on:** M4-T06, M5-T08  
  - Embed title+body; upsert to ChromaDB with memory id.

- [ ] **M5-T10** — Hook MemoryService: delete from ChromaDB on delete  
  - **Files:** `maira/modules/memory/service.py`  
  - **Depends on:** M5-T09  
  - Remove vector by id.

- [ ] **M5-T11** — Add semantic search to memory view  
  - **Files:** `maira/ui/views/memory/__init__.py`  
  - **Depends on:** M5-T08, M4-T10  
  - Search box calls `recall()`; show relevance score.

- [ ] **M5-T12** — Keyword fallback when embedder unavailable  
  - **Files:** `maira/modules/memory/service.py`  
  - **Depends on:** M5-T09  
  - Catch encoder errors; fall back to M4 keyword search.

- [ ] **M5-T13** — Extend `setup_models.py` for embedding model  
  - **Files:** `scripts/setup_models.py`  
  - **Depends on:** M5-T06  
  - Download/verify sentence-transformers model.

- [ ] **M5-T14** — Integration test: semantic retrieval  
  - **Files:** `tests/integration/test_semantic_retrieval.py`  
  - **Depends on:** M5-T08  
  - Store "I use VS Code" → query "coding editor" → match.

- [ ] **M5-T15** — Manual E2E smoke test (M5 exit criteria)  
  - **Files:** —  
  - **Depends on:** M5-T11, M5-T14  
  - Semantic search works; delete removes from both stores.

---

## Milestone 6: Context-Aware Brain

> **Goal:** Brain injects relevant memories into LLM prompts.  
> **Milestone depends on:** M2, M5  
> **Blocks:** M7, M10, M13

- [ ] **M6-T01** — Define `ContextAssembled` domain event  
  - **Files:** `maira/core/domain/events/__init__.py`  
  - **Depends on:** M4-T02  
  - Payload: query, memory ids injected, token count.

- [ ] **M6-T02** — Add context config to `default.yaml`  
  - **Files:** `config/default.yaml`, `maira/app/settings.py`  
  - **Depends on:** M0-T04  
  - Keys: `max_memories`, `max_context_tokens`.

- [ ] **M6-T03** — Expose `MemoryService.recall(query, k)`  
  - **Files:** `maira/modules/memory/service.py`  
  - **Depends on:** M5-T08  
  - Thin wrapper for Brain consumption.

- [ ] **M6-T04** — Implement context assembly submodule  
  - **Files:** `maira/modules/brain/context/__init__.py`  
  - **Depends on:** M6-T03, M6-T02  
  - Retrieve top-k; format system prompt block with delimiters.

- [ ] **M6-T05** — Implement token budget truncation  
  - **Files:** `maira/modules/brain/context/__init__.py`  
  - **Depends on:** M6-T04  
  - Drop oldest memories when over `max_context_tokens` (char estimate OK for v1).

- [ ] **M6-T06** — Integrate context into `BrainService.send_message()`  
  - **Files:** `maira/modules/brain/service.py`  
  - **Depends on:** M6-T05, M2-T10  
  - Prepend system message with memories before LLM call.

- [ ] **M6-T07** — Publish `ContextAssembled` event after assembly  
  - **Files:** `maira/modules/brain/context/__init__.py`  
  - **Depends on:** M6-T01, M6-T04  
  - For debug UI and logging.

- [ ] **M6-T08** — Optional debug panel in chat (dev toggle)  
  - **Files:** `maira/ui/views/chat/__init__.py`  
  - **Depends on:** M6-T07  
  - Collapsible list of injected memory titles; off by default.

- [ ] **M6-T09** — Unit tests for context assembly  
  - **Files:** `tests/unit/test_context_assembly.py`  
  - **Depends on:** M6-T05  
  - Mock recall; assert prompt contains/excludes memories.

- [ ] **M6-T10** — Regression check: streaming chat still works  
  - **Files:** `tests/integration/test_brain_streaming.py`  
  - **Depends on:** M6-T06, M1-T19  
  - Extend existing test with memory injection enabled.

- [ ] **M6-T11** — Manual E2E smoke test (M6 exit criteria)  
  - **Files:** —  
  - **Depends on:** M6-T08, M6-T09, M6-T10  
  - "My name is Alex" → "What's my name?" works.

---

## Milestone 7: Push-to-Talk Voice

> **Goal:** Speak to Maira offline; hear responses via Kokoro.  
> **Milestone depends on:** M1, M6  
> **Blocks:** M8

- [ ] **M7-T01** — Define `Voice` port (ABC)  
  - **Files:** `maira/core/interfaces/voice.py`  
  - **Depends on:** M0-T08  
  - `start_listening`, `stop_listening`, `speak`, `stop_speaking`, `mode`.

- [ ] **M7-T02** — Add voice config to `default.yaml`  
  - **Files:** `config/default.yaml`, `maira/app/settings.py`  
  - **Depends on:** M0-T04  
  - Keys: whisper model path, kokoro voice, audio device index.

- [ ] **M7-T03** — Implement audio stream capture/playback  
  - **Files:** `maira/infrastructure/speech/audio/stream.py`  
  - **Depends on:** M7-T02  
  - Record to buffer on hold; play WAV/audio bytes.

- [ ] **M7-T04** — Implement Whisper.cpp engine wrapper  
  - **Files:** `maira/infrastructure/speech/whisper/engine.py`  
  - **Depends on:** M7-T02  
  - `transcribe(audio_bytes) -> str`.

- [ ] **M7-T05** — Implement Kokoro TTS engine wrapper  
  - **Files:** `maira/infrastructure/speech/kokoro/engine.py`  
  - **Depends on:** M7-T02  
  - `synthesize(text) -> audio_bytes`.

- [ ] **M7-T06** — Implement STT submodule  
  - **Files:** `maira/modules/voice/stt/__init__.py`  
  - **Depends on:** M7-T04, M7-T03  
  - Push-to-talk: record → transcribe.

- [ ] **M7-T07** — Implement TTS submodule  
  - **Files:** `maira/modules/voice/tts/__init__.py`  
  - **Depends on:** M7-T05, M7-T03  
  - Synthesize and play; track speaking state.

- [ ] **M7-T08** — Implement `VoiceService` facade  
  - **Files:** `maira/modules/voice/service.py`  
  - **Depends on:** M7-T01, M7-T06, M7-T07  
  - PTT state machine: idle → recording → processing → speaking.

- [ ] **M7-T09** — Wire voice output to Brain (transcript → send_message)  
  - **Files:** `maira/modules/voice/service.py`  
  - **Depends on:** M7-T08, M6-T06  
  - On transcript: call Brain; on response complete: speak.

- [ ] **M7-T10** — Register VoiceService in container  
  - **Files:** `maira/app/container.py`, `maira/app/bootstrap.py`  
  - **Depends on:** M7-T09  
  - Init on startup; shutdown hook stops audio.

- [ ] **M7-T11** — Build voice view (mic button + status)  
  - **Files:** `maira/ui/views/voice/__init__.py`  
  - **Depends on:** M0-T13  
  - Hold-to-talk button; status: idle / listening / speaking.

- [ ] **M7-T12** — Implement `voice_controller.py`  
  - **Files:** `maira/ui/controllers/voice_controller.py`  
  - **Depends on:** M7-T10, M7-T11  
  - Mouse down/up on mic; update status label.

- [ ] **M7-T13** — Wire voice view into main window nav  
  - **Files:** `maira/ui/main_window/window.py`  
  - **Depends on:** M7-T12  
  - Sidebar Voice item works.

- [ ] **M7-T14** — Add PTT shortcut button to chat view  
  - **Files:** `maira/ui/views/chat/__init__.py`  
  - **Depends on:** M7-T12  
  - Small mic icon in chat toolbar.

- [ ] **M7-T15** — Audio error handling in UI  
  - **Files:** `maira/ui/controllers/voice_controller.py`  
  - **Depends on:** M7-T12  
  - No mic / engine failure → banner, no crash.

- [ ] **M7-T16** — Extend `setup_models.py` for Whisper + Kokoro  
  - **Files:** `scripts/setup_models.py`  
  - **Depends on:** M7-T04, M7-T05  
  - Verify model files exist; print setup instructions.

- [ ] **M7-T17** — Integration test: voice pipeline (optional hardware)  
  - **Files:** `tests/integration/test_voice_pipeline.py`  
  - **Depends on:** M7-T09  
  - Skip without models; mock audio if needed.

- [ ] **M7-T18** — Manual E2E smoke test (M7 exit criteria)  
  - **Files:** —  
  - **Depends on:** M7-T13, M7-T15, M7-T16  
  - PTT → transcript in chat → spoken response; works offline.

---

## Milestone 8: Wake Word & Interruptible Speech

> **Goal:** Hands-free wake word; interrupt TTS mid-sentence.  
> **Milestone depends on:** M7  
> **Blocks:** M15

- [ ] **M8-T01** — Add wake word config to `default.yaml`  
  - **Files:** `config/default.yaml`, `maira/app/settings.py`  
  - **Depends on:** M7-T02  
  - Keys: `wake_word`, `sensitivity`, `enabled`.

- [ ] **M8-T02** — Implement continuous listen mode in audio stream  
  - **Files:** `maira/infrastructure/speech/audio/stream.py`  
  - **Depends on:** M7-T03  
  - Background buffer for wake word detector.

- [ ] **M8-T03** — Implement wake word detection submodule  
  - **Files:** `maira/modules/voice/wake_word/__init__.py`  
  - **Depends on:** M8-T02, M8-T01  
  - Keyword spotting on audio stream; emit `voice.wake` event.

- [ ] **M8-T04** — Integrate wake word into VoiceService state machine  
  - **Files:** `maira/modules/voice/service.py`  
  - **Depends on:** M8-T03, M7-T08  
  - On wake → auto-start listening (no button hold).

- [ ] **M8-T05** — Implement interruptible TTS (stop on wake or mic press)  
  - **Files:** `maira/modules/voice/tts/__init__.py`, `maira/modules/voice/service.py`  
  - **Depends on:** M7-T07, M8-T04  
  - `stop_speaking()` within 500 ms.

- [ ] **M8-T06** — Add voice mode toggles to voice view  
  - **Files:** `maira/ui/views/voice/__init__.py`  
  - **Depends on:** M7-T11  
  - Radio/toggle: Off / Push-to-talk / Wake word.

- [ ] **M8-T07** — Wire mode toggles in voice controller  
  - **Files:** `maira/ui/controllers/voice_controller.py`  
  - **Depends on:** M8-T06, M8-T04  
  - Persist mode to config on change.

- [ ] **M8-T08** — Wake indicator UI (listening pulse)  
  - **Files:** `maira/ui/views/voice/__init__.py`  
  - **Depends on:** M8-T06  
  - Visual feedback when wake word detected.

- [ ] **M8-T09** — Unit tests for voice state machine  
  - **Files:** `tests/unit/test_wake_word_state_machine.py`  
  - **Depends on:** M8-T04  
  - Transitions: idle → wake → listen → speak → interrupt.

- [ ] **M8-T10** — Document CPU baseline for wake word in README  
  - **Files:** `README.md`  
  - **Depends on:** M8-T04  
  - Note idle CPU % on reference machine.

- [ ] **M8-T11** — Manual E2E smoke test (M8 exit criteria)  
  - **Files:** —  
  - **Depends on:** M8-T07, M8-T09  
  - Wake word activates; interrupt stops TTS; mode persists.

---

## Milestone 9: Security Gate

> **Goal:** Permission checks and confirmation before sensitive actions.  
> **Milestone depends on:** M0  
> **Blocks:** M10, M12

- [ ] **M9-T01** — Define `Security` port (ABC)  
  - **Files:** `maira/core/interfaces/security.py`  
  - **Depends on:** M0-T08  
  - `authorize(action) -> Allow | Deny | NeedsConfirmation`.

- [ ] **M9-T02** — Define `PermissionLevel` and `ActionRisk` value objects  
  - **Files:** `maira/core/domain/value_objects/__init__.py`  
  - **Depends on:** M0-T01  
  - Enums: safe, sensitive, dangerous.

- [ ] **M9-T03** — Define security domain events  
  - **Files:** `maira/core/domain/events/__init__.py`  
  - **Depends on:** M9-T02  
  - `DangerousActionRequested`, `ActionConfirmed`, `ActionDenied`.

- [ ] **M9-T04** — Write `004_audit_log.sql` migration  
  - **Files:** `maira/infrastructure/persistence/sqlite/migrations/004_audit_log.sql`  
  - **Depends on:** M2-T04  
  - Table: `audit_log` (action, timestamp, confirmed, details).

- [ ] **M9-T05** — Implement default permission policy  
  - **Files:** `maira/modules/security/permissions/__init__.py`  
  - **Depends on:** M9-T02  
  - Map action types to risk tiers.

- [ ] **M9-T06** — Implement `SecurityService.authorize()`  
  - **Files:** `maira/modules/security/service.py`  
  - **Depends on:** M9-T01, M9-T05  
  - Returns decision based on policy.

- [ ] **M9-T07** — Implement audit log writer  
  - **Files:** `maira/modules/security/service.py`  
  - **Depends on:** M9-T04, M9-T06  
  - Log confirmed and denied dangerous actions.

- [ ] **M9-T08** — Implement `confirm_dialog.py` widget  
  - **Files:** `maira/ui/widgets/confirm_dialog.py`  
  - **Depends on:** M0-T13  
  - Modal: description, Confirm / Cancel buttons.

- [ ] **M9-T09** — Implement confirmation flow submodule  
  - **Files:** `maira/modules/security/confirmation/__init__.py`  
  - **Depends on:** M9-T08, M9-T06  
  - Bridge service → Qt dialog on UI thread.

- [ ] **M9-T10** — Register SecurityService in container  
  - **Files:** `maira/app/container.py`, `maira/app/bootstrap.py`  
  - **Depends on:** M9-T09, M2-T08  
  - Available app-wide.

- [ ] **M9-T11** — Unit tests for security service  
  - **Files:** `tests/unit/test_security_service.py`  
  - **Depends on:** M9-T07  
  - All three tiers; audit log entries.

- [ ] **M9-T12** — Manual E2E smoke test (M9 exit criteria)  
  - **Files:** —  
  - **Depends on:** M9-T10, M9-T11  
  - Test action blocks until confirm; cancel logs deny.

---

## Milestone 10: Desktop Controller

> **Goal:** Open apps, URLs, search files, read documents via natural language.  
> **Milestone depends on:** M6, M9  
> **Blocks:** M12, M15

- [ ] **M10-T01** — Define `DesktopController` port (ABC)  
  - **Files:** `maira/core/interfaces/desktop.py`  
  - **Depends on:** M9-T01  
  - `open_app`, `open_url`, `search_files`, `read_document`.

- [ ] **M10-T02** — Add desktop config to `default.yaml`  
  - **Files:** `config/default.yaml`, `maira/app/settings.py`  
  - **Depends on:** M0-T04  
  - Keys: `allowed_apps`, `search_roots`.

- [ ] **M10-T03** — Implement Windows OS platform adapter  
  - **Files:** `maira/infrastructure/os/platform.py`  
  - **Depends on:** M10-T02  
  - `launch_app`, `open_url` via subprocess / `os.startfile`.

- [ ] **M10-T04** — Implement local filesystem adapter  
  - **Files:** `maira/infrastructure/filesystem/local.py`  
  - **Depends on:** M10-T02  
  - Walk search roots; glob by filename; read text files.

- [ ] **M10-T05** — Implement `read_document` for markdown and plain text  
  - **Files:** `maira/infrastructure/filesystem/local.py`  
  - **Depends on:** M10-T04  
  - Return file contents as string.

- [ ] **M10-T06** — Implement basic PDF text extraction  
  - **Files:** `maira/infrastructure/filesystem/local.py`  
  - **Depends on:** M10-T05  
  - Use lightweight PDF lib; handle failures gracefully.

- [ ] **M10-T07** — Implement desktop actions submodule  
  - **Files:** `maira/modules/desktop_controller/actions/__init__.py`  
  - **Depends on:** M10-T03, M10-T06  
  - One function per action; return structured result.

- [ ] **M10-T08** — Implement `DesktopControllerService` facade  
  - **Files:** `maira/modules/desktop_controller/service.py`  
  - **Depends on:** M10-T01, M10-T07, M9-T10  
  - Route non-read actions through `SecurityService`.

- [ ] **M10-T09** — Register DesktopController in container  
  - **Files:** `maira/app/container.py`, `maira/app/bootstrap.py`  
  - **Depends on:** M10-T08  
  - Inject security dependency.

- [ ] **M10-T10** — Add intent detection / tool dispatch to Brain  
  - **Files:** `maira/modules/brain/service.py`  
  - **Depends on:** M10-T09, M6-T06  
  - Parse commands or use simple keyword patterns for v1.

- [ ] **M10-T11** — Wire desktop results back into chat  
  - **Files:** `maira/ui/controllers/chat_controller.py`  
  - **Depends on:** M10-T10  
  - Display file lists and document contents as assistant messages.

- [ ] **M10-T12** — Unit tests for desktop actions (mocked OS)  
  - **Files:** `tests/unit/test_desktop_actions.py`  
  - **Depends on:** M10-T07  
  - Mock subprocess; test search and read.

- [ ] **M10-T13** — Integration test: desktop controller + security  
  - **Files:** `tests/integration/test_desktop_controller.py`  
  - **Depends on:** M10-T08  
  - Dangerous action requires confirmation mock.

- [ ] **M10-T14** — Manual E2E smoke test (M10 exit criteria)  
  - **Files:** —  
  - **Depends on:** M10-T11, M10-T13  
  - Open Notepad, open URL, find README, read file; cancel blocks execution.

---

## Milestone 11: Knowledge Base & Document Indexing

> **Goal:** Index local docs; answer questions via semantic search.  
> **Milestone depends on:** M5  
> **Blocks:** M15

- [ ] **M11-T01** — Define `KnowledgeBase` port (ABC)  
  - **Files:** `maira/core/interfaces/knowledge.py`  
  - **Depends on:** M5-T01  
  - `index_folder`, `search`, `get_index_status`.

- [ ] **M11-T02** — Add knowledge config to `default.yaml`  
  - **Files:** `config/default.yaml`, `maira/app/settings.py`  
  - **Depends on:** M5-T03  
  - Keys: `index_paths`, `chunk_size`, `chunk_overlap`.

- [ ] **M11-T03** — Create ChromaDB `documents` collection  
  - **Files:** `maira/infrastructure/vector/chromadb/collections.py`  
  - **Depends on:** M5-T05  
  - Separate from `memories` collection.

- [ ] **M11-T04** — Implement text chunking utility  
  - **Files:** `maira/modules/knowledge_base/indexing/__init__.py`  
  - **Depends on:** M11-T02  
  - Split by char/token count with overlap.

- [ ] **M11-T05** — Implement folder walk + file filter  
  - **Files:** `maira/modules/knowledge_base/indexing/__init__.py`  
  - **Depends on:** M10-T04, M11-T04  
  - Index `.md`, `.txt`, `.pdf` only.

- [ ] **M11-T06** — Implement embed + upsert pipeline for chunks  
  - **Files:** `maira/modules/knowledge_base/indexing/__init__.py`  
  - **Depends on:** M11-T05, M5-T06, M11-T03  
  - Store chunk id, source path, chunk index in metadata.

- [ ] **M11-T07** — Implement `KnowledgeBaseService` facade  
  - **Files:** `maira/modules/knowledge_base/service.py`  
  - **Depends on:** M11-T01, M11-T06  
  - `index_folder`, `search(query, k)`, status.

- [ ] **M11-T08** — Implement idempotent re-index (delete old chunks per file)  
  - **Files:** `maira/modules/knowledge_base/indexing/__init__.py`  
  - **Depends on:** M11-T06  
  - Hash file mtime; replace stale chunks.

- [ ] **M11-T09** — Register KnowledgeBaseService in container  
  - **Files:** `maira/app/container.py`, `maira/app/bootstrap.py`  
  - **Depends on:** M11-T07  
  - Available at startup.

- [ ] **M11-T10** — Add knowledge panel to settings or memory view  
  - **Files:** `maira/ui/views/settings/__init__.py` or `maira/ui/views/memory/__init__.py`  
  - **Depends on:** M11-T09  
  - Index path picker, Re-index button, status display.

- [ ] **M11-T11** — Wire knowledge search into Brain  
  - **Files:** `maira/modules/brain/service.py`  
  - **Depends on:** M11-T07, M6-T06  
  - On doc-related queries: search knowledge → inject passages.

- [ ] **M11-T12** — Integration test: knowledge indexing  
  - **Files:** `tests/integration/test_knowledge_indexing.py`  
  - **Depends on:** M11-T08  
  - Index temp folder; search returns correct source.

- [ ] **M11-T13** — Manual E2E smoke test (M11 exit criteria)  
  - **Files:** —  
  - **Depends on:** M11-T10, M11-T12  
  - Index 10+ files; ask question; correct file cited; re-index idempotent.

---

## Milestone 12: Workflow Automation

> **Goal:** Run multi-step workflows from a single command.  
> **Milestone depends on:** M10  
> **Blocks:** M15

- [ ] **M12-T01** — Define `Automation` port (ABC)  
  - **Files:** `maira/core/interfaces/automation.py`  
  - **Depends on:** M10-T01  
  - `list_workflows`, `run_workflow(name)`.

- [ ] **M12-T02** — Define workflow YAML schema  
  - **Files:** `maira/modules/automation/workflows/__init__.py`  
  - **Depends on:** M12-T01  
  - Fields: name, description, steps[{action, params}].

- [ ] **M12-T03** — Implement workflow YAML parser + validator  
  - **Files:** `maira/modules/automation/workflows/__init__.py`  
  - **Depends on:** M12-T02  
  - Reject invalid files with logged errors.

- [ ] **M12-T04** — Implement workflow step executor  
  - **Files:** `maira/modules/automation/workflows/__init__.py`  
  - **Depends on:** M12-T03, M10-T07  
  - Steps: `open_app`, `open_url`, `open_folder`, `delay`.

- [ ] **M12-T05** — Implement `AutomationService` facade  
  - **Files:** `maira/modules/automation/service.py`  
  - **Depends on:** M12-T04, M9-T10  
  - Confirm if workflow contains sensitive steps.

- [ ] **M12-T06** — Load workflows from `config/workflows/` and `assets/workflows/`  
  - **Files:** `maira/app/bootstrap.py`, `maira/modules/automation/service.py`  
  - **Depends on:** M12-T05  
  - Register at startup.

- [ ] **M12-T07** — Create bundled "start work" example workflow  
  - **Files:** `assets/workflows/start_work.yaml`  
  - **Depends on:** M12-T02  
  - 3 steps: open IDE, open folder, open URL.

- [ ] **M12-T08** — Add workflow config section to `default.yaml`  
  - **Files:** `config/default.yaml`  
  - **Depends on:** M12-T06  
  - Optional user workflow directory path.

- [ ] **M12-T09** — Wire workflow matching into Brain  
  - **Files:** `maira/modules/brain/service.py`  
  - **Depends on:** M12-T05, M6-T06  
  - Match user intent to workflow name/description.

- [ ] **M12-T10** — Report workflow progress/errors in chat  
  - **Files:** `maira/ui/controllers/chat_controller.py`  
  - **Depends on:** M12-T09  
  - Step-by-step status; abort message on failure.

- [ ] **M12-T11** — Unit tests for workflow parser  
  - **Files:** `tests/unit/test_workflow_parser.py`  
  - **Depends on:** M12-T03  
  - Valid/invalid YAML cases.

- [ ] **M12-T12** — Integration test: workflow execution  
  - **Files:** `tests/integration/test_workflow_execution.py`  
  - **Depends on:** M12-T05  
  - Mock desktop actions; assert step order.

- [ ] **M12-T13** — Manual E2E smoke test (M12 exit criteria)  
  - **Files:** —  
  - **Depends on:** M12-T10, M12-T12  
  - "Start my work environment" runs 3 steps after confirm.

---

## Milestone 13: Reminders & Daily Briefing

> **Goal:** Reminders with notifications; AI daily briefing on launch.  
> **Milestone depends on:** M3, M6  
> **Blocks:** M15

- [ ] **M13-T01** — Write `005_reminders.sql` migration  
  - **Files:** `maira/infrastructure/persistence/sqlite/migrations/005_reminders.sql`  
  - **Depends on:** M2-T04  
  - Table: `reminders` (title, datetime, repeat, enabled).

- [ ] **M13-T02** — Define `ReminderDue` domain event  
  - **Files:** `maira/core/domain/events/__init__.py`  
  - **Depends on:** M3-T02  
  - Payload: reminder id, title, due time.

- [ ] **M13-T03** — Implement reminder repository  
  - **Files:** `maira/infrastructure/persistence/sqlite/repositories/__init__.py`  
  - **Depends on:** M13-T01, M2-T05  
  - CRUD + query due reminders.

- [ ] **M13-T04** — Implement reminders submodule  
  - **Files:** `maira/modules/planner/reminders/__init__.py`  
  - **Depends on:** M13-T03  
  - Create one-shot and daily-repeat reminders.

- [ ] **M13-T05** — Implement background reminder timer  
  - **Files:** `maira/modules/planner/reminders/__init__.py`  
  - **Depends on:** M13-T04, M0-T08  
  - `QTimer` every 60 s; publish `ReminderDue`.

- [ ] **M13-T06** — Implement desktop notification on `ReminderDue`  
  - **Files:** `maira/ui/application.py` or `maira/modules/planner/reminders/__init__.py`  
  - **Depends on:** M13-T05  
  - Qt tray or system notification.

- [ ] **M13-T07** — Add reminders UI to planner view  
  - **Files:** `maira/ui/views/planner/__init__.py`, `maira/ui/controllers/planner_controller.py`  
  - **Depends on:** M13-T04, M3-T13  
  - List, add, delete reminders.

- [ ] **M13-T08** — Implement briefing data aggregator  
  - **Files:** `maira/modules/planner/briefing/__init__.py`  
  - **Depends on:** M3-T08, M13-T04, M4-T06  
  - Collect overdue todos, today's reminders, recent memories.

- [ ] **M13-T09** — Implement briefing LLM prompt + generation  
  - **Files:** `maira/modules/planner/briefing/__init__.py`, `maira/modules/brain/service.py`  
  - **Depends on:** M13-T08, M6-T06  
  - Structured data → natural language briefing.

- [ ] **M13-T10** — Show briefing panel in planner view  
  - **Files:** `maira/ui/views/planner/__init__.py`  
  - **Depends on:** M13-T09  
  - On-demand button + auto-show on first launch of day.

- [ ] **M13-T11** — Track last briefing date in config/data  
  - **Files:** `maira/modules/planner/briefing/__init__.py`  
  - **Depends on:** M13-T10  
  - Only auto-show once per calendar day.

- [ ] **M13-T12** — Unit tests for reminders  
  - **Files:** `tests/unit/test_reminders.py`  
  - **Depends on:** M13-T04  
  - CRUD, due detection logic.

- [ ] **M13-T13** — Unit tests for briefing aggregator  
  - **Files:** `tests/unit/test_briefing.py`  
  - **Depends on:** M13-T08  
  - Mock planner/memory data; assert summary shape.

- [ ] **M13-T14** — Manual E2E smoke test (M13 exit criteria)  
  - **Files:** —  
  - **Depends on:** M13-T07, M13-T10, M13-T12  
  - Reminder fires; briefing shows todos + memories.

---

## Milestone 14: Plugin System MVP

> **Goal:** Load external plugins with hooks into Brain and Planner.  
> **Milestone depends on:** M0, M1  
> **Blocks:** M15

- [ ] **M14-T01** — Define `Plugin` port (ABC)  
  - **Files:** `maira/core/interfaces/plugin.py`  
  - **Depends on:** M0-T08  
  - `name`, `version`, `register_hooks(registry)`.

- [ ] **M14-T02** — Implement plugin manifest schema  
  - **Files:** `maira/plugins/api/manifest.py`  
  - **Depends on:** M14-T01  
  - Parse `plugin.yaml`; validate required fields.

- [ ] **M14-T03** — Implement hook registry API  
  - **Files:** `maira/plugins/api/hooks.py`  
  - **Depends on:** M14-T01  
  - Decorators: `on_message_received`, `on_message_completed`, `on_todo_created`.

- [ ] **M14-T04** — Implement plugin loader  
  - **Files:** `maira/plugins/manager/loader.py`  
  - **Depends on:** M14-T02  
  - Scan `plugins_external/`; import entry point.

- [ ] **M14-T05** — Implement plugin registry  
  - **Files:** `maira/plugins/manager/registry.py`  
  - **Depends on:** M14-T03, M14-T04  
  - Track loaded plugins and hook bindings.

- [ ] **M14-T06** — Implement plugin lifecycle (activate/deactivate)  
  - **Files:** `maira/plugins/manager/lifecycle.py`  
  - **Depends on:** M14-T05  
  - Load on bootstrap; unregister on shutdown.

- [ ] **M14-T07** — Validate `maira_api` version compatibility  
  - **Files:** `maira/plugins/manager/loader.py`  
  - **Depends on:** M14-T04  
  - Skip incompatible plugins with error log.

- [ ] **M14-T08** — Wire Brain hooks into message pipeline  
  - **Files:** `maira/modules/brain/service.py`  
  - **Depends on:** M14-T05, M1-T10  
  - Call hooks before/after LLM response.

- [ ] **M14-T09** — Wire Planner hooks into todo creation  
  - **Files:** `maira/modules/planner/todos/__init__.py`  
  - **Depends on:** M14-T05, M3-T06  
  - Call `on_todo_created` after insert.

- [ ] **M14-T10** — Register plugin manager in bootstrap  
  - **Files:** `maira/app/bootstrap.py`, `maira/app/container.py`  
  - **Depends on:** M14-T06  
  - Load plugins after core services.

- [ ] **M14-T11** — Create builtin example plugin  
  - **Files:** `maira/plugins/builtin/example_greeting/`  
  - **Depends on:** M14-T03  
  - Logs or prefixes greeting on `on_message_received`.

- [ ] **M14-T12** — Implement `scripts/create_plugin.py`  
  - **Files:** `scripts/create_plugin.py`  
  - **Depends on:** M14-T02  
  - Copy `_template` to `plugins_external/<name>`.

- [ ] **M14-T13** — Integration test: plugin loading  
  - **Files:** `tests/integration/test_plugin_loading.py`  
  - **Depends on:** M14-T10  
  - Load test plugin; assert hook fired; invalid manifest skipped.

- [ ] **M14-T14** — Manual E2E smoke test (M14 exit criteria)  
  - **Files:** —  
  - **Depends on:** M14-T11, M14-T12, M14-T13  
  - Drop plugin in folder → loads on restart; `create_plugin.py` works.

---

## Milestone 15: Settings, Integration & V1 Polish

> **Goal:** Cohesive V1 product with settings UI and full subsystem wiring.  
> **Milestone depends on:** M8, M10, M11, M12, M13, M14  
> **Blocks:** —

- [ ] **M15-T01** — Build settings view shell (sidebar sections)  
  - **Files:** `maira/ui/views/settings/__init__.py`  
  - **Depends on:** M0-T13  
  - Sections: General, Ollama, Voice, Memory, Security, Plugins.

- [ ] **M15-T02** — Settings panel: Ollama (host, model)  
  - **Files:** `maira/ui/views/settings/__init__.py`  
  - **Depends on:** M15-T01, M1-T04  
  - Editable fields; save to user config.

- [ ] **M15-T03** — Settings panel: Voice (mode, wake word)  
  - **Files:** `maira/ui/views/settings/__init__.py`  
  - **Depends on:** M15-T01, M8-T01  
  - Mirror voice view toggles.

- [ ] **M15-T04** — Settings panel: Memory & knowledge index paths  
  - **Files:** `maira/ui/views/settings/__init__.py`  
  - **Depends on:** M15-T01, M11-T02  
  - Index path list; link to re-index.

- [ ] **M15-T05** — Settings panel: Security (confirm toggles)  
  - **Files:** `maira/ui/views/settings/__init__.py`  
  - **Depends on:** M15-T01, M9-T05  
  - Toggle confirmation for sensitive vs dangerous.

- [ ] **M15-T06** — Settings panel: Plugins (list, enable/disable)  
  - **Files:** `maira/ui/views/settings/__init__.py`  
  - **Depends on:** M15-T01, M14-T05  
  - Show loaded plugins from registry.

- [ ] **M15-T07** — Implement `settings_controller.py`  
  - **Files:** `maira/ui/controllers/settings_controller.py`  
  - **Depends on:** M15-T02, M15-T03, M15-T04, M15-T05, M15-T06  
  - Load/save all panels; persist across restart.

- [ ] **M15-T08** — Wire settings view into main window nav  
  - **Files:** `maira/ui/main_window/window.py`  
  - **Depends on:** M15-T07  
  - Settings sidebar item works.

- [ ] **M15-T09** — Add status bar to main window  
  - **Files:** `maira/ui/main_window/window.py`  
  - **Depends on:** M0-T13  
  - Placeholders for subsystem indicators.

- [ ] **M15-T10** — Status bar: Ollama connection indicator  
  - **Files:** `maira/ui/main_window/window.py`  
  - **Depends on:** M15-T09, M1-T05  
  - Green/red dot; poll on timer.

- [ ] **M15-T11** — Status bar: voice mode + offline badge  
  - **Files:** `maira/ui/main_window/window.py`  
  - **Depends on:** M15-T09, M8-T07  
  - Show current voice mode; "Offline" when no network needed badge.

- [ ] **M15-T12** — Status bar: plugin count  
  - **Files:** `maira/ui/main_window/window.py`  
  - **Depends on:** M15-T09, M14-T05  
  - Show N plugins loaded.

- [ ] **M15-T13** — Final DI container wiring for all services  
  - **Files:** `maira/app/container.py`, `maira/app/bootstrap.py`  
  - **Depends on:** M14-T10, M13-T05, M12-T06, M11-T09, M10-T09, M9-T10, M8-T04, M7-T10, M6-T06, M5-T07, M4-T07, M3-T09, M2-T08  
  - Single bootstrap path registers every module.

- [ ] **M15-T14** — Subsystem error boundaries (graceful degradation)  
  - **Files:** `maira/app/bootstrap.py`, module services  
  - **Depends on:** M15-T13  
  - Voice/ollama/embedder failure → disable feature, app still runs.

- [ ] **M15-T15** — Finalize `config/default.yaml` schema  
  - **Files:** `config/default.yaml`  
  - **Depends on:** M15-T13  
  - Document all keys; sensible defaults.

- [ ] **M15-T16** — UI test: main window loads all views  
  - **Files:** `tests/ui/test_main_window.py`  
  - **Depends on:** M15-T08  
  - pytest-qt: nav to each view without error.

- [ ] **M15-T17** — Integration test: full startup  
  - **Files:** `tests/integration/test_full_startup.py`  
  - **Depends on:** M15-T13  
  - Bootstrap completes; all services resolvable.

- [ ] **M15-T18** — End-to-end smoke test script/checklist  
  - **Files:** —  
  - **Depends on:** M15-T14  
  - Manual: launch → chat → save memory → voice → workflow → briefing.

- [ ] **M15-T19** — Write README (install, prerequisites, features)  
  - **Files:** `README.md`  
  - **Depends on:** M15-T18  
  - Ollama, Whisper, Kokoro, embedding model setup steps.

- [ ] **M15-T20** — V1 completion audit against VISION.md  
  - **Files:** `docs/DEVELOPMENT_ROADMAP.md`  
  - **Depends on:** M15-T18, M15-T19  
  - Check off every V1 Completion Checklist item.

---

## Task Count Summary

| Milestone | Tasks |
|---|---|
| M0 App Shell | 16 |
| M1 Offline Chat | 20 |
| M2 Conversation Persistence | 15 |
| M3 Todos & Notes | 15 |
| M4 Structured Memory | 13 |
| M5 Semantic Memory | 15 |
| M6 Context-Aware Brain | 11 |
| M7 Push-to-Talk Voice | 18 |
| M8 Wake Word | 11 |
| M9 Security Gate | 12 |
| M10 Desktop Controller | 14 |
| M11 Knowledge Base | 13 |
| M12 Workflow Automation | 13 |
| M13 Reminders & Briefing | 14 |
| M14 Plugin System | 14 |
| M15 V1 Polish | 20 |
| **Total** | **234** |

---

*Derived from [DEVELOPMENT_ROADMAP.md](./DEVELOPMENT_ROADMAP.md). Each task is scoped for < 2 hours.*
