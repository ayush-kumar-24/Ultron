"""Unit tests for Voice Comparison Lab (fakes — no network/model downloads)."""

from __future__ import annotations

import json
from pathlib import Path

from voice_lab.benchmark import ProviderRunResult, result_to_dict, write_results
from voice_lab.providers.base import SynthesisResult, TTSProvider
from voice_lab.runner import detect_providers, run_comparison


class FakeProvider(TTSProvider):
  def __init__(self, name: str, available: bool = True, fail: bool = False) -> None:
    self._name = name
    self._available = available
    self._fail = fail
    self._latency = 0.12

  def get_provider_name(self) -> str:
    return self._name

  def is_available(self) -> tuple[bool, str]:
    return (True, "ok") if self._available else (False, "not installed")

  def synthesize(self, text: str, *, script_id: str = "english") -> SynthesisResult:
    if self._fail:
      raise RuntimeError("boom")
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
      wav.setnchannels(1)
      wav.setsampwidth(2)
      wav.setframerate(16000)
      wav.writeframes(b"\x00\x00" * 1600)
    return SynthesisResult(audio_bytes=buf.getvalue(), sample_rate=16000)

  def save_audio(self, text: str, output_path: str | Path, *, script_id: str = "english") -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    result = self.synthesize(text, script_id=script_id)
    path.write_bytes(result.audio_bytes)
    return path

  def get_latency(self) -> float | None:
    return self._latency


def test_provider_order_and_names() -> None:
  rows = detect_providers()
  names = [p.get_provider_name() for p, _ok, _reason in rows]
  assert names[0] == "kokoro"
  assert "indic_parler" in names
  assert "veena" in names
  assert "chatterbox" in names
  assert len(names) == 4


def test_scripts_include_hindi() -> None:
  from voice_lab import config

  assert set(config.SCRIPTS) == {"english", "hindi", "hinglish"}
  assert "नमस्ते" in config.SCRIPTS["hindi"]


def test_run_comparison_continues_on_unavailable(monkeypatch, tmp_path) -> None:
  providers = [
    FakeProvider("kokoro", available=True),
    FakeProvider("indic_parler", available=False),
    FakeProvider("veena", available=True, fail=True),
    FakeProvider("chatterbox", available=False),
  ]

  monkeypatch.setattr("voice_lab.runner.all_providers", lambda: providers)
  monkeypatch.setattr("voice_lab.config.OUTPUT_DIR", tmp_path)
  monkeypatch.setattr("voice_lab.config.RESULTS_PATH", tmp_path / "results.json")
  monkeypatch.setattr(
    "voice_lab.config.SCRIPTS",
    {"english": "Hello from Maira.", "hindi": "नमस्ते।"},
  )

  results = run_comparison(scripts=["english", "hindi"])
  assert results["scripts"]["english"]["kokoro"]["status"] == "success"
  assert results["scripts"]["english"]["indic_parler"]["status"] == "unavailable"
  assert results["scripts"]["english"]["veena"]["status"] == "error"
  assert results["scripts"]["hindi"]["kokoro"]["status"] == "success"
  assert (tmp_path / "kokoro_english.wav").exists()
  assert (tmp_path / "kokoro_hindi.wav").exists()


def test_write_results_roundtrip(tmp_path) -> None:
  path = tmp_path / "results.json"
  payload = {
    "kokoro": result_to_dict(
      ProviderRunResult(status="success", latency_seconds=1.2, duration_seconds=3.4, file_size_mb=0.1)
    )
  }
  write_results(path, payload)
  loaded = json.loads(path.read_text(encoding="utf-8"))
  assert loaded["kokoro"]["status"] == "success"
