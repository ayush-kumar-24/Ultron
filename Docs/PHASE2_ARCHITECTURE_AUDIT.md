# Phase 2 Architecture Audit

**Date:** 2026-08-14  
**Scope:** Voice + real-time conversation + memory performance (preserve chat)

## 1. Existing architecture

```
ChatView / ProtoChatBridge
  → BrainService → ContextAssembler → OllamaClient → llama3.2
  → TokenStreamer / EventBus → UI streaming
```

Chat already has: reusable HTTP client, keep_alive, history window, latency logs, Maira identity prompt, retry.

## 2. Existing voice components (REUSE)

| Component | Path | Status |
|-----------|------|--------|
| VoiceService | `maira/modules/voice/service.py` | PTT + continuous loop |
| SpeechToText | `maira/modules/voice/stt/` | faster-whisper |
| TextToSpeech | `maira/modules/voice/tts/` | Kokoro stream play |
| AudioStream | `maira/infrastructure/speech/audio/stream.py` | Mic + playback + cancel |
| ProtoVoiceBridge | `maira/ui/prototype/integration/voice_bridge.py` | Live Chat voice |
| Wake word | `maira/modules/voice/wake_word/` | Stub only |

## 3. Memory

- Text chat **blocks** on `memory.recall()` → embedding encode before Ollama
- Voice turns already skip memory recall (`voice=True`)
- Writes encode on store/update

## 4. Threading

- Chat/PTT: `run_in_thread` (QThread)
- Continuous voice: daemon `threading.Thread`
- EventBus: sync handlers on publisher thread; UI uses QueuedConnection

## 5. UI

- Bootstrap launches **PrototypeWindow** (not legacy MainWindow)
- Voice UX lives in Chat `VoiceStage` + mic toggle

## 6. Current bottlenecks (voice)

1. **Wait for full LLM reply before TTS** (biggest UX gap)
2. STT after full utterance (expected for PTT)
3. Text-chat semantic encode on critical path
4. No AudioQueue / barge-in beyond `sd.stop()`

## 7. Reuse vs modify vs untouched

**Reuse:** BrainService, OllamaClient, EventBus, VoiceService shell, Whisper, Kokoro, AudioStream, Proto bridges, chat latency tooling.

**Modify:** VoiceService (stream LLM→chunker→TTS), Brain text memory path (non-blocking), config/settings, voice_lab download gates.

**Do not touch:** Chat streaming protocol, Ollama model choice (llama3.2), voice_lab as product Brain.

## 8. Phase 2 build plan (this delivery)

1. Provider interfaces + registry + download size guard  
2. TextChunker + AudioQueue + voice latency telemetry  
3. Streaming speak-while-generate in VoiceService  
4. MemoryWorker + policy (chat unblocked)  
5. WakeWordProvider stub, PTT shortcut, docs, tests, benchmarks  

## 9. Resource policy

- `max_model_download_gb: 1` — refuse automatic multi-GB downloads  
- Only selected TTS/STT provider active  
- No Veena / Indic Parler / Chatterbox auto-init in app
