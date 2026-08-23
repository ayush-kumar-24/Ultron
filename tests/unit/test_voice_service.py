"""Unit tests for VoiceService push-to-talk pipeline with fakes."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pytest

from maira.core.bus.event_bus import EventBus
from maira.core.domain.entities import Conversation, Message
from maira.core.domain.value_objects import MessageRole
from maira.core.interfaces.brain import Brain
from maira.core.interfaces.voice import VoiceStatus
from maira.modules.voice.service import (
  TOPIC_DICTATION,
  TOPIC_ERROR,
  TOPIC_REPLY,
  TOPIC_STATUS,
  TOPIC_TRANSCRIPT,
  VoiceService,
)


@dataclass
class FakeBrain(Brain):
  replies: list[str] = field(default_factory=lambda: ["Hello from Maira"])
  history: list[Message] = field(default_factory=list)
  sent: list[str] = field(default_factory=list)

  def send_message(self, text: str) -> None:
    self.sent.append(text)
    self.history.append(Message(role=MessageRole.USER, content=text))
    reply = self.replies.pop(0) if self.replies else "ok"
    self.history.append(Message(role=MessageRole.ASSISTANT, content=reply))

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
  def __init__(self) -> None:
    self.recording = False
    self.played: list[tuple] = []
    self._available = True

  def is_available(self) -> bool:
    return self._available

  def start_recording(self) -> None:
    self.recording = True

  def stop_recording(self):
    self.recording = False
    return np.ones(1600, dtype="float32") * 0.1

  def play(self, audio, sample_rate: int | None = None) -> None:
    self.played.append((len(audio), sample_rate))

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
  def __init__(self, text: str = "what is on my calendar") -> None:
    self.text = text
    self.calls = 0

  def is_available(self) -> bool:
    return True

  def transcribe(self, audio) -> str:
    self.calls += 1
    assert len(audio) > 0
    return self.text


class FakeTTS:
  def __init__(self) -> None:
    self.spoken: list[str] = []
    self.stopped = 0
    self.speaking = False

  def is_available(self) -> bool:
    return True

  def speak(self, text: str) -> None:
    self.speaking = True
    self.spoken.append(text)
    self.speaking = False

  def stop(self) -> None:
    self.stopped += 1
    self.speaking = False

@pytest.fixture
def voice_stack():
  bus = EventBus()
  brain = FakeBrain()
  audio = FakeAudio()
  stt = FakeSTT()
  tts = FakeTTS()
  voice = VoiceService(brain=brain, event_bus=bus, audio=audio, stt=stt, tts=tts)
  events = {"status": [], "transcript": [], "reply": [], "error": [], "dictation": []}
  bus.subscribe(TOPIC_STATUS, lambda p: events["status"].append(p["status"]))
  bus.subscribe(TOPIC_TRANSCRIPT, lambda p: events["transcript"].append(p["text"]))
  bus.subscribe(TOPIC_DICTATION, lambda p: events["dictation"].append(p["text"]))
  bus.subscribe(TOPIC_REPLY, lambda p: events["reply"].append(p["text"]))
  bus.subscribe(TOPIC_ERROR, lambda p: events["error"].append(p["message"]))
  return voice, brain, audio, stt, tts, events


def test_dictation_fills_text_without_brain_or_tts(voice_stack) -> None:
  voice, brain, _audio, stt, tts, events = voice_stack

  voice.start_dictation()
  assert voice.status() == VoiceStatus.LISTENING
  voice.stop_dictation()

  assert stt.calls == 1
  assert brain.sent == []
  assert tts.spoken == []
  assert events["dictation"] == ["what is on my calendar"]
  assert events["reply"] == []
  assert voice.status() == VoiceStatus.IDLE
  assert events["error"] == []


def test_push_to_talk_happy_path(voice_stack) -> None:
  voice, brain, _audio, stt, tts, events = voice_stack

  assert voice.is_available() is True
  voice.start_listening()
  assert voice.status() == VoiceStatus.LISTENING
  voice.stop_listening()

  assert stt.calls == 1
  assert brain.sent == ["what is on my calendar"]
  assert tts.spoken == ["Hello from Maira"]
  assert voice.status() == VoiceStatus.IDLE
  assert "listening" in events["status"]
  assert ("processing" in events["status"]) or ("thinking" in events["status"]) or (
    "transcribing" in events["status"]
  )
  assert "speaking" in events["status"]
  assert events["transcript"] == ["what is on my calendar"]
  assert events["reply"] == ["Hello from Maira"]
  assert events["error"] == []


def test_empty_transcript_reports_error(voice_stack) -> None:
  voice, brain, _audio, stt, tts, events = voice_stack
  stt.text = "   "

  voice.start_listening()
  voice.stop_listening()

  assert brain.sent == []
  assert tts.spoken == []
  assert events["error"]
  assert "error" in events["status"]
  assert voice.status() == VoiceStatus.IDLE


def test_stop_speaking_interrupts(voice_stack) -> None:
  voice, _brain, _audio, _stt, tts, _events = voice_stack
  voice.start_listening()
  # Simulate speaking status then interrupt
  voice._set_status(VoiceStatus.SPEAKING)  # noqa: SLF001
  voice.stop_speaking()
  assert tts.stopped == 1
  assert voice.status() == VoiceStatus.IDLE


def test_conversation_loop_one_turn(voice_stack) -> None:
  voice, brain, _audio, stt, tts, events = voice_stack
  # Stop after one utterance by flipping the flag from inside capture via soft stop
  original = voice._audio.capture_utterance

  calls = {"n": 0}

  def once(**kwargs):
    calls["n"] += 1
    if calls["n"] >= 2:
      voice._conversation_active = False  # noqa: SLF001
      return __import__("numpy").zeros(0, dtype="float32")
    return original(**kwargs)

  voice._audio.capture_utterance = once  # noqa: SLF001
  voice.start_conversation()
  thread_wait = 0
  import time

  while voice._conversation_active and thread_wait < 50:  # noqa: SLF001
    time.sleep(0.05)
    thread_wait += 1
  voice.stop_conversation()
  assert brain.sent == ["what is on my calendar"]
  assert tts.spoken == ["Hello from Maira"]
  assert events["transcript"] == ["what is on my calendar"]
