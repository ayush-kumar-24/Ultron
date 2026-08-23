"""End-to-end mock voice pipeline benchmark (no mic / no downloads).

Usage:
  python -m scripts.benchmark_voice_e2e
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

import numpy as np

from maira.core.bus.event_bus import EventBus
from maira.core.domain.entities import Conversation, Message
from maira.core.domain.value_objects import MessageRole
from maira.core.interfaces.brain import Brain
from maira.modules.brain.streaming import TOPIC_COMPLETE, TOPIC_TOKEN
from maira.modules.voice.service import VoiceService


class StreamingFakeBrain(Brain):
  def __init__(self, bus: EventBus, reply: str = "I can help you plan your day.") -> None:
    self._bus = bus
    self._reply = reply
    self.history: list[Message] = []

  def send_message(self, text: str, **kwargs) -> None:  # noqa: ANN003
    del kwargs
    self.history.append(Message(role=MessageRole.USER, content=text))
    # Simulate token stream
    for token in self._reply.split(" "):
      piece = token + " "
      self._bus.publish(TOPIC_TOKEN, {"token": piece})
      time.sleep(0.01)
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


class FakeAudio:
  def is_available(self) -> bool:
    return True

  def start_recording(self) -> None:
    return

  def stop_recording(self):
    return np.ones(1600, dtype="float32") * 0.1

  def play(self, audio, sample_rate=None) -> None:
    del audio, sample_rate
    time.sleep(0.02)

  def stop_playback(self) -> None:
    return

  def capture_utterance(self, **kwargs):  # noqa: ANN003
    del kwargs
    return np.ones(1600, dtype="float32") * 0.1

  def request_cancel(self) -> None:
    return

  def clear_cancel(self) -> None:
    return


class FakeSTT:
  def is_available(self) -> bool:
    return True

  def warm_up(self) -> None:
    return

  def transcribe(self, audio) -> str:
    del audio
    time.sleep(0.05)
    return "Hello Maira, what can you help me with?"


class FakeTTS:
  def __init__(self) -> None:
    self.spoken: list[str] = []
    self.speaking = False

  def is_available(self) -> bool:
    return True

  def warm_up(self) -> None:
    return

  def speak(self, text: str) -> None:
    self.speaking = True
    time.sleep(0.03)
    self.spoken.append(text)
    self.speaking = False

  def stop(self) -> None:
    self.speaking = False


def main() -> int:
  bus = EventBus()
  brain = StreamingFakeBrain(bus)
  voice = VoiceService(
    brain=brain,
    event_bus=bus,
    audio=FakeAudio(),
    stt=FakeSTT(),
    tts=FakeTTS(),
  )
  t0 = time.perf_counter()
  voice.start_listening()
  voice.stop_listening()
  total = time.perf_counter() - t0
  lat = voice.last_latency()
  print("VOICE E2E BENCHMARK (mock)")
  print("==========================")
  if lat:
    lat.log_summary()
  print(f"Wall total: {total:.2f}s")
  print(f"Spoken chunks: {len(getattr(voice._tts, 'spoken', []))}")  # noqa: SLF001
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
