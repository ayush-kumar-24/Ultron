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
