# Memory Architecture

## Hot path (chat)

```
User message
  → keyword recall (fast; default recall_mode=keyword)
  → Brain / Ollama stream
  → UI
  → MemoryWorker enqueue (background)
```

Semantic encode no longer blocks LLM when `memory.background_encoding: true`.

## MemoryWorker

- Thread-safe queue
- Policy filters greetings / noise
- Stores explicit remember / preferences
- Failures are logged; conversation continues

## Policy candidates

- Explicit “remember …”
- Preferences (“I prefer…”, “call me…”)
- Not: hi/thanks/ok short noise

## Config

```yaml
memory:
  background_encoding: true
  recall_mode: keyword   # or semantic
```
