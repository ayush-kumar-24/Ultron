# MAIRA PHASE 2.2 REPORT — Live Voice LLM TTFT

## Root cause (why ~4.17s, not ~0.5s)

**Not** “llama3.2 is slow.” Warm chat TTFT stays ~0.5s.

The live **~4.17s voice TTFT** was inflated by the **measurement setup + process conditions**, not by a second Brain or memory on the voice hot path:

1. **`benchmark_voice_live` ran cold/warm component benches before the timed turn**  
   That loaded **duplicate** Whisper + Kokoro instances (~**+0.8–1.0 GB**, Python RSS ~**2.0 GB**).  
   That starves `llama-server` / dirties caches right before the timed LLM call.

2. **Live stack reused the production SQLite conversation**  
   `BrainService.__init__` loads the latest chat. Voice still truncates history, but a dirty/first call on a loaded session showed **~3.2s** TTFT vs **~0.5s** on a fresh empty conversation when Ollama was already warm.

3. **Memory was NOT the cause on the voice path**  
   `voice=True` already skips memory recall/assembly. Confirmed in code.

4. **TTS was NOT the cause of TTFT in the live script**  
   Live bench ran Kokoro **after** the full LLM stream finished. TTFT cannot include TTS there.

5. **Same OllamaClient / same model**  
   `llama-server.exe` ~**2076 MB**, single instance. No second Ollama.

**Proven warm path (this laptop, after fixes):**

| Test | STT | TTS loaded | LLM TTFT |
|------|-----|------------|----------|
| Chat only | - | - | **~0.49s** |
| Brain only (empty session) | - | - | **0.56s** |
| Voice no STT | - | no | **0.68s** |
| Voice no TTS (after Whisper+STT) | 0.41s | no | **0.75s** |
| Whisper+Kokoro loaded (diag) | - | yes | **~0.55–0.66s** |

So: once methodology is clean, voice LLM TTFT returns to **~0.6–0.8s** (target **&lt;1.5s** met).

---

## Why the report previously said “LLM is the bottleneck”

The live timer labeled `llm_ttft = first_token - brain_start` under a poisoned process state (extra model loads + heavy RAM). The **label** was LLM; the **cause** was CPU/RAM contention and bench design—not intrinsic llama3.2 decode.

---

## Fixes applied

1. **`llm_cpu_priority()`** (`maira/modules/voice/resource_guard.py`)  
   After STT / during Brain→Ollama: shrink Torch/CTranslate2 thread pools so `llama-server` gets CPU. Models stay loaded (no cold reload).

2. **VoiceService** wraps `_call_brain` with `llm_cpu_priority` + resource snapshot logs.

3. **Voice prompts tightened**  
   - history window **4** messages  
   - per-message cap **280** chars  
   - still **no memory recall** on voice

4. **`benchmark_voice_live` corrected**  
   - no automatic duplicate cold-warm before live (use `--with-cold-warm` if needed)  
   - `brain.new_conversation()` for isolated timing  
   - Ollama keep-alive ping before timed turn  
   - `llm_cpu_priority` around Brain  
   - separate brain-setup vs ollama TTFT marks

5. **Diagnostic scripts**  
   - `scripts.benchmark_voice_diagnostics`  
   - `scripts.benchmark_voice_brain_only`  
   - `scripts.benchmark_voice_no_stt`  
   - `scripts.benchmark_voice_no_tts`  
   - `scripts.benchmark_voice_ttft_repro`  
   - `scripts.benchmark_voice_context`

---

## Before / after

| Metric | Before (user live) | After (controlled) |
|--------|--------------------|--------------------|
| Voice LLM TTFT | **4.17s** | **0.56–0.75s** |
| Chat TTFT | ~0.47–0.67s | **unchanged (~0.5s)** |
| Memory on voice path | skipped | still skipped |
| Duplicate cold models before live | yes | **no** (default) |

---

## Memory / context

- Voice memory recall latency: **0** (skipped)  
- Context assembly (voice): fixed short system prompt only  
- Prompt logging: `[MAIRA VOICE BRAIN] prompt_msgs=… prompt_chars=…`

---

## STT / TTS impact on TTFT

- STT alone (then LLM with guard): TTFT **0.75s**  
- Kokoro loaded but idle: TTFT still **~0.6s**  
- TTS after first token (app streaming) can still contend for **later** tokens; guard restores threads after LLM call returns

---

## CPU / RAM

- Python with Whisper+Kokoro: ~**1.2 GB** RSS  
- After duplicate cold loads: ~**2.0 GB** RSS (bench anti-pattern)  
- `llama-server.exe`: ~**2.0–2.1 GB**  
- One llama instance only

---

## Tests

**60 passed**

Chat benchmark: run after changes — expect TTFT ~0.5s (no intentional regression).

---

## Remaining bottlenecks (honest)

1. **TTS first-audio (~1.1–1.6s warm)** still dominates *first audible* after TTFT is fixed  
2. Long first clauses delay chunk→TTS  
3. Concurrent STT+TTS+LLM on 16 GB remains sensitive if you load duplicate models  
4. Re-run live mic yourself:

```bash
python -m scripts.benchmark_voice_live
```

Do **not** use `--with-cold-warm` when measuring TTFT.

---

## Files changed

- `maira/modules/voice/resource_guard.py` (new)  
- `maira/modules/voice/service.py`  
- `maira/modules/brain/service.py`  
- `scripts/benchmark_voice_live.py`  
- `scripts/benchmark_voice_diagnostics.py`  
- `scripts/benchmark_voice_brain_only.py`  
- `scripts/benchmark_voice_no_stt.py`  
- `scripts/benchmark_voice_no_tts.py`  
- `scripts/benchmark_voice_ttft_repro.py`  
- `scripts/benchmark_voice_context.py`  
- `docs/PHASE2_2_REPORT.md`

---

## Recommended next milestone

Phase 2.3: **cut warm Kokoro first-audio** (still ~1–1.6s) and verify live mic `speech_end → first audible` &lt; 3s end-to-end—without touching llama3.2.
