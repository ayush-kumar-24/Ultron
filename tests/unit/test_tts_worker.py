"""Heavy voices run in their own environment through tts_worker.py."""

from __future__ import annotations

import sys

import numpy as np
import pytest

from maira.infrastructure.speech.worker.engine import WorkerTTSEngine, split_sentences, voice_env_python


def _fake(**options) -> WorkerTTSEngine:
  # sys.executable stands in for voice_envs/<name>/python; "fake" needs only numpy.
  return WorkerTTSEngine("fake", options=options, python=sys.executable, default_sample_rate=24000)


def test_synthesizes_audio_through_the_worker() -> None:
  engine = _fake()
  try:
    assert engine.is_available()
    engine.warm_up()
    assert engine.sample_rate == 16000  # reported by the worker, not the default
    assert engine.device == "cpu"
    audio, rate = engine.synthesize("hello")
    assert rate == 16000
    assert audio.dtype == np.float32 and len(audio) == 5 * 160
  finally:
    engine.close()


def test_long_text_streams_sentence_by_sentence() -> None:
  engine = _fake()
  try:
    chunks = list(engine.synthesize_stream("Good morning! Aaj 2 tasks hain. Pehle call mom karo."))
    assert [len(c) for c in chunks] == [13 * 160, 17 * 160, 20 * 160]
  finally:
    engine.close()


def test_library_prints_do_not_break_the_protocol() -> None:
  # The fake engine prints to stdout on load and on every sentence.
  engine = _fake()
  try:
    for _ in range(3):
      assert len(engine.synthesize("abc")[0]) == 480
  finally:
    engine.close()


def test_a_failed_sentence_raises_and_the_next_one_works() -> None:
  engine = _fake()
  try:
    with pytest.raises(RuntimeError, match="fake synth failure"):
      list(engine.synthesize_stream("boom"))
    assert len(engine.synthesize("ok")[0]) == 320
  finally:
    engine.close()


def test_model_load_failure_is_reported_and_remembered() -> None:
  engine = _fake(fail_init=True)
  with pytest.raises(RuntimeError, match="fake init failure"):
    engine.warm_up()
  assert not engine.is_available()  # falls back instead of retrying every sentence
  with pytest.raises(RuntimeError):
    engine.synthesize("hi")


def test_missing_environment_is_unavailable(tmp_path) -> None:
  engine = WorkerTTSEngine("chatterbox", python=tmp_path / "nope" / "python")
  assert not engine.is_available()
  with pytest.raises(RuntimeError, match="setup_voice chatterbox"):
    engine.warm_up()


def test_split_sentences() -> None:
  assert split_sentences("Hi! Kaise ho? Theek hoon.\nBye") == ["Hi!", "Kaise ho?", "Theek hoon.", "Bye"]
  assert split_sentences("नमस्ते। आप कैसे हैं?") == ["नमस्ते।", "आप कैसे हैं?"]
  assert split_sentences("   ") == []
  long_parts = split_sentences("word " * 100)
  assert all(len(p) <= 220 for p in long_parts) and " ".join(long_parts).split() == ["word"] * 100


def test_env_python_path() -> None:
  assert voice_env_python("chatterbox", windows=True).parts[-4:] == ("voice_envs", "chatterbox", "Scripts", "python.exe")
  assert voice_env_python("chatterbox", windows=False).parts[-4:] == ("voice_envs", "chatterbox", "bin", "python")


def test_registry_builds_worker_providers_with_options() -> None:
  from maira.modules.voice.tts.registry import create_tts

  provider = create_tts("chatterbox", device="cuda", language="hi", reference_audio="C:/voice.wav", exaggeration=0.7)
  assert provider.get_provider_name() == "chatterbox"
  assert provider._engine._options == {  # noqa: SLF001
    "device": "cuda", "language": "hi", "exaggeration": 0.7, "reference_audio": "C:/voice.wav",
  }
  ok, reason = provider.is_available()
  assert not ok and "setup_voice chatterbox" in reason  # not installed in this environment

  parler = create_tts("indic_parler", speaker="Leela")
  assert parler._engine._options == {"device": "auto", "speaker": "Leela"}  # noqa: SLF001
  assert parler.sample_rate == 44100


def test_voice_settings_nested_provider_wins(tmp_path, monkeypatch) -> None:
  import maira.app.settings as settings_mod

  user = tmp_path / "config.yaml"
  user.write_text("voice:\n  tts:\n    provider: chatterbox\n    reference_audio: C:/me.wav\n", encoding="utf-8")
  monkeypatch.setattr(settings_mod, "user_config_path", lambda: user)
  loaded = settings_mod.load_settings()
  assert loaded.voice.tts_provider == "chatterbox"
  assert loaded.voice.tts_reference_audio == "C:/me.wav"
  assert loaded.voice.tts_speaker == "Divya"
