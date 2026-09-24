"""Check that Ultron can speak, step by step.

Run from the project folder:  python -X faulthandler -m scripts.test_voice
"""

from __future__ import annotations

import faulthandler
import sys
import time

faulthandler.enable()

SENTENCE = "Hello Ayush, main Ultron hoon. Aaj do tasks hain. Pehle call mom karo."


def step(text: str) -> None:
  print(text, flush=True)


def main() -> int:
  from maira.app.settings import load_settings  # noqa: PLC0415

  settings = load_settings()
  step(f"1. Voice settings: engine={settings.voice.tts_provider} voice={settings.voice.tts_voice} lang={settings.voice.tts_lang}")

  step("2. Speaker (sounddevice)...")
  try:
    import sounddevice as sd  # noqa: PLC0415

    out = sd.query_devices(kind="output")
    step(f"   default speaker: {out['name']}")
  except Exception as exc:  # noqa: BLE001
    step(f"   PROBLEM: {exc}")
    return 1

  step("3. Loading Kokoro (first time can take 1-2 minutes)...")
  from maira.infrastructure.speech.kokoro.engine import KokoroEngine  # noqa: PLC0415

  engine = KokoroEngine(voice=settings.voice.tts_voice, sample_rate=24000, lang_code=settings.voice.tts_lang)
  t0 = time.time()
  try:
    chunks = [c for c in engine.synthesize_stream(SENTENCE) if c is not None and len(c)]
  except Exception as exc:  # noqa: BLE001
    step(f"   PROBLEM: Kokoro failed: {exc}")
    chunks = []
  samples = sum(len(c) for c in chunks)
  step(f"   {len(chunks)} audio chunk(s), {samples / engine.sample_rate:.1f}s of audio, took {time.time() - t0:.1f}s")

  if chunks:
    step("4. Playing Kokoro voice now - listen...")
    for chunk in chunks:
      sd.play(chunk, samplerate=engine.sample_rate)
      sd.wait()
    step("   done")
  else:
    step("4. Kokoro gave no audio - skipping")

  step("5. Windows voice (fallback) - listen...")
  from maira.infrastructure.speech.windows.sapi import WindowsSpeech  # noqa: PLC0415

  windows = WindowsSpeech()
  if windows.is_available():
    windows.speak_and_wait(SENTENCE)
    step("   done")
  else:
    step("   not available on this system")

  step("Finished - tell Claude which of step 4 / step 5 you heard.")
  return 0


if __name__ == "__main__":
  sys.exit(main())
