"""Windows built-in voice fallback for announcements."""

from __future__ import annotations

import os
import stat
import time

import pytest

from maira.infrastructure.speech.windows.sapi import WindowsSpeech


@pytest.fixture
def fake_powershell(tmp_path):
  """A stand-in executable that writes whatever it receives on stdin to a file."""
  if os.name == "nt":
    pytest.skip("uses a POSIX shell script as the fake executable")
  out = tmp_path / "spoken.txt"
  script = tmp_path / "fake_powershell"
  script.write_text(f"#!/bin/sh\ncat > '{out}'\n", encoding="utf-8")
  script.chmod(script.stat().st_mode | stat.S_IEXEC)
  return str(script), out


def _wait_for(path, timeout=5.0) -> str:
  deadline = time.time() + timeout
  while time.time() < deadline:
    if path.exists() and path.read_text(encoding="utf-8"):
      return path.read_text(encoding="utf-8")
    time.sleep(0.05)
  return ""


def test_speaks_text_via_stdin(fake_powershell) -> None:
  exe, out = fake_powershell
  speech = WindowsSpeech(executable=exe, supported=True)
  text = 'Good morning, Ayush! Aaj 2 tasks hain. Pehle "Pay bill" karo; $env:x & more'
  assert speech.speak(text) is True
  assert _wait_for(out) == text  # quotes and symbols arrive untouched


def test_unavailable_off_windows() -> None:
  speech = WindowsSpeech(executable="/bin/true", supported=False)
  assert not speech.is_available()
  assert speech.speak("hello") is False


def test_empty_text_is_ignored(fake_powershell) -> None:
  exe, _out = fake_powershell
  assert WindowsSpeech(executable=exe, supported=True).speak("   ") is False


def test_voice_uses_fallback_when_kokoro_missing() -> None:
  from maira.core.bus.event_bus import EventBus
  from maira.modules.voice.service import VoiceService
  from tests.unit.test_voice_service import FakeAudio, FakeBrain, FakeSTT, FakeTTS

  class MissingTTS(FakeTTS):
    def is_available(self) -> bool:
      return False

  class Fallback:
    def __init__(self) -> None:
      self.spoken: list[str] = []
      self.stopped = False

    def is_available(self) -> bool:
      return True

    def speak(self, text: str) -> bool:
      self.spoken.append(text)
      return True

    def stop(self) -> None:
      self.stopped = True

  fallback = Fallback()
  voice = VoiceService(
    brain=FakeBrain(),
    event_bus=EventBus(),
    audio=FakeAudio(),
    stt=FakeSTT(),
    tts=MissingTTS(),
    announcement_fallback=fallback,
  )
  assert voice.announce("Good morning") is True
  assert fallback.spoken == ["Good morning"]
  voice.shutdown()
  assert fallback.stopped


def test_voice_without_any_voice_reports_false() -> None:
  from maira.core.bus.event_bus import EventBus
  from maira.modules.voice.service import VoiceService
  from tests.unit.test_voice_service import FakeAudio, FakeBrain, FakeSTT, FakeTTS

  class MissingTTS(FakeTTS):
    def is_available(self) -> bool:
      return False

  voice = VoiceService(brain=FakeBrain(), event_bus=EventBus(), audio=FakeAudio(), stt=FakeSTT(), tts=MissingTTS())
  assert voice.announce("Good morning") is False


class _Fallback:
  def __init__(self) -> None:
    self.said: list[str] = []

  def is_available(self) -> bool:
    return True

  def speak(self, text: str) -> bool:
    self.said.append(text)
    return True

  def speak_and_wait(self, text: str) -> bool:
    return self.speak(text)

  def stop(self) -> None:
    return


def _conversation_turn(tts, fallback) -> list:
  import time

  from maira.core.bus.event_bus import EventBus
  from maira.modules.voice.service import VoiceService
  from tests.unit.test_voice_service import FakeAudio, FakeBrain, FakeSTT

  bus = EventBus()
  errors: list = []
  bus.subscribe("voice.error", lambda p: errors.append(p["message"]))
  voice = VoiceService(
    brain=FakeBrain(), event_bus=bus, audio=FakeAudio(), stt=FakeSTT("hello"), tts=tts,
    announcement_fallback=fallback,
  )
  bus.subscribe("voice.reply", lambda _p: voice.stop_conversation())
  voice.start_conversation()
  deadline = time.time() + 10
  while voice.in_conversation and time.time() < deadline:
    time.sleep(0.05)
  voice.shutdown()
  return errors


def test_conversation_falls_back_when_voice_model_gives_no_audio() -> None:
  from tests.unit.test_voice_service import FakeTTS

  class SilentTTS(FakeTTS):
    def synthesize_chunks(self, text: str) -> list:
      return []

    def play_chunks(self, chunks: list) -> None:
      raise AssertionError("nothing to play")

  fallback = _Fallback()
  errors = _conversation_turn(SilentTTS(), fallback)
  assert fallback.said == ["Hello from Maira"]
  assert errors == []


def test_conversation_falls_back_when_voice_model_fails() -> None:
  from tests.unit.test_voice_service import FakeTTS

  class BrokenTTS(FakeTTS):
    def speak(self, text: str) -> None:
      raise RuntimeError("kokoro exploded")

  fallback = _Fallback()
  errors = _conversation_turn(BrokenTTS(), fallback)
  assert fallback.said == ["Hello from Maira"]
  assert errors == []


def test_without_fallback_a_failure_is_reported() -> None:
  from tests.unit.test_voice_service import FakeTTS

  class BrokenTTS(FakeTTS):
    def speak(self, text: str) -> None:
      raise RuntimeError("kokoro exploded")

  errors = _conversation_turn(BrokenTTS(), None)
  assert errors == ["I can still respond in text."]
