"""Check that Ultron can speak, step by step, and compare voices.

  python -X faulthandler -m scripts.test_voice                       # the voice in your config
  python -m scripts.test_voice --provider chatterbox                  # try another voice
  python -m scripts.test_voice --provider chatterbox --language hi    # Hindi mode
  python -m scripts.test_voice --provider indic_parler --speaker Leela
  python -m scripts.test_voice --text "Aaj ka plan batao"             # your own sentence
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
  import argparse  # noqa: PLC0415

  from maira.app.settings import load_settings  # noqa: PLC0415

  settings = load_settings()
  parser = argparse.ArgumentParser()
  parser.add_argument("--provider", default=settings.voice.tts_provider, choices=["kokoro", "chatterbox", "indic_parler"])
  parser.add_argument("--text", default=SENTENCE)
  parser.add_argument("--language", default=settings.voice.tts_language)
  parser.add_argument("--speaker", default=settings.voice.tts_speaker)
  parser.add_argument("--reference", default=settings.voice.tts_reference_audio)
  args = parser.parse_args()
  step(f"1. Voice: {args.provider}")

  step("2. Speaker (sounddevice)...")
  try:
    import sounddevice as sd  # noqa: PLC0415

    out = sd.query_devices(kind="output")
    step(f"   default speaker: {out['name']}")
  except Exception as exc:  # noqa: BLE001
    step(f"   PROBLEM: {exc}")
    return 1

  step(f"3. Loading {args.provider} (first time can take several minutes)...")
  if args.provider == "kokoro":
    from maira.infrastructure.speech.kokoro.engine import KokoroEngine  # noqa: PLC0415

    engine = KokoroEngine(voice=settings.voice.tts_voice, sample_rate=24000, lang_code=settings.voice.tts_lang)
  else:
    from maira.infrastructure.speech.worker.engine import WorkerTTSEngine  # noqa: PLC0415

    options = {"device": settings.voice.tts_device}
    if args.provider == "chatterbox":
      options.update(language=args.language, exaggeration=settings.voice.tts_exaggeration)
      if args.reference:
        options["reference_audio"] = args.reference
    else:
      options["speaker"] = args.speaker
    engine = WorkerTTSEngine(args.provider, options=options)
  t0 = time.time()
  try:
    if hasattr(engine, "warm_up") and args.provider != "kokoro":
      engine.warm_up()
      step(f"   loaded on {getattr(engine, 'device', '?')} in {time.time() - t0:.0f}s")
      t0 = time.time()
    chunks = [c for c in engine.synthesize_stream(args.text) if c is not None and len(c)]
  except Exception as exc:  # noqa: BLE001
    step(f"   PROBLEM: {args.provider} failed: {exc}")
    chunks = []
  samples = sum(len(c) for c in chunks)
  seconds = samples / engine.sample_rate
  took = time.time() - t0
  step(f"   {len(chunks)} chunk(s), {seconds:.1f}s of audio, took {took:.1f}s"
       + (f"  (speed: {seconds / took:.1f}x real time)" if took and seconds else ""))

  if chunks:
    step(f"4. Playing {args.provider} voice now - listen...")
    for chunk in chunks:
      sd.play(chunk, samplerate=engine.sample_rate)
      sd.wait()
    step("   done")
  else:
    step(f"4. {args.provider} gave no audio - skipping")

  if args.provider != "kokoro":
    if hasattr(engine, "close"):
      engine.close()
    step("Finished.")
    return 0
  step("5. Windows voice (fallback) - listen...")
  from maira.infrastructure.speech.windows.sapi import WindowsSpeech  # noqa: PLC0415

  windows = WindowsSpeech()
  if windows.is_available():
    windows.speak_and_wait(SENTENCE)
    step("   done")
  else:
    step("   not available on this system")

  if hasattr(engine, "close"):
    engine.close()
  step("Finished - tell Claude which of step 4 / step 5 you heard.")
  return 0


if __name__ == "__main__":
  sys.exit(main())
