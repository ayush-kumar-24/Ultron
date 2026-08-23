"""Unit tests for text chunker, audio queue, download guard, memory policy."""

from __future__ import annotations

import numpy as np
import pytest

from maira.core.bus.event_bus import EventBus
from maira.core.domain.entities import Conversation, Message
from maira.core.domain.value_objects import MessageRole
from maira.core.interfaces.brain import Brain
from maira.core.interfaces.voice import VoiceStatus
from maira.modules.memory.policy import MemoryPolicy
from maira.modules.memory.worker import MemoryWorker
from maira.modules.voice.audio.queue import AudioQueue
from maira.modules.voice.download_guard import ModelDownloadBlocked, assert_download_allowed
from maira.modules.voice.service import TOPIC_STATUS, VoiceService
from maira.modules.voice.streaming.chunker import TextChunker
from maira.modules.voice.tts.registry import create_tts, ensure_default_tts_providers
from maira.modules.brain.streaming import TOPIC_COMPLETE, TOPIC_TOKEN


def test_text_chunker_sentence_boundaries() -> None:
  chunker = TextChunker(min_chars=8, max_chars=80)
  out = chunker.push("Maira can help you plan your day. ")
  out += chunker.push("First, let's look at your tasks.")
  out += chunker.flush()
  assert any("plan your day" in c for c in out)
  assert any("tasks" in c for c in out)
  assert not any(c == "Maira" for c in out)


def test_audio_queue_cancel_clears() -> None:
  q = AudioQueue()
  q.put("one")
  q.put("two")
  q.cancel_all()
  assert q.cancelled is True
  assert q.get(timeout=0.05) is None
  q.reset()
  assert q.cancelled is False
  q.put("three")
  item = q.get(timeout=0.2)
  assert item is not None
  assert item.text == "three"


def test_download_guard_blocks_large_models() -> None:
  with pytest.raises(ModelDownloadBlocked):
    assert_download_allowed(estimated_gb=3.75, max_gb=1.0, provider="indic_parler", allow=False)


def test_heavy_tts_providers_unavailable_by_policy() -> None:
  ensure_default_tts_providers()
  provider = create_tts("veena", max_model_download_gb=1.0)
  ok, msg = provider.is_available()
  assert ok is False
  assert "disabled by the current local resource policy" in msg


def test_memory_policy_filters_noise() -> None:
  policy = MemoryPolicy()
  assert policy.evaluate("hi", role="user").should_store is False
  assert policy.evaluate("Remember that my name is Ayush", role="user").should_store is True
  assert policy.evaluate("I prefer dark mode always", role="user").should_store is True


def test_memory_worker_does_not_raise_on_failure() -> None:
  class BoomMemory:
    def store(self, **kwargs):  # noqa: ANN003
      raise RuntimeError("encode failed")

  worker = MemoryWorker(BoomMemory(), MemoryPolicy(min_chars=1))  # type: ignore[arg-type]
  worker.start()
  worker.enqueue("Remember that my favorite color is blue", role="user")
  import time

  time.sleep(0.3)
  worker.stop()


class _StreamingBrain(Brain):
  def __init__(self, bus: EventBus, reply: str) -> None:
    self._bus = bus
    self._reply = reply
    self.history: list[Message] = []
    self.sent: list[str] = []

  def send_message(self, text: str, **kwargs) -> None:  # noqa: ANN003
    del kwargs
    self.sent.append(text)
    self.history.append(Message(role=MessageRole.USER, content=text))
    for token in self._reply.split(" "):
      self._bus.publish(TOPIC_TOKEN, {"token": token + " "})
    self.history.append(Message(role=MessageRole.ASSISTANT, content=self._reply))
    self._bus.publish(TOPIC_COMPLETE, {"content": self._reply})

  def get_history(self) -> list[Message]:
    return list(self.history)

  def list_conversations(self) -> list[Conversation]:
    return []

  def new_conversation(self) -> Conversation:
    raise NotImplementedError

  def open_conversation(self, conversation_id: str) -> Conversation:
    raise NotImplementedError

  def get_active_conversation(self) -> Conversation:
    raise NotImplementedError


def test_voice_streaming_chunk_speak_and_interrupt() -> None:
  bus = EventBus()
  brain = _StreamingBrain(bus, "Maira can help you plan your day. First look at tasks.")
  spoken: list[str] = []

  class Audio:
    def is_available(self) -> bool:
      return True

    def start_recording(self) -> None:
      return

    def stop_recording(self):
      return np.ones(800, dtype="float32")

    def play(self, *a, **k) -> None:
      return

    def stop_playback(self) -> None:
      return

    def request_cancel(self) -> None:
      return

    def clear_cancel(self) -> None:
      return

  class STT:
    def is_available(self) -> bool:
      return True

    def transcribe(self, audio) -> str:
      return "hello maira"

  class TTS:
    def __init__(self) -> None:
      self.speaking = False
      self.stopped = 0

    def is_available(self) -> bool:
      return True

    def speak(self, text: str) -> None:
      self.speaking = True
      spoken.append(text)
      self.speaking = False

    def stop(self) -> None:
      self.stopped += 1
      self.speaking = False

  statuses: list[str] = []
  bus.subscribe(TOPIC_STATUS, lambda p: statuses.append(p["status"]))
  voice = VoiceService(brain=brain, event_bus=bus, audio=Audio(), stt=STT(), tts=TTS())
  voice.start_listening()
  voice.stop_listening()
  assert spoken
  assert "thinking" in statuses or "processing" in statuses
  assert "speaking" in statuses

  voice._set_status(VoiceStatus.SPEAKING)  # noqa: SLF001
  voice.start_listening()
  assert voice.status() in (VoiceStatus.LISTENING, VoiceStatus.INTERRUPTED)
  voice.stop_conversation()
  voice.shutdown()
