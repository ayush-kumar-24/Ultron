"""Voice facade — automated conversation loop + push-to-talk + streaming TTS."""

from __future__ import annotations

import threading
import time

from loguru import logger

from maira.core.bus.event_bus import EventBus
from maira.core.interfaces.brain import Brain
from maira.core.interfaces.voice import Voice, VoiceStatus
from maira.infrastructure.speech.audio.stream import AudioStream
from maira.modules.brain.streaming import TOPIC_COMPLETE, TOPIC_ERROR as BRAIN_ERROR, TOPIC_TOKEN
from maira.modules.voice.audio.queue import AudioQueue
from maira.modules.voice.latency import VoiceLatencyTrace
from maira.modules.voice.streaming.chunker import TextChunker
from maira.modules.voice.stt import SpeechToText
from maira.modules.voice.tts import TextToSpeech

TOPIC_STATUS = "voice.status"
TOPIC_TRANSCRIPT = "voice.transcript"
TOPIC_DICTATION = "voice.dictation"
TOPIC_ERROR = "voice.error"
TOPIC_REPLY = "voice.reply"
TOPIC_LATENCY = "voice.latency"


class VoiceService(Voice):
  def __init__(
    self,
    brain: Brain,
    event_bus: EventBus,
    audio: AudioStream,
    stt: SpeechToText,
    tts: TextToSpeech,
    *,
    silence_seconds: float = 0.9,
    max_reply_tokens: int = 64,
    chunk_min_chars: int = 12,
    chunk_max_chars: int = 160,
    interrupt_on_speech: bool = True,
    auto_speak: bool = True,
  ) -> None:
    self._brain = brain
    self._bus = event_bus
    self._audio = audio
    self._stt = stt
    self._tts = tts
    self._silence_seconds = silence_seconds
    self._max_reply_tokens = max_reply_tokens
    self._interrupt_on_speech = interrupt_on_speech
    self._auto_speak = auto_speak
    self._chunker = TextChunker(min_chars=chunk_min_chars, max_chars=chunk_max_chars)
    self._speech_queue = AudioQueue()
    self._status = VoiceStatus.IDLE
    self._lock = threading.Lock()
    self._conversation_active = False
    self._in_conversation_mode = False
    self._warmed = False
    self._generation = 0
    self._tts_stop = threading.Event()
    self._tts_thread: threading.Thread | None = None
    self._llm_done = threading.Event()
    self._spoken_any = False
    self._last_latency: VoiceLatencyTrace | None = None

  def is_available(self) -> bool:
    return self._audio.is_available() and self._stt.is_available() and self._tts.is_available()

  def status(self) -> VoiceStatus:
    return self._status

  def last_latency(self) -> VoiceLatencyTrace | None:
    return self._last_latency

  def start_listening(self) -> None:
    """Begin push-to-talk recording (manual stop via stop_listening)."""
    with self._lock:
      if self._status == VoiceStatus.LISTENING:
        return
      if self._status == VoiceStatus.SPEAKING or getattr(self._tts, "speaking", False):
        self._barge_in()
      if not self._audio.is_available():
        self._publish_error("Ultron can't access your microphone.")
        return
      try:
        self._audio.start_recording()
      except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to start recording")
        self._publish_error("Ultron can't access your microphone.")
        logger.debug("Mic start detail: {}", exc)
        return
      self._set_status(VoiceStatus.LISTENING)
      logger.info("[MAIRA VOICE] state=LISTENING")

  def stop_listening(self) -> None:
    """Stop recording, transcribe, send to Brain, and speak the reply."""
    with self._lock:
      if self._status != VoiceStatus.LISTENING:
        return
      self._set_status(VoiceStatus.TRANSCRIBING)

    try:
      audio = self._audio.stop_recording()
    except Exception as exc:  # noqa: BLE001
      logger.exception("Failed to stop recording")
      self._publish_error(f"Could not capture audio: {exc}")
      self._set_status(VoiceStatus.IDLE)
      return

    self._process_audio(audio, soft_empty=False, voice_mode=True)

  def start_dictation(self) -> None:
    """ChatGPT-style dictate: record only; stop_dictation fills the chat box."""
    if self._conversation_active:
      self.stop_conversation()
    self.start_listening()

  def stop_dictation(self) -> None:
    """Stop mic, transcribe into TOPIC_DICTATION — no Brain, no TTS."""
    with self._lock:
      if self._status != VoiceStatus.LISTENING:
        return
      self._set_status(VoiceStatus.TRANSCRIBING)

    try:
      audio = self._audio.stop_recording()
    except Exception as exc:  # noqa: BLE001
      logger.exception("Failed to stop dictation recording")
      self._publish_error(f"Could not capture audio: {exc}")
      self._set_status(VoiceStatus.IDLE)
      return

    logger.info("[MAIRA VOICE] state=DICTATING")
    self._bus.publish(TOPIC_STATUS, {"status": VoiceStatus.TRANSCRIBING.value})
    try:
      transcript = self._stt.transcribe(audio).strip()
    except Exception as exc:  # noqa: BLE001
      logger.exception("Dictation transcription failed")
      self._publish_error("Ultron can't access speech recognition right now.")
      logger.debug("Dictation STT detail: {}", exc)
      self._set_status(VoiceStatus.IDLE)
      return

    self._bus.publish(TOPIC_DICTATION, {"text": transcript})
    if not transcript:
      self._publish_error("No speech detected. Try speaking again.")
    self._set_status(VoiceStatus.IDLE)

  def cancel_dictation(self) -> None:
    """Stop recording without transcribing."""
    with self._lock:
      if self._status != VoiceStatus.LISTENING:
        self._set_status(VoiceStatus.IDLE)
        return
    try:
      self._audio.stop_recording()
    except Exception:  # noqa: BLE001
      pass
    self._set_status(VoiceStatus.IDLE)

  def start_conversation(self) -> None:
    """Hands-free loop: listen → silence ends turn → short reply → listen again."""
    if self._conversation_active:
      return
    if not self.is_available():
      self._publish_error(
        'Voice is unavailable. Install extras with: pip install -e ".[voice]"'
      )
      return

    self._in_conversation_mode = True
    self._conversation_active = True
    self._audio.clear_cancel()
    threading.Thread(
      target=self._conversation_loop,
      name="maira-voice-convo",
      daemon=True,
    ).start()

  def stop_conversation(self) -> None:
    """Leave continuous conversation; interrupt mic/TTS."""
    self._conversation_active = False
    self._in_conversation_mode = False
    self._audio.request_cancel()
    self._interrupt_playback()
    try:
      if self._status == VoiceStatus.LISTENING:
        self._audio.stop_recording()
    except Exception:  # noqa: BLE001
      pass
    self._set_status(VoiceStatus.IDLE)

  def announce(self, text: str) -> bool:
    """Speak text in the background (e.g. the daily briefing).

    Skipped when voice is unavailable or the user is mid-conversation.
    """
    if not text.strip():
      return False
    if not self._tts.is_available():
      logger.warning('Not speaking: voice model unavailable (pip install -e ".[voice]")')
      return False
    if not self._audio.is_available():
      logger.warning("Not speaking: no audio output (sounddevice missing or no speaker)")
      return False
    busy = {
      VoiceStatus.LISTENING,
      VoiceStatus.TRANSCRIBING,
      VoiceStatus.THINKING,
      VoiceStatus.PROCESSING,
      VoiceStatus.SPEAKING,
    }
    if self._status in busy or self._conversation_active:
      logger.info("Not speaking: voice is busy ({})", self._status.value)
      return False
    logger.info("Speaking announcement ({} chars)", len(text))

    def _speak() -> None:
      try:
        self._tts.speak(text)
      except Exception:  # noqa: BLE001
        logger.exception("Announcement speech failed")

    threading.Thread(target=_speak, name="ultron-announce", daemon=True).start()
    return True

  def stop_speaking(self) -> None:
    self._interrupt_playback()
    if self._status in (VoiceStatus.SPEAKING, VoiceStatus.INTERRUPTED):
      self._set_status(VoiceStatus.IDLE)

  def shutdown(self) -> None:
    self.stop_conversation()
    self._tts_stop.set()
    self._speech_queue.cancel_all()
    try:
      self._tts.stop()
    except Exception:  # noqa: BLE001
      pass
    if self._tts_thread and self._tts_thread.is_alive():
      self._tts_thread.join(timeout=1.5)
    self._tts_thread = None

  def _barge_in(self) -> None:
    logger.info("[MAIRA VOICE] state=INTERRUPTED")
    self._set_status(VoiceStatus.INTERRUPTED)
    self._interrupt_playback()

  def _interrupt_playback(self) -> None:
    self._generation += 1
    self._speech_queue.cancel_all()
    try:
      self._tts.stop()
    except Exception:  # noqa: BLE001
      pass

  def warm_up_models(self) -> None:
    """Public warm-up for startup / live benchmarks (idempotent)."""
    self._warm_up()

  def _warm_up(self) -> None:
    if self._warmed:
      return
    t0 = time.perf_counter()
    try:
      self._stt.warm_up()
      self._tts.warm_up()
      self._warmed = True
      logger.info("Voice models warmed in {:.2f}s", time.perf_counter() - t0)
    except Exception as exc:  # noqa: BLE001
      logger.warning("Voice warm-up failed: {}", exc)

  def _conversation_loop(self) -> None:
    logger.info("Voice conversation started")
    self._warm_up()
    while self._conversation_active:
      self._set_status(VoiceStatus.LISTENING)
      logger.info("[MAIRA VOICE] state=LISTENING")
      try:
        audio = self._audio.capture_utterance(
          silence_seconds=self._silence_seconds,
          should_stop=lambda: not self._conversation_active,
        )
      except Exception as exc:  # noqa: BLE001
        logger.exception("Utterance capture failed")
        if self._conversation_active:
          self._publish_error(f"Could not capture audio: {exc}")
        break

      if not self._conversation_active:
        break

      if audio is None or len(audio) == 0:
        continue

      if self._interrupt_on_speech and (
        self._status == VoiceStatus.SPEAKING or getattr(self._tts, "speaking", False)
      ):
        self._barge_in()

      self._set_status(VoiceStatus.TRANSCRIBING)
      self._process_audio(audio, soft_empty=True, voice_mode=True)

    self._conversation_active = False
    self._in_conversation_mode = False
    if self._status != VoiceStatus.ERROR:
      self._set_status(VoiceStatus.IDLE)
    logger.info("Voice conversation stopped")

  def _process_audio(self, audio, *, soft_empty: bool, voice_mode: bool) -> bool:
    """Transcribe → brain (streaming) → chunked TTS. Returns True when a reply was spoken."""
    trace = VoiceLatencyTrace()
    trace.mark("speech_end")
    self._last_latency = trace

    logger.info("[MAIRA VOICE] state=TRANSCRIBING")
    self._set_status(VoiceStatus.TRANSCRIBING)
    # Keep legacy "processing" signal for older UI subscribers
    self._bus.publish(TOPIC_STATUS, {"status": VoiceStatus.PROCESSING.value})

    trace.mark("stt_start")
    try:
      transcript = self._stt.transcribe(audio).strip()
    except Exception as exc:  # noqa: BLE001
      logger.exception("Transcription failed")
      self._publish_error("Ultron can't access speech recognition right now.")
      logger.debug("STT detail: {}", exc)
      self._set_status(VoiceStatus.IDLE)
      return False
    trace.mark("stt_complete")

    self._bus.publish(TOPIC_TRANSCRIPT, {"text": transcript})
    if not transcript:
      if soft_empty:
        self._set_status(VoiceStatus.IDLE)
        return False
      self._publish_error("No speech detected. Try speaking again.")
      self._set_status(VoiceStatus.IDLE)
      return False

    if not self._auto_speak:
      # Text-only path still uses brain; skip TTS
      return self._brain_only(transcript, voice_mode=voice_mode, soft_empty=soft_empty, trace=trace)

    return self._stream_reply(transcript, voice_mode=voice_mode, soft_empty=soft_empty, trace=trace)

  def _brain_only(
    self,
    transcript: str,
    *,
    voice_mode: bool,
    soft_empty: bool,
    trace: VoiceLatencyTrace,
  ) -> bool:
    del soft_empty
    self._set_status(VoiceStatus.THINKING)
    logger.info("[MAIRA VOICE] state=THINKING")
    trace.mark("brain_start")
    try:
      self._call_brain(transcript, voice_mode=voice_mode)
    except Exception as exc:  # noqa: BLE001
      logger.exception("Brain request from voice failed")
      self._publish_error(str(exc) or "Ultron can't reach the local AI model.")
      self._set_status(VoiceStatus.IDLE)
      return False
    reply = self._last_assistant_reply()
    if reply:
      self._bus.publish(TOPIC_REPLY, {"text": reply})
    trace.mark("complete")
    trace.log_summary()
    self._set_status(VoiceStatus.IDLE)
    return bool(reply)

  def _stream_reply(
    self,
    transcript: str,
    *,
    voice_mode: bool,
    soft_empty: bool,
    trace: VoiceLatencyTrace,
  ) -> bool:
    del soft_empty
    self._generation += 1
    gen = self._generation
    self._chunker.reset()
    self._speech_queue.reset()
    self._spoken_any = False
    self._llm_done.clear()
    reply_parts: list[str] = []
    brain_error: list[str] = []

    def on_token(payload: dict) -> None:
      if gen != self._generation:
        return
      token = str(payload.get("token", ""))
      if not token:
        return
      if trace.first_llm_token is None:
        trace.mark("first_llm_token")
      reply_parts.append(token)
      for sentence in self._chunker.push(token):
        if trace.first_sentence is None:
          trace.mark("first_sentence")
        self._enqueue_speech(sentence, gen, trace)

    def on_complete(payload: dict) -> None:
      if gen != self._generation:
        return
      content = str(payload.get("content", "")).strip()
      if content and not reply_parts:
        reply_parts.append(content)

    def on_brain_error(payload: dict) -> None:
      if gen != self._generation:
        return
      msg = str(payload.get("message", "")).strip()
      if msg:
        brain_error.append(msg)

    self._bus.subscribe(TOPIC_TOKEN, on_token)
    self._bus.subscribe(TOPIC_COMPLETE, on_complete)
    self._bus.subscribe(BRAIN_ERROR, on_brain_error)
    self._ensure_tts_worker()

    self._set_status(VoiceStatus.THINKING)
    logger.info("[MAIRA VOICE] state=THINKING")
    trace.mark("brain_start")
    try:
      self._call_brain(transcript, voice_mode=voice_mode)
    except Exception as exc:  # noqa: BLE001
      logger.exception("Brain request from voice failed")
      self._publish_error(str(exc) or "Ultron can't reach the local AI model.")
      self._set_status(VoiceStatus.IDLE)
      return False
    finally:
      self._bus.unsubscribe(TOPIC_TOKEN, on_token)
      self._bus.unsubscribe(TOPIC_COMPLETE, on_complete)
      self._bus.unsubscribe(BRAIN_ERROR, on_brain_error)
      for sentence in self._chunker.flush():
        if gen == self._generation:
          if trace.first_sentence is None:
            trace.mark("first_sentence")
          self._enqueue_speech(sentence, gen, trace)

    if brain_error:
      self._llm_done.set()
      self._publish_error(brain_error[0])
      self._set_status(VoiceStatus.IDLE)
      return False

    reply = "".join(reply_parts).strip() or self._last_assistant_reply()
    if not reply:
      self._llm_done.set()
      self._publish_error(
        "No reply received. Check that Ollama is running and a model is installed."
      )
      self._set_status(VoiceStatus.IDLE)
      return False

    if self._in_conversation_mode and not self._conversation_active:
      self._llm_done.set()
      self._set_status(VoiceStatus.IDLE)
      return False

    # Fakes / non-streaming brains: speak full reply if nothing was chunked.
    if not self._spoken_any and gen == self._generation:
      self._enqueue_speech(reply, gen, trace)

    self._llm_done.set()
    self._wait_speech_drain(gen, timeout=120.0)

    self._bus.publish(TOPIC_REPLY, {"text": reply})
    trace.mark("complete")
    trace.log_summary()
    self._bus.publish(
      TOPIC_LATENCY,
      {
        "stt": _fmt_delta(trace.stt_complete, trace.stt_start),
        "ttft": _fmt_delta(trace.first_llm_token, trace.brain_start),
        "tts_first_audio": _fmt_delta(trace.first_audio, trace.tts_start or trace.first_sentence),
        "total": _fmt_delta(trace.complete, trace.speech_end or trace.stt_start),
      },
    )

    if self._status == VoiceStatus.SPEAKING:
      self._set_status(VoiceStatus.IDLE)
    elif self._status not in (VoiceStatus.ERROR, VoiceStatus.LISTENING):
      self._set_status(VoiceStatus.IDLE)
    return True

  def _call_brain(self, transcript: str, *, voice_mode: bool) -> None:
    from maira.modules.voice.resource_guard import llm_cpu_priority, snapshot_resources

    resources = snapshot_resources()
    logger.info(
      "[MAIRA VOICE] pre_llm resources python_rss_mb={} cpu={} llama_hint={}",
      resources.get("python_rss_mb"),
      resources.get("cpu_percent"),
      resources.get("ollama_rss_mb"),
    )
    with llm_cpu_priority():
      try:
        if voice_mode:
          self._brain.send_message(
            transcript,
            voice=True,
            max_tokens=self._max_reply_tokens,
          )
        else:
          self._brain.send_message(transcript)
      except TypeError:
        self._brain.send_message(transcript)

  def _enqueue_speech(self, text: str, gen: int, trace: VoiceLatencyTrace) -> None:
    if gen != self._generation or not text.strip():
      return
    if trace.tts_start is None:
      trace.mark("tts_start")
    self._speech_queue.put(text, meta={"gen": gen})

  def _ensure_tts_worker(self) -> None:
    self._tts_stop.clear()
    if self._tts_thread and self._tts_thread.is_alive():
      return
    self._tts_thread = threading.Thread(
      target=self._tts_loop,
      name="maira-voice-tts",
      daemon=True,
    )
    self._tts_thread.start()

  def _tts_loop(self) -> None:
    """Play queue items; synthesize the next item while the current one plays."""
    can_pipeline = hasattr(self._tts, "synthesize_chunks") and hasattr(self._tts, "play_chunks")
    prepared: tuple[int, list] | None = None

    def _synth(text: str, gen: int) -> list | None:
      if gen != self._generation:
        return None
      chunks = self._tts.synthesize_chunks(text)
      if self._last_latency and self._last_latency.first_audio is None and chunks:
        self._last_latency.mark("first_audio")
      return chunks

    while not self._tts_stop.is_set():
      if not can_pipeline:
        item = self._speech_queue.get(timeout=0.25)
        if item is None:
          continue
        gen = int(item.meta.get("gen", -1))
        if gen != self._generation:
          continue
        self._set_status(VoiceStatus.SPEAKING)
        logger.info("[MAIRA VOICE] state=SPEAKING")
        try:
          if self._last_latency and self._last_latency.playback_start is None:
            self._last_latency.mark("playback_start")
          if self._last_latency and self._last_latency.first_audio is None:
            self._last_latency.mark("first_audio")
          self._tts.speak(item.text)
          self._spoken_any = True
        except Exception as exc:  # noqa: BLE001
          logger.exception("TTS failed")
          self._publish_error("I can still respond in text.")
          logger.debug("TTS detail: {}", exc)
          break
        continue

      if prepared is None:
        item = self._speech_queue.get(timeout=0.25)
        if item is None:
          continue
        gen = int(item.meta.get("gen", -1))
        if gen != self._generation:
          continue
        try:
          chunks = _synth(item.text, gen)
        except Exception as exc:  # noqa: BLE001
          logger.exception("TTS failed")
          self._publish_error("I can still respond in text.")
          logger.debug("TTS detail: {}", exc)
          break
        if not chunks:
          continue
        prepared = (gen, chunks)

      gen, chunks = prepared
      prepared = None
      if gen != self._generation:
        continue

      self._set_status(VoiceStatus.SPEAKING)
      logger.info("[MAIRA VOICE] state=SPEAKING")
      if self._last_latency and self._last_latency.playback_start is None:
        self._last_latency.mark("playback_start")

      play_error: list[BaseException] = []

      def _play() -> None:
        try:
          self._tts.play_chunks(chunks)
          self._spoken_any = True
        except BaseException as exc:  # noqa: BLE001
          play_error.append(exc)

      player = threading.Thread(target=_play, name="maira-voice-play", daemon=True)
      player.start()

      while player.is_alive() and not self._tts_stop.is_set():
        if prepared is None and gen == self._generation:
          nxt = self._speech_queue.get(timeout=0.05)
          if nxt is not None:
            ngen = int(nxt.meta.get("gen", -1))
            if ngen == self._generation:
              try:
                nchunks = _synth(nxt.text, ngen)
                if nchunks:
                  prepared = (ngen, nchunks)
              except Exception as exc:  # noqa: BLE001
                logger.exception("TTS prefetch failed")
                logger.debug("TTS prefetch detail: {}", exc)
        else:
          time.sleep(0.05)

      player.join(timeout=120.0)
      if play_error:
        self._publish_error("I can still respond in text.")
        break

  def _wait_speech_drain(self, gen: int, *, timeout: float) -> None:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
      if gen != self._generation:
        return
      speaking = bool(getattr(self._tts, "speaking", False))
      if self._llm_done.is_set() and self._speech_queue.empty() and not speaking:
        # Small settle for in-flight dequeue
        time.sleep(0.05)
        speaking = bool(getattr(self._tts, "speaking", False))
        if self._speech_queue.empty() and not speaking:
          return
      time.sleep(0.05)

  def _last_assistant_reply(self) -> str:
    history = self._brain.get_history()
    for message in reversed(history):
      role = message.role.value if hasattr(message.role, "value") else str(message.role)
      if role == "assistant" and message.content.strip():
        return message.content.strip()
    return ""

  def _set_status(self, status: VoiceStatus) -> None:
    self._status = status
    self._bus.publish(TOPIC_STATUS, {"status": status.value})

  def _publish_error(self, message: str) -> None:
    self._status = VoiceStatus.ERROR
    self._bus.publish(TOPIC_ERROR, {"message": message})
    self._bus.publish(TOPIC_STATUS, {"status": VoiceStatus.ERROR.value})


def _fmt_delta(end: float | None, start: float | None) -> float | None:
  if end is None or start is None:
    return None
  return round(end - start, 2)
